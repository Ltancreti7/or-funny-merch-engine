"""Live stock momentum scanner using Polygon.io data.

This script reads a CSV watchlist and enriches each ticker with live
pre‑market information from the Polygon REST API.  It calculates a
variety of scores (news, liquidity, flow and market backdrop) and prints
the results as a compact table ranked by conviction.

Usage
-----
```bash
python momentum_print_scan.py --csv watch.csv [--loop] [--interval 45]
```

Environment
-----------
The Polygon API key is loaded from the ``POLYGON_API_KEY`` environment
variable.
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd
import requests
from zoneinfo import ZoneInfo


API_KEY = os.getenv("POLYGON_API_KEY")
BASE_URL = "https://api.polygon.io"
NY = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def polygon_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Call Polygon REST endpoint and return JSON, swallowing errors.

    If the API key is missing or a request fails, an empty dictionary is
    returned so that the caller can continue gracefully.
    """

    params = params or {}
    if not API_KEY:
        return {}
    params["apiKey"] = API_KEY
    try:
        resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def parse_time(timestr: str) -> datetime:
    """Return a ``datetime`` for today's date at ``timestr`` in ET."""

    now = datetime.now(tz=NY)
    hour, minute = map(int, timestr.split(":"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def to_unix_ms(dt: datetime) -> int:
    """Convert a timezone aware ``datetime`` to unix milliseconds."""

    return int(dt.astimezone(ZoneInfo("UTC")).timestamp() * 1000)


def format_volume(vol: float | None) -> str:
    """Format a volume number with K/M/B suffixes."""

    if vol is None:
        return ""
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if vol >= div:
            return f"{vol / div:.1f}{unit}"
    return f"{vol:.0f}"


# ---------------------------------------------------------------------------
# Polygon data fetchers
# ---------------------------------------------------------------------------


@dataclass
class PremarketStats:
    price: float | None
    vwap: float | None
    volume: float
    alive: bool


def fetch_premarket(ticker: str, start: datetime) -> PremarketStats:
    """Fetch 1‑minute bars from ``start`` and compute pre‑market stats."""

    end = datetime.now(tz=NY)
    data = polygon_get(
        f"/v2/aggs/ticker/{ticker}/range/1/min/{to_unix_ms(start)}/{to_unix_ms(end)}",
        {"adjusted": "true", "sort": "asc", "limit": 5000},
    )
    results: List[Dict[str, Any]] = data.get("results", [])

    total_vol = sum(r.get("v", 0) for r in results)
    vwap = None
    if total_vol > 0:
        vwap = sum(r.get("c", 0) * r.get("v", 0) for r in results) / total_vol

    price = results[-1]["c"] if results else None

    trade = polygon_get(f"/v3/trades/{ticker}/last").get("results", {})
    if trade:
        price = trade.get("p", price)

    return PremarketStats(price=price, vwap=vwap, volume=total_vol, alive=total_vol > 10_000)


@dataclass
class QuoteStats:
    bid: float | None
    ask: float | None
    bid_size: float | None
    ask_size: float | None
    spread_pct: float | None
    liq_score: float


def fetch_quote(ticker: str) -> QuoteStats:
    """Fetch last quote and compute spread & liquidity score."""

    res = polygon_get(f"/v3/quotes/{ticker}/last").get("results", {})
    bid = res.get("bp")
    ask = res.get("ap")
    bid_size = res.get("bs")
    ask_size = res.get("as")
    spread_pct = None
    if bid and ask and bid > 0:
        spread_pct = (ask - bid) / bid * 100

    # Liquidity score: tight spread and larger sizes increase score.
    spread_score = 0.0
    size_score = 0.0
    if spread_pct is not None:
        spread_score = max(0.0, 1 - spread_pct / 5)  # 0% ->1, 5%->0
    if bid_size or ask_size:
        size_score = min(((bid_size or 0) + (ask_size or 0)) / 2000, 1.0)
    liq_score = (spread_score + size_score) / 2

    return QuoteStats(bid, ask, bid_size, ask_size, spread_pct, liq_score)


KEYWORD_WEIGHTS = {
    1.0: ["fda", "approval", "phase 3", "merger", "acquisition", "buyout"],
    0.6: ["earnings", "guidance", "contract", "partnership"],
    0.5: ["upgrade", "initiation"],
}


def fetch_news_score(ticker: str) -> Tuple[float, bool]:
    """Return news catalyst score in [0,1] and bool flag for any news."""

    since = datetime.utcnow() - timedelta(hours=36)
    data = polygon_get(
        "/v2/reference/news",
        {
            "ticker": ticker,
            "published_utc.gte": since.isoformat(),
            "order": "desc",
            "limit": 50,
        },
    )
    articles: Iterable[Dict[str, Any]] = data.get("results", [])
    score = 0.0
    for art in articles:
        title = (art.get("title") or "").lower()
        for weight, words in KEYWORD_WEIGHTS.items():
            if any(w in title for w in words):
                score += weight
    score = min(score, 1.0)
    return score, bool(list(articles))


def fetch_daily_high(ticker: str) -> float | None:
    """Return the highest daily high over the last 30 sessions."""

    end = datetime.now(tz=NY)
    start = end - timedelta(days=30)
    data = polygon_get(
        f"/v2/aggs/ticker/{ticker}/range/1/day/{start:%Y-%m-%d}/{end:%Y-%m-%d}",
        {"adjusted": "true", "sort": "desc", "limit": 120},
    )
    results = data.get("results", [])
    if not results:
        return None
    return max(r.get("h", 0) for r in results)


def fetch_market_score(start: datetime) -> float:
    """Return a market backdrop score based on SPY change since start."""

    end = datetime.now(tz=NY)
    data = polygon_get(
        f"/v2/aggs/ticker/SPY/range/1/min/{to_unix_ms(start)}/{to_unix_ms(end)}",
        {"adjusted": "true", "sort": "asc", "limit": 5000},
    )
    results = data.get("results", [])
    if not results:
        return 0.5
    first = results[0].get("o") or results[0].get("c")
    last = results[-1].get("c")
    if not first or not last:
        return 0.5
    pct = (last - first) / first * 100
    # Map -0.5%..+0.5% to 0..1
    score = (pct + 0.5) / 1.0
    return max(0.0, min(1.0, score))


def compute_flow_score(premkt: PremarketStats) -> float:
    score = 0.0
    if premkt.volume:
        score = min(premkt.volume / 5_000_000, 1.0)
    if premkt.price and premkt.vwap and premkt.price >= premkt.vwap:
        score = min(score + 0.1, 1.0)
    return score


# ---------------------------------------------------------------------------
# Watchlist loading and score computation
# ---------------------------------------------------------------------------


def load_watchlist(path: str) -> List[Dict[str, Any]]:
    """Load watchlist CSV into a list of dicts with normalized columns."""

    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    rename_map = {
        "symbol": "symbol",
        "sym": "symbol",
        "ticker": "symbol",
    }
    if "symbol" not in df.columns:
        for cand, tgt in rename_map.items():
            if cand in df.columns:
                df = df.rename(columns={cand: tgt})
    return df.to_dict("records")


def compute_targets(ticker: str, entry: float | None, t1: float | None, t2: float | None) -> Tuple[float | None, float | None]:
    if t1 and t2:
        return t1, t2
    high = fetch_daily_high(ticker)
    if high is None:
        return t1, t2
    if not t1:
        t1 = round(high, 2)
    if not t2:
        t2 = round(high * 1.05, 2)
    return t1, t2


def compute_confidence(base: float, news: float, flow: float, liq: float, market: float) -> float:
    return (
        0.35 * base
        + 0.25 * news
        + 0.20 * flow
        + 0.10 * liq
        + 0.10 * market
    ) * 100


def conviction_from_confidence(conf: float) -> str:
    if conf >= 75:
        return "High"
    if conf >= 55:
        return "Medium"
    return "Low"


def process_row(row: Dict[str, Any], start: datetime, mkt_score: float) -> Dict[str, Any]:
    ticker = str(row.get("symbol", "")).upper()
    if not ticker:
        return {}

    base_score = (float(row.get("score_10", 0)) or 0) / 10
    entry = row.get("entry") or row.get("px") or None
    entry = float(entry) if entry not in (None, "") else None
    stop = row.get("stop")
    stop = float(stop) if stop not in (None, "") else None
    t1 = row.get("t1")
    t1 = float(t1) if t1 not in (None, "") else None
    t2 = row.get("t2")
    t2 = float(t2) if t2 not in (None, "") else None

    premkt = fetch_premarket(ticker, start)
    quote = fetch_quote(ticker)
    news_score, has_news = fetch_news_score(ticker)
    flow_score = compute_flow_score(premkt)
    liq_score = quote.liq_score

    conf = compute_confidence(base_score, news_score, flow_score, liq_score, mkt_score)
    conviction = conviction_from_confidence(conf)

    if entry is None:
        entry = premkt.price
    if stop is None and entry:
        stop = round(entry * 0.97, 2)

    t1_final, t2_final = compute_targets(ticker, entry, t1, t2)

    return {
        "cv": conviction,
        "conv_num": {"High": 2, "Medium": 1, "Low": 0}[conviction],
        "conf": round(conf, 0),
        "sym": ticker,
        "px": round(float(row.get("px", premkt.price or 0)), 2) if row.get("px") else round(premkt.price or 0, 2),
        "entry": round(entry or 0, 2) if entry else None,
        "stop": round(stop or 0, 2) if stop else None,
        "T1": t1_final,
        "T2": t2_final,
        "pm_px": round(premkt.price or 0, 2) if premkt.price else None,
        "pm_vwap": round(premkt.vwap or 0, 2) if premkt.vwap else None,
        "pm_vol": premkt.volume,
        "spread%": round(quote.spread_pct or 0, 2) if quote.spread_pct else None,
        "score": row.get("score_10"),
        "news": has_news,
    }


# ---------------------------------------------------------------------------
# Main execution and table printing
# ---------------------------------------------------------------------------


def build_table(rows: List[Dict[str, Any]]) -> str:
    df = pd.DataFrame(rows)
    if df.empty:
        return "No data returned."

    df = df.sort_values(["conv_num", "conf", "pm_vol"], ascending=[False, False, False])
    df.drop(columns=["conv_num"], inplace=True)

    df["pm_vol"] = df["pm_vol"].apply(format_volume)

    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_string(index=False)


def run_scan(args: argparse.Namespace) -> None:
    watchlist = load_watchlist(args.csv)
    start = parse_time(args.premkt_start)
    mkt_score = fetch_market_score(start)

    rows: List[Dict[str, Any]] = []
    for row in watchlist:
        data = process_row(row, start, mkt_score)
        if data:
            rows.append(data)

    print(build_table(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description="Live pre-market momentum scanner")
    parser.add_argument("--csv", required=True, help="CSV watchlist export")
    parser.add_argument(
        "--premkt-start",
        default="04:00",
        help="premarket start time ET (HH:MM)",
    )
    parser.add_argument("--loop", action="store_true", help="refresh continuously")
    parser.add_argument(
        "--interval",
        type=int,
        default=45,
        help="refresh interval in seconds when looping",
    )
    args = parser.parse_args()

    while True:
        run_scan(args)
        if not args.loop:
            break
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    main()


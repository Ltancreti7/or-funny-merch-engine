"""Momentum Print Scanner.

Fetches top gaining U.S. stocks from Polygon and prints a ranked trade plan table."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import pandas as pd
import requests
from requests import HTTPError
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POLYGON_API_KEY")
if not API_KEY:
    print("POLYGON_API_KEY not found in environment.")
    sys.exit(1)

BASE_URL = "https://api.polygon.io"

def _get(url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    params = params or {}
    params["apiKey"] = API_KEY
    backoff = 1
    for _ in range(5):
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 429:
            time.sleep(backoff)
            backoff *= 2
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()

def fetch_top_gainers() -> List[Dict[str, Any]]:
    data = _get(f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/gainers")
    return data.get("tickers", [])

def fetch_grouped_aggs(day: str) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/v2/aggs/grouped/locale/us/market/stocks/{day}"
    data = _get(url, params={"adjusted": "true"})
    return data.get("results", [])

def fetch_ticker_snapshot(ticker: str) -> Dict[str, Any]:
    data = _get(f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
    return data.get("ticker", {})

def fetch_market_cap(ticker: str) -> float | None:
    data = _get(f"{BASE_URL}/v3/reference/tickers/{ticker}")
    return data.get("results", {}).get("market_cap")

def fetch_avg_volume(ticker: str, days: int = 30) -> float | None:
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/day/{start:%Y-%m-%d}/{end:%Y-%m-%d}"
    data = _get(url, params={"adjusted": "true", "limit": 120, "sort": "desc"})
    results = data.get("results", [])
    if not results:
        return None
    vols = [r.get("v", 0) for r in results[-days:]]
    return sum(vols) / len(vols) if vols else None

def fetch_latest_news(ticker: str) -> str:
    data = _get(f"{BASE_URL}/v2/reference/news", params={"ticker": ticker, "order": "desc", "limit": 1})
    results = data.get("results", [])
    return results[0].get("title", "") if results else ""

def find_recent_grouped_gainers(lookback: int) -> Tuple[List[Dict[str, Any]], str | None]:
    for i in range(1, lookback + 1):
        day = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            results = fetch_grouped_aggs(day)
        except HTTPError:
            continue
        if results:
            return results, day
    return [], None

def compute_trade_plan(price: float, vwap: float | None) -> Dict[str, Any]:
    entry = price
    stop = round(price * 0.97, 2)
    target1 = round(price * 1.05, 2)
    target2 = round(price * 1.10, 2)
    rr = round((target1 - entry) / (entry - stop), 2) if entry != stop else 0
    if vwap:
        entry_zone = f"{vwap*0.99:.2f}-{vwap*1.01:.2f}"
    else:
        entry_zone = f"{price:.2f}-{price*1.01:.2f}"
    return {
        "EntryZone": entry_zone,
        "Stop": stop,
        "Target1": target1,
        "Target2": target2,
        "R:R": rr,
    }

def confidence_score(pct_change: float, rvol: float) -> int:
    score = 5 + (pct_change - 10) / 10 + (rvol - 3) * 0.5
    return int(max(1, min(10, round(score))))

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-price", type=float, default=1.0)
    parser.add_argument("--max-price", type=float, default=20.0)
    parser.add_argument("--min-change", type=float, default=10.0)
    parser.add_argument("--min-volume", type=int, default=200_000)
    parser.add_argument("--force-fallback", action="store_true")
    parser.add_argument("--fallback-lookback", type=int, default=10)
    parser.add_argument("--no-news", action="store_true")
    args = parser.parse_args()

    rows: List[Dict[str, Any]] = []
    gainers: List[Dict[str, Any]] = []
    used_snapshot = False

    if not args.force_fallback:
        gainers = fetch_top_gainers()
        if gainers:
            used_snapshot = True
            print("Source: live gainers snapshot")

    if not gainers:
        grouped, day = find_recent_grouped_gainers(args.fallback_lookback)
        if not grouped:
            print("No data returned from Polygon API.")
            return
        print(f"Source: previous trading day grouped aggs ({day})")
        for r in grouped:
            o = r.get("o")
            c = r.get("c")
            v = r.get("v")
            if not all([o, c, v]):
                continue
            pct = (c - o) / o * 100 if o else 0
            price = c
            if not (args.min_price <= price <= args.max_price and pct >= args.min_change and v >= args.min_volume):
                continue
            gainers.append({
                "ticker": r.get("T"),
                "last": price,
                "pct_change": pct,
                "volume": v,
                "vwap": r.get("vw"),
            })
        gainers.sort(key=lambda x: x["pct_change"], reverse=True)

    for g in gainers:
        if used_snapshot:
            ticker = g.get("ticker")
            if not ticker:
                continue
            price = g.get("lastTrade", {}).get("p") or g.get("day", {}).get("c")
            pct_change = g.get("todaysChangePerc", 0)
            volume = g.get("day", {}).get("v")
            vwap = g.get("day", {}).get("vw")
        else:
            ticker = g.get("ticker")
            price = g.get("last")
            pct_change = g.get("pct_change")
            volume = g.get("volume")
            vwap = g.get("vwap")

        mcap = fetch_market_cap(ticker)
        avg_vol = fetch_avg_volume(ticker)
        if not all([price, pct_change is not None, volume, avg_vol, mcap]):
            continue
        rvol = round(volume / avg_vol, 2) if avg_vol else None
        snapshot = fetch_ticker_snapshot(ticker)
        vwap = vwap or snapshot.get("day", {}).get("vw")
        trade = compute_trade_plan(price, vwap)
        catalyst = "" if args.no_news else fetch_latest_news(ticker)
        above_vwap = price > vwap if vwap else False
        conf = confidence_score(pct_change, rvol) if rvol is not None else 1

        rows.append({
            "Ticker": ticker,
            "Price": round(price, 2),
            "%Chg": round(pct_change, 2),
            "Vol": int(volume),
            "RVOL(30d)": round(rvol, 2) if rvol else None,
            "MktCap": int(mcap) if mcap else None,
            ">VWAP": above_vwap,
            "VWAP": round(vwap, 2) if vwap else None,
            **trade,
            "Confidence": conf,
            "Catalyst": catalyst,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        print("No data returned from Polygon API.")
        return
    filtered = df[
        (df["Price"].between(args.min_price, args.max_price))
        & (df["%Chg"] >= args.min_change)
        & (df["RVOL(30d)"] >= 3)
        & (df["MktCap"] <= 1_000_000_000)
        & (df["Vol"] >= args.min_volume)
    ]
    filtered = filtered.sort_values("%Chg", ascending=False)
    print(filtered.to_string(index=False))

if __name__ == "__main__":
    main()

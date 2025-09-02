"""Momentum Print Scanner.

Fetches top gaining U.S. stocks from Polygon and prints a ranked trade plan table."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POLYGON_API_KEY")
if not API_KEY:
    raise EnvironmentError("POLYGON_API_KEY not found in environment.")

BASE_URL = "https://api.polygon.io"

def _get(url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    params = params or {}
    params["apiKey"] = API_KEY
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def fetch_top_gainers() -> List[Dict[str, Any]]:
    data = _get(f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/gainers")
    return data.get("tickers", [])

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

def compute_trade_plan(price: float, vwap: float) -> Dict[str, Any]:
    entry = price
    stop = round(price * 0.97, 2)
    target1 = round(price * 1.05, 2)
    target2 = round(price * 1.10, 2)
    rr = round((target1 - entry) / (entry - stop), 2) if entry != stop else 0
    entry_zone = f"{vwap*0.99:.2f}-{vwap*1.01:.2f}" if vwap else ""
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
    gainers = fetch_top_gainers()
    rows: List[Dict[str, Any]] = []
    for g in gainers:
        ticker = g.get("ticker")
        if not ticker:
            continue
        price = g.get("lastTrade", {}).get("p") or g.get("day", {}).get("c")
        pct_change = g.get("todaysChangePerc", 0)
        volume = g.get("day", {}).get("v")
        vwap = g.get("day", {}).get("vw")

        mcap = fetch_market_cap(ticker)
        avg_vol = fetch_avg_volume(ticker)
        if not all([price, pct_change is not None, volume, avg_vol, mcap]):
            continue
        rvol = round(volume / avg_vol, 2) if avg_vol else None
        snapshot = fetch_ticker_snapshot(ticker)
        vwap = vwap or snapshot.get("day", {}).get("vw")
        trade = compute_trade_plan(price, vwap)
        catalyst = fetch_latest_news(ticker)
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
        (df["Price"].between(1, 20))
        & (df["%Chg"] >= 10)
        & (df["RVOL(30d)"] >= 3)
        & (df["MktCap"] <= 1_000_000_000)
        & (df["Vol"] >= 200_000)
    ]
    filtered = filtered.sort_values("%Chg", ascending=False)
    print(filtered.to_string(index=False))

if __name__ == "__main__":
    main()

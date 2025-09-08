"""Real-time stock gainer scanner.

Periodically queries Polygon's top gainer endpoint and prints a concise
summary of symbols showing strong intraday momentum. The script refreshes
results every 30 seconds.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("POLYGON_API_KEY")
if not API_KEY:
    raise EnvironmentError("POLYGON_API_KEY not found in environment.")

BASE_URL = "https://api.polygon.io"


def _get(url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Perform a GET request to the Polygon API."""
    params = params or {}
    params["apiKey"] = API_KEY
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_top_gainers() -> List[Dict[str, Any]]:
    """Fetch the current top U.S. stock gainers."""
    data = _get(f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/gainers")
    return data.get("tickers", [])


def display(gainers: List[Dict[str, Any]]) -> None:
    """Pretty-print a simple table of gainer information."""
    print(f"\n{datetime.utcnow():%Y-%m-%d %H:%M:%S} UTC")
    print(f"{'TICKER':>6} {'PRICE':>8} {'%CHG':>6}")
    for g in gainers[:10]:  # show top 10
        ticker = g.get("ticker", "")
        price = g.get("lastTrade", {}).get("p") or g.get("day", {}).get("c")
        pct = g.get("todaysChangePerc", 0)
        if price is None:
            continue
        print(f"{ticker:>6} {price:8.2f} {pct:6.2f}")
    print("-" * 24)


def main() -> None:
    """Continuously print top gaining tickers every 30 seconds."""
    while True:
        try:
            gainers = fetch_top_gainers()
            display(gainers)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"Error fetching data: {exc}")
        time.sleep(30)


if __name__ == "__main__":
    main()

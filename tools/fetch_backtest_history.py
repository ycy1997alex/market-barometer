"""Prepare a dedicated long-history cache for offline replay.

Run once per symbol (or use --refresh to deliberately replace a snapshot).
Ordinary backtest runs read BacktestHistoryCache.load and never call an API.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer import config
from barometer.datasources.yfinance_src import fetch_daily
from barometer.storage.backtest_cache import BacktestHistoryCache


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="*", default=list(config.ALL_SYMBOLS))
    parser.add_argument("--period", default="max", help="Initial history span (default: max)")
    parser.add_argument("--refresh", action="store_true",
                        help="Explicitly re-fetch and replace existing snapshots")
    args = parser.parse_args()
    cache = BacktestHistoryCache()
    for symbol in args.symbols:
        bars = cache.prepare(symbol,
                             lambda selected: fetch_daily(selected, period=args.period),
                             refresh=args.refresh)
        print(f"{symbol}: {len(bars)} bars, {bars[0].date} to {bars[-1].date}; "
              f"cache={cache.path(symbol)}")


if __name__ == "__main__":
    main()

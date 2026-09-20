"""Separate, local-only history snapshot for repeatable backtests.

No network adapter is imported here. Only explicit ``prepare`` calls may
invoke a caller-supplied fetcher; ``load`` is always offline.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
from pathlib import Path
from typing import Callable, Sequence

from barometer import config
from barometer.domain.ports import PriceBar

_FIELDS = ("symbol", "date", "open", "high", "low", "close",
           "volume_shares", "source", "as_of", "stale")


class BacktestHistoryCache:
    def __init__(self, root: Path | None = None) -> None:
        self.directory = Path(root) / "backtest_history" if root else (
            config.stockdata_root() / "backtest_history")

    def path(self, symbol: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9._^=-]+", symbol):
            raise ValueError("invalid symbol for history cache")
        return self.directory / f"{symbol}.csv"

    def load(self, symbol: str) -> list[PriceBar]:
        path = self.path(symbol)
        if not path.is_file():
            raise FileNotFoundError(f"backtest history is missing: {path}")

        def number(raw: str) -> float | None:
            return float(raw) if raw else None

        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        return [PriceBar(
            symbol=row["symbol"], date=dt.date.fromisoformat(row["date"]),
            open=number(row["open"]), high=number(row["high"]),
            low=number(row["low"]), close=number(row["close"]),
            volume_shares=number(row["volume_shares"]), source=row["source"],
            as_of=dt.datetime.fromisoformat(row["as_of"]),
            stale=row["stale"] == "1",
        ) for row in rows]

    def prepare(
        self, symbol: str, fetch: Callable[[str], Sequence[PriceBar]],
        *, refresh: bool = False,
    ) -> list[PriceBar]:
        """Fetch once if absent; an existing snapshot is reused without API calls."""
        path = self.path(symbol)
        if path.exists() and not refresh:
            return self.load(symbol)
        # Some Yahoo responses include a synthetic Sunday row with plausible
        # OHLC and even nonzero volume. Sunday is never a regular session in
        # either supported market, so do not let it become a trading signal.
        bars = [bar for bar in fetch(symbol) if bar.date.weekday() != 6]
        if not bars or any(bar.symbol != symbol for bar in bars):
            raise ValueError(f"{symbol}: fetch returned no matching price bars")
        if any(a.date >= b.date for a, b in zip(bars, bars[1:])):
            raise ValueError(f"{symbol}: fetched bars are not strictly chronological")
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".csv.tmp")
        try:
            with temporary.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(_FIELDS)
                for bar in bars:
                    writer.writerow((bar.symbol, bar.date.isoformat(), bar.open,
                                     bar.high, bar.low, bar.close,
                                     bar.volume_shares, bar.source,
                                     bar.as_of.isoformat(), int(bar.stale)))
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return bars

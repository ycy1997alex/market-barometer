"""TTL decision for the existing price_current store; no second price cache."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from barometer.domain.ports import PriceBar

CACHE_VERSION = "1.0.0"
TAIL_OVERLAP_DAYS = 7


@dataclass(frozen=True, slots=True)
class CachedResult:
    current: list[PriceBar]
    adjusted: list[PriceBar]
    from_cache: bool


class CachedSource:
    """Read price_current/price_adjusted through injected readers; persist only TTL metadata."""

    def __init__(
        self, root: Path, fetcher: Callable, current_reader: Callable,
        adjusted_reader: Callable, *, ttl_seconds: int,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.metadata_path = root / "price_current" / ".cache_meta.json"
        self.fetcher = fetcher
        self.current_reader = current_reader
        self.adjusted_reader = adjusted_reader
        self.ttl_seconds = ttl_seconds
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))

    def _metadata(self) -> dict:
        if not self.metadata_path.exists():
            return {}
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    def mark_checked(self, symbol: str) -> None:
        data = self._metadata()
        data[symbol] = {"version": CACHE_VERSION,
                        "checked_at": self.clock().isoformat()}
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        temporary.replace(self.metadata_path)

    def get(self, symbol: str, *, period: str = "1y", force: bool = False,
            as_of: dt.datetime | None = None) -> CachedResult:
        current = self.current_reader(symbol)
        adjusted = self.adjusted_reader(symbol)
        meta = self._metadata().get(symbol, {})
        valid_version = meta.get("version") == CACHE_VERSION
        checked = dt.datetime.fromisoformat(meta["checked_at"]) if meta.get("checked_at") else None
        fresh = (valid_version and checked is not None and
                 dt.timedelta(0) <= self.clock() - checked < dt.timedelta(seconds=self.ttl_seconds))
        if current and adjusted and fresh and not force:
            return CachedResult(current, adjusted, True)

        start = (current[-1].date - dt.timedelta(days=TAIL_OVERLAP_DAYS)
                 if current and adjusted and valid_version else None)
        kwargs = {"as_of": as_of}
        if start is None:
            kwargs["period"] = period
        else:
            kwargs["start"] = start
        fetched_current = self.fetcher(symbol, auto_adjust=False, **kwargs)
        fetched_adjusted = self.fetcher(symbol, auto_adjust=True, **kwargs)
        if start is not None:
            previous = {bar.date: bar for bar in adjusted}
            old_overlap_changed = any(
                bar.date in previous and bar.date <= current[-1].date and
                (bar.open, bar.high, bar.low, bar.close) !=
                (previous[bar.date].open, previous[bar.date].high,
                 previous[bar.date].low, previous[bar.date].close)
                for bar in fetched_adjusted
            )
            if old_overlap_changed:
                fetched_adjusted = self.fetcher(
                    symbol, period=period, auto_adjust=True, as_of=as_of)
        return CachedResult(fetched_current, fetched_adjusted, False)

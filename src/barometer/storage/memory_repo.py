"""記憶體 adapter —— 與 SqliteRepo 實作同一組 Port。

存在的理由是 §3.2 的那句話：「傳一個 InMemoryScoreHistory 進去就能測完整流程，
不用碰檔案」。tests/test_repository_contract.py 用同一組測試同時餵這兩個實作，
兩邊都過才證明 Port 抽對了。
"""
from __future__ import annotations

import copy
import datetime as dt

from barometer.domain.ports import MacroSeries, PriceBar, ScoreRecord


class InMemoryRepo:
    def __init__(self) -> None:
        self._prices: dict[tuple[str, dt.date], PriceBar] = {}
        self._conflicts: list[dict] = []
        self._macro: dict[str, MacroSeries] = {}
        self._scores: dict[tuple[str, str, dt.date], ScoreRecord] = {}
        self._chips: dict[dt.date, dict] = {}
        self._adjustments: list[dict] = []
        self._runs: dict[str, dict] = {}

    # ---------------- PriceRepository ----------------

    def upsert_prices(self, bars: list[PriceBar]) -> int:
        for b in bars:
            self._prices[(b.symbol, b.date)] = b
        return len(bars)

    def get_prices(
        self,
        symbol: str,
        start: dt.date | None = None,
        end: dt.date | None = None,
    ) -> list[PriceBar]:
        out = [b for (s, _), b in self._prices.items() if s == symbol]
        if start:
            out = [b for b in out if b.date >= start]
        if end:
            out = [b for b in out if b.date <= end]
        return sorted(out, key=lambda b: b.date)

    def last_price_date(self, symbol: str) -> dt.date | None:
        dates = [d for (s, d) in self._prices if s == symbol]
        return max(dates) if dates else None

    def record_conflict(
        self,
        symbol: str,
        date: dt.date,
        field: str,
        shioaji_value: float | None,
        yf_value: float | None,
        taken: str,
        as_of: dt.datetime,
    ) -> None:
        self._conflicts.append(
            {
                "symbol": symbol,
                "date": date.isoformat(),
                "field": field,
                "shioaji_value": shioaji_value,
                "yf_value": yf_value,
                "taken": taken,
                "as_of": as_of.isoformat(),
            }
        )

    def get_conflicts(self, date: dt.date) -> list[dict]:
        rows = [c for c in self._conflicts if c["date"] == date.isoformat()]
        return sorted(copy.deepcopy(rows), key=lambda c: (c["symbol"], c["field"]))

    # ---------------- MacroRepository ----------------

    def put_macro(
        self,
        key: str,
        series: list[tuple[str, float]],
        fetched_at: dt.datetime,
        data_date: dt.date | None,
        stale_reason: str | None = None,
    ) -> None:
        self._macro[key] = MacroSeries(
            key=key,
            series=list(series),
            fetched_at=fetched_at,
            data_date=data_date,
            stale_reason=stale_reason,
        )

    def get_macro(self, key: str) -> MacroSeries | None:
        return self._macro.get(key)

    # ---------------- ScoreHistoryRepository ----------------

    def put_score(
        self,
        scope: str,
        symbol: str,
        as_of: dt.date,
        score: float,
        subscores: dict[str, float],
        price_version: str,
    ) -> None:
        self._scores[(scope, symbol, as_of)] = ScoreRecord(
            scope=scope,
            symbol=symbol,
            as_of=as_of,
            score=score,
            subscores=dict(subscores),
            price_version=price_version,
        )

    def get_scores(self, scope: str, symbol: str) -> list[ScoreRecord]:
        out = [
            r for (sc, sy, _), r in self._scores.items()
            if sc == scope and sy == symbol
        ]
        return sorted(out, key=lambda r: r.as_of)

    # ---------------- adjustment_event / run_log ----------------

    def record_adjustment(
        self,
        symbol: str,
        detected_at: dt.datetime,
        event_date: dt.date | None,
        ratio: float | None,
        rows_affected: int | None,
        note: str,
    ) -> None:
        self._adjustments.append(
            {
                "symbol": symbol,
                "detected_at": detected_at.isoformat(),
                "event_date": event_date.isoformat() if event_date else None,
                "ratio": ratio,
                "rows_affected": rows_affected,
                "note": note,
            }
        )

    def record_run(
        self,
        run_id: str,
        task: str,
        started_at: dt.datetime,
        ended_at: dt.datetime | None,
        status: str,
        counts: dict | None = None,
        quota: dict | None = None,
    ) -> None:
        self._runs[run_id] = {
            "run_id": run_id,
            "task": task,
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat() if ended_at else None,
            "status": status,
            "counts": counts or {},
            "quota": quota or {},
        }

    # ---------------- ChipRepository ----------------

    def put_chips(self, date: dt.date, payload: dict, as_of: dt.datetime) -> None:
        self._chips[date] = copy.deepcopy(payload)

    def get_chips(self, date: dt.date) -> dict | None:
        got = self._chips.get(date)
        return copy.deepcopy(got) if got is not None else None

    def get_chip_range(
        self, start: dt.date, end: dt.date
    ) -> list[tuple[dt.date, dict]]:
        return [
            (d, copy.deepcopy(p))
            for d, p in sorted(self._chips.items())
            if start <= d <= end
        ]

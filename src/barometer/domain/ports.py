"""Port 定義（ToDo §3.2 Ports & Adapters）。

介面定義在內層、實作在外層 —— domain 不知道 SQLite 存在。
表現層（views / presenters / render）只認這裡的 Protocol，
永遠不 import storage/，那條界線由 tests/test_layer_boundary.py 守著。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class PriceBar:
    """一根日 K。

    volume_shares 一律是**股**（§1 第 10 條）—— 台股顯示成「張」是顯示層
    除以 1000 的事，資料層不做這個換算，也不存張。
    """

    symbol: str
    date: dt.date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume_shares: float | None
    source: str
    as_of: dt.datetime
    stale: bool = False


@dataclass(frozen=True, slots=True)
class MacroSeries:
    """一條總經序列，含它自己的資料日期。

    data_date 是**這條序列的資料落在哪一天**，不是抓取時間 —— CPI 標 8 月、
    利差標昨天，兩個都對，所以頁面上沒有單一的「最後更新時間」（§9 Day 25 第 3 項）。
    """

    key: str
    series: list[tuple[str, float]]
    fetched_at: dt.datetime
    data_date: dt.date | None
    stale_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ScoreRecord:
    scope: str
    symbol: str
    as_of: dt.date
    score: float
    subscores: dict[str, float] = field(default_factory=dict)
    price_version: str = "v1"


@runtime_checkable
class PriceRepository(Protocol):
    def upsert_prices(self, bars: list[PriceBar]) -> int: ...

    def get_prices(
        self,
        symbol: str,
        start: dt.date | None = None,
        end: dt.date | None = None,
    ) -> list[PriceBar]: ...

    def last_price_date(self, symbol: str) -> dt.date | None: ...

    def record_conflict(
        self,
        symbol: str,
        date: dt.date,
        field: str,
        shioaji_value: float | None,
        yf_value: float | None,
        taken: str,
        as_of: dt.datetime,
    ) -> None: ...

    def get_conflicts(self, date: dt.date) -> list[dict]: ...


@runtime_checkable
class MacroRepository(Protocol):
    def put_macro(
        self,
        key: str,
        series: list[tuple[str, float]],
        fetched_at: dt.datetime,
        data_date: dt.date | None,
        stale_reason: str | None = None,
    ) -> None: ...

    def get_macro(self, key: str) -> MacroSeries | None: ...


@runtime_checkable
class ScoreHistoryRepository(Protocol):
    def put_score(
        self,
        scope: str,
        symbol: str,
        as_of: dt.date,
        score: float,
        subscores: dict[str, float],
        price_version: str,
    ) -> None: ...

    def get_scores(self, scope: str, symbol: str) -> list[ScoreRecord]: ...


@runtime_checkable
class ChipRepository(Protocol):
    """市場級籌碼面（ToDo §8.2）。

    payload 刻意是 dict 而不是一個 dataclass —— 籌碼面的欄位還在變，
    而 Port 定得越死，加一個維度就越要動到每一層。
    domain 端要型別的話用 domain/chips.py 的 ChipSnapshot。
    """

    def put_chips(
        self, date: dt.date, payload: dict, as_of: dt.datetime
    ) -> None: ...

    def get_chips(self, date: dt.date) -> dict | None: ...

    def get_chip_range(
        self, start: dt.date, end: dt.date
    ) -> list[tuple[dt.date, dict]]: ...

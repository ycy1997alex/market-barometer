"""指數的「量」不是股數，不能拿去跨源比對。

2026-09-06 實測：^TWII 在 shioaji 與 yfinance 的 volume 差約 2000 倍，而**價格
四欄完全對得上**。差的不是資料品質，是「成交量」在指數上根本不是同一個定義
（各家的統計口徑不同）。

所以：指數不套「張→股」換算，也不比對量 —— 硬比只會每天產生一堆假衝突，
淹掉真正該注意的那幾筆。§4.2 說「筆數突然變多本身就是警報」，那前提是
平常的筆數是有意義的。
"""
from __future__ import annotations

import datetime as dt

from barometer.config import is_index
from barometer.domain.reconcile import cross_check
from barometer.domain.ports import PriceBar

AS_OF = dt.datetime(2026, 9, 6, 18, 0)


def bar(symbol: str, close: float, volume: float, source: str) -> PriceBar:
    return PriceBar(
        symbol=symbol, date=dt.date(2026, 9, 4),
        open=close, high=close, low=close, close=close,
        volume_shares=volume, source=source, as_of=AS_OF,
    )


class TestIsIndex:
    def test_recognises_both_indices(self):
        assert is_index("^TWII") is True
        assert is_index("^GSPC") is True

    def test_etfs_and_stocks_are_not_indices(self):
        for s in ("0050.TW", "006208.TW", "SPY", "VOO", "2330.TW", "NVDA"):
            assert is_index(s) is False, s


class TestVolumeComparisonCanBeSkipped:
    def test_index_volume_mismatch_is_not_a_conflict_when_skipped(self):
        """實測數量級：shioaji 9,256,323,000 vs yfinance 4,388,800。"""
        sj = [bar("^TWII", 46551.13, 9_256_323_000.0, "shioaji")]
        yf = [bar("^TWII", 46551.13, 4_388_800.0, "yfinance")]
        _, conflicts = cross_check(sj, yf, compare_volume=False)
        assert conflicts == [], "指數的量不比對，不該產生衝突"

    def test_price_is_still_compared_for_indices(self):
        """跳過的只有量，價格照比 —— 價格才是指數真正該對帳的東西。"""
        sj = [bar("^TWII", 46551.13, 9_256_323_000.0, "shioaji")]
        yf = [bar("^TWII", 40000.00, 4_388_800.0, "yfinance")]
        _, conflicts = cross_check(sj, yf, compare_volume=False)
        assert {c["field"] for c in conflicts} == {"open", "high", "low", "close"}

    def test_volume_is_compared_by_default(self):
        sj = [bar("0050.TW", 107.9, 1_941_000.0, "shioaji")]
        yf = [bar("0050.TW", 107.9, 1_962_986.0, "yfinance")]
        _, conflicts = cross_check(sj, yf)
        assert [c["field"] for c in conflicts] == ["volume"]

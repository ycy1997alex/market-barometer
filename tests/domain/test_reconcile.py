"""§4.1 比對／§4.2 交叉比對。

Day 24 第 7 項驗收：「故意改一格本機資料再跑一次，suspect_adjust 旗標亮起
且**資料沒被自動改掉**」。§12 紅線第 7 條：自動修復歷史資料一律不做。

比對是純規則 → 放 domain，離線可測。
"""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.domain.reconcile import (
    compare_overlap,
    cross_check,
    CLOSE_TOLERANCE,
    VOLUME_TOLERANCE,
)
from barometer.domain.ports import PriceBar

AS_OF = dt.datetime(2026, 9, 6, 18, 0)


def bar(day: int, close: float, symbol="0050.TW", source="yfinance", **kw) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        date=dt.date(2026, 9, day),
        open=kw.get("open", close),
        high=kw.get("high", close),
        low=kw.get("low", close),
        close=close,
        volume_shares=kw.get("volume_shares", 1_000_000),
        source=source,
        as_of=AS_OF,
    )


class TestCompareOverlap:
    """本機已存的 vs 今天抓回來的 —— 偵測資料源有沒有回頭改寫歷史。"""

    def test_identical_data_is_not_suspect(self):
        stored = [bar(2, 100.0), bar(3, 101.0)]
        fetched = [bar(2, 100.0), bar(3, 101.0)]
        result = compare_overlap(stored, fetched)
        assert result.suspect_adjust is False
        assert result.mismatches == []

    def test_rewritten_history_raises_the_flag(self):
        """分割會把整條歷史乘上同一個常數 —— 最新幾根對不上就足以知道。"""
        stored = [bar(2, 100.0), bar(3, 101.0)]
        fetched = [bar(2, 25.0), bar(3, 25.25)]  # 疑似 4:1 分割
        result = compare_overlap(stored, fetched)
        assert result.suspect_adjust is True
        assert len(result.mismatches) == 2

    def test_flag_only_no_data_is_returned_for_writing(self):
        """§4.1：比對**不改**資料，只記旗標。回傳裡不得有「該寫入什麼」。"""
        stored = [bar(2, 100.0)]
        fetched = [bar(2, 25.0)]
        result = compare_overlap(stored, fetched)
        assert not hasattr(result, "corrected_bars")
        assert not hasattr(result, "rows_to_write")

    def test_constant_ratio_is_reported(self):
        """整條被乘上同一個常數 → 回報那個比例，人才知道發生了什麼。"""
        stored = [bar(2, 100.0), bar(3, 200.0)]
        fetched = [bar(2, 25.0), bar(3, 50.0)]
        result = compare_overlap(stored, fetched)
        assert result.ratio == pytest.approx(0.25)

    def test_inconsistent_diffs_report_no_ratio(self):
        """比例不一致 → 不是分割，是別的問題，不要硬套一個比例。"""
        stored = [bar(2, 100.0), bar(3, 200.0)]
        fetched = [bar(2, 25.0), bar(3, 199.0)]
        result = compare_overlap(stored, fetched)
        assert result.suspect_adjust is True
        assert result.ratio is None

    def test_tiny_float_noise_is_not_a_mismatch(self):
        stored = [bar(2, 100.0)]
        fetched = [bar(2, 100.00001)]
        assert compare_overlap(stored, fetched).suspect_adjust is False

    def test_only_overlapping_dates_are_compared(self):
        """新的日期不是「對不上」，是還沒存過 —— 那是回看的事，不是比對的事。"""
        stored = [bar(2, 100.0)]
        fetched = [bar(2, 100.0), bar(3, 101.0)]
        result = compare_overlap(stored, fetched)
        assert result.suspect_adjust is False
        assert result.compared_dates == [dt.date(2026, 9, 2)]

    def test_no_overlap_is_not_suspect(self):
        result = compare_overlap([bar(2, 100.0)], [bar(5, 101.0)])
        assert result.suspect_adjust is False
        assert result.compared_dates == []

    def test_stale_rows_are_skipped(self):
        """自己標成 stale 的那格本來就是保留前一日值，拿去比對只會製造假警報。"""
        stored = [PriceBar(symbol="0050.TW", date=dt.date(2026, 9, 2), open=1.0,
                           high=1.0, low=1.0, close=105.5, volume_shares=1.0,
                           source="yfinance", as_of=AS_OF, stale=True)]
        fetched = [bar(2, 106.2)]
        assert compare_overlap(stored, fetched).suspect_adjust is False


class TestCrossCheck:
    """§4.2 shioaji × yfinance —— 衝突以 shioaji 為主。"""

    def test_within_tolerance_takes_shioaji_without_conflict(self):
        sj = [bar(4, 100.00, source="shioaji")]
        yf = [bar(4, 100.05, source="yfinance")]  # 0.05% < 0.1%
        merged, conflicts = cross_check(sj, yf)
        assert conflicts == []
        assert merged[0].close == pytest.approx(100.00)
        assert merged[0].source == "shioaji"

    def test_beyond_tolerance_records_conflict_and_takes_shioaji(self):
        # 只讓 close 差開 —— open/high/low 維持一致，才驗得出「一格衝突記一列」
        sj = [bar(4, 100.0, source="shioaji")]
        yf = [bar(4, 105.0, source="yfinance", open=100.0, high=100.0, low=100.0)]
        merged, conflicts = cross_check(sj, yf)
        assert merged[0].close == pytest.approx(100.0), "衝突取 shioaji"
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c["field"] == "close"
        assert c["taken"] == "shioaji"
        assert c["shioaji_value"] == pytest.approx(100.0)
        assert c["yf_value"] == pytest.approx(105.0)

    def test_volume_has_a_looser_tolerance(self):
        sj = [bar(4, 100.0, source="shioaji", volume_shares=1_000_000)]
        yf = [bar(4, 100.0, source="yfinance", volume_shares=1_005_000)]  # 0.5% < 1%
        _, conflicts = cross_check(sj, yf)
        assert conflicts == []

    def test_volume_beyond_one_percent_is_a_conflict(self):
        sj = [bar(4, 100.0, source="shioaji", volume_shares=1_000_000)]
        yf = [bar(4, 100.0, source="yfinance", volume_shares=1_100_000)]  # 10%
        _, conflicts = cross_check(sj, yf)
        assert [c["field"] for c in conflicts] == ["volume"]

    def test_yfinance_only_is_tagged_yf_only(self):
        merged, conflicts = cross_check([], [bar(4, 100.0)])
        assert merged[0].source == "yf_only"
        assert conflicts == []

    def test_shioaji_only_is_kept(self):
        merged, _ = cross_check([bar(4, 100.0, source="shioaji")], [])
        assert merged[0].source == "shioaji"

    def test_tolerances_are_the_documented_ones(self):
        assert CLOSE_TOLERANCE == pytest.approx(0.001)
        assert VOLUME_TOLERANCE == pytest.approx(0.01)

    def test_all_four_price_fields_are_checked(self):
        sj = [bar(4, 100.0, source="shioaji", open=10.0, high=11.0, low=9.0)]
        yf = [bar(4, 100.0, source="yfinance", open=20.0, high=22.0, low=18.0)]
        _, conflicts = cross_check(sj, yf)
        assert {c["field"] for c in conflicts} == {"open", "high", "low"}

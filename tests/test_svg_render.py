"""Day 25 第 4 項驗收：「月頻的 CPI 與日頻的利差畫在同一頁而不誤導
（月頻用階梯或點，不要拉成連續線）」。

為什麼這是規則而不是美學：把每月一個點用直線連起來，等於宣稱中間那些日子
有值、而且是線性變化的 —— 那是畫出來的，不是量到的。日頻可以連續，
月頻與季頻不行。

render/ 層的測試放這裡（不是 tests/domain/），因為它是表現層。
"""
from __future__ import annotations

import re

import pytest

from barometer.render.svg import (
    sparkline,
    FREQ_CONTINUOUS,
    FREQ_STEPPED,
    freq_style,
)


DAILY = [(f"2026-09-{d:02d}", 100.0 + d) for d in range(1, 11)]
MONTHLY = [("2026-05", 3.1), ("2026-06", 3.2), ("2026-07", 3.4)]
QUARTERLY = [("2025Q4", 1.2), ("2026Q1", 15.4), ("2026Q2", 12.9)]


class TestFreqStyle:
    def test_daily_is_continuous(self):
        assert freq_style("每日") == FREQ_CONTINUOUS

    def test_monthly_and_quarterly_are_stepped(self):
        assert freq_style("每月") == FREQ_STEPPED
        assert freq_style("每季") == FREQ_STEPPED

    def test_irregular_is_stepped(self):
        """不定期（Fed 利率、央行重貼現率）本來就是階梯狀的政策值。"""
        assert freq_style("不定期") == FREQ_STEPPED

    def test_unknown_freq_defaults_to_stepped(self):
        """不確定就用比較保守的那個 —— 階梯不會假裝中間有資料。"""
        assert freq_style("每 17 天") == FREQ_STEPPED


class TestSparkline:
    def test_returns_svg_markup(self):
        out = sparkline(DAILY, freq="每日")
        assert out.startswith("<svg") and out.endswith("</svg>")
        assert "viewBox" in out

    def test_daily_uses_a_single_polyline(self):
        out = sparkline(DAILY, freq="每日")
        assert out.count("<polyline") == 1
        assert "<circle" not in out, "日頻不逐點畫圓，會太吵"

    def test_monthly_draws_markers_for_every_point(self):
        """月頻每個點都要看得見 —— 它們是實際量到的值。"""
        out = sparkline(MONTHLY, freq="每月")
        assert out.count("<circle") == len(MONTHLY)

    def test_monthly_path_is_stepped_not_diagonal(self):
        """階梯路徑的頂點數是點數的兩倍左右；斜線則等於點數。"""
        out = sparkline(MONTHLY, freq="每月")
        pts = re.search(r'points="([^"]+)"', out).group(1).split()
        assert len(pts) > len(MONTHLY), "月頻不得畫成點對點的斜線"

    def test_quarterly_is_also_stepped(self):
        out = sparkline(QUARTERLY, freq="每季")
        assert out.count("<circle") == len(QUARTERLY)

    def test_single_point_does_not_crash(self):
        out = sparkline([("2026-09-04", 5.0)], freq="每日")
        assert out.startswith("<svg")

    def test_empty_series_renders_a_placeholder_not_a_lie(self):
        out = sparkline([], freq="每日")
        assert "<polyline" not in out
        assert "—" in out or "no-data" in out

    def test_flat_series_does_not_divide_by_zero(self):
        flat = [("2026-09-0%d" % d, 7.0) for d in range(1, 6)]
        out = sparkline(flat, freq="每日")
        assert out.startswith("<svg")
        assert "nan" not in out.lower()

    def test_none_values_are_skipped_not_zeroed(self):
        """缺值不得被當成 0 畫下去 —— 那會在圖上憑空造出一次崩跌。"""
        series = [("2026-09-01", 100.0), ("2026-09-02", None),
                  ("2026-09-03", 102.0)]
        out = sparkline(series, freq="每日")
        assert "0,0" not in out.replace(" ", "")

    def test_no_external_dependency_is_referenced(self):
        """inline SVG，不用任何圖表函式庫（§3.4）。"""
        out = sparkline(DAILY, freq="每日")
        for bad in ("http://", "https://", "<script", "d3", "chart.js"):
            assert bad not in out.lower()

"""§9 Day 26 第 1 項驗收：「對一段手算過的資料，每個指標的數值對得上」。

所有預期值都是手算出來的，不是跑程式印出來貼回去的。
"""
import math

import pytest

from barometer.domain.indicators import (
    moving_average,
    rsi,
    bollinger,
    annualised_volatility,
    drawdown_from_high,
)

# 手算基準：1..10 的等差序列
RAMP = [float(i) for i in range(1, 11)]


class TestMovingAverage:
    def test_last_ma_of_ramp_is_hand_computed(self):
        # 最後 5 筆是 6,7,8,9,10 → 平均 8.0
        assert moving_average(RAMP, 5)[-1] == pytest.approx(8.0)
        # 最後 3 筆是 8,9,10 → 平均 9.0
        assert moving_average(RAMP, 3)[-1] == pytest.approx(9.0)

    def test_window_not_yet_filled_is_none(self):
        out = moving_average(RAMP, 5)
        assert out[:4] == [None, None, None, None]
        assert out[4] == pytest.approx(3.0)  # 1..5 平均 = 3

    def test_series_shorter_than_window_is_all_none(self):
        assert moving_average([1.0, 2.0], 5) == [None, None]

    def test_nan_in_window_yields_none_not_nan(self):
        # §4.3：缺值不得污染指標，該格是 None 而不是 NaN
        series = [1.0, 2.0, float("nan"), 4.0, 5.0]
        out = moving_average(series, 3)
        assert out[2] is None and out[3] is None and out[4] is None
        assert not any(v is not None and math.isnan(v) for v in out)


class TestRSI:
    def test_monotonic_rise_gives_100(self):
        # 一路上漲，沒有任何下跌 → 平均跌幅 0 → RSI = 100
        assert rsi(RAMP, period=5)[-1] == pytest.approx(100.0)

    def test_monotonic_fall_gives_0(self):
        assert rsi(list(reversed(RAMP)), period=5)[-1] == pytest.approx(0.0)

    def test_hand_computed_wilder_value(self):
        # period=2，序列 [10, 11, 10.5]
        #   變動：+1.0、-0.5
        #   首個平均：gain = 1.0/2 = 0.5、loss = 0.5/2 = 0.25
        #   RS = 2.0 → RSI = 100 - 100/(1+2) = 66.6667
        out = rsi([10.0, 11.0, 10.5], period=2)
        assert out[-1] == pytest.approx(66.6667, abs=1e-4)

    def test_insufficient_data_is_none(self):
        assert rsi([1.0, 2.0], period=14)[-1] is None


class TestBollinger:
    def test_hand_computed_band_on_constant_then_step(self):
        # 五筆全部 10 → 標準差 0 → 上下軌都貼在中線
        mid, upper, lower = bollinger([10.0] * 5, period=5, num_std=2.0)
        assert mid[-1] == pytest.approx(10.0)
        assert upper[-1] == pytest.approx(10.0)
        assert lower[-1] == pytest.approx(10.0)

    def test_hand_computed_std(self):
        # [2,4,4,4,5,5,7,9] 的母體標準差是教科書例題 = 2.0，平均 = 5.0
        series = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        mid, upper, lower = bollinger(series, period=8, num_std=2.0)
        assert mid[-1] == pytest.approx(5.0)
        assert upper[-1] == pytest.approx(9.0)
        assert lower[-1] == pytest.approx(1.0)


class TestAnnualisedVolatility:
    def test_zero_when_price_never_moves(self):
        assert annualised_volatility([100.0] * 30) == pytest.approx(0.0)

    def test_hand_computed_scaling(self):
        # 日報酬固定 ±1% 交替 → 日標準差 = 0.01（母體）
        # 年化 = 0.01 × sqrt(252) = 0.158745…
        prices = [100.0]
        for i in range(40):
            prices.append(prices[-1] * (1.01 if i % 2 == 0 else 1 / 1.01))
        vol = annualised_volatility(prices)
        assert vol == pytest.approx(0.01 * math.sqrt(252), rel=0.02)

    def test_insufficient_data_is_none(self):
        assert annualised_volatility([100.0]) is None


class TestDrawdownFromHigh:
    def test_at_the_high_is_zero(self):
        assert drawdown_from_high(RAMP) == pytest.approx(0.0)

    def test_hand_computed_drawdown(self):
        # 高點 100、現價 80 → 回撤 -20%
        assert drawdown_from_high([50.0, 100.0, 80.0]) == pytest.approx(-0.20)

    def test_ignores_nan_high(self):
        assert drawdown_from_high([50.0, float("nan"), 100.0, 80.0]) == pytest.approx(-0.20)

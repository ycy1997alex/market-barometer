"""Day 25 第 2 項驗收：「純函式、零 I/O，餵固定輸入得到固定輸出的測試通過」。

兩層結構（§8 沿用既有專案的設計）：
  第一層 每個指標各自判定是否警示
  第二層 依層別算未警示比例，合成 0~100

§2.1 紅線：market-barometer 的評分輸出**不得**含任何行動字眼 ——
所以這裡沒有 advice 欄位，那是刻意的，有一個測試守著。
"""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.domain.scoring_macro import (
    alert_vix, alert_dxy, alert_us10y, alert_t10y2y, alert_cpi,
    alert_unrate, alert_phlfed, alert_fedfunds,
    alert_usdtwd, alert_sox, alert_tw_light, alert_tw_export,
    alert_tw_gdp, alert_cbc_rate,
    score_layer, summarize,
    LayerScore,
)


def series(values: list[float]) -> list[tuple[str, float]]:
    """(日期, 值) 由舊到新。判定只看值，日期是給顯示層用的。"""
    return [(f"2026-{(i % 12) + 1:02d}-01", v) for i, v in enumerate(values)]


class TestWorldAlerts:
    def test_vix_thresholds(self):
        assert alert_vix(series([15.0]))[0] is False
        assert alert_vix(series([28.3]))[0] is True   # > 25
        assert alert_vix(series([40.0]))[0] is True   # > 35 強警示
        assert "35" in alert_vix(series([40.0]))[1] or "恐慌" in alert_vix(series([40.0]))[1]

    def test_vix_boundary_is_not_inclusive(self):
        assert alert_vix(series([25.0]))[0] is False, "門檻是 > 25，等於不算"

    def test_dxy_five_day_move(self):
        # 需要至少 6 筆；s[-1] 對 s[-6]
        assert alert_dxy(series([100, 100, 100, 100, 100, 100.5]))[0] is False
        assert alert_dxy(series([100, 100, 100, 100, 100, 103.0]))[0] is True  # +3% > 2%
        assert alert_dxy(series([100, 100, 100, 100, 100, 97.0]))[0] is True   # -3%

    def test_us10y_moves_in_percentage_points(self):
        assert alert_us10y(series([4.0, 4, 4, 4, 4, 4.10]))[0] is False  # +0.10pp
        assert alert_us10y(series([4.0, 4, 4, 4, 4, 4.25]))[0] is True   # +0.25pp > 0.20

    def test_t10y2y_inversion_is_the_alert(self):
        assert alert_t10y2y(series([0.5]))[0] is False
        assert alert_t10y2y(series([-0.1]))[0] is True, "倒掛就是警示"
        assert "倒掛" in alert_t10y2y(series([-0.1]))[1]

    def test_cpi_yoy_or_mom(self):
        # 13 筆才算得出 YoY
        flat = [100.0] * 13
        assert alert_cpi(series(flat))[0] is False
        hot_yoy = [100.0] * 12 + [104.0]      # YoY +4% > 3%
        assert alert_cpi(series(hot_yoy))[0] is True
        hot_mom = [100.0] * 12 + [100.5]      # MoM +0.5% > 0.4%
        assert alert_cpi(series(hot_mom))[0] is True

    def test_unrate_sahm_rule(self):
        # 最新值 − 近 12 個月最低 >= 0.5pp
        calm = series([4.0] * 13)
        assert alert_unrate(calm)[0] is False
        rising = series([3.5] * 12 + [4.1])   # 4.1 - 3.5 = 0.6 >= 0.5
        assert alert_unrate(rising)[0] is True
        assert "Sahm" in alert_unrate(rising)[1]

    def test_phlfed_zero_is_the_line(self):
        assert alert_phlfed(series([5.0]))[0] is False
        assert alert_phlfed(series([-3.0]))[0] is True
        assert alert_phlfed(series([0.0]))[0] is False, "榮枯線是 0，等於不算收縮"

    def test_fedfunds_recent_change(self):
        assert alert_fedfunds(series([5.5] * 31))[0] is False
        assert alert_fedfunds(series([5.5] * 30 + [5.25]))[0] is True


class TestTaiwanAlerts:
    def test_usdtwd_one_and_a_half_percent(self):
        assert alert_usdtwd(series([30.0] * 5 + [30.2]))[0] is False   # +0.67%
        assert alert_usdtwd(series([30.0] * 5 + [30.6]))[0] is True    # +2%

    def test_sox_below_60ma(self):
        rising = series(list(range(1, 81)))
        assert alert_sox(rising)[0] is False, "站上 60 日均線"
        falling = series(list(range(80, 0, -1)))
        assert alert_sox(falling)[0] is True

    def test_sox_insufficient_data_is_not_an_alert(self):
        ok, msg = alert_sox(series([100.0] * 10))
        assert ok is False and "資料不足" in msg

    def test_tw_light_alerts_at_both_ends(self):
        assert alert_tw_light(series([27.0]))[0] is False  # 綠燈
        assert alert_tw_light(series([16.0]))[0] is True   # 藍燈
        assert alert_tw_light(series([38.0]))[0] is True   # 紅燈
        assert "藍燈" in alert_tw_light(series([16.0]))[1]

    def test_tw_export_diffusion_line_is_50(self):
        assert alert_tw_export(series([52.0]))[0] is False
        assert alert_tw_export(series([48.0]))[0] is True

    def test_tw_gdp_negative(self):
        assert alert_tw_gdp(series([2.5]))[0] is False
        assert alert_tw_gdp(series([-0.5]))[0] is True

    def test_cbc_rate_alerts_only_on_a_recent_adjustment(self):
        """判定看的是「距今幾天」，不是「值有沒有變」。

        這張表相鄰兩列的值必然不同（不然不會被記成一次調整），拿值去比會永遠
        亮燈 —— 實測 2026-09-06 抓到的最新調整是 2024-03-22，早就過了觀察窗。
        """
        today = dt.date(2026, 9, 6)
        stale = [("2024-03-22", 2.0)]
        assert alert_cbc_rate(stale, today=today)[0] is False
        assert "距今" in alert_cbc_rate(stale, today=today)[1]

    def test_cbc_rate_alerts_inside_the_window(self):
        today = dt.date(2026, 9, 6)
        assert alert_cbc_rate([("2026-08-01", 2.25)], today=today)[0] is True
        # 邊界：90 天整仍算「剛動過」
        assert alert_cbc_rate([("2026-06-08", 2.25)], today=today)[0] is True
        assert alert_cbc_rate([("2026-06-07", 2.25)], today=today)[0] is False

    def test_cbc_rate_empty_is_insufficient(self):
        assert alert_cbc_rate([])[0] is False


class TestInsufficientData:
    """資料筆數不足時一律「不警示 + 資料不足」，不硬算。"""

    @pytest.mark.parametrize("fn", [
        alert_dxy, alert_us10y, alert_cpi, alert_unrate, alert_usdtwd,
    ])
    def test_short_series_never_alerts(self, fn):
        ok, msg = fn(series([1.0]))
        assert ok is False
        assert "資料不足" in msg

    def test_empty_series_never_alerts(self):
        for fn in (alert_vix, alert_t10y2y, alert_phlfed, alert_tw_light):
            ok, msg = fn([])
            assert ok is False and "資料不足" in msg


class TestLayerScore:
    def test_no_alerts_is_100(self):
        assert score_layer({"a": False, "b": False}).score == pytest.approx(100.0)

    def test_all_alerts_is_0(self):
        assert score_layer({"a": True, "b": True}).score == pytest.approx(0.0)

    def test_half_alerts_is_50(self):
        assert score_layer({"a": True, "b": False}).score == pytest.approx(50.0)

    def test_hand_computed_two_of_seven(self):
        alerts = {f"k{i}": (i < 2) for i in range(7)}
        assert score_layer(alerts).score == pytest.approx(100 * (1 - 2 / 7))

    def test_empty_layer_is_none(self):
        assert score_layer({}).score is None

    def test_reports_which_indicators_alerted(self):
        out = score_layer({"vix": True, "dxy": False, "cpi": True})
        assert set(out.alert_keys) == {"vix", "cpi"}
        assert out.valid == 3


class TestSummarize:
    def test_combines_world_and_taiwan(self):
        world = LayerScore(score=80.0, valid=8, alert_keys=["vix"])
        tw = LayerScore(score=60.0, valid=6, alert_keys=["sox", "tw_gdp"])
        out = summarize(world, tw)
        # 兩層等權：(80 + 60) / 2 = 70
        assert out["score"] == pytest.approx(70.0)
        assert out["world"] == pytest.approx(80.0)
        assert out["taiwan"] == pytest.approx(60.0)

    def test_missing_layer_does_not_break_the_total(self):
        world = LayerScore(score=80.0, valid=8, alert_keys=[])
        tw = LayerScore(score=None, valid=0, alert_keys=[])
        out = summarize(world, tw)
        assert out["score"] == pytest.approx(80.0), "沒有成員的層不計入權重"

    def test_all_layers_missing_gives_none(self):
        empty = LayerScore(score=None, valid=0, alert_keys=[])
        assert summarize(empty, empty)["score"] is None

    def test_low_data_flag(self):
        world = LayerScore(score=100.0, valid=2, alert_keys=[])
        tw = LayerScore(score=100.0, valid=1, alert_keys=[])
        assert summarize(world, tw)["low_data"] is True

    def test_no_advice_field_is_produced(self):
        """§2.1 紅線：market-barometer 不產生任何把分數翻譯成動作的東西。

        既有專案的 summarize() 有 advice 欄位（「建議降低部位、提高現金比重」），
        那正是這一側**不可以**有的。這個測試守著那條線。
        """
        world = LayerScore(score=40.0, valid=8, alert_keys=["vix"])
        tw = LayerScore(score=30.0, valid=6, alert_keys=["sox"])
        out = summarize(world, tw)
        for banned in ("advice", "suggestion", "action", "建議"):
            assert banned not in out, f"輸出不得有 {banned} 欄位（§2.1）"

    def test_output_is_a_measurement_not_an_instruction(self):
        """氣壓計告訴你現在幾百帕，不告訴你要不要帶傘。"""
        world = LayerScore(score=20.0, valid=8, alert_keys=["vix", "cpi"])
        tw = LayerScore(score=20.0, valid=6, alert_keys=["sox"])
        blob = repr(summarize(world, tw))
        for word in ("買進", "賣出", "加碼", "減碼", "觀望", "進場", "出場"):
            assert word not in blob

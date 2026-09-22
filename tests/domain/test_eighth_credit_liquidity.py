"""第八批 8-1：高收益債信用利差 + Fed 淨流動性。

兩項都是**看變化不看水位**：
  - 信用利差：股市還在撐的時候信用市場通常先報警，所以看的是相對近期低點的升幅。
    **只有擴大算警示** —— 利差收斂是風險偏好回來，記成警示會讓它在多頭時一直亮燈。
  - 淨流動性 `WALCL − RRPONTSYD`：看四週變化的方向。
    ⚠️ **基期為 0 一律視為缺料，不是 −100%** —— `RRPONTSYD` 2013 年以前長期為 0，
    照算會得到一個假的「流動性極差」訊號。
"""
from __future__ import annotations

from barometer.domain import macro_spec as spec
from barometer.domain import scoring_macro as sm


def _daily(values: list[float]) -> list[tuple[str, float]]:
    return [(f"2026-09-{i + 1:02d}", v) for i, v in enumerate(values)]


# ---------------- 高收益債信用利差 BAMLH0A0HYM2 ----------------

def test_spread_widening_off_the_recent_low_is_an_alert():
    series = _daily([3.0] * 19 + [4.2])
    hit, text = sm.alert_credit_spread(series)
    assert hit
    assert "1.20" in text and "門檻" in text


def test_spread_narrowing_is_not_an_alert():
    hit, text = sm.alert_credit_spread(_daily([5.0] * 10 + [3.0] * 10))
    assert not hit
    assert sm.INSUFFICIENT not in text


def test_spread_needs_enough_history_before_it_says_anything():
    assert sm.alert_credit_spread(_daily([3.0, 3.1]))[1] == sm.INSUFFICIENT


# ---------------- 淨流動性 WALCL − RRPONTSYD ----------------

def test_net_liquidity_contraction_is_an_alert():
    series = _daily([6000.0, 6000.0, 5990.0, 5980.0, 5880.0])
    hit, text = sm.alert_net_liquidity(series)
    assert hit
    assert "四週" in text and "門檻" in text


def test_net_liquidity_expansion_is_not_an_alert():
    hit, _ = sm.alert_net_liquidity(_daily([5800.0, 5850.0, 5900.0, 5950.0, 6000.0]))
    assert not hit


def test_zero_base_is_missing_data_not_minus_one_hundred_percent():
    """⚠️ 這一條是 8-1 的整個重點：基期 0 不得變成 −100% 的假警示。"""
    hit, text = sm.alert_net_liquidity(_daily([0.0, 10.0, 20.0, 30.0, 40.0]))
    assert not hit
    assert text == sm.INSUFFICIENT


# ---------------- 接線 ----------------

def test_both_indicators_are_wired_into_the_world_layer():
    keys = {i.key for i in spec.WORLD}
    assert {"credit_spread", "net_liquidity"} <= keys
    for key in ("credit_spread", "net_liquidity"):
        assert key in sm.ALERT_FUNCS
        assert spec.BY_KEY[key].scored


def test_every_scored_series_has_a_publish_lag_entry():
    """平移表漏一筆，歷史重放就會在那一項上安靜地讀到未來（§7.2）。"""
    for indicator in spec.SCORED:
        if not indicator.backtest:
            continue  # 8-6 的原油曲線刻意不進重放
        assert indicator.sid in spec.PUBLISH_LAG_DAYS, indicator.key

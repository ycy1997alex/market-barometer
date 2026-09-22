"""第八批 8-6：原油近遠月曲線（近月 vs +6 個月）。

⚠️ **遠月代碼每個月都變，不准寫死。** 由當月動態生成：`CL` + 月碼 + 兩位年 + `.NYM`。
⚠️ **不進回測。** 固定到期月的合約，在不同日期距到期的月數不同 —— 前後不可比。
   回測時這一項當缺料處理，不是當成 0 分也不是拿別的東西頂替。
判定用**絕對價差水位**的對稱映射：±8%／6 個月，兩端都算不尋常。
"""
from __future__ import annotations

import datetime as dt

from barometer.domain import futures
from barometer.domain import macro_spec as spec
from barometer.domain import scoring_macro as sm


def _s(values):
    return [(f"2026-09-{i + 1:02d}", v) for i, v in enumerate(values)]


def test_deferred_symbol_is_generated_from_the_current_month():
    assert futures.deferred_crude_symbol(dt.date(2026, 9, 22)) == "CLH27.NYM"
    assert futures.deferred_crude_symbol(dt.date(2026, 1, 5)) == "CLN26.NYM"
    assert futures.deferred_crude_symbol(dt.date(2026, 12, 31)) == "CLM27.NYM"


def test_month_codes_follow_the_exchange_convention():
    assert futures.MONTH_CODES[0] == "F" and futures.MONTH_CODES[11] == "Z"
    assert len(futures.MONTH_CODES) == 12


def test_steep_backwardation_is_an_alert():
    hit, text = sm.alert_oil_curve(_s([-2.0, -9.9]))
    assert hit
    assert "backwardation" in text and "門檻" in text


def test_steep_contango_is_also_an_alert():
    hit, text = sm.alert_oil_curve(_s([1.0, 8.5]))
    assert hit
    assert "contango" in text


def test_a_flat_curve_is_not_an_alert():
    hit, _ = sm.alert_oil_curve(_s([1.2]))
    assert not hit


def test_no_data_is_insufficient():
    assert sm.alert_oil_curve([])[1] == sm.INSUFFICIENT


def test_the_curve_is_scored_but_kept_out_of_the_replay():
    indicator = spec.BY_KEY["oil_curve"]
    assert indicator.scored
    assert not indicator.backtest          # ⚠️ 不進回測
    assert "oil_curve" in sm.ALERT_FUNCS


def test_replay_skips_indicators_that_are_not_backtestable():
    from barometer.domain import macro_replay

    series = {ind.key: [("2026-09-21", 1.0)] for ind in spec.WORLD}
    got = macro_replay.score_world_on(series, dt.date(2026, 9, 22))

    assert got.valid <= len([i for i in spec.WORLD if i.backtest])


def test_every_backtestable_scored_series_still_has_a_publish_lag():
    for indicator in spec.SCORED:
        if indicator.backtest:
            assert indicator.sid in spec.PUBLISH_LAG_DAYS, indicator.key

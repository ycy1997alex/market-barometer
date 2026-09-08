"""三項復活的指標（作者 2026-09-07 決定保留）。

原本被 Claude 以「與失業率重複或共線」「需要另一把金鑰」為由刪掉，作者指出
這個判斷太武斷：

  - **初領失業金與非農就業**：確實有學派認為它們與失業率共線，但也有學派
    認為三者要配合看。三個指標量的是勞動市場的不同切面 —— 失業率是存量、
    初領是每週的邊際流量、非農是每月的淨增減。刪掉兩個等於只留存量。
  - **EIA 原油庫存**：2026 年 9 月的戰爭狀態下，庫存是供給面的直接讀數，
    跟油價（已在觀測項）講的不是同一件事。

判定邏輯的共同原則跟其他指標一致：**看變化，不看水位**，而且兩端都可能警示。
"""
from __future__ import annotations

import pytest

from barometer.domain import scoring_macro as sm


def _weekly(values: list[float]) -> list[tuple[str, float]]:
    """週頻序列，日期只是佔位，判定不看日期。"""
    return [(f"2026-{(i // 4) + 1:02d}-{(i % 4) * 7 + 1:02d}", v)
            for i, v in enumerate(values)]


# ---------------- 初領失業金 ICSA ----------------

def test_claims_rising_sharply_off_the_low_is_an_alert():
    """四週均值相對近期低點明顯上升，是勞動市場轉弱的經典訊號。"""
    v = [200_000] * 20 + [260_000] * 4
    alert, why = sm.alert_claims(_weekly(v))
    assert alert is True
    assert "%" in why


def test_claims_flat_is_not_an_alert():
    alert, why = sm.alert_claims(_weekly([205_000] * 24))
    assert alert is False


def test_claims_falling_is_not_an_alert():
    """初領下降是勞動市場轉強，不是警示。這一項刻意**不是**兩端都警示。"""
    v = [260_000] * 20 + [200_000] * 4
    alert, _ = sm.alert_claims(_weekly(v))
    assert alert is False


def test_claims_needs_enough_history():
    alert, why = sm.alert_claims(_weekly([200_000] * 5))
    assert alert is False
    assert why == sm.INSUFFICIENT


# ---------------- 非農就業 PAYEMS ----------------

def test_payrolls_shrinking_is_an_alert():
    """月增為負代表整體就業人數減少。"""
    alert, why = sm.alert_payrolls([("2026-07-01", 159_200.0),
                                    ("2026-08-01", 159_075.0)])
    assert alert is True
    assert "-" in why


def test_payrolls_growing_is_not_an_alert():
    alert, why = sm.alert_payrolls([("2026-07-01", 158_900.0),
                                    ("2026-08-01", 159_075.0)])
    assert alert is False
    assert "+" in why


def test_payrolls_needs_two_points():
    alert, why = sm.alert_payrolls([("2026-08-01", 159_075.0)])
    assert alert is False
    assert why == sm.INSUFFICIENT


# ---------------- EIA 原油庫存 ----------------

def test_crude_stocks_sharp_draw_is_an_alert():
    """庫存快速去化，戰爭期間是供給緊張的直接讀數。"""
    alert, why = sm.alert_crude_stocks(-3.2)
    assert alert is True
    assert "去化" in why


def test_crude_stocks_sharp_build_is_also_an_alert():
    """兩端都算：急速累積代表需求塌陷，同樣不尋常。"""
    alert, why = sm.alert_crude_stocks(+3.5)
    assert alert is True
    assert "累積" in why


def test_crude_stocks_small_change_is_not_an_alert():
    alert, why = sm.alert_crude_stocks(-1.1)
    assert alert is False
    assert "-1.1" in why


def test_crude_stocks_missing_is_insufficient_not_zero():
    alert, why = sm.alert_crude_stocks(None)
    assert alert is False
    assert why == sm.INSUFFICIENT


# ---------------- 清單 ----------------

def test_the_three_are_back_in_the_world_layer():
    from barometer.domain import macro_spec
    keys = {i.key for i in macro_spec.WORLD}
    assert {"claims", "payrolls", "crude_stocks"} <= keys


def test_world_layer_now_has_eleven_scored_indicators():
    from barometer.domain import macro_spec
    assert len(macro_spec.WORLD) == 11
    assert len(macro_spec.SCORED) == 17


def test_every_scored_indicator_has_an_alert_function():
    from barometer.domain import macro_spec
    missing = [i.key for i in macro_spec.SCORED if i.key not in sm.ALERT_FUNCS]
    assert not missing, missing

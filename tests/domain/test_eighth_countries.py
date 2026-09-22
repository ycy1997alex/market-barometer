"""第八批 8-8：各國總經序列（日韓出口年增率、匯率、央行政策利率）。

⚠️ **這些只進世界層總經評分，不對任何國家的股指評分。** 日經、KOSPI 都不在
這個系統的評分範圍裡（§8）—— 加進來的是總體環境的讀數，不是對那些市場的看法。
"""
from __future__ import annotations

from barometer.domain import macro_spec as spec
from barometer.domain import scoring_macro as sm

COUNTRY_KEYS = ("jp_exports", "kr_exports", "usdjpy", "usdkrw",
                "jp_policy", "kr_policy")


def _monthly(values):
    return [(f"{2024 + i // 12}-{i % 12 + 1:02d}", v) for i, v in enumerate(values)]


def _daily(values):
    return [(f"2026-09-{i + 1:02d}", v) for i, v in enumerate(values)]


# ---------------- 出口年增率 ----------------

def test_exports_contracting_year_on_year_is_an_alert():
    hit, text = sm.alert_exports_yoy(_monthly([100.0] * 12 + [90.0]))
    assert hit
    assert "年增率" in text and "-10" in text


def test_exports_growing_is_not_an_alert():
    hit, text = sm.alert_exports_yoy(_monthly([100.0] * 12 + [115.0]))
    assert not hit
    assert "+15" in text


def test_exports_need_thirteen_months():
    assert sm.alert_exports_yoy(_monthly([100.0] * 12))[1] == sm.INSUFFICIENT


def test_a_zero_base_month_is_missing_data_not_infinite_growth():
    assert sm.alert_exports_yoy(_monthly([0.0] + [100.0] * 12))[1] == sm.INSUFFICIENT


# ---------------- 匯率 ----------------

def test_a_sharp_currency_move_is_an_alert_in_either_direction():
    assert sm.alert_fx_move(_daily([100.0] * 5 + [103.0]))[0]
    assert sm.alert_fx_move(_daily([100.0] * 5 + [97.0]))[0]


def test_a_quiet_currency_is_not_an_alert():
    hit, text = sm.alert_fx_move(_daily([100.0, 100.2, 100.1, 100.3, 100.2, 100.4]))
    assert not hit
    assert "門檻" in text


# ---------------- 央行政策利率 ----------------

def test_a_policy_rate_that_just_moved_is_an_alert():
    hit, text = sm.alert_foreign_policy_rate(_monthly([0.5] * 12 + [0.75]))
    assert hit
    assert "0.75" in text


def test_a_policy_rate_sitting_still_is_not_an_alert():
    hit, _ = sm.alert_foreign_policy_rate(_monthly([0.5] * 13))
    assert not hit


# ---------------- 接線與紅線 ----------------

def test_all_six_are_scored_in_the_world_layer():
    for key in COUNTRY_KEYS:
        indicator = spec.BY_KEY[key]
        assert indicator.layer == "world", key
        assert key in sm.ALERT_FUNCS, key
        assert indicator.sid in spec.PUBLISH_LAG_DAYS, key


def test_no_foreign_equity_index_is_scored():
    """⚠️ §8：各國市場只進總經層，不對股指評分。"""
    scored_sids = {i.sid for i in spec.SCORED}
    assert not ({"^N225", "^KS11", "^HSI", "000001.SS", "^STOXX50E"} & scored_sids)


# ---------------- 慢來源的容忍度 ----------------

def test_oecd_export_series_are_slow_not_frozen():
    """OECD MEI 的出口序列本來就慢：實測 2026-09-22 最新只到 2026-06（113 天）。

    用每月序列的 75 天容忍去看它，會天天判成「凍結」而永遠缺料 —— 那不是
    來源壞掉，是這條序列的節奏本來就這樣。⚠️ 例外只放寬**這兩個 key**，
    其他每月序列照舊。
    """
    import datetime as dt

    from barometer.domain import freshness

    today = dt.date(2026, 9, 22)
    slow = dt.date(2026, 6, 1)
    for key in ("jp_exports", "kr_exports"):
        assert freshness.assess("每月", slow, today, key=key).usable, key
    assert not freshness.assess("每月", slow, today, key="cpi").usable
    # 放寬不等於永遠不過期：再慢半年還是要被抓出來
    assert not freshness.assess("每月", dt.date(2025, 6, 1), today, key="jp_exports").usable

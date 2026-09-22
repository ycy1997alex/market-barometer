"""第八批 8-5、8-7：工業金屬需求與金油比。

兩項都**看變化不看水位**，而且措辭有紅線：

  - 8-5 ⚠️ 頁面講的是「**工業金屬需求**」，不是商品代碼。在一頁有分數的地方寫
    「銅走弱」，會被讀成這個系統對 `HG=F` 有看法 —— 它沒有，它只是拿銅當需求的讀數。
  - 8-7 ⚠️ 分母（油價）缺料回 `INSUFFICIENT`，**不是回 0、不是拿舊值**。
  - ⚠️ 白銀／白金／鈀一律只進 OBSERVE：白銀同時是工業金屬與避險標的，
    兩種性質混在一起就無法誠實地說成單一讀數。
"""
from __future__ import annotations

from barometer.domain import macro_spec as spec
from barometer.domain import scoring_macro as sm
from barometer.pipeline import run_macro


def _s(values):
    return [(f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", v) for i, v in enumerate(values)]


# ---------------- 8-5 工業金屬需求 ----------------

def test_a_sharp_fall_in_industrial_metal_demand_is_an_alert():
    hit, text = sm.alert_copper(_s([5.0] * 20 + [4.5]))
    assert hit
    assert "工業金屬需求" in text and "門檻" in text
    assert "HG" not in text and "銅" not in text


def test_a_rally_is_not_an_alert():
    hit, text = sm.alert_copper(_s([4.0] * 20 + [5.0]))
    assert not hit
    assert "工業金屬需求" in text


def test_copper_needs_a_full_window():
    assert sm.alert_copper(_s([5.0, 5.1]))[1] == sm.INSUFFICIENT


# ---------------- 8-7 金油比 ----------------

def test_gold_oil_ratio_jumping_is_an_alert():
    hit, text = sm.alert_gold_oil(_s([30.0] * 20 + [39.0]))
    assert hit
    assert "金油比" in text and "門檻" in text


def test_gold_oil_ratio_drifting_is_not_an_alert():
    hit, _ = sm.alert_gold_oil(_s([30.0] * 20 + [31.0]))
    assert not hit


def test_ratio_series_drops_days_whose_denominator_is_missing_or_zero():
    gold = [("2026-09-18", 3600.0), ("2026-09-21", 3610.0), ("2026-09-22", 3620.0)]
    oil = [("2026-09-18", 90.0), ("2026-09-21", 0.0)]

    got = run_macro.ratio_series(gold, oil)

    assert [label for label, _ in got] == ["2026-09-18"]
    assert got[0][1] == 40.0


def test_a_missing_denominator_is_insufficient_not_a_stale_value():
    assert sm.alert_gold_oil([])[1] == sm.INSUFFICIENT


# ---------------- 接線 ----------------

def test_copper_and_gold_oil_are_scored_and_the_rest_only_observed():
    assert spec.BY_KEY["copper"].scored and spec.BY_KEY["gold_oil"].scored
    for key in ("brent", "silver", "platinum", "palladium"):
        assert spec.BY_KEY[key].layer == "observe"
        assert key not in sm.ALERT_FUNCS


def test_precious_metals_never_enter_the_score():
    observe_keys = {i.key for i in spec.OBSERVE}
    assert {"silver", "platinum", "palladium"} <= observe_keys
    scored_keys = {i.key for i in spec.SCORED}
    assert not ({"silver", "platinum", "palladium"} & scored_keys)


def test_page_name_for_copper_does_not_lead_with_the_commodity():
    assert "工業金屬需求" in spec.BY_KEY["copper"].name

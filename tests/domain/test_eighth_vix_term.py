"""第八批 8-3：VIX 期限結構（近月／三個月）。

判定看的是**結構**不是水位：比值 > 1 就是 backwardation（近月比三個月貴），
代表市場在為眼前的事定價。VIX 本身很高但期限結構正常，是另一回事。
"""
from __future__ import annotations

from barometer.domain import macro_spec as spec
from barometer.domain import scoring_macro as sm
from barometer.pipeline import run_macro


def _s(values):
    return [(f"2026-09-{i + 1:02d}", v) for i, v in enumerate(values)]


def test_backwardation_is_an_alert():
    hit, text = sm.alert_vix_term(_s([0.9, 1.08]))
    assert hit
    assert "1.080" in text and "backwardation" in text


def test_normal_term_structure_is_not_an_alert():
    hit, text = sm.alert_vix_term(_s([0.85]))
    assert not hit
    assert sm.INSUFFICIENT not in text


def test_missing_series_is_insufficient():
    assert sm.alert_vix_term([])[1] == sm.INSUFFICIENT


def test_ratio_only_uses_days_both_sources_have():
    vix = [("2026-09-17", 18.0), ("2026-09-18", 20.0), ("2026-09-21", 22.0)]
    vix3m = [("2026-09-18", 18.24), ("2026-09-21", 18.08), ("2026-09-22", 18.0)]

    got = run_macro.vix_term_series(vix, vix3m)

    assert [label for label, _ in got] == ["2026-09-18", "2026-09-21"]
    assert round(got[-1][1], 4) == round(22.0 / 18.08, 4)


def test_a_zero_denominator_drops_the_day_instead_of_dividing():
    got = run_macro.vix_term_series([("2026-09-21", 22.0)], [("2026-09-21", 0.0)])
    assert got == []


def test_indicator_is_wired_and_sourced_from_cboe():
    indicator = spec.BY_KEY["vix_term"]
    assert indicator.scored
    assert "CBOE" in indicator.note or "cboe" in indicator.source
    assert "vix_term" in sm.ALERT_FUNCS
    assert indicator.sid in spec.PUBLISH_LAG_DAYS

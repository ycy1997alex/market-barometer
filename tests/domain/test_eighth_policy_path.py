"""第八批 8-4：Fed Funds 期貨隱含的政策路徑。

隱含利率 = `100 − 報價`，跟現行的 `DFEDTARU` 上限相減，得到「市場定價比現在低／高幾碼」。

⚠️ **文字一律用「市場定價的政策路徑」，不准出現「預期降息機率」。**
期貨價格給的是一個定價，不是一個機率分布 —— 把它講成機率，等於憑空多出一個
沒有計算過的東西。
"""
from __future__ import annotations

from barometer.domain import macro_spec as spec
from barometer.domain import scoring_macro as sm
from barometer.pipeline import run_macro


def _s(values):
    return [(f"2026-09-{i + 1:02d}", v) for i, v in enumerate(values)]


def test_a_gap_of_one_full_cut_is_an_alert():
    hit, text = sm.alert_policy_path(_s([-0.05, -0.30]))
    assert hit
    assert "市場定價" in text and "機率" not in text


def test_a_small_gap_is_not_an_alert():
    hit, text = sm.alert_policy_path(_s([-0.05]))
    assert not hit
    assert "機率" not in text


def test_missing_series_is_insufficient():
    assert sm.alert_policy_path([])[1] == sm.INSUFFICIENT


def test_implied_rate_is_a_hundred_minus_the_quote_and_gap_uses_the_standing_target():
    futures = [("2026-09-21", 95.985), ("2026-09-22", 95.75)]
    target = [("2026-03-20", 4.50), ("2026-09-18", 4.25)]

    got = run_macro.policy_path_series(futures, target)

    assert [label for label, _ in got] == ["2026-09-21", "2026-09-22"]
    assert round(got[0][1], 3) == round((100 - 95.985) - 4.25, 3)
    assert round(got[1][1], 3) == round((100 - 95.75) - 4.25, 3)


def test_days_before_any_published_target_are_dropped():
    got = run_macro.policy_path_series([("2026-01-05", 95.9)], [("2026-03-20", 4.5)])
    assert got == []


def test_no_module_talks_about_rate_cut_probability():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "barometer"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "降息機率" not in node.value, path
                assert "升息機率" not in node.value, path


def test_indicator_is_wired():
    indicator = spec.BY_KEY["policy_path"]
    assert indicator.scored
    assert "policy_path" in sm.ALERT_FUNCS
    assert indicator.sid in spec.PUBLISH_LAG_DAYS

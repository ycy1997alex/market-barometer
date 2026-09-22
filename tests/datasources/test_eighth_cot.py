"""第八批 8-11：CFTC COT 只當觀測項。

⚠️ **不評分、不算百分位、不加解讀文字。**
「非商業淨多 +12,345 口，週變化 −3,210 口」這句話不需要任何額外的字，
讀的人自己就知道要怎麼看。加上「處於歷史高檔」「顯示樂觀情緒」都是在替讀者下判斷。
"""
from __future__ import annotations

import datetime as dt

from barometer.datasources import cftc_src
from barometer.domain import macro_spec as spec
from barometer.domain import scoring_macro as sm

PAYLOAD = [
    {"report_date_as_yyyy_mm_dd": "2026-09-15T00:00:00.000",
     "noncomm_positions_long_all": "240290", "noncomm_positions_short_all": "340751",
     "change_in_noncomm_long_all": "1200", "change_in_noncomm_short_all": "-800"},
    {"report_date_as_yyyy_mm_dd": "2026-09-08T00:00:00.000",
     "noncomm_positions_long_all": "239090", "noncomm_positions_short_all": "341551",
     "change_in_noncomm_long_all": "-300", "change_in_noncomm_short_all": "500"},
]


def test_net_position_is_long_minus_short_oldest_first():
    got = cftc_src.parse_report(PAYLOAD)
    assert [label for label, _ in got] == ["2026-09-08", "2026-09-15"]
    assert got[-1][1] == 240290 - 340751


def test_weekly_change_comes_from_the_official_change_columns():
    assert cftc_src.weekly_change(PAYLOAD) == 1200 - (-800)


def test_rows_missing_a_position_are_dropped_not_zero_filled():
    payload = PAYLOAD + [{"report_date_as_yyyy_mm_dd": "2026-09-22T00:00:00.000",
                          "noncomm_positions_long_all": "", "noncomm_positions_short_all": "1"}]
    assert len(cftc_src.parse_report(payload)) == 2


def test_an_empty_payload_is_an_error_not_an_empty_series():
    import pytest

    from barometer.datasources.base import FetchError

    with pytest.raises(FetchError):
        cftc_src.parse_report([])


def test_data_date_is_the_latest_report():
    assert cftc_src.data_date(cftc_src.parse_report(PAYLOAD)) == dt.date(2026, 9, 15)


# ---------------- 紅線 ----------------

def test_cot_indicators_are_observe_only():
    for key in ("cot_spx", "cot_gold", "cot_wti"):
        indicator = spec.BY_KEY[key]
        assert indicator.layer == "observe", key
        assert key not in sm.ALERT_FUNCS, key
        assert indicator.key not in {i.key for i in spec.SCORED}


def test_no_percentile_or_interpretation_is_computed_for_cot():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(cftc_src.__file__).read_text(encoding="utf-8"))
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert not any("percentile" in name or "rank" in name for name in names)

    # 模組 docstring 講的是這條規則本身，不會流到頁面上 —— 守的是其他字串常數。
    doc_node = (tree.body[0].value
                if tree.body and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Constant) else None)
    banned = ("百分位", "樂觀", "悲觀", "高檔", "低檔", "偏多", "偏空")
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if node is doc_node:
            continue
        for word in banned:
            assert word not in node.value, (word, node.value[:40])

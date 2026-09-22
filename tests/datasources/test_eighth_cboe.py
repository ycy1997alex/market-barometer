"""第八批 8-3：VIX 期限結構要走 CBOE 官方 CSV。

⚠️ **不留 Yahoo fallback。** Yahoo 的 `^VIX3M` 已經凍結，留著當退路的意思是
「平常用官方的，壞掉時安靜地改用一條不會動的序列」—— 那比直接缺料還糟。
"""
from __future__ import annotations

import datetime as dt

from barometer.datasources import cboe_src

CSV = (
    "DATE,OPEN,HIGH,LOW,CLOSE\n"
    "09/17/2026,18.500000,18.770000,18.480000,18.550000\n"
    "09/18/2026,18.470000,18.710000,18.220000,18.240000\n"
    "09/21/2026,18.080000,18.180000,17.960000,18.080000\n"
)


def test_parses_the_american_date_format_into_iso_ordered_oldest_first():
    got = cboe_src.parse_history(CSV)
    assert got == [("2026-09-17", 18.55), ("2026-09-18", 18.24), ("2026-09-21", 18.08)]


def test_rows_without_a_usable_close_are_dropped_not_zero_filled():
    text = CSV + "09/22/2026,18.0,18.0,18.0,\n"
    assert [label for label, _ in cboe_src.parse_history(text)] == [
        "2026-09-17", "2026-09-18", "2026-09-21"]


def test_an_empty_payload_is_an_error_not_an_empty_series():
    import pytest

    from barometer.datasources.base import FetchError

    with pytest.raises(FetchError):
        cboe_src.parse_history("DATE,OPEN,HIGH,LOW,CLOSE\n")


def test_tail_keeps_the_newest_rows():
    assert len(cboe_src.parse_history(CSV, tail=2)) == 2
    assert cboe_src.parse_history(CSV, tail=2)[0][0] == "2026-09-18"


def test_no_module_falls_back_to_the_frozen_yahoo_ticker():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "barometer"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value.strip() in ("^VIX3M", "VIX3M=X")
            for node in ast.walk(tree)
        ), path


def test_data_date_is_the_last_row():
    assert cboe_src.data_date(cboe_src.parse_history(CSV)) == dt.date(2026, 9, 21)

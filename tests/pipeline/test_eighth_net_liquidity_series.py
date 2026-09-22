"""第八批 8-1：淨流動性是兩條 FRED 序列相減，單位不同。

⚠️ `WALCL` 的單位是**百萬美元**（6,746,548 = 6.75 兆），`RRPONTSYD` 是**十億美元**
（0.582 = 5.8 億）。直接相減會得到一個差了一千倍、但看起來很正常的數字。
"""
from __future__ import annotations

from barometer.pipeline import run_macro


def test_walcl_is_converted_to_billions_before_subtracting_rrp():
    walcl = [("2026-09-09", 6_740_619.0), ("2026-09-16", 6_746_548.0)]
    rrp = [("2026-09-09", 10.0), ("2026-09-16", 20.0)]

    got = run_macro.net_liquidity_series(walcl, rrp)

    assert got == [("2026-09-09", 6730.619), ("2026-09-16", 6726.548)]


def test_weekly_walcl_takes_the_most_recent_rrp_on_or_before_that_day():
    """WALCL 是週三一筆，RRP 是每個營業日一筆 —— 對不到當天就往前找最近的一筆。"""
    walcl = [("2026-09-16", 6_746_548.0)]
    rrp = [("2026-09-14", 5.0), ("2026-09-15", 7.0)]

    assert run_macro.net_liquidity_series(walcl, rrp) == [("2026-09-16", 6739.548)]


def test_a_walcl_row_with_no_earlier_rrp_is_dropped_not_guessed():
    walcl = [("2026-09-02", 6_737_204.0), ("2026-09-16", 6_746_548.0)]
    rrp = [("2026-09-10", 1.0)]

    got = run_macro.net_liquidity_series(walcl, rrp)

    assert [label for label, _ in got] == ["2026-09-16"]

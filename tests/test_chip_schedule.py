"""籌碼面分兩班抓（作者 2026-09-07 提供的實際公布時間）。

  三大法人 T86     約 17:30 更新完  → 18:00 那班抓得到
  融資融券 MI_MARGN 約 21:30 更新完（可能更晚）→ 18:00 抓不到，改 22:30 再抓

所以 18:00 那一班**刻意不抓融資融券** —— 不是抓了失敗，是根本不去問。
少打一次註定落空的請求，run log 也不會每天多一筆假的失敗（§6）。

22:30 那一班只補融資融券，而且必須**併進**當天已經存在的那一列，
不能覆寫掉 18:00 已經寫好的三大法人與台指期。
"""
from __future__ import annotations

import datetime as dt

from barometer.pipeline import run_chips

D = dt.date(2026, 9, 7)


def test_evening_shift_skips_margin():
    assert "margin" not in run_chips.EVENING_PARTS
    assert {"t86", "futures", "pcratio"} <= set(run_chips.EVENING_PARTS)


def test_late_shift_only_fetches_margin():
    assert run_chips.LATE_PARTS == ("margin",)


def test_the_two_shifts_together_cover_everything():
    assert set(run_chips.EVENING_PARTS) | set(run_chips.LATE_PARTS) == set(
        run_chips.ALL_PARTS
    )


def test_shifts_do_not_overlap():
    """重疊的話 22:30 會白打一次 17:30 就抓好的東西。"""
    assert not set(run_chips.EVENING_PARTS) & set(run_chips.LATE_PARTS)


# ---------------- 合併，不覆寫 ----------------

def test_merge_keeps_what_the_earlier_shift_wrote():
    existing = {"total_net_shares": 577_637_662,
                "fut_foreign_net_oi_contracts": -82_389}
    incoming = {"margin_lots": 8_919_251, "short_lots": 219_160}
    merged = run_chips.merge_payload(existing, incoming)
    assert merged["total_net_shares"] == 577_637_662
    assert merged["fut_foreign_net_oi_contracts"] == -82_389
    assert merged["margin_lots"] == 8_919_251


def test_merge_lets_the_later_shift_correct_an_earlier_value():
    """同一個 key 由後來的那一班覆寫 —— 融資的今日餘額本來就會被改。"""
    merged = run_chips.merge_payload({"margin_lots": 1}, {"margin_lots": 2})
    assert merged["margin_lots"] == 2


def test_merge_ignores_none_so_a_failed_fetch_cannot_erase_a_good_value():
    """抓失敗回 None，不能把昨天寫好的值洗掉。"""
    merged = run_chips.merge_payload({"margin_lots": 8_919_251},
                                     {"margin_lots": None})
    assert merged["margin_lots"] == 8_919_251


def test_merge_on_an_empty_day_just_takes_the_new_payload():
    assert run_chips.merge_payload({}, {"margin_lots": 5}) == {"margin_lots": 5}


def test_merge_does_not_mutate_the_inputs():
    a, b = {"x": 1}, {"y": 2}
    run_chips.merge_payload(a, b)
    assert a == {"x": 1} and b == {"y": 2}

"""融資融券（TWSE MI_MARGN）的解析（ToDo §9 Day 26 第 2 項）。

驗收句：「單位標對、且非交易日拿到空 CSV 時當『這天還沒有』而不是 0」。
這裡把它翻成三組測試：

1. **單位**：MI_MARGN 的「交易單位」是**張**，不是股 —— 而 T86 的買賣超是**股**。
   同一天的兩份盤後資料，單位不同，這是既有專案踩過的坑（§10 張／股）。
2. **前日餘額才是定稿**：TWSE 自己在備註寫「請以『前日餘額』為準，而以
   『今日餘額』為輔助參考資料」。所以 D 這天抓到的「今日餘額」是暫定的，
   D 的定稿要等 D+1 的「前日餘額」。這件事不寫成程式就會被忘掉。
3. **沒資料的長相**：TWSE 回的不是空字串，是「很抱歉，沒有符合條件的資料」
   這一句中文 —— 判成「還沒公布」，不是 0。

用錄下來的回應，不打真的 API（§3.3）。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from barometer.datasources import twse_src

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_margin_and_short_in_lots():
    """交易單位是張。數值直接對錄下來的那一天。"""
    r = twse_src.parse_margin(
        _fixture("twse_margin_20260904.csv"), dt.date(2026, 9, 4)
    )

    assert r.date == dt.date(2026, 9, 4)
    assert r.unit == "張"
    # 融資(交易單位)：前日餘額 8,902,986 / 今日餘額 8,919,251
    assert r.margin_prev_lots == pytest.approx(8_902_986)
    assert r.margin_today_lots == pytest.approx(8_919_251)
    # 融券(交易單位)：前日餘額 222,843 / 今日餘額 219,160
    assert r.short_prev_lots == pytest.approx(222_843)
    assert r.short_today_lots == pytest.approx(219_160)
    # 融資金額(仟元)
    assert r.margin_today_ktwd == pytest.approx(581_894_588)


def test_today_balance_is_provisional_and_previous_is_final():
    """§10：TWSE 自己說以『前日餘額』為準。程式要把這個差別講出來。"""
    r = twse_src.parse_margin(
        _fixture("twse_margin_20260904.csv"), dt.date(2026, 9, 4)
    )

    # 今日餘額屬於當天，但是暫定值
    assert r.provisional_for == dt.date(2026, 9, 4)
    assert r.provisional_margin_lots == pytest.approx(8_919_251)

    # 前日餘額才是定稿，而且它屬於**前一個交易日**，不是當天
    assert r.final_for is not None
    assert r.final_for < r.date
    assert r.final_margin_lots == pytest.approx(8_902_986)


def test_no_data_message_is_not_published_yet_not_zero():
    """「很抱歉，沒有符合條件的資料」→ 還沒公布，不是餘額歸零。"""
    with pytest.raises(twse_src.NotPublishedYet):
        twse_src.parse_margin(
            _fixture("twse_margin_20260906_empty.csv"), dt.date(2026, 9, 6)
        )


def test_blank_response_is_not_published_yet():
    with pytest.raises(twse_src.NotPublishedYet):
        twse_src.parse_margin("", dt.date(2026, 9, 6))


def test_margin_lots_convert_to_shares_only_at_the_boundary():
    """張→股的換算只有一個入口，資料層拿到的仍是張。"""
    r = twse_src.parse_margin(
        _fixture("twse_margin_20260904.csv"), dt.date(2026, 9, 4)
    )
    assert r.margin_today_shares == pytest.approx(8_919_251 * 1000)

"""總經序列的「該不該更新了」判定（ToDo §9 Day 28 第 2 項）。

驗收句：**「能證明『真的沒更新』與『突然更新了』是兩種不同的判定，各給一個實例」**。

這一條看起來瑣碎，其實是 §10 那個央行 bug 的一般化：

  > 央行那張表是**歷次調整紀錄**，相鄰兩列的值必然不同（不然不會被記成一次
  > 調整），拿值去比會**永遠亮燈**。

所以判定必須分成三種狀態，而不是「有沒有變」這個二分：

    ON_TIME     還沒到下次公布時間 —— 沒更新是正常的，不必看
    OVERDUE     早該公布了還沒動 —— 這才是「真的沒更新」，要警示
    UNEXPECTED  不該公布的時候動了 —— 「突然更新了」，也要警示

拿更新頻率當節拍器，而不是拿「值有沒有變」。頻率是已知的（CPI 每月、
利差每日、央行不定期），所以「該不該有新的」是算得出來的。
"""
from __future__ import annotations

import datetime as dt

from barometer.domain import freshness

D = dt.date
TODAY = D(2026, 9, 7)


def test_daily_series_updated_yesterday_is_on_time():
    s = freshness.assess("每日", data_date=D(2026, 9, 4), today=TODAY,
                         previous_data_date=D(2026, 9, 3))
    assert s.state == freshness.ON_TIME


def test_daily_series_stuck_for_two_weeks_is_overdue():
    """「真的沒更新」的實例。"""
    s = freshness.assess("每日", data_date=D(2026, 8, 20), today=TODAY,
                         previous_data_date=D(2026, 8, 20))
    assert s.state == freshness.OVERDUE
    assert "18" in s.reason or "天" in s.reason


def test_monthly_series_one_month_behind_is_on_time():
    """CPI 標 7 月、今天 9/7 —— 月頻本來就有一到兩個月的落差，不是壞掉。"""
    s = freshness.assess("每月", data_date=D(2026, 7, 1), today=TODAY,
                         previous_data_date=D(2026, 6, 1))
    assert s.state == freshness.ON_TIME


def test_monthly_series_half_a_year_behind_is_overdue():
    s = freshness.assess("每月", data_date=D(2026, 2, 1), today=TODAY,
                         previous_data_date=D(2026, 1, 1))
    assert s.state == freshness.OVERDUE


def test_quarterly_series_is_allowed_to_lag_a_lot():
    s = freshness.assess("每季", data_date=D(2026, 4, 1), today=TODAY,
                         previous_data_date=D(2026, 1, 1))
    assert s.state == freshness.ON_TIME


def test_irregular_series_never_goes_overdue():
    """央行重貼現率停在 2024-03-22、距今 898 天 —— **正確結果是不警示**。

    §10：那張表是歷次調整紀錄，拿「值有沒有變」去比會永遠亮燈；
    拿「多久沒動」去比又會把「政策就是沒動」當成故障。不定期就是不定期。
    """
    s = freshness.assess("不定期", data_date=D(2024, 3, 22), today=TODAY,
                         previous_data_date=D(2023, 3, 23))
    assert s.state == freshness.ON_TIME
    assert "不定期" in s.reason


def test_irregular_series_moving_is_the_newsworthy_event():
    """「突然更新了」的實例 —— 不定期序列動了，那本身就是事件。"""
    s = freshness.assess("不定期", data_date=TODAY, today=TODAY,
                         previous_data_date=D(2024, 3, 22))
    assert s.state == freshness.UNEXPECTED
    assert "898" in s.reason or "距上一次" in s.reason


def test_monthly_series_updating_twice_in_a_week_is_unexpected():
    """月頻序列一週內動兩次 —— 可能是修正，可能是抓錯，總之要有人看一眼。"""
    s = freshness.assess("每月", data_date=D(2026, 9, 5), today=TODAY,
                         previous_data_date=D(2026, 9, 1))
    assert s.state == freshness.UNEXPECTED


def test_no_data_at_all_is_its_own_state():
    s = freshness.assess("每日", data_date=None, today=TODAY,
                         previous_data_date=None)
    assert s.state == freshness.NO_DATA
    assert s.state != freshness.OVERDUE   # 沒抓過 ≠ 早該更新沒更新


def test_the_two_alert_states_are_distinguishable():
    """驗收句的字面要求：兩種判定必須是**不同的**，不是同一個旗標。"""
    overdue = freshness.assess("每日", data_date=D(2026, 8, 20), today=TODAY,
                               previous_data_date=D(2026, 8, 20))
    unexpected = freshness.assess("不定期", data_date=TODAY, today=TODAY,
                                  previous_data_date=D(2024, 3, 22))
    assert overdue.state != unexpected.state
    assert overdue.needs_attention and unexpected.needs_attention


def test_scan_sorts_the_ones_needing_attention_first():
    rows = [
        ("t10y2y", "每日", D(2026, 9, 4), D(2026, 9, 3)),
        ("cbc_rate", "不定期", D(2024, 3, 22), D(2023, 3, 23)),
        ("vix", "每日", D(2026, 8, 20), D(2026, 8, 20)),
    ]
    got = freshness.scan(rows, today=TODAY)
    assert got[0].key == "vix"
    assert got[0].needs_attention
    assert not got[-1].needs_attention


# ---------------- 預期下次更新時間（作者 2026-09-07 要求） ----------------

def test_daily_series_is_expected_again_the_next_day():
    assert freshness.next_expected("每日", D(2026, 9, 4)) == D(2026, 9, 5)


def test_monthly_series_is_expected_a_month_later():
    """CPI 標 7/1，下一筆是 8/1 —— 但**公布**還會再晚一段，見 is_due。"""
    assert freshness.next_expected("每月", D(2026, 7, 1)) == D(2026, 8, 1)


def test_quarterly_series_is_expected_a_quarter_later():
    nxt = freshness.next_expected("每季", D(2026, 4, 1))
    assert nxt.year == 2026 and nxt.month == 7


def test_irregular_series_has_no_expected_next_time():
    """央行什麼時候調利率沒有人知道 —— 回 None，不要編一個日期出來。"""
    assert freshness.next_expected("不定期", D(2024, 3, 22)) is None


def test_never_fetched_series_is_always_due():
    assert freshness.is_due("每日", None, today=TODAY) is True


def test_series_updated_today_is_not_due():
    assert freshness.is_due("每日", D(2026, 9, 7), today=TODAY) is False


def test_daily_series_from_three_days_ago_is_due():
    assert freshness.is_due("每日", D(2026, 9, 4), today=TODAY) is True


def test_monthly_series_is_not_due_the_day_after_its_data_date():
    """月頻資料標 9/1 不代表 9/2 就該有下一筆 —— 下一筆是十月的事。"""
    assert freshness.is_due("每月", D(2026, 9, 1), today=TODAY) is False


def test_monthly_series_two_months_stale_is_due():
    assert freshness.is_due("每月", D(2026, 6, 1), today=TODAY) is True


def test_irregular_series_is_due_on_a_slow_cadence_not_never():
    """不定期不能永遠不抓 —— 不然真的調息了也不會知道。

    但也不必每天問：用一個慢節奏（預設一週）去掃就夠了。
    """
    assert freshness.is_due("不定期", D(2026, 9, 6), today=TODAY) is False
    assert freshness.is_due("不定期", D(2026, 8, 1), today=TODAY) is True


def test_due_keys_picks_only_the_ones_that_need_fetching():
    rows = [
        ("t10y2y", "每日", D(2026, 9, 4)),
        ("vix", "每日", D(2026, 9, 7)),
        ("cpi", "每月", D(2026, 7, 1)),
        ("cbc_rate", "不定期", D(2024, 3, 22)),
    ]
    due = freshness.due_keys(rows, today=TODAY)
    assert "t10y2y" in due       # 日頻停在 9/4
    assert "vix" not in due      # 今天剛更新
    assert "cbc_rate" in due     # 不定期，很久沒掃了

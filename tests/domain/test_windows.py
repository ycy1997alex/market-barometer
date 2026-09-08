"""交易日視窗與跨市場對齊（ToDo §10「2026-09-07 美股休市」、§9 Day 28）。

§10 對這個坑的處置只有一句：**「任何假設兩市場日期對齊的程式碼都會在這裡
錯位 —— 寫成測試」**。這支就是那個測試。

2026 年九月的第一個星期一是 9/7，美國勞動節，NYSE 不開盤，台股照常。所以：

    台股五個交易日：9/4、9/7、9/8、9/9、9/10
    美股五個交易日：9/3、9/4、9/8、9/9、9/10   ← 回推到 9/3 才滿五天

兩組**錯開一天、中間缺一天**。

還有一件更容易錯的事：對照分析時「台股 9/8 對到美股哪一天」。答案是 **9/4**，
不是 9/7（那天沒開），也不是 9/8 —— 台股 13:30 收盤時，美股 9/8 那一場
還沒開始。台股某一天面對的是**嚴格早於它**的那一場美股收盤。

這裡刻意不維護交易日曆（§1 第 6 條）—— 交易日就是「資料裡有這一天」，
勞動節不需要任何特判就自動被處理掉。
"""
from __future__ import annotations

import datetime as dt

from barometer.domain import windows

D = dt.date

# 實際落在資料裡的日期（回溯視窗前後各多帶幾天）
TW_SESSIONS = [D(2026, 9, 1), D(2026, 9, 2), D(2026, 9, 3), D(2026, 9, 4),
               D(2026, 9, 7), D(2026, 9, 8), D(2026, 9, 9), D(2026, 9, 10)]
US_SESSIONS = [D(2026, 9, 1), D(2026, 9, 2), D(2026, 9, 3), D(2026, 9, 4),
               D(2026, 9, 8), D(2026, 9, 9), D(2026, 9, 10)]  # 9/7 勞動節休市


def test_last_five_sessions_taiwan():
    assert windows.last_n_sessions(TW_SESSIONS, 5) == [
        D(2026, 9, 4), D(2026, 9, 7), D(2026, 9, 8), D(2026, 9, 9), D(2026, 9, 10)
    ]


def test_last_five_sessions_us_reaches_further_back():
    """美股少了 9/7，所以同樣五天要回推到 9/3。"""
    assert windows.last_n_sessions(US_SESSIONS, 5) == [
        D(2026, 9, 3), D(2026, 9, 4), D(2026, 9, 8), D(2026, 9, 9), D(2026, 9, 10)
    ]


def test_the_two_windows_are_not_the_same_dates():
    """這一條就是 §10 那個坑本身 —— 拿日期直接對齊會錯位。"""
    tw = windows.last_n_sessions(TW_SESSIONS, 5)
    us = windows.last_n_sessions(US_SESSIONS, 5)
    assert len(tw) == len(us) == 5
    assert tw != us
    assert set(tw) - set(us) == {D(2026, 9, 7)}
    assert set(us) - set(tw) == {D(2026, 9, 3)}


def test_window_shorter_than_requested_returns_what_there_is():
    """SPCX 那種上市不久的標的：給幾天算幾天，不補、不假裝。"""
    assert windows.last_n_sessions([D(2026, 9, 9), D(2026, 9, 10)], 5) == [
        D(2026, 9, 9), D(2026, 9, 10)
    ]


def test_empty_input_is_empty_window():
    assert windows.last_n_sessions([], 5) == []


def test_unsorted_input_is_sorted_first():
    assert windows.last_n_sessions([D(2026, 9, 10), D(2026, 9, 4), D(2026, 9, 9)], 2) == [
        D(2026, 9, 9), D(2026, 9, 10)
    ]


# ---------------- 跨市場對照 ----------------

def test_taiwan_0908_faces_the_us_close_of_0904():
    """§9 Day 28：9/8 台股對到的是美股 9/4 的收盤，不是 9/7。"""
    assert windows.preceding_session(D(2026, 9, 8), US_SESSIONS) == D(2026, 9, 4)


def test_taiwan_0907_also_faces_0904():
    """9/7 當天美股根本沒開 —— 台股面對的仍然是 9/4。"""
    assert windows.preceding_session(D(2026, 9, 7), US_SESSIONS) == D(2026, 9, 4)


def test_preceding_session_is_strictly_earlier():
    """同一天不算 —— 台股 13:30 收盤時，當天的美股還沒開始。"""
    assert windows.preceding_session(D(2026, 9, 9), US_SESSIONS) == D(2026, 9, 8)


def test_preceding_session_before_all_data_is_none():
    assert windows.preceding_session(D(2026, 9, 1), US_SESSIONS) is None


def test_pair_window_maps_every_taiwan_day():
    pairs = windows.pair_sessions(
        windows.last_n_sessions(TW_SESSIONS, 5), US_SESSIONS
    )
    assert pairs == [
        (D(2026, 9, 4), D(2026, 9, 3)),
        (D(2026, 9, 7), D(2026, 9, 4)),
        (D(2026, 9, 8), D(2026, 9, 4)),   # ← 兩天對到同一場美股收盤
        (D(2026, 9, 9), D(2026, 9, 8)),
        (D(2026, 9, 10), D(2026, 9, 9)),
    ]


def test_pair_window_can_map_two_days_to_the_same_session():
    """勞動節的直接後果：9/7 與 9/8 兩天台股，面對的是同一場美股收盤。

    任何「一天對一天」的假設在這裡就會壞掉。
    """
    pairs = dict(
        windows.pair_sessions(
            windows.last_n_sessions(TW_SESSIONS, 5), US_SESSIONS
        )
    )
    assert pairs[D(2026, 9, 7)] == pairs[D(2026, 9, 8)]

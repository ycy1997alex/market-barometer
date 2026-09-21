"""交易日視窗與跨市場對齊（ToDo §10、§9 Day 28）。純函式、零 I/O。

**這裡沒有交易日曆，而且刻意不要有**（§1 第 6 條）。交易日的定義就是
「資料裡有這一天」—— 颱風假、美國假期、資料延遲全都自動被處理掉，不必為了
2026 年的勞動節寫一條特判，明年也不必再維護一次。

代價是：沒抓到資料的那天，跟真的沒開盤的那天，在這一層長得一樣。這是接受的
取捨，因為兩者的處置相同（§10「空 CSV 一律當『這天還沒有』」）。

**兩個市場的日期不會對齊。** 2026-09-07 是美國勞動節，NYSE 休市而台股照常，
所以同樣是「最近五個交易日」，台股是 9/4–9/10、美股要回推到 9/3。任何假設兩
市場日期對齊的程式碼都會在這裡錯位 —— 所以對齊這件事集中在這個模組，
由 tests/domain/test_windows.py 守著。
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo


def latest_complete_us_date(now_utc: dt.datetime | None = None) -> dt.date:
    """NYSE daily bars are provisional until 16:30 New York time."""
    moment = now_utc or dt.datetime.now(dt.timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    local = moment.astimezone(ZoneInfo("America/New_York"))
    if local.time() < dt.time(16, 30):
        return local.date() - dt.timedelta(days=1)
    return local.date()


def last_n_sessions(dates: list[dt.date], n: int = 5) -> list[dt.date]:
    """最近 n 個交易日，由舊到新。

    不足 n 天就給有幾天算幾天 —— **不補、不外推**。SPCX 那種上市不久的標的
    本來就只有這麼多天，補出來的日期會讓後面每一個加權都是假的（§10）。
    """
    if not dates:
        return []
    return sorted(set(dates))[-n:]


def missing_sessions(
    dates: list[dt.date], reference: list[dt.date]
) -> list[dt.date]:
    """`reference` 有、`dates` 沒有，而且落在 `dates` 自己涵蓋範圍內的交易日。

    參考基準刻意是「同一批其他標的的聯集」，不是交易日曆 —— 這個專案不維護
    交易日曆（颱風假、臨時休市、資料延遲都會讓它過期）。同一批裡別人有、
    我沒有，本身就是夠強的訊號。

    **限定在自己的涵蓋範圍內**，否則歷史比較短的標的會把它上市之前的每一天
    都報成缺漏 —— SPCX 只有 67 根，同一批的 NVDA 有 251 根，那不是洞。

    呼叫端要自己先分市場。台股與美股的交易日不對齊（2026-09-07 美國勞動節
    台股照常），混在一起比會讓每一檔都亮燈。
    """
    if not dates:
        return []
    have = set(dates)
    lo, hi = min(dates), max(dates)
    return sorted(d for d in set(reference) if lo <= d <= hi and d not in have)


def preceding_session(day: dt.date, other_sessions: list[dt.date]) -> dt.date | None:
    """`day` 這一天，另一個市場**最近一場已經收完**的交易日。

    「嚴格早於」是重點，不是「早於或等於」：台股 13:30 收盤的時候，當天的
    美股連開都還沒開（美股 21:30 台北時間才開）。用 `<=` 會讓台股某一天對到
    一場當時還不存在的收盤 —— 那種錯不會報錯，只會安靜地產生一組看起來很
    合理的對照數字。

    回 None 代表另一個市場在那之前沒有任何資料，不是 0、也不是「同一天」。
    """
    earlier = [d for d in other_sessions if d < day]
    return max(earlier) if earlier else None


def pair_sessions(
    days: list[dt.date], other_sessions: list[dt.date]
) -> list[tuple[dt.date, dt.date | None]]:
    """把一個市場的交易日逐日對到另一個市場的前一場收盤。

    **兩天對到同一場是正常的**，不是 bug —— 2026 年 9/7 勞動節之後，台股
    9/7 與 9/8 面對的都是美股 9/4 的收盤。任何「一天對一天」的假設在這裡壞掉。
    """
    return [(d, preceding_session(d, other_sessions)) for d in days]

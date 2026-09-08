"""總經序列的「該不該更新了」判定（ToDo §9 Day 28 第 2 項）。純函式、零 I/O。

**拿更新頻率當節拍器，不要拿「值有沒有變」。**

這條規則是 §10 那個央行 bug 的一般化。當時的錯是：央行重貼現率那張表是**歷次
調整紀錄**，相鄰兩列的值必然不同（不然不會被記成一次調整），所以拿值去比會
永遠亮燈。而且那個 bug 靠實資料才發現 —— 單元測試當初照著錯誤理解寫，一起錯。

所以判定不是「有沒有變」這個二分，是四種狀態：

    ON_TIME     還沒到下次公布時間 —— 沒更新是正常的
    OVERDUE     早該公布了還沒動 —— 這是「**真的**沒更新」
    UNEXPECTED  不該公布的時候動了 —— 這是「**突然**更新了」
    NO_DATA     從來沒抓到過 —— 跟「早該更新沒更新」是兩回事

頻率是已知的（CPI 每月、利差每日、央行不定期），所以「該不該有新的」算得出來。

**不定期永遠不會 OVERDUE。** 央行停在 2024-03-22、距今 898 天，正確結果是
不警示 —— 政策就是沒動，那不是故障。但它**動了**的時候要標 UNEXPECTED，
因為對一條兩年沒動的序列來說，動本身就是事件。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

ON_TIME = "on_time"
OVERDUE = "overdue"
UNEXPECTED = "unexpected"
NO_DATA = "no_data"

IRREGULAR = "不定期"

# 各頻率「幾天內有新的算正常」。給的是寬鬆值，不是理論間隔 ——
# 日頻放到 10 天是因為連假加上資料延遲很容易疊到一週以上，
# 而誤報一次的代價（下次就沒人看了）比晚三天發現高。
TOLERANCE_DAYS: dict[str, int] = {
    "每日": 10,
    "每週": 21,
    "每月": 75,
    "每季": 200,
}

# 「動得太頻繁」的下限：低於這個間隔就是 UNEXPECTED
MIN_INTERVAL_DAYS: dict[str, int] = {
    "每日": 0,
    "每週": 3,
    "每月": 20,
    "每季": 60,
}

# 不定期序列「多久沒動才算久」—— 久違地動了一次就值得注意
IRREGULAR_QUIET_DAYS = 180

# 各頻率「下一筆預期落在幾天／幾個月之後」。給自動更新用的節拍。
NEXT_AFTER_DAYS: dict[str, int] = {"每日": 1, "每週": 7}
NEXT_AFTER_MONTHS: dict[str, int] = {"每月": 1, "每季": 3}

# 不定期沒有預期時間，但也不能永遠不掃 —— 不然真的調息了也不會知道。
# 一週掃一次：夠快到不會漏掉，也慢到不會天天浪費一次請求。
IRREGULAR_SCAN_DAYS = 7


@dataclass(frozen=True, slots=True)
class Freshness:
    key: str
    state: str
    reason: str

    @property
    def needs_attention(self) -> bool:
        return self.state in (OVERDUE, UNEXPECTED)


def assess(
    freq: str,
    data_date: dt.date | None,
    today: dt.date,
    previous_data_date: dt.date | None = None,
    key: str = "",
) -> Freshness:
    """判定一條序列的新鮮度。

    `previous_data_date` 是**上一次**的資料日期 —— 沒有它就分不出
    「這條序列本來就是這個節奏」與「它剛剛動了」。
    """
    if data_date is None:
        return Freshness(key, NO_DATA, "從來沒有抓到過（不是早該更新沒更新）")

    lag = (today - data_date).days

    if freq == IRREGULAR:
        # 不定期永遠不會 OVERDUE —— 沒動不代表壞掉
        if previous_data_date is not None:
            gap = (data_date - previous_data_date).days
            if lag <= 3 and gap >= IRREGULAR_QUIET_DAYS:
                return Freshness(
                    key, UNEXPECTED,
                    f"不定期序列動了：距上一次 {gap} 天，這次是 {data_date}",
                )
        return Freshness(key, ON_TIME, f"不定期，停在 {data_date}（{lag} 天前）")

    tolerance = TOLERANCE_DAYS.get(freq, 30)
    min_interval = MIN_INTERVAL_DAYS.get(freq, 0)

    if previous_data_date is not None:
        gap = (data_date - previous_data_date).days
        if 0 < gap < min_interval:
            return Freshness(
                key, UNEXPECTED,
                f"{freq}序列間隔只有 {gap} 天（正常至少 {min_interval} 天）"
                f"—— 可能是修正，也可能是抓錯，要有人看一眼",
            )

    if lag > tolerance:
        return Freshness(
            key, OVERDUE,
            f"{freq}序列停在 {data_date}，已經 {lag} 天沒有新的"
            f"（容忍 {tolerance} 天）",
        )
    return Freshness(key, ON_TIME, f"{freq}，資料日期 {data_date}（{lag} 天前）")


def scan(
    rows: list[tuple[str, str, dt.date | None, dt.date | None]],
    today: dt.date,
) -> list[Freshness]:
    """整批掃描並排序 —— **要注意的排前面**。

    rows 的每一筆是 (key, freq, data_date, previous_data_date)。

    排序是刻意的：一頁二十幾條序列，需要看的那兩條混在中間等於沒有報警。
    """
    got = [assess(freq, d, today, prev, key=key) for key, freq, d, prev in rows]
    return sorted(got, key=lambda f: (not f.needs_attention, f.key))


# ---------------- 預期下次更新時間（給「到期才自動抓」用） ----------------

def _add_months(d: dt.date, months: int) -> dt.date:
    """加月份。落到不存在的日期（1/31 + 1 個月）就退到當月最後一天。"""
    total = (d.year * 12 + d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    for day in range(d.day, 0, -1):
        try:
            return dt.date(year, month, day)
        except ValueError:
            continue
    return dt.date(year, month, 1)


def next_expected(freq: str, data_date: dt.date | None) -> dt.date | None:
    """這條序列的下一筆**預期**落在哪一天。

    **不定期回 None** —— 央行什麼時候調利率沒有人知道，編一個日期出來只會
    讓自動更新每天亮一次燈（§10 那個「拿值去比會永遠亮燈」的變形）。

    這是「預期」不是「保證」：月頻資料標 7/1，下一筆標 8/1，但**公布**還會
    再晚兩三週。所以 is_due() 用它當門檻是保守的 —— 早問幾次比漏掉好，
    而且問到沒有的時候本來就會被當成「還沒公布」（§10）。
    """
    if data_date is None or freq == IRREGULAR:
        return None
    if freq in NEXT_AFTER_DAYS:
        return data_date + dt.timedelta(days=NEXT_AFTER_DAYS[freq])
    if freq in NEXT_AFTER_MONTHS:
        return _add_months(data_date, NEXT_AFTER_MONTHS[freq])
    return data_date + dt.timedelta(days=30)


def is_due(freq: str, data_date: dt.date | None, today: dt.date) -> bool:
    """現在該不該去抓這一條。

    三種情形：

        沒抓過        → 一定要抓
        不定期        → 每 IRREGULAR_SCAN_DAYS 天掃一次
        其餘          → 預期時間到了就抓
    """
    if data_date is None:
        return True
    if freq == IRREGULAR:
        return (today - data_date).days >= IRREGULAR_SCAN_DAYS
    nxt = next_expected(freq, data_date)
    return nxt is not None and nxt <= today


def due_keys(
    rows: list[tuple[str, str, dt.date | None]], today: dt.date
) -> list[str]:
    """整批判斷，回「該抓的那幾條」的 key。

    rows 的每一筆是 (key, freq, data_date)。

    自動更新只抓這幾條，不是整批重抓 —— 那才是「按更新頻率自動掃、自動排」
    的意思（§9 Day 28 第 2 項）。想整批重抓是另一個動作（強制重抓）。
    """
    return [key for key, freq, d in rows if is_due(freq, d, today)]

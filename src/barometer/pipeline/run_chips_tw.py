"""台股籌碼面的兩班排程進入點（ToDo §9 Day 26 第 2 項）。

    18:00  chips_tw_evening  三大法人 + 台指期 + put/call
    22:30  chips_tw_late     只補融資融券

**為什麼要分兩班**：證交所的三大法人約 17:30 更新完，18:00 抓得到；
融資融券約 21:30 才更新完，而且可能更晚。18:00 那班去問融資融券只會拿到
「很抱歉，沒有符合條件的資料」，然後在 run log 留下一筆看起來像故障的失敗。

回看的窗開七個日曆日 —— 融資融券的「今日餘額」是暫定值，隔天的「前日餘額」
才是定稿，所以往回多帶幾天可以把前幾天的暫定值換成定稿（§4.1 回看）。
"""
from __future__ import annotations

import datetime as dt
import sys

from barometer.pipeline import run_chips

LOOKBACK_DAYS = 7


def _weekdays(end: dt.date, days: int = LOOKBACK_DAYS) -> list[dt.date]:
    """只列週一到週五。**這不是交易日曆** —— 只是不去問週末。

    國定假日照樣會被問到，然後由「空回應 = 還沒公布」自己吃掉（§1 第 6 條）。
    """
    out = []
    for i in range(days, -1, -1):
        d = end - dt.timedelta(days=i)
        if d.weekday() < 5:
            out.append(d)
    return out


SHIFTS = {
    "evening": (run_chips.EVENING_PARTS, "chips_tw_evening"),
    "late": (run_chips.LATE_PARTS, "chips_tw_late"),
}


def main(argv: list[str]) -> int:
    shift = argv[0] if argv else "evening"
    if shift not in SHIFTS:
        # **不要落到一個「差不多」的預設值。** 這裡原本是
        # `.get(shift, (ALL_PARTS, "chips_tw"))`，結果 run_daily.ps1 的
        # PowerShell 陣列被展開成字串、再被 splatting 拆成字元，傳進來的是
        # 'l'，於是它安靜地跑了十天的 ALL_PARTS —— exit 0、資料照寫、
        # run log 有紀錄，只是每晚白打六次 TWSE。
        #
        # 錯的參數要大聲失敗。安靜地跑一個不同的班，事後跟「跑對了」
        # 長得一模一樣。
        raise ValueError(
            f"不認識的班別 {shift!r}（可用：{'、'.join(SHIFTS)}）—— "
            "不猜、不用預設值，請檢查 run_daily.ps1 傳了什麼"
        )
    parts, task = SHIFTS[shift]

    log = run_chips.run(_weekdays(dt.date.today()), task=task, parts=parts)
    print(f"[{log.started_at:%Y-%m-%d %H:%M}] {task} "
          f"status={log.status} counts={log.counts}")
    for n in log.notes:
        print(f"  ! {n}")
    return 0 if log.status in ("ok", "partial") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

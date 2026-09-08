"""美股每日排程進入點（ToDo §9 Day 24 第 10 項）。

Windows 工作排程器每天 09:00（台北） 呼叫這支。**不是 GitHub Actions cron** ——
金鑰全留本機，CI 不抓資料就不需要任何 Key（§1 第 3 條）。

每天跑，**資料沒變就不 commit**（§1 第 6 條）—— 不必維護交易日曆；
美國假期（例如 9/7 勞動節）、休市、資料延遲全都自動處理掉 ——
    任何假設兩個市場日期對齊的程式碼都會在勞動節那天錯位。
"""
from __future__ import annotations

import sys

from barometer import config
from barometer.pipeline import fetch_prices


def main() -> int:
    log = fetch_prices.run(
        list(config.US_SYMBOLS), task="daily_us", period="1y"
    )
    print(f"[{log.started_at:%Y-%m-%d %H:%M}] daily_us "
          f"status={log.status} counts={log.counts}")
    for n in log.notes:
        print(f"  ! {n}")
    # partial 不算失敗 —— 單一標的失敗不該讓排程任務標成錯誤
    return 0 if log.status in ("ok", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())

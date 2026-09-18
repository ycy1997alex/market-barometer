"""把 `price_current` 裡缺的交易日從 SQLite 補回來（2026-09-18，ToDo §10）。

為什麼會缺：`write_current` 以前是整份覆寫，而 yfinance 回 `0050.TW`、
`006208.TW` 時固定漏掉前一個交易日。DB 那份沒有洞（upsert 累積），CSV 有 ——
而 `build_page` 讀的是 CSV。`write_current` 已經改成合併寫入，明天起不會再挖
新的洞；**這一支是拿來填已經挖好的那些**。

這不是重抓（§4.1）：

  - **只加，不改。** CSV 已經有的日期一格都不碰，即使 DB 的值不一樣 ——
    那種不一樣是「來源回頭改寫歷史」，處置是記旗標 + 手動 `refetch.py`，
    不是在這裡悄悄抹平。
  - 補進來的值來自本機 DB，不是重新對外抓的。沒有任何新的對外請求。

預設只看不寫。要真的寫檔請加 `--apply`。不給標的就跑 market-barometer 自己的
六檔；stock-research 那 15 檔共用同一個資料層，要一起補就把代號列在後面。

    python tools\\repair_current.py            # 只報告
    python tools\\repair_current.py --apply     # 真的補
    python tools\\repair_current.py --apply 0050.TW 006208.TW
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer import config  # noqa: E402
from barometer.pipeline.runlog import RunLog  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    symbols = [a for a in argv if not a.startswith("--")] or list(config.ALL_SYMBOLS)

    log = RunLog(task="repair_current")
    config.ensure_dirs()
    repo = SqliteRepo(config.db_path())
    repo.init_schema()

    total = 0
    try:
        for symbol in symbols:
            on_disk = csv_audit.read_current(symbol)
            if not on_disk:
                print(f"{symbol:12s} 本機沒有序列，跳過")
                continue

            have = {b.date for b in on_disk}
            lo, hi = min(have), max(have)
            # 只補涵蓋範圍**之內**的洞。範圍之外是「這一份比較短」，不是洞。
            missing = [
                b for b in repo.get_prices(symbol, start=lo, end=hi)
                if b.date not in have
            ]

            if not missing:
                print(f"{symbol:12s} {len(on_disk):4d} 根，沒有洞")
                continue

            days = "、".join(b.date.isoformat() for b in missing)
            print(f"{symbol:12s} {len(on_disk):4d} 根，缺 {len(missing)} 天：{days}")
            total += len(missing)
            log.set_count(f"filled::{symbol}", len(missing))
            log.note(f"{symbol}: 從 SQLite 補回 {len(missing)} 個交易日（{days}）")

            if apply:
                merged = sorted(on_disk + missing, key=lambda b: b.date)
                csv_audit.write_current(symbol, merged, replace=True)

        log.set_count("symbols", len(symbols))
        log.finish("ok")
    finally:
        repo.close()

    print()
    if not total:
        print("沒有任何洞要補。")
    elif apply:
        log.append()
        print(f"補了 {total} 個交易日，已寫回 price_current 並記進 run log。")
    else:
        print(f"共 {total} 個交易日可補。**沒有寫任何檔案** —— 要寫請加 --apply。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

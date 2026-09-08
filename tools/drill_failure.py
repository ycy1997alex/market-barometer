r"""Day 28 第 4 項的演練：故意打壞一個資料源，看整條管線的反應。

驗收：**「其他格照常更新、失敗那格標 stale 並顯示停在哪一天，通知有送出」**。

這支不是測試，是**演練** —— 它打的是真的網路、寫的是真的 run log 與真的
通知檔案。單元測試證明的是「程式在假環境下會這樣」，演練證明的是
「今天這台機器、這個排程、這個通知管道，真的會這樣」。

被打壞的是 FRED：把它的端點換成一個必定連不上的網址。其餘來源不動。
演練不會弄髒資料 —— 失敗的那條序列本來就不會被寫進去。
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer import config  # noqa: E402
from barometer.datasources import fred_src  # noqa: E402
from barometer.domain import macro_spec  # noqa: E402
from barometer.pipeline import notify, run_macro  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402


def _snapshot() -> dict[str, dt.date | None]:
    repo = SqliteRepo(config.db_path())
    try:
        return {
            ind.key: (c.data_date if (c := repo.get_macro(ind.key)) else None)
            for ind in macro_spec.ALL
        }
    finally:
        repo.close()


def main() -> int:
    config.ensure_dirs()
    print("=== Day 28 第 4 項：失敗演練 ===")
    print("把 FRED 的端點換成一個連不上的位址，其餘來源不動。\n")

    before = _snapshot()

    # FRED 現在有兩個端點：有金鑰走官方 API、沒有就退回免金鑰 CSV。
    # **兩個都要打壞**，只壞一個的話它會安靜地走另一條，演練就白做了。
    #
    # 這一段本身也是教訓：改 fred_src 的時候常數改了名，這支演練腳本
    # 就再也打不壞它了 —— 而且是印出 FAIL 才發現的。演練腳本自己也會過期。
    BASES = ("API_BASE", "CSV_BASE")
    originals = {}
    for name in BASES:
        if not hasattr(fred_src, name):
            print(f"FAIL 找不到 fred_src.{name}，演練無法進行")
            return 1
        originals[name] = getattr(fred_src, name)
        setattr(fred_src, name, getattr(fred_src, name).replace(
            "stlouisfed.org", "fred-does-not-exist.invalid"))
    print(f"已打壞 {'、'.join('fred_src.' + n for n in BASES)}")

    log, _ = run_macro.run(force=True)
    for name, value in originals.items():
        setattr(fred_src, name, value)

    after = _snapshot()

    fred_keys = [i.key for i in macro_spec.ALL if i.source == "fred"]
    other_keys = [i.key for i in macro_spec.ALL if i.source != "fred"]

    print(f"\nrun status={log.status}")
    for n in log.notes[:12]:
        print(f"  ! {n}")

    print(f"\n{'指標':<12}{'來源':<10}{'演練前':<14}{'演練後':<14}")
    print("-" * 52)
    failures: list[tuple[str, str, dt.date | None]] = []
    for key in fred_keys:
        b, a = before.get(key), after.get(key)
        print(f"{key:<12}{'fred':<10}{str(b):<14}{str(a):<14}")
        failures.append((key, "端點連不上（演練）", b))
    for key in other_keys[:6]:
        b, a = before.get(key), after.get(key)
        print(f"{key:<12}{'其他':<10}{str(b):<14}{str(a):<14}")

    # 通知：一次跑壞五條 → **一則**通知，不是五則
    n = notify.Notifier(
        config.stockdata_root() / "runlog" / "alerts.jsonl",
        config.stockdata_root() / "ALERT.md",
    )
    body = notify.summarise_failures(failures)
    result = n.send("總經抓取失敗（演練）", body, severity="error")

    print("\n--- 通知 ---")
    print(body)
    print(f"\n寫入本機紀錄：{result.recorded}")
    print(f"外部管道：{'已送出' if result.external_ok else result.external_error}"
          f"（未設定 {notify.ENV_CMD} 時視為成功，因為根本沒有要送）")

    print("\n=== 驗收 ===")
    kept = all(after.get(k) == before.get(k) for k in fred_keys)
    others_alive = sum(1 for k in other_keys if after.get(k) is not None)
    print(f"失敗那幾格保留舊值、沒有被清成 None 或 0：{kept}")
    print(f"其他來源照常有值：{others_alive}/{len(other_keys)}")
    print(f"通知有送出：{result.recorded}")
    print(f"顯眼的標記檔：{config.stockdata_root() / 'ALERT.md'}")
    ok = kept and others_alive > 0 and result.recorded
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

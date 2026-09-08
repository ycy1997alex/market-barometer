"""Day 24 第 9 項驗收：runlog 有內容，欄位含 run_id / task / status / counts / quota。

run log 也是 Day 28 回顧的主體之一 —— 價格可以事後回補，
**管線自己的執行紀錄補不回來**。
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer import config  # noqa: E402
from barometer.pipeline.runlog import read_runs  # noqa: E402

REQUIRED = ("run_id", "task", "started_at", "status", "counts", "quota")


def main() -> int:
    ym = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().strftime("%Y-%m")
    rows = read_runs(ym)
    path = config.runlog_path(ym)
    print(f"{path}  共 {len(rows)} 筆\n")

    if not rows:
        print("FAIL run log 是空的")
        return 1

    print(f"{'task':<18}{'status':<9}{'started':<21}{'run_id':<14}摘要")
    print("-" * 104)
    for r in rows:
        counts = {
            k: v for k, v in r["counts"].items()
            if not k.startswith(("rows::", "conflicts::"))
        }
        quota = r["quota"].get("requests")
        if quota is None and "shioaji_usage" in r["quota"]:
            rb = r["quota"]["shioaji_usage"].get("remaining_bytes")
            quota = f"shioaji 剩餘 {rb / 1048576:.0f} MB" if rb else "shioaji usage 未取得"
        print(f"{r['task']:<18}{r['status']:<9}{r['started_at']:<21}"
              f"{r['run_id']:<14}{counts} {quota or ''}")
        for n in r.get("notes", [])[:2]:
            print(f"{'':<62}! {n[:70]}")

    missing = [f for f in REQUIRED if f not in rows[0]]
    if missing:
        print(f"\nFAIL 缺欄位：{missing}")
        return 1
    print(f"\nOK 欄位齊備：{', '.join(REQUIRED)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

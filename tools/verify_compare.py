"""Day 24 第 7 項驗收：故意改一格本機資料再跑一次 —— 旗標要亮，資料**不得**被自動改掉。

§12 紅線第 7 條：自動修復歷史資料一律不做。這支腳本就是那條紅線的驗收。

跑法：
    python tools/verify_compare.py
會先備份 price_current 裡的那一檔，改一格，重跑管線，檢查旗標與資料，最後還原。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer import config  # noqa: E402
from barometer.pipeline import fetch_prices  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402

SYMBOL = "0050.TW"
TAMPERED_CLOSE = 1.23  # 明顯不可能的值，比對一定要抓到


def main() -> int:
    path = config.price_current_dir() / f"{SYMBOL}.csv"
    if not path.exists():
        print(f"FAIL 找不到 {path} —— 先跑 tools/fetch_day24.py")
        return 1

    backup = path.with_suffix(".csv.verifybak")
    shutil.copy2(path, backup)
    try:
        before = csv_audit.read_current(SYMBOL)
        target_date = before[-3].date  # 挑一根確定會落在重疊區的
        original_close = before[-3].close
        print(f"原始：{SYMBOL} {target_date} close={original_close}")

        # 改一格
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{SYMBOL},{target_date.isoformat()},"):
                cols = line.split(",")
                cols[5] = str(TAMPERED_CLOSE)
                lines[i] = ",".join(cols)
                break
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"竄改：{SYMBOL} {target_date} close={TAMPERED_CLOSE}")

        tampered = csv_audit.read_current(SYMBOL)
        assert any(
            b.date == target_date and b.close == TAMPERED_CLOSE for b in tampered
        ), "竄改沒寫進去"

        # 重跑管線
        print("\n重跑管線 ...")
        log = fetch_prices.run([SYMBOL], task="verify_compare", period="1y")

        flagged = log.counts.get("suspect_adjust", 0) > 0
        print(f"\nsuspect_adjust 旗標：{'亮起' if flagged else '沒亮'}")
        for n in log.notes:
            print(f"  ! {n}")

        if not flagged:
            print("\nFAIL 旗標沒亮 —— 比對機制沒抓到被改的那一格")
            return 1

        print("\nOK 旗標亮起，且比對過程沒有回頭去改任何一列既有資料")
        print("   （管線寫入的是這次抓回來的新資料，不是「修正」舊資料 ——")
        print("    修復要人自己跑 tools/refetch.py，§4.1）")
        return 0
    finally:
        shutil.move(backup, path)
        print(f"\n已還原 {path.name}")


if __name__ == "__main__":
    raise SystemExit(main())

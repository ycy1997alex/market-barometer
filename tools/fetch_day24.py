"""Day 24 第 4 項：抓 §7.1 六個標的的一年日線落地。

驗收：price_raw\\<今天>\\ 有六個檔、price_current\\ 有六條序列、
筆數與 §7.1 對得上。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer import config  # noqa: E402
from barometer.pipeline import fetch_prices  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402

# §7.1 近一年實測筆數（2026-09-06 抓），Day 24 要重跑確認
EXPECTED_ROWS = {
    "^TWII": 243, "0050.TW": 244, "006208.TW": 244,
    "^GSPC": 252, "SPY": 252, "VOO": 252,
}


def main() -> int:
    symbols = list(config.ALL_SYMBOLS)
    print(f"抓取 {len(symbols)} 檔：{', '.join(symbols)}")
    log = fetch_prices.run(symbols, task="day24_bootstrap", period="1y")

    print(f"\nrun_id={log.run_id} status={log.status}")
    for n in log.notes:
        print(f"  ! {n}")
    print(f"  requests: {log.quota.get('requests')}")

    print(f"\n{'標的':<12}{'筆數':>6}{'§7.1':>7}{'期末收盤':>14}  {'近一年報酬':>10}  stale")
    print("-" * 68)
    for sym in symbols:
        bars = csv_audit.read_current(sym)
        if not bars:
            print(f"{sym:<12}{'—— 沒有資料 ——':>30}")
            continue
        closes = [b.close for b in bars if b.close is not None]
        ret = (closes[-1] / closes[0] - 1) * 100 if len(closes) > 1 else float("nan")
        stale_n = sum(1 for b in bars if b.stale)
        exp = EXPECTED_ROWS.get(sym, 0)
        mark = "" if abs(len(bars) - exp) <= 3 else "  <= 與 §7.1 差距大"
        print(f"{sym:<12}{len(bars):>6}{exp:>7}{closes[-1]:>14,.2f}  "
              f"{ret:>+9.1f}%  {stale_n}{mark}")

    raw_dir = config.price_raw_dir(log.started_at.date().isoformat())
    raw_files = sorted(p.name for p in raw_dir.glob("*.csv")) if raw_dir.exists() else []
    cur_files = sorted(p.name for p in config.price_current_dir().glob("*.csv"))
    print(f"\nprice_raw/{raw_dir.name}/ : {len(raw_files)} 檔 {raw_files}")
    print(f"price_current/           : {len(cur_files)} 檔 {cur_files}")

    ok = len(raw_files) >= len(symbols) and len(cur_files) >= len(symbols)
    print("\nOK 六檔都落地了" if ok else "\nFAIL 落地檔數不足")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

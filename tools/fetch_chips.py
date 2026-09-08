"""Day 26 第 2 項：抓市場級籌碼面。

驗收：單位標對（T86 是**股**、融資融券是**張**、台指期未平倉是**口**），
且非交易日拿到空回應時當「這天還沒有」而不是 0。

日期給法：`python tools/fetch_chips.py 2026-09-01 2026-09-04`（含頭含尾，
只跑週一到週五；週末本來就沒有盤後資料，不必浪費請求去問）。
不給日期就抓最近七個日曆日 —— TWSE 的回看窗（§4.1）。
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer import config  # noqa: E402
from barometer.pipeline import run_chips  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402


def _weekdays(start: dt.date, end: dt.date) -> list[dt.date]:
    """只列週一到週五。

    這**不是**交易日曆 —— 只是不去問週末，省掉兩次註定回空的請求。
    國定假日照樣會被問到，然後由「空回應 = 還沒公布」自己吃掉（§1 第 6 條）。
    """
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def main(argv: list[str]) -> int:
    if len(argv) >= 2:
        start, end = dt.date.fromisoformat(argv[0]), dt.date.fromisoformat(argv[1])
    else:
        end = dt.date.today()
        start = end - dt.timedelta(days=7)

    days = _weekdays(start, end)
    print(f"抓籌碼面 {start} ~ {end}，共 {len(days)} 個平日")

    log = run_chips.run(days, task="chips_tw")
    print(f"\nrun_id={log.run_id} status={log.status}")
    for n in log.notes:
        print(f"  ! {n}")

    repo = SqliteRepo(config.db_path())
    try:
        rows = repo.get_chip_range(start, end)
    finally:
        repo.close()

    print(f"\n{'日期':<12}{'融資(張)':>14}{'融券(張)':>12}"
          f"{'外資期貨(口)':>16}{'P/C OI(%)':>12}{'三大法人(股)':>18}")
    print("-" * 86)
    for d, p in rows:
        def f(key, fmt="{:,.0f}"):
            v = p.get(key)
            return fmt.format(v) if v is not None else "—"
        print(f"{d.isoformat():<12}{f('margin_lots'):>14}{f('short_lots'):>12}"
              f"{f('fut_foreign_net_oi_contracts'):>16}"
              f"{f('pc_oi_ratio_pct', '{:.1f}'):>12}"
              f"{f('total_net_shares'):>18}")

    print("\n=== 驗收 ===")
    print(f"落地天數：{len(rows)}／{len(days)} 個平日")
    print(f"沒有資料而未落地（當作還沒公布，不是 0）：{log.counts.get('days_empty', 0)} 天")
    units_ok = all(
        set(p) <= {
            "foreign_net_shares", "trust_net_shares", "dealer_net_shares",
            "total_net_shares", "margin_lots", "short_lots",
            "margin_is_provisional", "margin_prev_lots",
            "fut_foreign_net_oi_contracts", "fut_total_net_oi_contracts",
            "pc_oi_ratio_pct", "pc_volume_ratio_pct",
        }
        for _, p in rows
    )
    print("OK 欄位名都帶單位" if units_ok else "FAIL 有欄位沒帶單位")
    return 0 if rows and units_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

r"""手動全序列重抓（ToDo §4.1、§4.4 第 3 點）。

**重抓永遠是手動的。** 每天自動跑的只有「比對」—— 比對是煙霧偵測器、回看是
補漏、重抓是修復，自動化只做第一件。

理由寫在 §4.1 最後一句：**半夜自己重寫歷史卻沒人知道，比壞掉還糟。**

所以流程刻意有一個人在中間：
    排程跑 → 比對對不上 → run log 亮 suspect_adjust 旗標 → **人看到** →
    跑這支 → 全序列重抓、覆寫 price_current、寫一筆 adjustment_event →
    標記評分歷史需要重算

用法：
    python tools/refetch.py 0050.TW
    python tools/refetch.py 0050.TW --note "2026-09 除權息"
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer import config  # noqa: E402
from barometer.datasources import yfinance_src  # noqa: E402
from barometer.domain.reconcile import compare_overlap  # noqa: E402
from barometer.pipeline.runlog import RunLog  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    symbol = argv[0]
    note = ""
    if "--note" in argv:
        note = argv[argv.index("--note") + 1]

    log = RunLog(task="refetch")
    config.ensure_dirs()
    as_of = dt.datetime.now()

    before = csv_audit.read_current(symbol)
    print(f"本機現有 {len(before)} 根")

    print(f"重抓 {symbol} 的完整序列…")
    bars = yfinance_src.fetch_daily(symbol, period="max", as_of=as_of)
    print(f"抓回 {len(bars)} 根")

    cmp = compare_overlap(before, bars)
    ratio = cmp.ratio
    changed = len(cmp.mismatches)
    print(f"\n重疊 {len(cmp.compared_dates)} 天，其中 {changed} 格與本機不同"
          + (f"，疑似比例 {ratio:.6g}" if ratio else ""))

    if changed == 0:
        print("\n本機與來源一致 —— 沒有東西需要修，不寫 adjustment_event。")
        log.note(f"{symbol}: 重抓後無差異，未覆寫")
        log.finish("ok")
        log.append()
        return 0

    # 稽核軌跡先留一份，再覆寫計算用的那份（§4.4 第 1 點）
    csv_audit.write_raw(symbol, bars, dt.date.today())
    csv_audit.write_current(symbol, bars)

    repo = SqliteRepo(config.db_path())
    repo.init_schema()
    try:
        repo.upsert_prices(bars)
        repo.record_adjustment(
            symbol=symbol,
            detected_at=as_of,
            event_date=None,
            ratio=ratio,
            rows_affected=changed,
            note=note or "手動重抓：全序列覆寫 price_current",
        )
        # §3.5：分割或除權息之後所有價格型指標都會變，昨天的分數今天算會不一樣。
        # 這裡只標記需要重算，**不代跑** —— 重算要看得見，不該藏在重抓裡面。
        old = repo.get_scores("index", symbol)
        print(f"\n已寫 adjustment_event。score_history 有 {len(old)} 筆用舊價格算的，"
              f"需要重算：\n  python tools/score_index.py")
    finally:
        repo.close()

    log.set_count("rows", len(bars))
    log.set_count("changed_cells", changed)
    log.note(f"{symbol}: 全序列重抓覆寫，{changed} 格與舊值不同")
    log.finish("ok")
    log.append()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

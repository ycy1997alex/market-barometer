r"""撰稿前的手動全量比對（ToDo §4.4 第 5 點、§9 Day 28 第 1 項）。

驗收：**「確認這五天的數字沒被回頭改過；有改就記 adjustment_event 並重算評分」**。

為什麼這一次非做不可：每天自動跑的比對只看**重疊的最後 5 根**（§4.1，那是
煙霧偵測器，成本要低）。要寫進文章的數字得看整條 —— §7.1 那張表的台股數字
在寫計畫與實作之間就變過一次，而且變的原因只是 Yahoo 把一格 NaN 補上，
就足以讓一個結論位移 3.2 個百分點。

**這支只比對、不修。** 對不上就印出來、記旗標，重抓仍然是手動跑
`tools/refetch.py`（§4.1「自動修復一律不做」）。
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))
sys.path.insert(0, str(_HERE.parent / "stock-research" / "src"))

from barometer import config  # noqa: E402
from barometer.datasources import yfinance_src  # noqa: E402
from barometer.datasources.base import COUNTER, FetchError  # noqa: E402
from barometer.domain import windows  # noqa: E402
from barometer.pipeline.runlog import RunLog  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402

TOL = 0.001  # 0.1%，與 §4.2 的價格容忍一致


def _rel(a: float, b: float) -> float:
    return abs(a - b) / abs(b) if b else (0.0 if a == b else 1.0)


def main(argv: list[str]) -> int:
    include_stocks = "--with-stocks" in argv
    symbols = list(config.ALL_SYMBOLS)
    if include_stocks:
        from research import config as rc  # noqa: E402
        symbols += list(rc.ALL_SYMBOLS)

    log = RunLog(task="full_reconcile")
    COUNTER.reset()
    print("=== Day 28 第 1 項：撰稿前手動全量比對 ===")
    print("只比對，不修 —— 對不上就記旗標，重抓仍然是手動的（§4.1）。\n")

    total_changed = 0
    for symbol in symbols:
        stored = csv_audit.read_current(symbol)
        if not stored:
            print(f"{symbol:<12}本機沒有序列，跳過")
            continue
        try:
            fresh = yfinance_src.fetch_daily(symbol, period="1y")
        except FetchError as exc:
            print(f"{symbol:<12}抓取失敗：{exc}")
            log.note(f"{symbol}: 全量比對抓取失敗 — {exc}")
            log.count("fetch_failed")
            continue

        by_date = {b.date: b for b in fresh}
        mismatches: list[str] = []
        for b in stored:
            other = by_date.get(b.date)
            if other is None:
                continue
            for field in ("open", "high", "low", "close"):
                mine, theirs = getattr(b, field), getattr(other, field)
                if mine is None or theirs is None:
                    if mine != theirs:
                        mismatches.append(f"{b.date} {field}: {mine} → {theirs}")
                    continue
                if _rel(mine, theirs) > TOL:
                    mismatches.append(
                        f"{b.date} {field}: {mine:,.4f} → {theirs:,.4f}"
                        f"（{_rel(mine, theirs) * 100:.3f}%）"
                    )

        overlap = len(set(by_date) & {b.date for b in stored})
        flag = "" if not mismatches else f"  ← {len(mismatches)} 格對不上"
        print(f"{symbol:<12}本機 {len(stored):>4} 根、來源 {len(fresh):>4} 根、"
              f"重疊 {overlap:>4} 天{flag}")
        for m in mismatches[:5]:
            print(f"             {m}")
        if len(mismatches) > 5:
            print(f"             （另有 {len(mismatches) - 5} 格）")

        total_changed += len(mismatches)
        log.set_count(f"mismatch::{symbol}", len(mismatches))
        if mismatches:
            log.note(f"{symbol}: 全量比對有 {len(mismatches)} 格對不上 —— "
                     f"要不要修由人決定，跑 tools/refetch.py {symbol}")

    # 兩個市場的回溯視窗（§10：不會對齊）
    tw_days = windows.last_n_sessions(
        [b.date for b in csv_audit.read_current(config.TW_INDEX)], 5)
    us_days = windows.last_n_sessions(
        [b.date for b in csv_audit.read_current(config.US_INDEX)], 5)
    print(f"\n回溯視窗（§10 兩市場不對齊）")
    print(f"  台股：{[d.isoformat() for d in tw_days]}")
    print(f"  美股：{[d.isoformat() for d in us_days]}")

    log.quota["requests"] = COUNTER.snapshot()
    log.set_count("mismatch_total", total_changed)
    log.finish("ok")
    log.append()

    print(f"\n=== 驗收 ===")
    print(f"對不上的格數合計：{total_changed}")
    if total_changed == 0:
        print("OK 這段期間的數字沒有被回頭改過")
    else:
        print("有變動 —— 逐檔跑 tools/refetch.py <symbol> 再跑 tools/score_index.py 重算")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

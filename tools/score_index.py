"""Day 26 第 3 項：大盤與 ETF 評分，逐日回算 + 五日加權。

驗收：權重加總 = 1.0（由 tests/domain/test_weighting.py 守著），且用回溯視窗
的五個交易日真實資料跑出完整評分序列。

**五個交易日只有五個點 —— 一律定性觀察，不是統計證據**（§12 第 10 條）。
這支腳本每次都會把這句話印出來。

§2.1：只出分數與分項，不產生任何建議。
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer import config  # noqa: E402
from barometer.domain import chips as chips_domain  # noqa: E402
from barometer.domain import scoring_index  # noqa: E402
from barometer.pipeline import run_scores  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402

QUALITATIVE = "五個交易日只有五個點，以下一律是定性觀察，不是統計證據。"


def main() -> int:
    symbols = list(config.ALL_SYMBOLS)
    print("=== Day 26 第 3 項：大盤與 ETF 評分 ===")
    print(QUALITATIVE + "\n")

    log = run_scores.run(symbols, task="scores_index")
    print(f"run_id={log.run_id} status={log.status}")
    for n in log.notes:
        print(f"  ! {n}")

    ok = True
    for symbol in symbols:
        bars = csv_audit.read_current(symbol)
        if not bars:
            print(f"\n{symbol}: 本機沒有序列")
            ok = False
            continue

        scored = run_scores.score_series(symbol, bars)
        summary = run_scores.summarize_window(scored)

        print(f"\n--- {symbol} ---")
        for day, s in scored:
            sc = f"{s.score:.1f}" if s.score is not None else "資料不足"
            alerts = "、".join(s.alert_keys) or "無"
            print(f"  {day}  分數 {sc:>9}  警示：{alerts}")

        avg = summary["simple_average"]
        wavg = summary["weighted_average"]
        print(f"  簡單平均 {avg:.1f}／加權平均 {wavg:.1f}"
              if avg is not None and wavg is not None
              else "  平均：資料不足")

        latest = scored[-1][1] if scored else None
        if latest and latest.reasons:
            print("  最新一日的分項：")
            for k, why in latest.reasons.items():
                print(f"    {k:<12}{why}")

        note = chips_domain.reading(symbol)
        print(f"  籌碼面讀法：{note.caveat}")

        gaps = scoring_index.etf_data_gaps(symbol)
        if gaps:
            print(f"  ETF 特有但算不出來的：{'、'.join(gaps)}（{scoring_index.INSUFFICIENT}）")

        if len(scored) < 5:
            print(f"  ! 視窗只有 {len(scored)} 天，還沒滿五個交易日")

    print("\n=== 驗收 ===")
    print(f"有評分的標的：{log.counts.get('symbols_ok', 0)}／{len(symbols)}")
    print("OK" if ok else "FAIL 有標的沒有序列")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

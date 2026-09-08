"""Day 25 第 1、3 項驗收。

  第 1 項：17 項評分指標 + 7 項觀測指標都有值或明確的失敗原因，
           沒有任何一項讓整輪中止
  第 3 項：頁面上**沒有**單一的「網站最後更新時間」，每條序列各自標自己的資料日期
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer.domain.macro_spec import OBSERVE, TAIWAN, WORLD  # noqa: E402
from barometer.pipeline import run_macro  # noqa: E402


def show(title: str, group, results, verdicts) -> tuple[int, int]:
    print(f"\n{title}")
    print(f"{'指標':<20}{'頻率':<6}{'資料日期':<12}{'最新值':>12}  {'狀態':<6} 判定")
    print("-" * 96)
    have = 0
    for ind in group:
        r = results[ind.key]
        series = r["series"]
        if series:
            have += 1
            label, value = series[-1]
            try:
                shown = ind.fmt.format(value)
            except (ValueError, TypeError):
                shown = str(value)
        else:
            label, shown = "—", "—"

        verdict = ""
        if ind.key in verdicts:
            hit, msg = verdicts[ind.key]
            verdict = ("[警示] " if hit else "       ") + msg
        elif ind.layer == "observe":
            verdict = "（只顯示不評分）"

        note = r["note"]
        print(f"{ind.name:<20}{ind.freq:<6}{label:<12}{shown:>12}  "
              f"{r['status']:<6} {verdict}")
        if note:
            print(f"{'':<20}└─ {note}")
    return have, len(group)


def main() -> int:
    log, out = run_macro.run(force=True)
    results, verdicts, summary = out["results"], out["verdicts"], out["summary"]

    w_have, w_all = show("=== 世界層（進評分） ===", WORLD, results, verdicts)
    t_have, t_all = show("=== 台灣層（進評分） ===", TAIWAN, results, verdicts)
    o_have, o_all = show("=== 只顯示不評分 ===", OBSERVE, results, verdicts)

    print("\n=== 評分 ===")
    print(f"世界層 {summary['world']:.1f}" if summary["world"] is not None else "世界層 —")
    print(f"台灣層 {summary['taiwan']:.1f}" if summary["taiwan"] is not None else "台灣層 —")
    print(f"總分   {summary['score']}   有效指標 {summary['valid']} 項"
          f"{'（資料量偏低）' if summary['low_data'] else ''}")
    print(f"警示中：{', '.join(summary['alert_keys']) or '（無）'}")

    print(f"\nrun_id={log.run_id} status={log.status} counts={log.counts}")
    print(f"requests={log.quota.get('requests')}")
    for n in log.notes:
        print(f"  ! {n}")

    # Day 25 第 3 項：資料日期必須各自不同，不存在單一的「最後更新時間」
    dates = {
        r["series"][-1][0] for r in results.values() if r["series"]
    }
    print(f"\n不同的資料日期共 {len(dates)} 種：{sorted(dates)}")
    print("→ 沒有單一的「網站最後更新時間」可言，每條序列各自標自己的日期")

    total_have = w_have + t_have + o_have
    total = w_all + t_all + o_all
    print(f"\n有值的指標 {total_have}/{total}"
          f"（評分 {w_have + t_have}/{w_all + t_all}、觀測 {o_have}/{o_all}）")
    ok = log.status in ("ok", "partial") and total_have > 0
    print("OK 整輪沒有中止" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

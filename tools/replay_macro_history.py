"""Offline engineering report for macro publish-lag replay.

Usage: python tools/replay_macro_history.py --snapshot history.json --output report.md
The snapshot is an explicit input; this command never fetches or alters sources.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer.domain.macro_replay import replay_world  # noqa: E402
from barometer.domain.macro_spec import PUBLISH_LAG_DAYS, WORLD  # noqa: E402

WINDOWS = ("2008-10", "2020-03", "2022-09")
START = dt.date(2000, 1, 1)
END = dt.date(2025, 12, 31)
MIN_VALID = 6


def make_report(series_by_key: dict, generated_at: dt.datetime) -> str:
    points = replay_world(series_by_key, START, END)
    usable = [p for p in points if p.score is not None and p.valid >= MIN_VALID]
    if not usable:
        raise ValueError("no dates with sufficient historical macro coverage")
    median = statistics.median(p.score for p in usable)
    lines = [
        "# 總經發布落差歷史回放（工程報告）", "",
        f"產生時間：{generated_at:%Y-%m-%d %H:%M:%S}（Asia/Taipei，UTC+08:00）", "",
        f"範圍：{START} 至 {END}；以 VIX 有交易資料的日期取樣；"
        f"至少 {MIN_VALID}/{len(WORLD)} 項有有效判定才列入統計。", "",
        f"全期有效日：{len(usable)}；分數中位數：**{median:.1f}**；"
        f"有效項數範圍：{min(p.valid for p in usable)}–"
        f"{max(p.valid for p in usable)}/{len(WORLD)}。", "",
        "| 視窗 | 有效日 | 分數中位數 | 與全期差距（分） | 分數範圍 | 有效項數 |", 
        "|---|---:|---:|---:|---:|---:|",
    ]
    for month in WINDOWS:
        window = [p for p in usable if p.date.strftime("%Y-%m") == month]
        if not window:
            raise ValueError(f"no evaluable dates in {month}")
        value = statistics.median(p.score for p in window)
        lines.append(
            f"| {month} | {len(window)} | {value:.1f} | {value - median:+.1f} | "
            f"{min(p.score for p in window):.1f}–{max(p.score for p in window):.1f} | "
            f"{min(p.valid for p in window)}–{max(p.valid for p in window)} |"
        )
    lines.extend([
        "", "## 計算條件", "",
        "- 每一列先依 `macro_spec.PUBLISH_LAG_DAYS` 加上日曆日落差；評分日只讀已到假定發布日的列。",
        "- CPI +45 天、失業率與非農 +35 天、初領 +5 天、10Y-2Y 利差 +1 天；完整平移表在程式中。",
        "- Yahoo 日價格以當日收盤可見計（+0 天）；FRED 日序列按 T-1 落地（+1 天）。",
        "- 評分規則沿用目前的 `scoring_macro`，FRED 每項最多回看 30 筆，Yahoo 日資料最多回看 130 筆。",
        "- 快照包含世界層 10 項的目前 FRED 與 Yahoo 歷史值；EIA 原油庫存沒有長期快照，未進本次分母。",
        "- FRED 一般歷史序列是目前修訂後的值，固定天數也只是發布日期近似；本報告不是當年資料版本的重建。FRED 的 [real-time periods 說明](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html)指出，預設查詢代表今天可見的歷史資料；要取當年版本需指定歷史 real-time period。",
        "- 本報告只描述這把現有分數尺在歷史上呈現的數字，不推論未來報酬，也不調整警示門檻。",
        "", "## 資料覆蓋", "",
        "| 指標 | 筆數 | 首筆 | 末筆 | 假定落差（天） |", "|---|---:|---|---|---:|",
    ])
    for ind in WORLD:
        rows = series_by_key.get(ind.key, [])
        lines.append(f"| {ind.key} | {len(rows)} | {rows[0][0] if rows else '—'} | "
                     f"{rows[-1][0] if rows else '—'} | {PUBLISH_LAG_DAYS[ind.sid]} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.snapshot.read_text(encoding="utf-8"))
    report = make_report(data, dt.datetime.now())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(args.output)
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

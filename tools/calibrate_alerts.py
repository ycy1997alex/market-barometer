"""Empirical alert-frequency report for the world layer (ToDo §7.2, batch 8-12).

Reads a history snapshot and counts how often each alert fires. Pure
computation: no fetches, no writes to the database, no parameter changes.

⚠️ The output is an engineering report ("what this ruler looked like in
history"), not an accuracy claim. Nothing here touches future returns (§8).

Usage:
  python tools/calibrate_alerts.py --snapshot history.json --years 5 --output report.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer.domain import scoring_macro as sm  # noqa: E402
from barometer.domain.macro_replay import alert_frequency  # noqa: E402
from barometer.domain.macro_spec import BY_KEY, WORLD  # noqa: E402

TARGET_LOW, TARGET_HIGH = 5.0, 15.0   # §7.2：單一指標一年亮燈 5~15 次

# 每個指標目前的門檻寫在哪個具名常數裡 —— 報告要能一眼看到要改哪裡
THRESHOLDS = {
    "vix": "25／35（水位）", "dxy": "±2%（5 日）",
    "us10y": f"±{sm.US10Y_MOVE_PP:.2f}pp（週）",
    "t10y2y": "0（倒掛）", "cpi": "YoY 3%／MoM 0.4%", "unrate": "Sahm 0.5pp",
    "phlfed": "0（榮枯線）", "fedfunds": "近 30 筆有變動",
    "claims": f"{sm.CLAIMS_RISE_PCT:.0f}%（四週均值 vs 近期低點）",
    "payrolls": "月增 < 0",
    "credit_spread": f"{sm.HY_SPREAD_RISE_PP:.2f}pp／{sm.HY_SPREAD_LOOKBACK} 日低點",
    "net_liquidity": f"−{sm.LIQUIDITY_DROP_PCT:.1f}%（{sm.LIQUIDITY_WEEKS} 週）",
    "breadth_us": f"{sm.BREADTH_WEAK_PCT:.0f}%（站上 200MA 比例）",
    "vix_term": "1.0（近月／三個月）",
    "policy_path": f"±{sm.POLICY_GAP_PP:.2f}pp",
    "copper": f"−{sm.METAL_FALL_PCT:.0f}%（{sm.METAL_WINDOW} 日）",
    "gold_oil": f"+{sm.GOLD_OIL_RISE_PCT:.0f}%（{sm.METAL_WINDOW} 日）",
    "jp_exports": "年增率 < 0", "kr_exports": "年增率 < 0",
    "usdjpy": f"±{sm.FX_MOVE_PCT:.2f}%（5 日）", "usdkrw": f"±{sm.FX_MOVE_PCT:.2f}%（5 日）",
    "jp_policy": f"近 {sm.FOREIGN_POLICY_MONTHS} 個月有變動",
    "kr_policy": f"近 {sm.FOREIGN_POLICY_MONTHS} 個月有變動",
}


def verdict(per_year: float) -> str:
    if per_year < TARGET_LOW:
        return "偏少"
    if per_year > TARGET_HIGH:
        return "偏多"
    return "落在區間"


def build_report(stats, start: dt.date, end: dt.date) -> str:
    lines = [
        "# 世界層警示門檻的頻率校準（8-12）",
        "",
        f"視窗：{start} ~ {end}。每一格是「這個門檻在這段歷史上亮了幾次」。",
        "",
        f"⚠️ 這是**頻率統計不是準確率**。§7.2 的目標是單一指標一年亮燈 "
        f"{TARGET_LOW:.0f}~{TARGET_HIGH:.0f} 次；沒有任何一欄跟未來報酬有關（§8）。",
        "⚠️ **調門檻與調分數帶切點擇一**，不要兩個都做。",
        "",
        "| 指標 | 目前門檻 | 可評估天數 | 亮燈天數 | 年均亮燈次數 | 對照 5~15 次 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for ind in WORLD:
        stat = stats.get(ind.key)
        if stat is None:
            continue
        lines.append(
            f"| {ind.name} | {THRESHOLDS.get(ind.key, '—')} | {stat.evaluated:,} | "
            f"{stat.hits:,} | {stat.episodes_per_year:.1f} | {verdict(stat.episodes_per_year)} |"
        )
    missing = [ind.name for ind in WORLD
               if ind.backtest and ind.key not in stats]
    if missing:
        lines += ["", f"沒有歷史因此不在表內：{'、'.join(missing)}。"]
    excluded = [ind.name for ind in WORLD if not ind.backtest]
    if excluded:
        lines += ["", f"刻意不進回測：{'、'.join(excluded)}（§7.1）。"]
    lines += [
        "",
        "## 讀這張表之前要知道的一件事",
        "",
        "**不是每一項都該落在 5~15 次。** 這裡有兩種指標：",
        "",
        "- **事件型**（VIX、DXY、匯率、廣度、期限結構）：亮燈是一次一次的事件，",
        "  5~15 次／年是合理的期待，偏多代表門檻太鬆、偏少代表太緊。",
        "- **狀態型**（10Y-2Y 倒掛、CPI 高於門檻、出口負成長、央行近期動過）：",
        "  它們描述的是一段**持續的狀態**，本來就是亮很久、次數很少。",
        "  10Y-2Y 在這段歷史裡亮了 789 天但只有 0.8 次／年 —— 把它硬調成一年 10 次，",
        "  等於把「倒掛」重新定義成某種短期波動，那會毀掉這一項的意思。",
        "",
        "所以**只有事件型的偏多／偏少才是要處理的訊號**；狀態型看的是亮燈天數比例。",
        "",
        "本報告只數亮燈次數，不改任何參數；要不要調、調哪一邊，是人的決定。",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    raw = json.loads(args.snapshot.read_text(encoding="utf-8"))
    series = {key: [(label, value) for label, value in rows] for key, rows in raw.items()}
    end = dt.date.today()
    start = end - dt.timedelta(days=365 * args.years)

    stats = alert_frequency(series, start, end)
    report = build_report(stats, start, end)
    print(report, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"\n寫出 {args.output}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())

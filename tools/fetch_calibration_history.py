"""Fetch long history for the world-layer alerts (ToDo §7.2, batch 8-12).

One-off engineering input for tools/calibrate_alerts.py. Writes a snapshot JSON
of {indicator key: [(date, value)]}. Indicators whose source cannot provide a
history (the EIA weekly comparison table) are simply absent; the report then
leaves them out instead of pretending they never fire.

Usage:
  python tools/fetch_calibration_history.py --output history.json [--base old.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer.datasources import cboe_src, fred_src, yfinance_src  # noqa: E402
from barometer.datasources.base import FetchError  # noqa: E402
from barometer.domain import breadth, macro_spec  # noqa: E402
from barometer.pipeline import run_macro  # noqa: E402

DEEP_TAIL = 8000          # FRED：拿得到多少就拿多少
MARKET_PERIOD = "10y"     # yfinance：十年日線


def _yf(symbol: str) -> list[tuple[str, float]]:
    bars = yfinance_src.fetch_daily(symbol, period=MARKET_PERIOD)
    return [(b.date.isoformat(), b.close) for b in bars if b.close is not None]


def fetch_one(ind) -> list[tuple[str, float]]:
    if ind.source == "fred":
        return fred_src.fetch(ind.sid, tail=DEEP_TAIL)
    if ind.source == "yfinance":
        return _yf(ind.sid)
    if ind.source == "fred_derived":
        left, right = ind.sid.split("-", 1)
        return run_macro.net_liquidity_series(
            fred_src.fetch(left, tail=DEEP_TAIL), fred_src.fetch(right, tail=DEEP_TAIL))
    if ind.source == "cboe_derived":
        return run_macro.vix_term_series(_yf("^VIX"), cboe_src.fetch_vix3m(tail=DEEP_TAIL))
    if ind.source == "policy_derived":
        left, right = ind.sid.split("-", 1)
        return run_macro.policy_path_series(_yf(f"{left}=F"),
                                            fred_src.fetch(right, tail=DEEP_TAIL))
    if ind.source == "ratio_derived":
        left, right = ind.sid.split("-", 1)
        return run_macro.ratio_series(_yf(f"{left}=F"), _yf(f"{right}=F"))
    if ind.source == "yfinance_breadth":
        closes = {symbol: _yf(symbol) for symbol in run_macro.SECTOR_ETFS}
        ratio, cover = breadth.breadth_series(
            {k: v for k, v in closes.items() if v}, days=0)
        return ratio if ind.sid.endswith("_BREADTH") else cover
    raise FetchError(f"{ind.key}: 這個來源給不出歷史（{ind.source}）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base", type=Path, help="先前的快照，缺的才去抓")
    args = parser.parse_args(argv)

    snapshot: dict[str, list] = {}
    if args.base and args.base.exists():
        snapshot.update(json.loads(args.base.read_text(encoding="utf-8")))
        print(f"沿用既有快照 {len(snapshot)} 條序列")

    for ind in macro_spec.WORLD:
        if not ind.backtest:
            print(f"  {ind.key:16s} 略過（不進回測）")
            continue
        if ind.key in snapshot and snapshot[ind.key]:
            print(f"  {ind.key:16s} 沿用 {len(snapshot[ind.key])} 筆")
            continue
        try:
            rows = fetch_one(ind)
        except Exception as exc:  # noqa: BLE001 — 一條抓不到不擋其他
            print(f"  {ind.key:16s} 沒有歷史：{type(exc).__name__}: {exc}")
            continue
        snapshot[ind.key] = [[label, value] for label, value in rows]
        print(f"  {ind.key:16s} {len(rows):6d} 筆  {rows[0][0]} ~ {rows[-1][0]}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    print(f"\n寫出 {args.output}（{len(snapshot)} 條序列，{dt.date.today()}）")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())

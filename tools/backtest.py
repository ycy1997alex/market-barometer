"""Replay dated score snapshots against adjusted bars with next-open fills."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from barometer import config  # noqa: E402
from barometer.domain.backtest import BacktestParams, run_backtest  # noqa: E402
from barometer.domain.ports import PriceBar  # noqa: E402


def _scores(path: Path) -> dict[dt.date, float]:
    got: dict[dt.date, float] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            day = dt.date.fromisoformat(row["date"])
            if day in got:
                raise ValueError(f"duplicate score date {day}")
            got[day] = float(row["score"])
    return got


def _bars(path: Path, symbol: str) -> list[PriceBar]:
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return [PriceBar(symbol, dt.date.fromisoformat(row["date"]),
                         row["open"], row["high"], row["low"], row["close"],
                         row["volume_shares"], row["source"],
                         dt.datetime.fromisoformat(row["as_of"]), bool(row["stale"]))
                for row in conn.execute("SELECT * FROM price_adjusted WHERE symbol=? AND stale=0 ORDER BY date", (symbol,))]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--scores", type=Path, required=True, help="CSV with date,score snapshots")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=config.db_path())
    args = parser.parse_args(argv)
    bars, scores = _bars(args.db, args.symbol), _scores(args.scores)
    if not bars or not scores:
        raise ValueError("adjusted bars and dated scores are both required")
    market = "tw" if args.symbol.endswith((".TW", ".TWO")) else "us"
    result = run_backtest(bars, BacktestParams(market=market),
                          lambda prefix: scores.get(prefix[-1].date))
    compounded = 1.0
    for trade in result.trades:
        compounded *= 1 + trade.ret_pct / 100
    error_pct = abs(result.equity[-1] - compounded) * 100
    if error_pct >= .5:
        raise ValueError(f"accounting mismatch: {error_pct:.3f} percentage points")
    report = (f"# {args.symbol} 已存分數回測工程檢查\n\n"
              f"只讀訊號當日或之前已存的分數，下一根開盤執行；來源檔須由逐日無前視評分產生。\n\n"
              f"市場日：{len(result.dates)}；交易：{len(result.trades)}；"
              f"會計差：{error_pct:.3f} 個百分點（門檻 0.5）。\n\n"
              "此工具不依未來報酬校準權重。\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

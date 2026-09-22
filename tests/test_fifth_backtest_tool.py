import csv
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

from barometer.domain.ports import PriceBar
from barometer.storage.sqlite_repo import SqliteRepo
from tools.backtest import _bars


def test_cli_replays_precomputed_asof_scores_at_next_open(tmp_path):
    days = [dt.date(2026, 9, 14) + dt.timedelta(days=i) for i in range(5)]
    bars = [PriceBar("2330.TW", day, 100+i, 101+i, 99+i, 100+i,
                     1000, "test", dt.datetime(2026, 9, 21)) for i, day in enumerate(days)]
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(bars)
    score_file = tmp_path / "scores.csv"
    with score_file.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(("date", "score"))
        writer.writerows((day.isoformat(), 90 if i < 2 else -30) for i, day in enumerate(days))
    out = tmp_path / "report.md"
    env = {**os.environ, "STOCKDATA_ROOT": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "tools" / "backtest.py"),
                             "--symbol", "2330.TW", "--scores", str(score_file),
                             "--output", str(out)], capture_output=True, text=True,
                            encoding="utf-8", env=env)
    assert result.returncode == 0, result.stderr
    text = out.read_text(encoding="utf-8")
    assert "下一根開盤" in text and "會計差" in text


def test_backtest_skips_forward_filled_stale_bar(tmp_path):
    day = dt.date(2026, 9, 21)
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices([
            PriceBar("AAPL", day, 100, 101, 99, 100, 1000, "test", dt.datetime(2026, 9, 21), True),
        ])
    assert _bars(tmp_path / "market.db", "AAPL") == []

"""0-2: daily gzip audit keeps each fetch and reads legacy CSV."""

import csv
import datetime as dt
import gzip
import json

from barometer.domain.ports import PriceBar
from barometer.storage import csv_audit
from tools.migrate_price_raw import migrate_day


DAY = dt.date(2026, 9, 18)
SYMBOL = "0050.TW"


def _bar(close):
    return PriceBar(
        symbol=SYMBOL,
        date=DAY,
        open=close,
        high=close,
        low=close,
        close=close,
        volume_shares=1000.0,
        source="yfinance",
        as_of=dt.datetime(2026, 9, 18, 18, 0),
    )


def test_daily_gzip_appends_each_fetch_without_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))

    first = csv_audit.write_raw(SYMBOL, [_bar(100.0)], DAY)
    second = csv_audit.write_raw(SYMBOL, [_bar(101.0)], DAY)

    assert first == second == tmp_path / "price_raw" / "2026-09-18.jsonl.gz"
    with gzip.open(first, "rt", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    assert [row["close"] for row in rows] == ["100.0", "101.0"]
    assert csv_audit.read_raw(DAY) == rows


def test_legacy_csv_remains_readable_and_migrates_without_loss(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    raw_root = tmp_path / "price_raw"
    legacy_dir = raw_root / DAY.isoformat()
    legacy_dir.mkdir(parents=True)
    legacy = legacy_dir / "0050.TW.csv"
    with legacy.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["symbol", "date", "open", "high", "low", "close", "volume_shares", "source", "as_of", "stale"])
        writer.writerow([SYMBOL, DAY.isoformat(), "100.0", "100.0", "100.0", "100.0", "1000.0", "yfinance", "2026-09-18T18:00:00", "0"])
    before = csv_audit.read_raw(DAY)
    assert len(before) == 1

    migrated = migrate_day(raw_root, DAY)

    assert migrated == 1
    assert not legacy.exists()
    assert csv_audit.read_raw(DAY) == before
    assert migrate_day(raw_root, DAY) == 0

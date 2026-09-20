"""Convert legacy per-symbol raw CSVs to one audited JSONL gzip file per day.

Run without ``--apply`` to inspect counts. Applying writes a verified temporary
gzip file, atomically replaces the daily file, then removes only the converted
CSV files. A rerun recognizes an already copied block before cleanup.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer import config  # noqa: E402


def _read_gzip(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _already_copied(existing: list[dict[str, str]], legacy: list[dict[str, str]]) -> bool:
    if not legacy:
        return True
    size = len(legacy)
    return any(row == legacy[0] and existing[index:index + size] == legacy for index, row in enumerate(existing))


def migrate_day(raw_root: Path, run_date: dt.date) -> int:
    """Migrate one day and return its legacy row count; safe to rerun."""
    raw_root = raw_root.resolve()
    day_dir = (raw_root / run_date.isoformat()).resolve()
    if not day_dir.is_relative_to(raw_root):
        raise ValueError("Legacy day directory escaped price_raw root")
    files = sorted(day_dir.glob("*.csv")) if day_dir.exists() else []
    if not files:
        return 0
    legacy: list[dict[str, str]] = []
    for path in files:
        if path.resolve().parent != day_dir:
            raise ValueError(f"Legacy CSV escaped day directory: {path}")
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Malformed legacy CSV: {path}")
                legacy.append(dict(row))
    target = raw_root / f"{run_date.isoformat()}.jsonl.gz"
    existing = _read_gzip(target)
    if not _already_copied(existing, legacy):
        combined = existing + legacy
        with tempfile.NamedTemporaryFile(dir=raw_root, prefix=f".{run_date.isoformat()}.", suffix=".tmp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with gzip.open(temporary_path, "wt", encoding="utf-8", newline="\n") as fh:
                for row in combined:
                    fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            if _read_gzip(temporary_path) != combined:
                raise ValueError(f"Verification failed for {run_date}")
            os.replace(temporary_path, target)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
    if not _already_copied(_read_gzip(target), legacy):
        raise ValueError(f"Legacy records missing after migration for {run_date}")
    for path in files:
        path.unlink()
    if not any(day_dir.iterdir()):
        day_dir.rmdir()
    return len(legacy)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write verified gzip files and remove converted CSVs")
    args = parser.parse_args()
    raw_root = (config.stockdata_root() / "price_raw").resolve()
    days = sorted(path for path in raw_root.iterdir() if path.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name))
    print(f"Legacy days: {len(days)}")
    print(f"Legacy CSV files: {sum(len(list(day.glob('*.csv'))) for day in days)}")
    if not args.apply:
        print("Dry run only; pass --apply to migrate")
        return
    total = 0
    for day in days:
        count = migrate_day(raw_root, dt.date.fromisoformat(day.name))
        print(f"{day.name}: {count} records migrated")
        total += count
    print(f"Verified records migrated: {total}")


if __name__ == "__main__":
    main()

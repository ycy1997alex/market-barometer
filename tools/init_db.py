"""建立資料根目錄與 SQLite schema（ToDo §9 Day 24 第 2 項）。

驗收：列出 §3.5 的六張表。可重複執行，schema.sql 全是 IF NOT EXISTS。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer import config  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402

EXPECTED = {
    "price_daily",
    "price_conflict",
    "macro_cache",
    "score_history",
    "adjustment_event",
    "run_log",
}


def main() -> int:
    config.ensure_dirs()
    print(f"STOCKDATA_ROOT = {config.stockdata_root()}")
    repo = SqliteRepo(config.db_path())
    repo.init_schema()
    tables = repo.tables()
    repo.close()

    print(f"db = {config.db_path()}")
    for t in tables:
        print(f"  - {t}")
    print(f"共 {len(tables)} 張表")

    missing = EXPECTED - set(tables)
    if missing:
        print(f"FAIL 缺少表：{sorted(missing)}")
        return 1
    print("OK 六張表齊備")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

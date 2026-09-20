"""0-3: extending an existing SQLite database must retain its rows."""

import sqlite3

from barometer.storage.sqlite_repo import SqliteRepo


def test_existing_score_history_survives_schema_upgrade(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE score_history (scope TEXT NOT NULL, symbol TEXT NOT NULL, as_of TEXT NOT NULL, score REAL NOT NULL, subscores_json TEXT NOT NULL, price_version TEXT NOT NULL, PRIMARY KEY (scope, symbol, as_of))")
        conn.execute("INSERT INTO score_history VALUES ('stock','2330.TW','2026-09-18',62.0,'{}','v1')")

    with SqliteRepo(path) as repo:
        repo.init_schema()
        columns = {row[1] for row in repo.conn.execute("PRAGMA table_info(score_history)")}
        old = repo.get_scores("stock", "2330.TW")

    assert {"comparable", "native", "strength"} <= columns
    assert len(old) == 1 and old[0].score == 62.0
    assert old[0].native is None


def test_each_new_table_has_data_date_and_retrieval_time(tmp_path):
    with SqliteRepo(tmp_path / "new.db") as repo:
        repo.init_schema()
        for table in ("stock_chip_daily", "price_adjusted", "tw_stock_daily", "tw_market_daily", "tw_stock_weekly", "tw_stock_monthly", "us_stock_local"):
            columns = {row[1] for row in repo.conn.execute(f"PRAGMA table_info({table})")}
            assert "as_of" in columns
            assert "date" in columns or "data_date" in columns
        stock_chip_pk = [row[1] for row in repo.conn.execute("PRAGMA table_info(stock_chip_daily)") if row[5]]
        assert stock_chip_pk == ["date", "symbol"]

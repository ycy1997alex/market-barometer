"""SQLite adapter —— 實作 domain/ports.py 的三個 Port（被驅動側 adapter）。

這一層知道 SQL，domain 不知道。表現層也不知道（tests/test_layer_boundary.py 守著）。
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from barometer.domain.ports import MacroSeries, PriceBar, ScoreRecord

_SCHEMA = Path(__file__).with_name("schema.sql")


def _as_date(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


class SqliteRepo:
    """一個連線同時實作 PriceRepository / MacroRepository / ScoreHistoryRepository。

    三個 Port 分開定義是為了讓 domain 只依賴它真正用到的那一個；
    實作合在一起只是因為它們共用一個資料庫檔，這不影響上層的抽象。
    """

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self.conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SqliteRepo":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def tables(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    # ---------------- PriceRepository ----------------

    def upsert_prices(self, bars: list[PriceBar]) -> int:
        rows = [
            (
                b.symbol, b.date.isoformat(), b.open, b.high, b.low, b.close,
                b.volume_shares, b.source, b.as_of.isoformat(), int(b.stale),
            )
            for b in bars
        ]
        self.conn.executemany(
            "INSERT INTO price_daily "
            "(symbol,date,open,high,low,close,volume_shares,source,as_of,stale) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(symbol,date) DO UPDATE SET "
            "open=excluded.open, high=excluded.high, low=excluded.low, "
            "close=excluded.close, volume_shares=excluded.volume_shares, "
            "source=excluded.source, as_of=excluded.as_of, stale=excluded.stale",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def get_prices(
        self,
        symbol: str,
        start: dt.date | None = None,
        end: dt.date | None = None,
    ) -> list[PriceBar]:
        sql = "SELECT * FROM price_daily WHERE symbol = ?"
        params: list[object] = [symbol]
        if start:
            sql += " AND date >= ?"
            params.append(start.isoformat())
        if end:
            sql += " AND date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY date"
        return [
            PriceBar(
                symbol=r["symbol"],
                date=dt.date.fromisoformat(r["date"]),
                open=r["open"], high=r["high"], low=r["low"], close=r["close"],
                volume_shares=r["volume_shares"],
                source=r["source"],
                as_of=dt.datetime.fromisoformat(r["as_of"]),
                stale=bool(r["stale"]),
            )
            for r in self.conn.execute(sql, params)
        ]

    def last_price_date(self, symbol: str) -> dt.date | None:
        row = self.conn.execute(
            "SELECT MAX(date) AS d FROM price_daily WHERE symbol = ?", (symbol,)
        ).fetchone()
        return _as_date(row["d"] if row else None)

    def record_conflict(
        self,
        symbol: str,
        date: dt.date,
        field: str,
        shioaji_value: float | None,
        yf_value: float | None,
        taken: str,
        as_of: dt.datetime,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO price_conflict "
            "(symbol,date,field,shioaji_value,yf_value,taken,as_of) "
            "VALUES (?,?,?,?,?,?,?)",
            (symbol, date.isoformat(), field, shioaji_value, yf_value,
             taken, as_of.isoformat()),
        )
        self.conn.commit()

    def get_conflicts(self, date: dt.date) -> list[dict]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM price_conflict WHERE date = ? ORDER BY symbol, field",
                (date.isoformat(),),
            )
        ]

    # ---------------- MacroRepository ----------------

    def put_macro(
        self,
        key: str,
        series: list[tuple[str, float]],
        fetched_at: dt.datetime,
        data_date: dt.date | None,
        stale_reason: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO macro_cache "
            "(key,series_json,fetched_at,data_date,stale_reason) VALUES (?,?,?,?,?)",
            (
                key,
                json.dumps(series, ensure_ascii=False),
                fetched_at.isoformat(),
                data_date.isoformat() if data_date else None,
                stale_reason,
            ),
        )
        self.conn.commit()

    def get_macro(self, key: str) -> MacroSeries | None:
        row = self.conn.execute(
            "SELECT * FROM macro_cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return MacroSeries(
            key=row["key"],
            series=[tuple(x) for x in json.loads(row["series_json"])],
            fetched_at=dt.datetime.fromisoformat(row["fetched_at"]),
            data_date=_as_date(row["data_date"]),
            stale_reason=row["stale_reason"],
        )

    # ---------------- ScoreHistoryRepository ----------------

    def put_score(
        self,
        scope: str,
        symbol: str,
        as_of: dt.date,
        score: float,
        subscores: dict[str, float],
        price_version: str,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO score_history "
            "(scope,symbol,as_of,score,subscores_json,price_version) "
            "VALUES (?,?,?,?,?,?)",
            (scope, symbol, as_of.isoformat(), score,
             json.dumps(subscores, ensure_ascii=False), price_version),
        )
        self.conn.commit()

    def get_scores(self, scope: str, symbol: str) -> list[ScoreRecord]:
        return [
            ScoreRecord(
                scope=r["scope"],
                symbol=r["symbol"],
                as_of=dt.date.fromisoformat(r["as_of"]),
                score=r["score"],
                subscores=json.loads(r["subscores_json"]),
                price_version=r["price_version"],
            )
            for r in self.conn.execute(
                "SELECT * FROM score_history WHERE scope = ? AND symbol = ? "
                "ORDER BY as_of",
                (scope, symbol),
            )
        ]

    # ---------------- adjustment_event / run_log ----------------

    def record_adjustment(
        self,
        symbol: str,
        detected_at: dt.datetime,
        event_date: dt.date | None,
        ratio: float | None,
        rows_affected: int | None,
        note: str,
    ) -> None:
        """§4.4 第 3 點：重抓是手動的，這裡只留下「修過了」的紀錄。"""
        self.conn.execute(
            "INSERT OR REPLACE INTO adjustment_event "
            "(symbol,detected_at,event_date,ratio,rows_affected,note) "
            "VALUES (?,?,?,?,?,?)",
            (symbol, detected_at.isoformat(),
             event_date.isoformat() if event_date else None,
             ratio, rows_affected, note),
        )
        self.conn.commit()

    def record_run(
        self,
        run_id: str,
        task: str,
        started_at: dt.datetime,
        ended_at: dt.datetime | None,
        status: str,
        counts: dict | None = None,
        quota: dict | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO run_log "
            "(run_id,task,started_at,ended_at,status,counts_json,quota_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (run_id, task, started_at.isoformat(),
             ended_at.isoformat() if ended_at else None, status,
             json.dumps(counts or {}, ensure_ascii=False),
             json.dumps(quota or {}, ensure_ascii=False)),
        )
        self.conn.commit()

    # ---------------- ChipRepository ----------------

    def put_chips(self, date: dt.date, payload: dict, as_of: dt.datetime) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO chip_daily (date,payload_json,as_of) "
            "VALUES (?,?,?)",
            (date.isoformat(), json.dumps(payload, ensure_ascii=False),
             as_of.isoformat()),
        )
        self.conn.commit()

    def get_chips(self, date: dt.date) -> dict | None:
        """查不到就是 None —— **不回一個全零的 dict**（§10「還沒公布」不是 0）。"""
        row = self.conn.execute(
            "SELECT payload_json FROM chip_daily WHERE date = ?", (date.isoformat(),)
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def get_chip_range(
        self, start: dt.date, end: dt.date
    ) -> list[tuple[dt.date, dict]]:
        return [
            (dt.date.fromisoformat(r["date"]), json.loads(r["payload_json"]))
            for r in self.conn.execute(
                "SELECT date, payload_json FROM chip_daily "
                "WHERE date >= ? AND date <= ? ORDER BY date",
                (start.isoformat(), end.isoformat()),
            )
        ]

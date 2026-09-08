"""Day 24 第 3 項驗收：「寫一個 InMemory* 假實作跑通同一組測試」。

同一組測試同時餵給 SqliteRepo 與 InMemoryRepo。兩邊都過，才證明 Port 抽對了 ——
表現層拿到哪一個實作都不該有差別，這正是 §3.2 想要的好處。
"""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.domain.ports import PriceBar
from barometer.storage.sqlite_repo import SqliteRepo
from barometer.storage.memory_repo import InMemoryRepo


@pytest.fixture(params=["sqlite", "memory"])
def repo(request, tmp_path):
    if request.param == "sqlite":
        r = SqliteRepo(tmp_path / "test.db")
        r.init_schema()
        yield r
        r.close()
    else:
        yield InMemoryRepo()


def bar(date: str, close: float, symbol: str = "0050.TW", **kw) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        date=dt.date.fromisoformat(date),
        open=kw.get("open", close),
        high=kw.get("high", close),
        low=kw.get("low", close),
        close=close,
        volume_shares=kw.get("volume_shares", 1_000_000),
        source=kw.get("source", "yfinance"),
        as_of=kw.get("as_of", dt.datetime(2026, 9, 6, 18, 0)),
        stale=kw.get("stale", False),
    )


class TestPriceRepository:
    def test_roundtrip_single_bar(self, repo):
        repo.upsert_prices([bar("2026-09-04", 106.20)])
        got = repo.get_prices("0050.TW")
        assert len(got) == 1
        assert got[0].close == pytest.approx(106.20)
        assert got[0].date == dt.date(2026, 9, 4)

    def test_returns_sorted_by_date_ascending(self, repo):
        repo.upsert_prices(
            [bar("2026-09-04", 3.0), bar("2026-09-02", 1.0), bar("2026-09-03", 2.0)]
        )
        assert [b.close for b in repo.get_prices("0050.TW")] == [1.0, 2.0, 3.0]

    def test_upsert_overwrites_same_symbol_and_date(self, repo):
        repo.upsert_prices([bar("2026-09-04", 100.0)])
        repo.upsert_prices([bar("2026-09-04", 106.20)])
        got = repo.get_prices("0050.TW")
        assert len(got) == 1, "同一個 (symbol, date) 必須是覆寫，不是長出第二列"
        assert got[0].close == pytest.approx(106.20)

    def test_symbols_do_not_bleed_into_each_other(self, repo):
        repo.upsert_prices([bar("2026-09-04", 106.20, symbol="0050.TW")])
        repo.upsert_prices([bar("2026-09-04", 46551.13, symbol="^TWII")])
        assert len(repo.get_prices("0050.TW")) == 1
        assert repo.get_prices("^TWII")[0].close == pytest.approx(46551.13)

    def test_date_range_filter(self, repo):
        repo.upsert_prices([bar(f"2026-09-0{d}", float(d)) for d in range(1, 6)])
        got = repo.get_prices(
            "0050.TW", start=dt.date(2026, 9, 2), end=dt.date(2026, 9, 4)
        )
        assert [b.date.day for b in got] == [2, 3, 4]

    def test_unknown_symbol_is_empty_not_error(self, repo):
        assert repo.get_prices("NOPE") == []

    def test_stale_flag_survives_roundtrip(self, repo):
        """§4.3：缺值那格標 stale，讀回來要還在。"""
        repo.upsert_prices([bar("2026-09-04", 106.20, stale=True)])
        assert repo.get_prices("0050.TW")[0].stale is True

    def test_last_date_reports_latest_stored(self, repo):
        assert repo.last_price_date("0050.TW") is None
        repo.upsert_prices([bar("2026-09-02", 1.0), bar("2026-09-04", 3.0)])
        assert repo.last_price_date("0050.TW") == dt.date(2026, 9, 4)


class TestConflictLog:
    def test_records_and_reads_back(self, repo):
        """§4.2：衝突取 shioaji，但兩邊的值都要留著才查得出來。"""
        repo.record_conflict(
            symbol="2330.TW",
            date=dt.date(2026, 9, 4),
            field="close",
            shioaji_value=1250.0,
            yf_value=1248.0,
            taken="shioaji",
            as_of=dt.datetime(2026, 9, 6, 18, 0),
        )
        rows = repo.get_conflicts(dt.date(2026, 9, 4))
        assert len(rows) == 1
        assert rows[0]["taken"] == "shioaji"
        assert rows[0]["shioaji_value"] == pytest.approx(1250.0)
        assert rows[0]["yf_value"] == pytest.approx(1248.0)

    def test_empty_day_is_empty_list(self, repo):
        assert repo.get_conflicts(dt.date(2026, 9, 4)) == []


class TestMacroCache:
    def test_roundtrip_series(self, repo):
        series = [("2026-07-01", 3.1), ("2026-08-01", 3.2)]
        repo.put_macro("cpi", series, fetched_at=dt.datetime(2026, 9, 6, 12, 0),
                       data_date=dt.date(2026, 8, 1))
        got = repo.get_macro("cpi")
        assert got is not None
        assert got.series == series
        assert got.data_date == dt.date(2026, 8, 1)

    def test_missing_key_is_none(self, repo):
        assert repo.get_macro("nope") is None

    def test_put_replaces_previous(self, repo):
        repo.put_macro("cpi", [("2026-08-01", 3.2)],
                       fetched_at=dt.datetime(2026, 9, 6, 12, 0),
                       data_date=dt.date(2026, 8, 1))
        repo.put_macro("cpi", [("2026-09-01", 3.4)],
                       fetched_at=dt.datetime(2026, 9, 6, 13, 0),
                       data_date=dt.date(2026, 9, 1))
        got = repo.get_macro("cpi")
        assert got.series == [("2026-09-01", 3.4)]


class TestScoreHistory:
    def test_roundtrip_with_subscores(self, repo):
        repo.put_score(
            scope="index", symbol="0050.TW", as_of=dt.date(2026, 9, 4),
            score=62.0, subscores={"rsi": 40.0, "ma": 70.0}, price_version="v1",
        )
        rows = repo.get_scores("index", "0050.TW")
        assert len(rows) == 1
        assert rows[0].score == pytest.approx(62.0)
        assert rows[0].subscores["rsi"] == pytest.approx(40.0)
        assert rows[0].price_version == "v1"

    def test_series_is_sorted_ascending(self, repo):
        for day, sc in [(4, 62.0), (2, 58.0), (3, 60.0)]:
            repo.put_score(scope="index", symbol="0050.TW",
                           as_of=dt.date(2026, 9, day), score=sc,
                           subscores={}, price_version="v1")
        assert [r.score for r in repo.get_scores("index", "0050.TW")] == [58.0, 60.0, 62.0]

    def test_same_day_rescoring_overwrites(self, repo):
        """§3.5：重抓後要重算，同一天不該留下兩筆互相矛盾的分數。"""
        for sc in (62.0, 65.0):
            repo.put_score(scope="index", symbol="0050.TW",
                           as_of=dt.date(2026, 9, 4), score=sc,
                           subscores={}, price_version="v2")
        rows = repo.get_scores("index", "0050.TW")
        assert len(rows) == 1 and rows[0].score == pytest.approx(65.0)


class TestChipRepository:
    """市場級籌碼面的落地（ToDo §9 Day 26 第 2 項）。

    一天一列、payload 直接塞 JSON —— 跟 §3.2 說的一樣，扁平表、零 JOIN、
    不上 ORM。籌碼面的欄位還會變（融資維持率至今找不到市場級的來源），
    塞 JSON 就不必為了加一個欄位改 schema。
    """

    def test_roundtrip(self, repo):
        payload = {
            "margin_lots": 8_919_251,
            "fut_foreign_net_oi_contracts": -82_389,
            "pc_oi_ratio_pct": 99.8,
        }
        repo.put_chips(dt.date(2026, 9, 4), payload,
                       as_of=dt.datetime(2026, 9, 6, 19, 0))
        got = repo.get_chips(dt.date(2026, 9, 4))
        assert got["margin_lots"] == pytest.approx(8_919_251)
        assert got["fut_foreign_net_oi_contracts"] == pytest.approx(-82_389)

    def test_missing_day_is_none_not_zero(self, repo):
        """§10：「還沒公布」不是 0。查不到就是 None，不要回一個假的零。"""
        assert repo.get_chips(dt.date(2026, 9, 6)) is None

    def test_range_is_sorted_ascending(self, repo):
        for day, lots in [(4, 8_919_251), (2, 8_800_000), (3, 8_902_986)]:
            repo.put_chips(dt.date(2026, 9, day), {"margin_lots": lots},
                           as_of=dt.datetime(2026, 9, 6, 19, 0))
        rows = repo.get_chip_range(dt.date(2026, 9, 1), dt.date(2026, 9, 30))
        assert [d for d, _ in rows] == [
            dt.date(2026, 9, 2), dt.date(2026, 9, 3), dt.date(2026, 9, 4)
        ]
        assert rows[-1][1]["margin_lots"] == pytest.approx(8_919_251)

    def test_put_replaces_same_day(self, repo):
        """今日餘額是暫定值，隔天會被前日餘額改寫 —— 同一天只能有一列。"""
        repo.put_chips(dt.date(2026, 9, 4), {"margin_lots": 8_919_251},
                       as_of=dt.datetime(2026, 9, 4, 19, 0))
        repo.put_chips(dt.date(2026, 9, 4), {"margin_lots": 8_902_986},
                       as_of=dt.datetime(2026, 9, 5, 19, 0))
        assert repo.get_chips(dt.date(2026, 9, 4))["margin_lots"] == pytest.approx(
            8_902_986
        )

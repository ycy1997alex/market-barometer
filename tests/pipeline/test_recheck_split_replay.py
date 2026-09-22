"""回補批 R-2：4-3 的分割偵測在正式資料上從未觸發過。

正式庫 `adjustment_event` 是 0 列 —— `price_daily` 最早只到 2025-09-04，
0050 的 4:1 分割在 2025-06-18，事件落在價格史起點之前，這條路沒有機會跑到。
原本的 `test_split_notice.py` 用的是手寫的 188 → 47；這一份改用**當天真的收盤價**
（`tests/fixtures/split_0050_202506.json`，證交所 STOCK_DAY 原始價 + yfinance 還原價）
端到端跑一次，確認偵測、公告核對與「只記旗標不改資料」在真實序列上成立。
"""
import ast
import datetime as dt
import json
from pathlib import Path

from barometer.domain.ports import PriceBar
from barometer.pipeline import fetch_prices
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "split_0050_202506.json")
    .read_text(encoding="utf-8")
)
AS_OF = dt.datetime(2025, 6, 30, 16)
EVENT = dt.date(2025, 6, 18)
RUN_DATE = dt.date(2025, 6, 30)


def _bars(block: str, source: str) -> list[PriceBar]:
    return [PriceBar("0050.TW", dt.date.fromisoformat(row["date"]), row["open"],
                     row["high"], row["low"], row["close"], row["volume_shares"],
                     source, AS_OF)
            for row in FIXTURE[block]["rows"]]


def test_real_june_2025_series_is_confirmed_against_the_twse_notice(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    official = _bars("twse_stock_day", "twse")        # 官方原始價（未還原）
    adjusted = _bars("yfinance", "yfinance")          # yfinance 已把分割前的價格除以 4

    # 真實資料本身就要先站得住：分割前整段固定四倍，分割後兩邊一致
    before = {b.date: b.close for b in official if b.date < EVENT}
    pre = [b for b in adjusted if b.date in before]
    assert pre and all(abs(before[b.date] / b.close - 4) < 0.01 for b in pre)
    after = {b.date: b.close for b in official if b.date >= EVENT}
    post = [b for b in adjusted if b.date in after]
    assert post and all(abs(after[b.date] - b.close) < 0.01 for b in post)

    csv_audit.write_current("0050.TW", official)
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_prices(official)
    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily", lambda *a, **k: adjusted)
    monkeypatch.setattr(fetch_prices.twse_src, "fetch_stock_day_all", lambda _: {})

    log = fetch_prices.run(["0050.TW"], "recheck_split_replay", run_date=RUN_DATE)

    with SqliteRepo(tmp_path / "market.db") as repo:
        events = repo.conn.execute("SELECT * FROM adjustment_event").fetchall()
        assert len(events) == 1
        assert events[0]["event_date"] == EVENT.isoformat()
        assert events[0]["ratio"] == 4.0
        assert "twse.com.tw" in events[0]["note"]          # 來源是證交所公告
        assert "yfinance" not in events[0]["note"]
    assert log.counts["split_notices"] == 1
    assert (tmp_path / "ALERT.md").exists()
    # 只記旗標：原始價一根都沒被改寫
    assert csv_audit.read_current("0050.TW") == official


def test_the_fixture_shows_yfinance_never_reported_the_split():
    """把「不能靠 yfinance 的 `Stock Splits`」從註解變成事實。

    當天抓下來的那 21 根裡，`Stock Splits` 全是 0 —— 真的照它判就會漏掉這次分割。
    """
    flags = [row["stock_splits"] for row in FIXTURE["yfinance"]["rows"]]
    assert flags and set(flags) == {0.0}


def test_no_production_module_reads_the_yfinance_split_column():
    root = Path(__file__).resolve().parents[2] / "src" / "barometer"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.replace("_", " ").lower() == "stock splits"
            for node in ast.walk(tree)
        ), path

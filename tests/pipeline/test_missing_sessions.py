"""少了一個交易日要有人喊（2026-09-18 撞到的坑，ToDo §10）。

驗收：**同一批抓取裡，某一檔缺了同批其他標的都有的交易日時，run log 要有一筆
`missing_sessions::<symbol>`，並在 notes 說出是哪幾天。**

為什麼需要這條：`0050.TW` 的洞連續四天沒有任何警報。既有的 `stale` 欄位只認
「有這一格但值是空的」，整列不存在不算；`compare_overlap` 只看重疊日期，
不在重疊裡的日期它連看都不看。**兩個偵測器都是對的，只是都不看這個方向。**

參考基準是「同一批的聯集」，不是交易日曆 —— 這個專案刻意不維護交易日曆
（颱風假、臨時休市、資料延遲都會讓它過期）。同一批裡別人有、我沒有，
本身就是夠強的訊號。

**但比較必須分市場。** `day24_stocks` 那一批混了台股與美股 15 檔，
2026-09-07 美國勞動節台股照常 —— 拿聯集去比會讓每一檔都亮燈。
"""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.domain import windows
from barometer.domain.ports import PriceBar
from barometer.pipeline import fetch_prices, runlog


def _d(day: int) -> dt.date:
    return dt.date(2026, 9, day)


# ---------------- 純函式（domain 層，零 I/O） ----------------

def test_missing_sessions_finds_the_hole():
    assert windows.missing_sessions(
        [_d(15), _d(16), _d(18)], [_d(15), _d(16), _d(17), _d(18)]
    ) == [_d(17)]


def test_missing_sessions_ignores_dates_outside_own_range():
    """歷史比較短的標的不該把它上市之前的每一天都報成缺漏。

    `SPCX` 只有 67 根，同一批的 `NVDA` 有 251 根 —— 那不是洞。
    """
    assert windows.missing_sessions(
        [_d(16), _d(17)], [_d(14), _d(15), _d(16), _d(17), _d(18)]
    ) == []


def test_missing_sessions_empty_series_is_not_all_holes():
    """本機沒有序列是另一回事（`no_data`），不要在這裡變成一長串缺漏。"""
    assert windows.missing_sessions([], [_d(16), _d(17)]) == []


# ---------------- 管線（run log 要看得到） ----------------

@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    return tmp_path


def _bars(symbol: str, days: list[int]) -> list[PriceBar]:
    return [
        PriceBar(symbol=symbol, date=_d(day), open=100.0, high=101.0, low=99.0,
                 close=100.0, volume_shares=1000.0, source="test",
                 as_of=dt.datetime(2026, 9, 18, 18, 0, 0))
        for day in days
    ]


def _fake_source(monkeypatch, by_symbol: dict[str, list[int]]):
    monkeypatch.setattr(
        fetch_prices.yfinance_src, "fetch_daily",
        lambda symbol, **kw: _bars(symbol, by_symbol[symbol]),
    )


def test_hole_lands_in_the_run_log(isolated_root, monkeypatch):
    """實際發生的那一種：指數有 9/17，兩檔 ETF 沒有。"""
    _fake_source(monkeypatch, {
        "^TWII": [15, 16, 17, 18],
        "0050.TW": [15, 16, 18],
        "006208.TW": [15, 16, 18],
    })

    log = fetch_prices.run(["^TWII", "0050.TW", "006208.TW"],
                           task="test_tw", run_date=_d(18))

    assert log.counts.get("missing_sessions::0050.TW") == 1
    assert log.counts.get("missing_sessions::006208.TW") == 1
    assert "missing_sessions::^TWII" not in log.counts
    assert any("0050.TW" in n and "2026-09-17" in n for n in log.notes), log.notes


def test_run_log_on_disk_carries_it_too(isolated_root, monkeypatch):
    """排程跑完之後人只看得到 jsonl —— 記憶體裡的那份不算數。"""
    _fake_source(monkeypatch, {"^TWII": [15, 16, 17], "0050.TW": [15, 17]})
    fetch_prices.run(["^TWII", "0050.TW"], task="test_tw", run_date=_d(18))

    runs = [r for r in runlog.read_runs("2026-09") if r["task"] == "test_tw"]
    assert runs and runs[-1]["counts"].get("missing_sessions::0050.TW") == 1


def test_two_markets_in_one_batch_do_not_flag_each_other(isolated_root, monkeypatch):
    """`day24_stocks` 那一批混了兩個市場。9/7 美國勞動節，台股照常。

    這一條是回歸測試：拿整批的聯集去比，15 檔會全部亮燈。
    """
    _fake_source(monkeypatch, {
        "2330.TW": [7, 8, 9],   # 台股 9/7 有交易
        "NVDA": [8, 9],         # 美股 9/7 勞動節休市
    })

    log = fetch_prices.run(["2330.TW", "NVDA"], task="test_mixed", run_date=_d(18))

    assert not [k for k in log.counts if k.startswith("missing_sessions::")], log.counts


def test_no_hole_no_noise(isolated_root, monkeypatch):
    """正常的一天，run log 裡不該多出任何 missing_sessions。"""
    _fake_source(monkeypatch, {"^TWII": [16, 17], "0050.TW": [16, 17]})
    log = fetch_prices.run(["^TWII", "0050.TW"], task="test_tw", run_date=_d(18))

    assert not [k for k in log.counts if k.startswith("missing_sessions::")]

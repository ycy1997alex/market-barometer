"""`write_current` 不得讓計算用的那份序列縮短（2026-09-18 撞到的坑，ToDo §10）。

驗收：**`write_current` 不得讓 `price_current` 的交易日數量減少** —— 來源這次
沒回、本機已存的日期要留著，並記進 run log。

這條規則來自一次連續四天沒人發現的失效：yfinance 回 `0050.TW`、`006208.TW`
時固定會漏掉前一個交易日（隔天才補），而 `write_current` 是整份覆寫，於是
`price_current\\0050.TW.csv` 每天都有一個洞。SQLite 那份沒有洞（upsert 累積），
但 `build_page._index_rows()` 讀的是 CSV，所以發布出去的五日視窗真的少一根 K，
同一張表上的 `^TWII` 卻是完整的 —— 同一頁兩種口徑。

**這是補洞（backfill，§4.1），不是重抓。** 既有的列一個值都不動，只是來源
這次沒回的日期不要被刪掉。整條覆寫仍然存在，但只留給 `tools/refetch.py`
（`replace=True`）—— 那一支本來就只能手動觸發（§1 紅線 6）。
"""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.domain.ports import PriceBar
from barometer.storage import csv_audit

SYMBOL = "0050.TW"


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    """整個資料層指到暫存目錄 —— `config.root()` 每次都重讀環境變數。"""
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    return tmp_path


def _bar(day: int, close: float, source: str = "yfinance") -> PriceBar:
    return PriceBar(
        symbol=SYMBOL,
        date=dt.date(2026, 9, day),
        open=close, high=close, low=close, close=close,
        volume_shares=1000.0,
        source=source,
        as_of=dt.datetime(2026, 9, day, 18, 0, 0),
    )


def _dates(symbol: str = SYMBOL) -> list[dt.date]:
    return [b.date for b in csv_audit.read_current(symbol)]


def test_retains_the_session_the_source_stopped_returning(isolated_root):
    """實際發生的那一種：昨天有 9/17，今天抓回來的序列裡沒有它。"""
    csv_audit.write_current(SYMBOL, [_bar(15, 106.9), _bar(16, 107.4), _bar(17, 108.0)])
    csv_audit.write_current(SYMBOL, [_bar(15, 106.9), _bar(16, 107.4), _bar(18, 109.85)])

    assert _dates() == [
        dt.date(2026, 9, 15), dt.date(2026, 9, 16),
        dt.date(2026, 9, 17), dt.date(2026, 9, 18),
    ]


def test_retained_row_keeps_its_original_values(isolated_root):
    """保留下來的那一列是原封不動的那一列，不是拿旁邊的值補出來的。"""
    csv_audit.write_current(SYMBOL, [_bar(16, 107.4), _bar(17, 108.0)])
    csv_audit.write_current(SYMBOL, [_bar(16, 107.4), _bar(18, 109.85)])

    kept = next(b for b in csv_audit.read_current(SYMBOL) if b.date == dt.date(2026, 9, 17))
    assert kept.close == 108.0
    assert kept.as_of == dt.datetime(2026, 9, 17, 18, 0, 0)


def test_new_fetch_wins_on_the_same_date(isolated_root):
    """同一天兩邊都有 → 以這次抓回來的為準。

    來源回頭改寫歷史是 `compare_overlap` 的職責（記旗標），不是這裡的。
    這裡只負責「不要把列弄不見」。
    """
    csv_audit.write_current(SYMBOL, [_bar(16, 107.4)])
    csv_audit.write_current(SYMBOL, [_bar(16, 31.69)])

    bars = csv_audit.read_current(SYMBOL)
    assert len(bars) == 1
    assert bars[0].close == 31.69


def test_result_reports_which_sessions_were_retained(isolated_root):
    """回傳值要說得出保留了哪幾天 —— run log 記的就是這個。

    安靜地補洞跟安靜地挖洞一樣糟：兩者事後都查不出來。
    """
    csv_audit.write_current(SYMBOL, [_bar(16, 107.4), _bar(17, 108.0)])
    result = csv_audit.write_current(SYMBOL, [_bar(16, 107.4), _bar(18, 109.85)])

    assert result.retained == [dt.date(2026, 9, 17)]
    assert result.path.exists()


def test_nothing_retained_when_the_source_is_complete(isolated_root):
    """正常的一天不該留下任何紀錄 —— 每天都報一句就沒有人會再讀它。"""
    csv_audit.write_current(SYMBOL, [_bar(16, 107.4)])
    result = csv_audit.write_current(SYMBOL, [_bar(16, 107.4), _bar(17, 108.0)])

    assert result.retained == []


def test_replace_truly_overwrites(isolated_root):
    """`tools/refetch.py` 的入口：整條覆寫仍然要做得到，但要明講。

    重抓的用途正是「本機這份是錯的」，這時候保留舊列會把要修掉的東西留下來。
    """
    csv_audit.write_current(SYMBOL, [_bar(15, 106.9), _bar(16, 107.4), _bar(17, 108.0)])
    result = csv_audit.write_current(SYMBOL, [_bar(16, 107.4)], replace=True)

    assert _dates() == [dt.date(2026, 9, 16)]
    assert result.retained == []


def test_merged_series_is_sorted_by_date(isolated_root):
    """合併之後要照日期排好 —— 下游的 `score_series` 直接吃這個順序。"""
    csv_audit.write_current(SYMBOL, [_bar(17, 108.0)])
    csv_audit.write_current(SYMBOL, [_bar(15, 106.9), _bar(16, 107.4)])

    assert _dates() == sorted(_dates())

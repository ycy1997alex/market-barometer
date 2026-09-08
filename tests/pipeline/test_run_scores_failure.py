"""管線中止時仍要留下 runlog（2026-09-08）。

`summarize_window` 現在會對不滿五天的標的直接報錯（大聲失敗，刻意的）。
但原本 `run()` 只有 `try/finally` —— `record_run()` 與 `log.append()` 都在
`try` 的尾巴，錯誤一往上拋就全部跳過了。

**結果是失敗的那一次在 runlog 裡完全不存在。** 這比失敗本身更麻煩：

  - runlog 是 Day 28 回顧的主體之一，價格可以事後回補，執行紀錄補不回來
  - 「昨天到底有沒有跑」變成無法回答 —— 沒有紀錄，跟沒有排程長得一模一樣

所以要包一層 except：**記完 runlog 再重拋**。重拋是重點 ——
吞掉的話就變回「安靜失敗」，那正是這次要避免的。

測試用 `tmp_path` 改寫 STOCKDATA_ROOT，所以完全不碰真的資料層。
"""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.domain.ports import PriceBar
from barometer.pipeline import run_scores, runlog


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    """把整個資料層指到暫存目錄 —— `config.root()` 每次都重讀環境變數。"""
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    return tmp_path


def _bars(symbol: str, n: int) -> list[PriceBar]:
    days = [dt.date(2026, 9, d) for d in (1, 2, 3, 4, 7)][:n]
    now = dt.datetime(2026, 9, 8, 18, 0, 0)
    return [
        PriceBar(symbol=symbol, date=d, open=100.0, high=101.0, low=99.0,
                 close=100.0, volume_shares=1000.0, source="test", as_of=now)
        for d in days
    ]


@pytest.fixture
def three_days(monkeypatch):
    """本機只有 3 個交易日 —— 新上市或剛加進清單的標的就長這樣。"""
    monkeypatch.setattr(
        run_scores.csv_audit, "read_current",
        lambda symbol, **kw: _bars(symbol, 3),
    )


def _runs(started: dt.datetime | None = None) -> list[dict]:
    month = (started or dt.datetime.now()).strftime("%Y-%m")
    return runlog.read_runs(month)


def test_short_history_still_raises(isolated_root, three_days):
    """先確認「大聲失敗」本身沒有被這次的修改弄不見。"""
    with pytest.raises(ValueError, match="0050.TW"):
        run_scores.run(["0050.TW"])


def test_failed_run_is_recorded_in_the_runlog(isolated_root, three_days):
    """中止的那一次也要在 runlog 裡看得到。"""
    with pytest.raises(ValueError):
        run_scores.run(["0050.TW"], task="test_scores")

    runs = _runs()
    assert len(runs) == 1, "失敗的執行沒有留下任何 runlog"
    assert runs[0]["task"] == "test_scores"


def test_failed_run_is_marked_error_not_ok(isolated_root, three_days):
    with pytest.raises(ValueError):
        run_scores.run(["0050.TW"])

    assert _runs()[0]["status"] == "error"


def test_failed_run_records_why(isolated_root, three_days):
    """光知道「失敗了」不夠 —— runlog 要說出是哪一檔、為什麼。"""
    with pytest.raises(ValueError):
        run_scores.run(["0050.TW"])

    notes = " ".join(_runs()[0]["notes"])
    assert "0050.TW" in notes
    assert "3/5" in notes


def test_failed_run_keeps_the_counts_it_got_to(isolated_root, three_days):
    """炸掉之前已經算完的部分要留著 —— 那是「跑到哪裡」的唯一線索。"""
    with pytest.raises(ValueError):
        run_scores.run(["0050.TW"])

    counts = _runs()[0]["counts"]
    assert "scored::0050.TW" not in counts   # 這一檔沒走完
    assert _runs()[0]["ended_at"] is not None


def test_successful_run_still_records_ok(isolated_root, monkeypatch):
    """修完之後，成功那條路不能跟著壞掉。"""
    monkeypatch.setattr(
        run_scores.csv_audit, "read_current",
        lambda symbol, **kw: _bars(symbol, 5),
    )
    log = run_scores.run(["0050.TW"], task="test_ok")

    assert log.status == "ok"
    runs = _runs()
    assert len(runs) == 1 and runs[0]["status"] == "ok"


def test_runlog_written_only_once_per_run(isolated_root, three_days):
    """重拋不得讓同一次執行被記兩筆。"""
    with pytest.raises(ValueError):
        run_scores.run(["0050.TW"])

    assert len(_runs()) == 1

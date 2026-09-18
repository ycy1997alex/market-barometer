"""分數的歷史要有人在寫（2026-09-18 撞到的坑，ToDo §10）。

驗收：**`publish.py` 跑完之後，`score_history` 必須有一筆 `as_of` 等於該 scope
最新交易日的分數。**

失效的樣子是安靜的：頁面完全正常，因為 `build_page._index_rows()` 是在發布
當下現算的。但 `score_history` 的 `index` scope 停在 2026-09-11、`stock` 停在
2026-09-04 —— 排程裡根本沒有評分那一班，兩支 `scores_*` 都是手動跑過一次而已。

**分數的歷史補不回來。** `score_history` 有 `price_version` 欄位正是為了
「昨天的分數今天算會不一樣」（分割、除權息之後所有價格型指標都會變），
序列一斷，那個欄位就沒有意義了。

處置刻意不是加第九支排程，而是發布時把**已經算出來的那一份**落地 ——
stock-research 的 `run_daily.ps1` 當初拒絕排一班評分，理由是「先算一次存起來
再算一次只會多一份會過期的中間狀態」，那個理由現在仍然成立。
"""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

from barometer import config
from barometer.domain.ports import PriceBar
from barometer.pipeline import run_scores
from barometer.storage.sqlite_repo import SqliteRepo

ROOT = Path(__file__).resolve().parents[2]
PUBLISH = ROOT / "tools" / "publish.py"


def _calls(path: Path) -> set[str]:
    """檔案裡所有 `a.b(...)` 形式的呼叫，攤平成 "a.b"。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                out.add(f"{node.func.value.id}.{node.func.attr}")
    return out


def test_publish_persists_the_scores_it_just_computed():
    """發布的路徑上一定要有一次落地 —— 否則 score_history 永遠停在手動跑的那天。"""
    assert "run_scores.run" in _calls(PUBLISH), (
        "tools/publish.py 沒有呼叫 run_scores.run() —— "
        "頁面照樣出得來，但 score_history 不會前進，而且補不回來"
    )


# ---------------- 落地本身真的有效 ----------------

@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    return tmp_path


def _sessions(n: int = 250, last: dt.date = dt.date(2026, 9, 18)) -> list[dt.date]:
    """往回數 n 個工作日。評分需要至少 200 根才算得出分數（§10「一年在兩個
    市場不是同一個數字」），五根只會得到一整排 None，那不是這條測試要驗的事。
    """
    out: list[dt.date] = []
    day = last
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= dt.timedelta(days=1)
    return sorted(out)


SESSIONS = _sessions()


@pytest.fixture
def one_year_of_sessions(monkeypatch):
    def _read(symbol, **kw):
        return [
            PriceBar(symbol=symbol, date=d, open=100.0, high=101.0, low=99.0,
                     close=100.0 + i * 0.1, volume_shares=1000.0, source="test",
                     as_of=dt.datetime(2026, 9, 18, 18, 0, 0))
            for i, d in enumerate(SESSIONS)
        ]
    monkeypatch.setattr(run_scores.csv_audit, "read_current", _read)


def test_latest_session_reaches_score_history(isolated_root, one_year_of_sessions):
    run_scores.run(["^TWII"], task="test_scores")

    with SqliteRepo(config.db_path()) as repo:
        repo.init_schema()
        got = repo.get_scores(scope="index", symbol="^TWII")

    assert got, "score_history 一列都沒有"
    assert max(r.as_of for r in got) == SESSIONS[-1]

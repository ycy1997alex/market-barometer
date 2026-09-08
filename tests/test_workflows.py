"""CI 工作流程的紅線（ToDo §1 第 3、4 條、§9 Day 27 第 4 項）。

驗收句：**「workflow 裡沒有任何 secret 引用」**。

這一條看起來像廢話，但它是整個架構決定的證據：**排程放本機、CI 只做部署**，
所以 CI 不需要任何金鑰。哪天有人為了方便在 Actions 裡加一支抓資料的 job，
第一件要做的事就是往 workflow 裡塞 `secrets.FRED_KEY` —— 這支測試會在那一刻
擋下來，而不是等到金鑰外洩才發現。

順帶守著「CI 不抓資料、不寫資料」（§1 第 4 條）：兩個排程器都寫資料會衝突，
寫入者必須單邊。
"""
from __future__ import annotations

from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows")
                   .glob("*.yml"))


def test_there_are_workflows_to_check():
    assert WORKFLOWS, "找不到任何 workflow —— 這支測試會變成永遠通過的擺設"


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_secret_references(wf: Path):
    """`secrets.GITHUB_TOKEN` 也不行 —— 需要它就用 permissions，不用引用。"""
    text = wf.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in text.splitlines()
        if "secrets." in line and not line.strip().startswith("#")
    ]
    assert not offenders, f"{wf.name} 引用了 secret：\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_ci_does_not_fetch_or_write_data(wf: Path):
    """§1 第 4 條：Actions 只做部署與打包，不抓資料、不寫資料。"""
    banned = ("yfinance", "shioaji", "run_tw", "run_us", "run_macro",
              "fetch_day24", "fetch_chips", "tools/publish.py")
    # 註解與「不含 shioaji」這種否定句不算 —— 跟 render/lint.py 的
    # 否定語白名單同一個道理：在講「我們不做這件事」不等於在做這件事。
    # 沒有這一層，release notes 裡那句「不含 shioaji」會把自己的測試搞紅。
    negations = ("不含", "不裝", "不抓", "不寫", "不需要", "沒有")
    hits = []
    for line in wf.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or any(n in stripped for n in negations):
            continue
        hits.extend(b for b in banned if b in stripped)
    assert not hits, f"{wf.name} 出現了抓/寫資料的字樣：{sorted(set(hits))}"


def test_pages_workflow_is_push_triggered_not_scheduled():
    """§1 第 3 條：排程用 Windows 工作排程器，不是 GitHub Actions cron。"""
    pages = next(w for w in WORKFLOWS if w.name == "pages.yml")
    assert "schedule:" not in pages.read_text(encoding="utf-8")
    assert "cron" not in pages.read_text(encoding="utf-8")

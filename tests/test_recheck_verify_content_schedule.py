"""回補批 R-3：`verify_content.py` 從來沒有在正式資料上比過昨今，也不在排程裡。

2-5 把工具做出來了，但它不在 `register_tasks.ps1`；快照目錄只留下一份
`2026-09-21.json`，逐格比對等於一次都沒真的跑過。它的價值在**天天比**。

⚠️ 進排程不改變 2-5 的那一條：**輸出是給人讀的報告，不阻擋發布。**
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = (ROOT / "tools" / "register_tasks.ps1").read_text(encoding="utf-8-sig")


def _scheduled_at(task: str) -> str:
    match = re.search(rf'Name = "{task}";\s+At = "(\d\d:\d\d)"', REGISTER)
    assert match, f"{task} 不在 register_tasks.ps1 裡"
    return match.group(1)


def test_verify_content_is_declared_in_scheduler():
    assert 'Name = "Barometer-Verify-Content"' in REGISTER
    assert 'Script = "verify_content.ps1"' in REGISTER


def test_it_runs_after_the_data_tasks_but_before_publish():
    assert _scheduled_at("Barometer-Chips-TW-Late") < _scheduled_at("Barometer-Verify-Content")
    assert _scheduled_at("Barometer-Verify-Content") < _scheduled_at("Barometer-Publish")


def test_wrapper_leaves_system32_before_running_python():
    script = (ROOT / "tools" / "verify_content.ps1").read_text(encoding="utf-8-sig")
    assert 'Set-Location -LiteralPath (Join-Path $env:STOCKDATA_ROOT "runlog")' in script
    assert script.index("Set-Location") < script.index("& $Python")
    assert "verify_content.py" in script


def test_publishing_does_not_depend_on_the_review_report():
    """報告是給人讀的。發布那一支不得因為它而多一個失敗點（§9.1、2-5）。"""
    publish = (ROOT / "tools" / "publish_and_push.ps1").read_text(encoding="utf-8-sig")
    assert "verify_content" not in publish

    wrapper = (ROOT / "tools" / "verify_content.ps1").read_text(encoding="utf-8-sig")
    assert "exit 0" in wrapper, "比對結果不得變成排程的失敗碼"

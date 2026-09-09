"""排程自動 push 的紅線（ToDo §1 第 6 條、§9 Day 28 第 3 項）。

驗收句：**「排程只動得到 `docs/`」**。

自動 push 與手動 push 的差別，是沒有人在按 Enter 之前看一眼 diff。那一眼原本
擋的就是「順手把 `secrets/` 也 add 進去」—— 那一眼拿掉之後，換這幾支測試接手。

第一支測的是編碼，看起來跟安全無關但它是同一件事：`.ps1` 少了 BOM，
PowerShell 5.1 會用 cp950 解檔案、在第一個中文註解就死在解析階段。**解析失敗
的腳本一行都沒跑**，而排程只會記一個非零的 LastResult —— 跟「今天沒有資料要
發布」在事後長得幾乎一樣。
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "publish_and_push.ps1"


def _lines() -> list[str]:
    """非註解、非空白的行。"""
    return [ln.strip() for ln in SCRIPT.read_text(encoding="utf-8-sig").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def test_script_is_utf8_with_bom():
    assert SCRIPT.read_bytes()[:3] == b"\xef\xbb\xbf", (
        f"{SCRIPT.name} 少了 UTF-8 BOM —— 5.1 會用 cp950 解，中文註解會讓它解析失敗"
    )


def test_git_add_only_stages_docs():
    # 只認真正的呼叫（開頭是 `& git`）—— 錯誤訊息字串裡的 "git add" 不算
    adds = [ln for ln in _lines() if re.match(r"^& git\b.*\badd\b", ln)]
    assert adds, "腳本裡沒有 git add —— 這支測試會變成永遠通過的擺設"
    for ln in adds:
        assert ln.endswith("add -- docs"), f"stage 了 docs/ 以外的東西：{ln}"


def test_never_force_or_blanket_add():
    """`-f` 會繞過 .gitignore，而 secrets/ 與 Key/ 正是靠它擋著。"""
    banned = ("add -A", "add .", "add -f", "add --force",
              "push --force", "push -f", "-C $RepoRoot add ..")
    for ln in _lines():
        hits = [b for b in banned if b in ln]
        assert not hits, f"出現了危險的 git 用法 {hits}：{ln}"


def test_aborts_when_index_is_not_empty():
    """作者手上 staged 的東西，排程不碰 —— 也不會替他 reset 掉。"""
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert "diff --cached --name-only" in text, "沒有檢查進來時 index 是不是空的"
    assert "git -C $RepoRoot reset" not in text, "排程不該去動作者的 index"


def test_no_interactive_prompts():
    """排程跑的時候 stdin 是關的，任何提示都會變成掛住或直接錯。"""
    for bad in ("Read-Host", "Get-Credential", "Out-GridView", "PromptForChoice"):
        assert bad not in SCRIPT.read_text(encoding="utf-8-sig"), f"不得使用 {bad}"

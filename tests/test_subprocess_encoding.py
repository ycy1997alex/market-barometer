"""解文字的 subprocess 呼叫一律要釘死 `encoding="utf-8"`（2026-09-11 撞到）。

`text=True` 不帶 `encoding` 時，Python 用的是**本機語系編碼**，這台機器是 cp950。
`verify_publish.py` 因此在 `git log` 讀到 commit 訊息開頭那顆 emoji 時整支掛掉：
解碼錯誤發生在 subprocess 的讀取執行緒裡，`run()` 回來的 `.stdout` 是 `None`，
外面那個 `except Exception` 一點忙都幫不上，最後死在 `None.strip()`。

症狀出現的時機特別壞：repo 剛建好時 `git log` 是空的，什麼事都沒有；
**等到排程開始自動 commit（訊息開頭是 🔧）才第一次爆**，而那時沒有人在看。

只管會解碼的呼叫。`notify.py` 那支拿的是 bytes（只給 `capture_output`），
不解碼就沒有這個問題，不要為了統一而逼它也帶 encoding。
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("tools", "src")

DECODING_KWARGS = {"text", "universal_newlines"}
SUBPROCESS_FUNCS = {"run", "check_output", "Popen", "call", "check_call"}


def _python_files() -> list[Path]:
    out: list[Path] = []
    for d in SCAN_DIRS:
        out.extend(sorted((ROOT / d).rglob("*.py")))
    return out


def _subprocess_calls(tree: ast.AST):
    """只認 `subprocess.<func>(...)` 這種寫法。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (isinstance(fn, ast.Attribute)
                and fn.attr in SUBPROCESS_FUNCS
                and isinstance(fn.value, ast.Name)
                and fn.value.id == "subprocess"):
            yield node


def test_text_mode_subprocess_pins_utf8():
    offenders: list[str] = []
    seen = 0
    for py in _python_files():
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for call in _subprocess_calls(tree):
            seen += 1
            kw = {k.arg: k.value for k in call.keywords if k.arg}
            decodes = any(
                isinstance(kw.get(name), ast.Constant) and kw[name].value is True
                for name in DECODING_KWARGS
            )
            if not decodes:
                continue  # 拿 bytes 的呼叫不解碼，沒有這個問題
            enc = kw.get("encoding")
            if not (isinstance(enc, ast.Constant) and enc.value == "utf-8"):
                offenders.append(
                    f"{py.relative_to(ROOT)}:{call.lineno} "
                    f"text=True 但沒有 encoding=\"utf-8\"（這台會走 cp950）"
                )

    assert seen, "掃不到任何 subprocess 呼叫 —— 這支測試變成擺設了"
    assert not offenders, "\n  " + "\n  ".join(offenders)

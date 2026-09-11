"""排程進入點的硬規定（2026-09-11 撞到的坑，ToDo §10）。

驗收：每一支被 `tools/run_daily.ps1` 的 switch 指到的模組，都要能被
`python -m` 呼叫並真的跑起來 —— 有 `main()`，也有 `if __name__ == "__main__"`
那一段把它接上。

這條規則來自一次實際的失效：`run_macro` 兩樣都沒有，所以
`python -m barometer.pipeline.run_macro` 只是載入模組、什麼都不做、回傳 0。
工作排程器連三天寫著「上次執行結果：0」，runlog 一筆都沒有，總經資料停在
三天前，沒有任何通知。**成功地什麼都沒做，和沒被觸發長得一模一樣。**

掃的是 `run_daily.ps1` 那份宣告，不是 `pipeline/` 底下的檔名 —— 排程呼叫誰，
就檢查誰。新增一班排程只要改 ps1，這條測試自己會跟上。
"""
from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUN_DAILY = ROOT / "tools" / "run_daily.ps1"
SRC = ROOT / "src"

MODULE_RE = re.compile(r'"(barometer\.pipeline\.[A-Za-z_][A-Za-z0-9_]*)"')


def _scheduled_modules() -> list[str]:
    text = RUN_DAILY.read_text(encoding="utf-8")
    return sorted(set(MODULE_RE.findall(text)))


def _module_path(module: str) -> Path:
    return SRC / Path(*module.split(".")).with_suffix(".py")


def _has_main_guard(path: Path) -> bool:
    """模組層有沒有 `if __name__ == "__main__":`。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and any(isinstance(c, ast.Constant) and c.value == "__main__"
                        for c in test.comparators)):
            return True
    return False


def test_run_daily_declares_the_modules_we_think_it_does():
    """先確認掃得到東西 —— 正規表示式沒對到任何一支時，下面兩條會全綠。"""
    modules = _scheduled_modules()
    assert len(modules) >= 4, f"run_daily.ps1 只掃到 {modules}"
    assert "barometer.pipeline.run_macro" in modules


@pytest.mark.parametrize("module", _scheduled_modules())
def test_scheduled_module_is_runnable_as_main(module):
    """`python -m <module>` 一定要真的跑到 main()，不能只是載入模組。"""
    path = _module_path(module)
    assert path.is_file(), f"{module} 在 run_daily.ps1 裡，但 {path} 不存在"

    mod = importlib.import_module(module)
    assert callable(getattr(mod, "main", None)), (
        f"{module} 沒有 main()：排程呼叫它會安靜地成功、什麼都不做"
    )
    assert _has_main_guard(path), (
        f'{module} 缺少 if __name__ == "__main__" —— '
        f"有 main() 但沒人呼叫它，症狀跟完全沒有一樣"
    )

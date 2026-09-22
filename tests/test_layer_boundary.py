"""§3.2 硬規定：views/、presenters/、render/ 一律不得 import storage/。

Day 24 第 3 項與 Day 27 第 2 項的驗收都是這一條。
寫成 grep 測試，不靠自律 —— 邊界規則寫成測試，不寫成註解（§3.3）。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "barometer"

# 表現層：驅動側 adapter，只能認 domain 定義的 Port
PRESENTATION_DIRS = ["render", "app/views", "app/presenters"]

FORBIDDEN_ROOTS = {"storage", "datasources"}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相對 import：還原成 barometer.<...>
                parts = path.relative_to(SRC).parts[:-1]
                base = list(parts[: len(parts) - (node.level - 1)])
                found.add(".".join(base + ([node.module] if node.module else [])))
            elif node.module:
                found.add(node.module)
    return found


def _python_files(rel_dir: str) -> list[Path]:
    d = SRC / rel_dir
    return sorted(d.rglob("*.py")) if d.is_dir() else []


@pytest.mark.parametrize("rel_dir", PRESENTATION_DIRS)
def test_presentation_layer_does_not_import_outer_adapters(rel_dir):
    offenders: list[str] = []
    for py in _python_files(rel_dir):
        for mod in _imported_modules(py):
            tail = mod.split("barometer.")[-1]
            root = tail.split(".")[0]
            if root in FORBIDDEN_ROOTS:
                offenders.append(f"{py.relative_to(SRC)} imports {mod}")
    assert not offenders, (
        "表現層洩漏到被驅動側 adapter（§3.2）：\n  " + "\n  ".join(offenders)
    )


def test_domain_imports_nothing_from_outer_layers():
    """Domain 是核心，不得認識 storage / datasources / render / app。"""
    offenders: list[str] = []
    for py in _python_files("domain"):
        for mod in _imported_modules(py):
            tail = mod.split("barometer.")[-1]
            root = tail.split(".")[0]
            if root in FORBIDDEN_ROOTS | {"render", "app", "pipeline"}:
                offenders.append(f"{py.relative_to(SRC)} imports {mod}")
    assert not offenders, (
        "domain 反向依賴外層（§3.1 純規則，不知道 SQLite 存在）：\n  "
        + "\n  ".join(offenders)
    )


def test_domain_is_free_of_io():
    """Domain 層零 I/O：不得碰 sqlite3、requests、yfinance、open()。"""
    banned = {"sqlite3", "requests", "yfinance", "shioaji", "pathlib", "os"}
    offenders: list[str] = []
    for py in _python_files("domain"):
        for mod in _imported_modules(py):
            if mod.split(".")[0] in banned:
                offenders.append(f"{py.relative_to(SRC)} imports {mod}")
    assert not offenders, "domain 層出現 I/O 依賴（§3.1）：\n  " + "\n  ".join(offenders)


def test_there_is_a_domain_to_guard():
    """守衛本身不能因為資料夾改名就安靜地變成零檔案通過。

    少了這一條，把 `domain/` 改名之後上面幾條會變成「掃了 0 個檔案，全過」——
    綠燈，而且什麼都沒守到。
    """
    assert _python_files("domain"), "domain/ 底下一支 .py 都沒有，上面幾條守衛等於沒在守"


def test_domain_is_free_of_dataframe_libraries():
    """Domain 不得依賴 pandas / numpy（§9.1 第 6 條）。

    原本只有 `tests/domain/test_fifth_indicators.py` 掃 `indicators.py` 一支，
    其餘 domain 檔沒有任何東西擋著 —— 回補批 R-1 把它擴成整個套件。
    """
    banned = {"pandas", "numpy"}
    offenders: list[str] = []
    for py in _python_files("domain"):
        for mod in _imported_modules(py):
            if mod.split(".")[0] in banned:
                offenders.append(f"{py.relative_to(SRC)} imports {mod}")
    assert not offenders, (
        "domain 層出現 DataFrame 依賴（§9.1 第 6 條，純 Python list 版本）：\n  "
        + "\n  ".join(offenders)
    )

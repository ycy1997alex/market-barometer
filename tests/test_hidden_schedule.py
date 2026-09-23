"""排程任務不得跳出視窗搶走焦點（2026-09-23）。

工作排程器直接跑 `powershell.exe` 時，Windows 11 會替它開一個主控台視窗（預設交給
Windows Terminal），每一班都跳到前景。改由 `pythonw.exe tools/run_hidden.py` 啟動：
整條鏈不開視窗，而且 .ps1 的結束代碼要原樣傳回 —— 排程的成敗仍以它為準。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "tools" / "run_hidden.py"
REGISTER = (ROOT / "tools" / "register_tasks.ps1").read_text(encoding="utf-8-sig")


def _load_launcher():
    spec = importlib.util.spec_from_file_location("run_hidden", LAUNCHER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scheduler_launches_through_windowless_python():
    assert "pythonw.exe" in REGISTER
    assert "run_hidden.py" in REGISTER
    assert '-Execute "powershell.exe"' not in REGISTER, "直接跑 powershell.exe 會開視窗"


def test_launcher_starts_the_script_without_a_window(monkeypatch):
    launcher = _load_launcher()
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(cmd=cmd, **kwargs)
        return subprocess.CompletedProcess(cmd, 3)

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    assert launcher.main([r"X:\tools\run_daily.ps1", "-Market", "tw"]) == 3
    assert seen["cmd"] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                           "-File", r"X:\tools\run_daily.ps1", "-Market", "tw"]
    assert seen["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_exit_code_reaches_the_scheduler(tmp_path):
    """conhost --headless 就是死在這裡：不開視窗，但結束代碼一律變成 0。"""
    script = tmp_path / "fail.ps1"
    script.write_text("exit 7", encoding="utf-8")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    assert subprocess.run([str(pythonw), str(LAUNCHER), str(script)]).returncode == 7

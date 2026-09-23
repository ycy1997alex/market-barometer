"""排程任務的無視窗啟動器：每一班排程都不再跳出終端機視窗搶走焦點。

工作排程器直接跑 powershell.exe 時，Windows 11 會替它開一個主控台視窗（預設交給
Windows Terminal）。這支由 pythonw.exe 執行 —— pythonw 本身沒有主控台 —— 再用
CREATE_NO_WINDOW 啟動原本的 .ps1，整條鏈（powershell → python / git）都不開視窗。

**結束代碼原樣傳回**：排程任務的成敗仍以 .ps1 的 exit code 為準。

為什麼不用別的（2026-09-23 實測）：
- `powershell -WindowStyle Hidden`：視窗先開再藏，預設終端機是 Windows Terminal 時根本藏不掉。
- `conhost.exe --headless`：不開視窗，但結束代碼一律變成 0，排程的「上次執行結果」會永遠是成功。
- 「不論使用者是否登入都執行」（S4U）：沒有密碼就解不開認證管理員，publish_and_push 的 git push 會失敗。

用法（register_tasks.ps1 產生的排程動作）：
    pythonw.exe tools\\run_hidden.py tools\\run_daily.ps1 -Market tw
"""
from __future__ import annotations

import subprocess
import sys


def main(argv: list[str]) -> int:
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", *argv]
    return subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

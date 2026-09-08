# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller .spec —— market-barometer 桌面儀表（ToDo §9 Day 27 第 5 項）。

onefile。這支程式的相依很輕（tkinter + requests + pandas/numpy 的一小部分），
沒有 torch 那種等級的東西，所以 onefile 的體積與啟動時間都可以接受。

**shioaji 刻意不打包進來** —— 它是 pyproject 的 [tw] 選配相依，只有本機每日
對帳那一支用得到。桌面程式只讀本機快取與打 yfinance/FRED，把一個有下單能力
的套件塞進要發出去的 exe 沒有任何好處（§12 第 5 條）。

資源檔（schema.sql、shell.html）要進 datas，不然 onefile 解壓到暫存目錄之後
`Path(__file__).with_name(...)` 會找不到它們。
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# --- conda 環境的原生 DLL 在 <sys.prefix>\Library\bin，那不在 PyInstaller 的
# 相依搜尋路徑上。少了這一行，build 會成功、exe 會在啟動時死於
# `ImportError: DLL load failed while importing _ctypes`。
# 驗收看的是「build log 裡零個 Library not found」，不是 exit 0 —— 兩種情況都 exit 0。
# CI 上跑的是官方 python，這個目錄不存在，多一段 PATH 沒有副作用。
os.environ["PATH"] = (
    os.path.join(sys.prefix, "Library", "bin") + os.pathsep + os.environ["PATH"]
)

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

# --- numpy 2.5 的子模組要整包收，不能靠內建 hook ---
#
# 實測：只靠 PyInstaller 6.11.1 附的 numpy hook，build 會成功、exe 會在啟動時
# 死在 `No module named 'numpy._core._exceptions'`，而 pandas 把它轉譯成
# 一句沒什麼幫助的「Unable to import required dependency numpy」。
#
# 這是「build exit 0 不等於跑得起來」最典型的一種 —— 測試全綠也抓不到，
# 因為測試跑的是 env 裡的 numpy，不是打包進去的那一份。
np_datas, np_binaries, np_hidden = collect_all("numpy")

# ttkbootstrap 的主題定義是資料檔，不收的話 exe 會找不到 darkly
bs_datas, bs_binaries, bs_hidden = collect_all("ttkbootstrap")

a = Analysis(
    [str(SRC / "barometer" / "app" / "main.py")],
    pathex=[str(SRC)],
    binaries=np_binaries + bs_binaries,
    datas=[
        (str(SRC / "barometer" / "storage" / "schema.sql"), "barometer/storage"),
        (str(SRC / "barometer" / "crypto" / "shell.html"), "barometer/crypto"),
        # 圖示也要進 datas，不只是 icon= —— 前者給執行中的視窗與工作列用，
        # 後者只決定 Explorer 裡那顆。兩個來源不同，缺一個就會有一面不對。
        (str(SRC / "barometer" / "app.ico"), "barometer"),
    ] + np_datas + bs_datas,
    hiddenimports=["barometer.app.views.dashboard", "ttkbootstrap"] + np_hidden + bs_hidden,
    hookspath=[],
    runtime_hooks=[],
    # 這幾個是這支 exe 用不到、但會被相依樹拖進來的重量級東西。
    # 沿用而不修剪：換過環境之後多半會有幾條對不上任何東西，留著當保險。
    # ⚠️ excludes 會過期，而且過期的方式是「exe 打得起來、跑不起來」。
    # PIL 本來在這張清單上（那時候程式沒用到它），改用 ttkbootstrap 之後
    # 它變成必要相依 —— build 照樣 exit 0、零個 Library not found，
    # 一啟動才死在 `No module named 'PIL'`。
    excludes=[
        "shioaji", "matplotlib", "scipy", "IPython", "jupyter",
        "pytest", "setuptools", "PyQt5", "PySide6",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="market-barometer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # console=False：這是 GUI 程式，不要在背後開一個黑窗。
    # 打包壞掉時改成 True 重建一次，traceback 才看得到（見 exe-verify）。
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 多解析度圖示（16/24/32/48/64/128/256）。單一尺寸在某些地方會糊掉，
    # 或者乾脆退回預設圖示。這顆決定的是 **Explorer 裡** 那一面；
    # 視窗標題列與工作列那兩面在 app/main.py 設。
    icon=str(SRC / "barometer" / "app.ico"),
)

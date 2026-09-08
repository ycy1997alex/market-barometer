"""桌面程式的組裝根（ToDo §3.2、§9 Day 27 第 1 項）。

**這是唯一一個可以同時認得 storage 與 datasources 的地方。**
Ports & Adapters 的形狀就是這樣：介面在內層、實作在外層，而把兩者接起來的
組裝根待在最外面。`views/` 與 `presenters/` 一個都不准 import 這兩層
（tests/test_layer_boundary.py 用 AST 掃描守著）。

跑法：
    python -m barometer.app.main

---

**視窗建立的順序有兩件事不能反過來：**

1. `SetCurrentProcessExplicitAppUserModelID` 要在 root 建立**之前**呼叫。
   Windows 是按這個 ID 把視窗歸到工作列的哪一格，晚了就沒用，工作列會顯示
   Python 直譯器的圖示而不是這支程式的。
2. 用 ttkbootstrap 開視窗時要傳 `iconphoto=None`。`bs.Window()` 預設會拿
   ttkbootstrap 自己的 logo 去呼叫 `Tk.iconphoto`，而 `iconphoto` 的優先權
   高過 `iconbitmap` —— 不傳這個參數的話，之後怎麼設 .ico 都會被它蓋掉，
   而且不會有任何錯誤訊息。

圖示是 `src/barometer/app.ico`，多解析度（16/24/32/48/64/128/256）。
**三個面要各自設，來源不同**：Explorer 那一面來自 .spec 的 `icon=`；
標題列與工作列這兩面來自這裡的 `iconbitmap` 加上 AppUserModelID。
少設一處就會有一面顯示的是別的東西，而且不會有任何錯誤訊息。
"""
from __future__ import annotations

import sys

import ttkbootstrap as bs

from barometer import config
from barometer.app.presenters.dashboard import DashboardPresenter
from barometer.app.views.dashboard import DashboardWindow
from barometer.pipeline import fetch_prices, run_macro, run_scores
from barometer.storage.sqlite_repo import SqliteRepo

APP_ID = "alexyu.market-barometer"
THEME = "darkly"          # ttkbootstrap 主題，明確指定不用預設
ICON_NAME = "app.ico"


def _refresher(force: bool = False) -> None:
    """兩種更新背後的那件事 —— **只有這裡會打網路**。

    `force=True`（強制重抓）忽略快取重新掃一次總經，**並且**重抓價格、
    重算大盤評分，讓四個分頁一起到最新。`False`（到期自動更新）只跑總經，
    而且讓各資料源自己的 TTL 決定要不要真的出去。

    為什麼自動那一路不碰價格：價格有自己的排程（台股 18:00、美股 09:00），
    桌面程式沒有必要在中午多抓一次一模一樣的東西。

    它跑在 View 開的背景執行緒上，所以這裡**不能**碰任何 widget，
    也不能共用主執行緒那條 SQLite 連線 —— 每支 pipeline 自己開一條。
    """
    run_macro.run(force=force)
    if not force:
        return
    # 強制重抓才連價格與評分一起更新。任何一段失敗都不該讓整次更新爆掉 ——
    # 總經已經抓好了，沒有理由因為價格抓不到就把它一起丟掉。
    try:
        fetch_prices.run(list(config.ALL_SYMBOLS), task="app_force_prices")
        run_scores.run(list(config.ALL_SYMBOLS), task="app_force_scores")
    except Exception:  # noqa: BLE001
        pass


def _set_taskbar_identity() -> None:
    """讓工作列認得這支程式，而不是把它歸到 Python 直譯器底下。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:  # noqa: BLE001 — 設不了圖示不該讓程式開不起來
        pass


def _enable_dpi_awareness() -> float:
    """宣告自己看得懂 DPI，回傳縮放倍率。**必須在建立 root 之前呼叫。**

    不宣告的話，Windows 會給一個縮放後的邏輯螢幕尺寸（150% 的 1920×1080 會
    回報成 1280×720），然後再把整個視窗放大 1.5 倍貼上去 —— 結果是字糊掉，
    而且 `winfo_screenwidth()` 量到的根本不是實際解析度，
    「視窗佔螢幕幾 %」就會差個 0.5~1%。

    代價是宣告之後 tk 的字級會照實體像素算，所以要把縮放倍率補回去
    （`tk scaling`），不然在高 DPI 螢幕上字會小到看不清楚。
    """
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes

        # 2 = PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return (dpi or 96) / 96.0
    except Exception:  # noqa: BLE001
        return 1.0


def _apply_icon(root) -> None:
    """設定視窗標題列的圖示。

    路徑走 `resource_path`，因為 onefile 會把 datas 解壓到暫存目錄 ——
    寫死相對路徑的話，直接跑 python 沒事、打包成 exe 才壞。
    """
    path = config.resource_path(ICON_NAME)
    if not path.exists():
        return
    try:
        root.iconbitmap(str(path))
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    config.ensure_dirs()
    repo = SqliteRepo(config.db_path())
    repo.init_schema()

    _set_taskbar_identity()
    scale = _enable_dpi_awareness()   # 一定要在 bs.Window() 之前
    # iconphoto=None：不讓 ttkbootstrap 的 logo 蓋掉 .ico（見模組說明）
    root = bs.Window(themename=THEME, iconphoto=None)
    if scale != 1.0:
        # DPI-aware 之後字級照實體像素算，把縮放倍率補回去
        root.tk.call("tk", "scaling", scale * 96 / 72)
    _apply_icon(root)

    try:
        DashboardWindow(root, DashboardPresenter(repo, _refresher))
        root.mainloop()
    finally:
        # 不論正常關窗還是未攔到的例外，連線都要關掉
        repo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

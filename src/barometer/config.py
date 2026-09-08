"""路徑與標的清單（ToDo §3.4、§7.1）。

**兩個 repo 都不得寫死絕對路徑** —— 一律走 STOCKDATA_ROOT，
預設 D:\\Research\\_stockdata。資料根目錄刻意放在兩個 repo 之外，
一份資料餵兩個站（§1 第 8 條）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_ROOT = Path(r"D:\Research\_stockdata")


def stockdata_root() -> Path:
    """資料根目錄。環境變數 STOCKDATA_ROOT 優先，否則用預設值。"""
    raw = os.environ.get("STOCKDATA_ROOT", "").strip()
    return Path(raw) if raw else DEFAULT_ROOT


def resource_path(relative: str) -> Path:
    """打包進 exe 的靜態資源（圖示之類）的實際位置。

    PyInstaller 的 onefile 會把 datas 解壓到一個暫存目錄，路徑放在
    `sys._MEIPASS`。寫死相對路徑的話，直接跑 python 時沒事、打包成 exe
    之後才壞，而且是那種「檔案明明就在旁邊」的壞法。

    **這跟 stockdata_root() 是兩回事**：資源是唯讀、跟著程式走；
    資料層是可寫、跟著機器走。兩者不共用路徑。
    """
    base = getattr(sys, "_MEIPASS", None)
    # 打包後資源放在 `_MEIPASS/barometer/`（.spec 的 datas 把它們放進套件目錄），
    # 不是 `_MEIPASS/` 根目錄。少了這一段 barometer，直接跑 python 時
    # 找得到、打包成 exe 之後就找不到 —— 而且不會報錯，只會安靜地退回預設圖示。
    root = Path(base) / "barometer" if base else Path(__file__).parent
    return root / relative


def db_path() -> Path:
    return stockdata_root() / "market.db"


def price_raw_dir(date_iso: str) -> Path:
    """當天抓到什麼就存什麼的稽核軌跡，append-only（§4.4 第 1 點）。"""
    return stockdata_root() / "price_raw" / date_iso


def price_current_dir() -> Path:
    """最新完整序列，允許被覆寫，計算用。"""
    return stockdata_root() / "price_current"


def runlog_path(year_month: str) -> Path:
    return stockdata_root() / "runlog" / f"{year_month}.jsonl"


def build_dir() -> Path:
    """明文 HTML 落地處 —— 在兩個 repo 之外，明文絕不進 git（§5.4 第 2 條）。"""
    return stockdata_root() / "build"


def secrets_dir() -> Path:
    return stockdata_root() / "secrets"


def ensure_dirs() -> None:
    for p in (
        stockdata_root(),
        stockdata_root() / "price_raw",
        price_current_dir(),
        stockdata_root() / "runlog",
        build_dir(),
        secrets_dir(),
    ):
        p.mkdir(parents=True, exist_ok=True)


# ---------------- §7.1 標的清單（market-barometer） ----------------

# 每個市場「指數 + 兩檔 ETF」，是為了讓 Day 26 有東西可比。
TW_INDEX = "^TWII"
TW_ETFS = ("0050.TW", "006208.TW")
US_INDEX = "^GSPC"
US_ETFS = ("SPY", "VOO")

TW_SYMBOLS = (TW_INDEX,) + TW_ETFS
US_SYMBOLS = (US_INDEX,) + US_ETFS
ALL_SYMBOLS = TW_SYMBOLS + US_SYMBOLS

# 顯示單位：台股「張」、美股「股」。內部一律存股，只在顯示層換算（§1 第 10 條）。
SHARES_PER_LOT = 1000


INDEX_SYMBOLS = (TW_INDEX, US_INDEX)


def is_index(symbol: str) -> bool:
    """指數不可交易，而且它的「量」不是股數 —— 別把它當標的處理。"""
    return symbol in INDEX_SYMBOLS


def is_tw(symbol: str) -> bool:
    return symbol.endswith((".TW", ".TWO")) or symbol == TW_INDEX


def display_volume(symbol: str, volume_shares: float | None) -> tuple[float | None, str]:
    """把內部的「股」換算成顯示用的單位。回傳 (數值, 單位字串)。

    這是**唯一**該做這個換算的地方 —— 既有專案出過「標題寫張、資料其實是股」
    的 bug，所以換算集中在顯示層一處，資料層永遠是股。
    """
    if volume_shares is None:
        return None, "張" if is_tw(symbol) else "股"
    if is_tw(symbol):
        return volume_shares / SHARES_PER_LOT, "張"
    return volume_shares, "股"

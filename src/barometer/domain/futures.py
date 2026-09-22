"""期貨合約代碼（ToDo §7.1、§9 第八批 8-6）。純函式、零 I/O。

⚠️ **遠月代碼每個月都會變。** 寫死一個 ticker 的後果不是報錯，是三個月後
它還在跑、抓到的卻是一個快要到期或已經沒量的合約 —— 看起來一切正常。
所以代碼由當月動態生成，不進任何設定檔。
"""
from __future__ import annotations

import datetime as dt

# 交易所的月碼：一月到十二月。I 不用（避免與 1 混淆），這是慣例不是筆誤。
MONTH_CODES = ("F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z")

CRUDE_ROOT = "CL"
CRUDE_SUFFIX = ".NYM"
DEFERRED_MONTHS = 6


def deferred_crude_symbol(today: dt.date, months: int = DEFERRED_MONTHS) -> str:
    """當月 + `months` 個月的西德州原油合約代碼，例如 2026-09 → `CLH27.NYM`。"""
    index = today.month - 1 + months
    year = today.year + index // 12
    return f"{CRUDE_ROOT}{MONTH_CODES[index % 12]}{year % 100:02d}{CRUDE_SUFFIX}"

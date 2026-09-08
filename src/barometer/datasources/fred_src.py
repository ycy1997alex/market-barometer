"""FRED adapter（ToDo §6、§7.3）。

**有金鑰走官方 API，沒有金鑰退回免金鑰的 CSV 端點。**

金鑰換到的是額度：官方 API 120 req/min，免金鑰的 `fredgraph.csv` 沒有公布
數字。兩條路都固定節流 1 秒/次，也就是最多 60 req/min，只用一半額度（§6）。

**金鑰是選配，不是必要條件。** 沒有它整套照樣跑，只是額度低一點。這正是
Day 28「金鑰分級」那一段的例子：讀取型的金鑰唯讀、可撤銷、掉了重發就好，
跟有下單能力的 Shioaji 完全不是同一個等級。

---

⚠️ **這支檔案最危險的一行是錯誤訊息。**

官方 API 把金鑰放在 query string 裡（`?api_key=...`），而 requests 的例外
訊息會把整個 URL 回顯出來。什麼都不做的話，一次連線失敗就會把金鑰寫進
run log、寫進 ALERT.md、印在終端機上。

所以**所有對外的字串都先過 `redact()`**，而且有測試守著（test_fred_key.py）。

⚠️ **不要偽裝 User-Agent** —— 實測過：偽裝 Mozilla 反而因 TLS 指紋不符被擋，
用 requests 預設 UA 才放行（§6 規則 7）。這是反直覺的，所以寫成註解留著。
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode

import requests

from barometer.datasources.base import (
    COUNTER,
    FetchError,
    RateLimitError,
    Throttle,
    retry_once,
)

SOURCE = "fred"

API_BASE = "https://api.stlouisfed.org/fred/series/observations"
CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"

ENV_KEY = "FRED_API_KEY"
KEY_FILENAMES = ("FRED API Key.txt", "fred_api_key.txt", "fred.key")

# FRED 的金鑰是 32 個小寫英數。認得出格式才不會把一句說明文字當成金鑰用，
# 那種錯會變成「一直 400，但看不出為什麼」。
_KEY_RE = re.compile(r"^[a-z0-9]{32}$")

# module-level 節流器 —— 繞不過去（§6 規則 1）
_THROTTLE = Throttle(min_interval=1.0)

TAIL = 30  # 取最後 30 筆（§7.3）


# ---------------- 金鑰 ----------------

def _default_search() -> list[Path]:
    """依序找：repo 根目錄的 `Key/`、資料層的 `secrets/`。

    兩個 repo 底下都有一份 `Key/`，而且被 .gitignore 擋著（實測過
    `git status` 看不到它）。
    """
    repo_root = Path(__file__).resolve().parents[3]
    return [
        repo_root / "Key",
        Path(os.environ.get("STOCKDATA_ROOT", r"D:\Research\_stockdata")) / "secrets",
    ]


def load_api_key(search: list[Path] | None = None) -> str | None:
    """找 FRED 金鑰。找不到回 None —— **那是正常狀態，不是故障。**

    順序：環境變數 → 各搜尋目錄底下的金鑰檔。

    金鑰檔允許「標題行 + 值」的格式（作者的 Shioaji 金鑰就是那樣存的），
    所以逐行掃，取第一個長得像金鑰的字串。
    """
    env = os.environ.get(ENV_KEY, "").strip()
    if _KEY_RE.match(env):
        return env

    for d in (search if search is not None else _default_search()):
        for name in KEY_FILENAMES:
            f = d / name
            if not f.is_file():
                continue
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                token = line.strip()
                if _KEY_RE.match(token):
                    return token
    return None


def redact(text: str) -> str:
    """把 `api_key=<金鑰>` 換成 `api_key=***`。

    對外的每一個字串都要過這裡：例外訊息、run log 的 note、通知內容。
    只遮金鑰那一段，其他 query 參數留著 —— 全部遮掉的話錯誤訊息就沒用了。
    """
    return re.sub(r"(api_key=)[A-Za-z0-9]+", r"\1***", text)


# ---------------- 端點 ----------------

def build_url(sid: str, api_key: str | None, tail: int = TAIL) -> str:
    """有金鑰走官方 API，沒有就走免金鑰 CSV。

    官方 API 這邊刻意加了 `sort_order=desc` + `limit`：只要最後幾十筆，
    不必把 1947 年至今的整條序列拉回來。省的是別人的頻寬跟自己的時間。
    """
    if api_key:
        return API_BASE + "?" + urlencode({
            "series_id": sid,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": tail,
        })
    return CSV_BASE + "?" + urlencode({"id": sid})


def _get(url: str, sid: str) -> str:
    _THROTTLE.wait()
    COUNTER.bump(SOURCE)
    try:
        # 刻意不帶 headers：預設 UA 才過得了 FRED 的防護
        resp = requests.get(url, timeout=25)
    except requests.RequestException as exc:
        # **一定要遮** —— 例外訊息裡有完整 URL，URL 裡有金鑰。
        # `from None` 也是刻意的：不然原始例外會跟著 traceback 一起被印出來。
        raise FetchError(f"FRED {sid}: {redact(str(exc))}") from None

    if resp.status_code in (429, 403):
        raise RateLimitError(f"FRED {sid}: HTTP {resp.status_code}")
    if resp.status_code != 200:
        raise FetchError(
            f"FRED {sid}: HTTP {resp.status_code} {redact(resp.text[:200])}"
        )
    return resp.text


# ---------------- 解析 ----------------

def parse_api(payload: str) -> list[tuple[str, float]]:
    """解析官方 API 的 JSON。回傳**由舊到新**。

    抓的時候要 desc（最新在前，才配得上 limit），這裡翻回來，
    讓兩條路徑回一樣的順序 —— 呼叫端不必知道今天走的是哪一條。
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise FetchError(f"FRED: 回應不是 JSON（{exc}）") from None

    obs = data.get("observations")
    if not isinstance(obs, list):
        msg = data.get("error_message", "回應沒有 observations")
        raise FetchError(f"FRED: {redact(str(msg))}")

    rows: list[tuple[str, float]] = []
    for o in obs:
        value = str(o.get("value", "")).strip()
        if value in (".", "", "NA"):
            continue  # FRED 的缺值標記。**跳過，不補 0**
        try:
            rows.append((str(o.get("date", "")).strip(), float(value)))
        except ValueError:
            continue
    return sorted(rows, key=lambda r: r[0])


def parse_csv(text: str) -> list[tuple[str, float]]:
    """解析免金鑰 CSV 端點。回傳由舊到新。"""
    rows: list[tuple[str, float]] = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or len(header) < 2:
        raise FetchError("FRED: 回應不是預期的 CSV")

    for row in reader:
        if len(row) < 2:
            continue
        date_s, value_s = row[0].strip(), row[1].strip()
        if value_s in (".", "", "NA"):
            continue
        try:
            rows.append((date_s, float(value_s)))
        except ValueError:
            continue
    return rows


def fetch(sid: str, tail: int = TAIL,
          api_key: str | None = None) -> list[tuple[str, float]]:
    """回 (日期, 值) 由舊到新。

    `api_key` 不給就自己去找；找不到就走免金鑰端點。
    """
    key = api_key if api_key is not None else load_api_key()
    url = build_url(sid, key, tail)
    text = retry_once(lambda: _get(url, sid), backoff=3.0)

    rows = parse_api(text) if key else parse_csv(text)
    if not rows:
        raise FetchError(f"FRED {sid}: 沒有任何有效資料點")
    return rows[-tail:]


def data_date(series: list[tuple[str, float]]) -> dt.date | None:
    """這條序列的資料日期 —— CPI 標 8 月、利差標昨天，兩個都對（§9 Day 25 第 3 項）。"""
    if not series:
        return None
    try:
        return dt.date.fromisoformat(series[-1][0])
    except ValueError:
        return None

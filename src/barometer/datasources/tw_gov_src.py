"""台灣政府開放資料 adapter：國發會 / 主計總處 / 央行（ToDo §7.3）。

三個來源合在一個模組，因為它們共用兩件麻煩事：
  1. **憑證鏈不全** —— 部分台灣政府主機缺中繼憑證，certifi 驗不過。
     處理：先正常驗證，**僅在 SSLError 時**降級 verify=False 重試（§6 規則 8）。
     只降級這一種例外，不是全域關掉驗證。
  2. **資源 URL 會變** —— 先問 data.gov.tw API 拿當前 URL，失敗才用寫死備援。

國發會那支 ZIP 一份餵兩個指標，所以**同一輪更新共用一次下載**（記憶體快取 1 小時），
不要為了兩個指標打兩次（§6 規則 5）。

央行那支是 HTML 爬取，**結構變了就會壞** —— 這是已知的脆弱點，不假裝它穩固。
"""
from __future__ import annotations

import io
import re
import time
import zipfile

import pandas as pd
import requests

from barometer.datasources.base import COUNTER, FetchError, Throttle

SOURCE_NDC = "ndc"
SOURCE_DGBAS = "dgbas"
SOURCE_CBC = "cbc"

_GOV_DETAIL = "https://data.gov.tw/api/front/dataset/detail?nid={nid}"

# 寫死備援：data.gov.tw API 掛掉時用。這些路徑每月原地更新，實測穩定。
_NDC_ZIP_FALLBACK = (
    "https://ws.ndc.gov.tw/Download.ashx?u=LzAwMS9hZG1pbmlzdHJhdG9yLzEwL3JlbGZpbGUv"
    "NTc4MS82MzkyL2VhMjM1YmQ5LWQwNTItNGE2OS1hYmZjLWQ1Yzc4NWQzZDBlMi56aXA%3d"
    "&n=5pmv5rCj5oyH5qiZ5Y%2bK54eI6JmfLnppcA%3d%3d&icon=.zip"
)
_DGBAS_XML_FALLBACK = (
    "https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230514/na8101a1q.xml"
)
_CBC_RATE_PAGE = "https://www.cbc.gov.tw/tw/lp-640-1-1-20.html"

# 政府網站對預設 UA 有時直接拒絕，這裡誠實標示用途
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

_THROTTLE = Throttle(min_interval=0.6)

TAIL = 30


def _http_get(url: str, timeout: int = 30, browser_ua: bool = True):
    """共用 GET。僅在 SSLError 時降級跳過驗證重試。"""
    _THROTTLE.wait()
    headers = {"User-Agent": _UA} if browser_ua else {}
    try:
        return requests.get(url, timeout=timeout, headers=headers)
    except requests.exceptions.SSLError:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return requests.get(url, timeout=timeout, headers=headers, verify=False)


def _gov_resource_url(nid: int, file_format: str, fallback: str) -> str:
    try:
        r = _http_get(_GOV_DETAIL.format(nid=nid), timeout=20)
        r.raise_for_status()
        for res in r.json()["payload"].get("resources", []):
            if res.get("file_format", "").upper() == file_format and res.get("url"):
                return res["url"]
    except Exception:  # noqa: BLE001 — 解析失敗就走備援，這不是致命錯誤
        pass
    return fallback


# ---------------- 國發會 6099 ZIP（一份餵兩個指標） ----------------

_ndc_zip_mem: tuple[float, bytes] | None = None
_NDC_TTL_SECONDS = 3600


def _ndc_zip() -> zipfile.ZipFile:
    global _ndc_zip_mem
    now = time.monotonic()
    if _ndc_zip_mem is not None and now - _ndc_zip_mem[0] < _NDC_TTL_SECONDS:
        return zipfile.ZipFile(io.BytesIO(_ndc_zip_mem[1]))

    url = _gov_resource_url(6099, "ZIP", _NDC_ZIP_FALLBACK)
    COUNTER.bump(SOURCE_NDC)
    r = _http_get(url, timeout=60)
    if r.status_code != 200:
        raise FetchError(f"國發會 6099 ZIP: HTTP {r.status_code}")
    _ndc_zip_mem = (now, r.content)
    return zipfile.ZipFile(io.BytesIO(r.content))


def _ndc_csv_series(csv_name: str, col: str) -> list[tuple[str, float]]:
    """讀 ZIP 內的 CSV 取單欄。Date=YYYYMM → YYYY-MM。"""
    try:
        raw = _ndc_zip().read(csv_name).decode("utf-8-sig", errors="replace")
    except KeyError as exc:
        raise FetchError(f"國發會 ZIP 內找不到 {csv_name}（結構可能變更）") from exc

    df = pd.read_csv(io.StringIO(raw))
    if col not in df.columns:
        raise FetchError(f"{csv_name} 內找不到欄位「{col}」（結構可能變更）")
    df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=[col]).tail(TAIL)
    if df.empty:
        raise FetchError(f"{csv_name} 的「{col}」沒有任何有效值")
    return [
        (f"{str(r['Date'])[:4]}-{str(r['Date'])[4:6]}", float(r[col]))
        for _, r in df.iterrows()
    ]


def fetch_tw_light() -> list[tuple[str, float]]:
    """台灣景氣對策信號綜合分數（月）。"""
    return _ndc_csv_series("景氣指標與燈號.csv", "景氣對策信號綜合分數")


def fetch_tw_export() -> list[tuple[str, float]]:
    """台灣外銷訂單動向指數，以家數計（月）。"""
    return _ndc_csv_series("領先指標構成項目.csv", "外銷訂單動向指數(以家數計)")


# ---------------- 主計總處 6799 XML ----------------

def fetch_tw_gdp() -> list[tuple[str, float]]:
    """台灣經濟成長率 YoY（季）：Item=經濟成長率(%)、FREQ=Q、TYPE=原始值。"""
    url = _gov_resource_url(6799, "XML", _DGBAS_XML_FALLBACK)
    COUNTER.bump(SOURCE_DGBAS)
    r = _http_get(url, timeout=60)
    if r.status_code != 200:
        raise FetchError(f"主計總處 6799 XML: HTTP {r.status_code}")

    txt = r.content.decode("utf-8-sig", errors="replace")
    obs = re.findall(
        r"<Obs><Item>經濟成長率\(%\)</Item>"
        r"<TIME_PERIOD>([^<]+)</TIME_PERIOD><FREQ>Q</FREQ>"
        r"<TYPE>原始值</TYPE>\s*<Item_VALUE>([^<]*)</Item_VALUE>",
        txt,
    )
    pairs = [(p, float(v)) for p, v in obs if v.strip()]
    if not pairs:
        raise FetchError("主計總處 XML 內查無經濟成長率原始值（結構可能變更）")
    return pairs[-TAIL:]


# ---------------- 央行重貼現率（HTML 爬取，脆弱） ----------------

def fetch_cbc_rate() -> list[tuple[str, float]]:
    """央行利率調整表。回傳歷次調整紀錄（舊→新），**不是日資料**。

    這支是純 HTML 爬取，頁面結構一改就壞。已知脆弱，不假裝它穩固 ——
    壞掉時走 §7.3「單一指標失敗不擋整頁」的路徑，顯示快取或「—」。
    """
    COUNTER.bump(SOURCE_CBC)
    r = _http_get(_CBC_RATE_PAGE, timeout=40)
    if r.status_code != 200:
        raise FetchError(f"央行利率表: HTTP {r.status_code}")

    dates = re.findall(r'data-th="調整日期"><span>([^<]+)</span>', r.text)
    rates = re.findall(r'data-th="重貼現率"><span>([^<]+)</span>', r.text)
    if not dates or len(dates) != len(rates):
        raise FetchError("央行利率表解析失敗（頁面結構可能變更）")

    pairs: list[tuple[str, float]] = []
    for d, v in zip(dates, rates):
        try:
            y, m, dd = d.strip().split("/")
            pairs.append((f"{int(y):04d}-{int(m):02d}-{int(dd):02d}", float(v)))
        except ValueError:
            continue
    if not pairs:
        raise FetchError("央行利率表沒有可解析的列")
    pairs.reverse()  # 頁面是新→舊，統一成舊→新
    return pairs[-TAIL:]

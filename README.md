# market-barometer

世界與台灣總體經濟、台股與美股大盤及 ETF 的**本機資料管線**。抓取、計算、加密都在本機完成，只有加密後的頁面會推上 GitHub Pages。

> **這是一支氣壓計，不是一支羅盤。**
> 它只輸出分數與指標，**不產生任何買賣建議或短中長線建議**。氣壓計告訴你現在幾百帕，不告訴你要不要帶傘。

---

## Overview

- **抓什麼**：世界層 11 項與台灣層 6 項總經指標（進評分）、7 項只顯示不評分的觀測指標，以及台股 `^TWII` / `0050.TW` / `006208.TW` 與美股 `^GSPC` / `SPY` / `VOO` 的日線。
- **在哪裡跑**：全部在本機。排程走 Windows 工作排程器，不是 GitHub Actions cron —— 金鑰因此完全不必離開這台機器。
- **推什麼上去**：只有加密後的 HTML。**原始價格序列不進任何 repo**，連加密的也不放。
- **GitHub Actions 做什麼**：只做 `on: push` → 部署 Pages。它不抓資料、不寫資料。寫入者必須單邊，否則兩個排程器會打架。

### 刻意不做的事

| 不做 | 為什麼 |
|---|---|
| 買賣建議、短中長線建議 | 具名可交易標的的建議落在投顧業務範圍。這條線畫在**內容本身**，不畫在鎖上 |
| 自動修復被回頭改寫的歷史資料 | 半夜自己重寫歷史卻沒人知道，比壞掉還糟。偵測到只記旗標，修復由人手動觸發 |
| ORM | 六張扁平表、零 JOIN、payload 直接塞 JSON。上 ORM 是拿依賴與打包體積換零收益 |
| 後端 API + PostgreSQL | 單機單使用者，而且會失去離線能力 |
| 併發抓同一個來源 | `threads=True`、`asyncio.gather` 一律不用。額度是會被用完的東西 |

---

## Architecture

**單一進程的分層架構（Layered / N-tier），表現層採用 MVP（Model-View-Presenter）。**

更精確一點是 **local-first 的分層架構** —— SQLite 存的是快取與衍生結果，真相在外部 API。砍掉資料庫程式還是能跑，只是每次都要重抓。

```
        ┌──────────────────────────────┐
        │   app/views + app/presenters │  ← 驅動側 adapter
        │   render/（產 HTML）          │
        └──────────────┬───────────────┘
                       │ 只認 Port（Protocol）
        ┌──────────────▼───────────────┐
        │        Domain Core           │
        │  indicators / scoring /      │  ← 純規則，不知道 SQLite 存在
        │  weighting / reconcile       │
        │                              │
        │  定義 Port：                  │
        │   PriceRepository            │
        │   MacroRepository            │
        │   ScoreHistoryRepository     │
        └──────────────┬───────────────┘
                       │ 實作
        ┌──────────────▼───────────────┐
        │  被驅動側 adapter             │
        │  SqlitePriceRepo / InMemory  │
        │  YFinanceSource / Shioaji…   │
        └──────────────────────────────┘
```

**硬規定：`app/views/`、`app/presenters/`、`render/` 一律不得 import `storage/` 或 `datasources/`。**
這條界線由 `tests/test_layer_boundary.py` 用 AST 掃描守著，不靠自律。

拿到的好處具體是：傳一個 `InMemoryRepo` 進去就能測完整流程，不用碰檔案。`tests/test_repository_contract.py` 用**同一組測試**同時餵 `SqliteRepo` 與 `InMemoryRepo`，兩邊都過才算 Port 抽對了。

### 三個詞的定義（不得混用）

| 詞 | 做什麼 | 何時做 | 會不會改資料 |
|---|---|---|---|
| **比對**（reconcile） | 拿今天抓回來的跟本機已存的同一批日期逐格比 | 每天，成本零 | **不改**，只記旗標 |
| **回看**（backfill） | 往回抓漏掉或從未抓過的日期 | 固定小窗或手動 | 補進缺的列，不動既有列 |
| **重抓**（refetch） | 把某一檔的完整歷史整條抓下來覆寫 | **只手動觸發** | 覆寫整條 |

**比對是煙霧偵測器、回看是補漏、重抓是修復。自動化只做第一件。**

---

## Directory structure

```
src/barometer/
├─ config.py            ← 路徑解析與標的清單（不得寫死絕對路徑）
├─ secrets_store.py     ← 機器綁定的憑證加解密
├─ domain/              ← 純規則，零 I/O、零 UI 依賴
│  ├─ ports.py          ← Protocol 介面定義
│  ├─ indicators.py     ← MA / RSI / 布林 / 年化波動度 / 回撤
│  ├─ scoring_macro.py  ← 世界層、台灣層總經評分
│  ├─ scoring_index.py  ← 大盤與 ETF 的五個技術面維度
│  ├─ chips.py          ← 市場級籌碼面，含「ETF 要換個讀法」的但書
│  ├─ freshness.py      ← 按頻率判定「真的沒更新」vs「突然更新了」
│  ├─ windows.py        ← 交易日視窗與跨市場對齊（勞動節就卡在這裡）
│  ├─ macro_spec.py     ← 指標清單（純資料定義）
│  ├─ reconcile.py      ← 比對與 shioaji × yfinance 交叉比對
│  └─ weighting.py      ← 五日加權 10/15/20/25/30
├─ datasources/         ← 外部來源 adapter，**節流寫在這一層**
│  ├─ base.py           ← Throttle / retry_once / RequestCounter
│  ├─ yfinance_src.py
│  ├─ shioaji_src.py
│  ├─ fred_src.py       ← 官方 API（有金鑰）／免金鑰 CSV（沒有金鑰時）
│  ├─ eia_src.py        ← 原油庫存，走 WPSR 公開 CSV（免金鑰）
│  ├─ twse_src.py       ← T86 三大法人（股）、MI_MARGN 融資融券（張）
│  ├─ taifex_src.py     ← 台指期未平倉（口）、put/call ratio
│  └─ tw_gov_src.py     ← 國發會 / 主計總處 / 央行
├─ storage/
│  ├─ sqlite_repo.py    ← 實作 ports
│  ├─ memory_repo.py    ← 同一組 Port 的記憶體實作，測試用
│  ├─ csv_audit.py      ← price_raw append-only + price_current
│  └─ schema.sql
├─ pipeline/
│  ├─ fetch_prices.py / run_macro.py / run_chips.py / run_scores.py
│  ├─ build_page.py     ← 資料層 → render 的 view model（界線在這裡轉一次）
│  ├─ publish_gate.py   ← 明文沒變就不動 docs/（看明文指紋，不看密文）
│  ├─ notify.py         ← 失敗通知，通知掛掉不得拖垮管線
│  └─ runlog.py
├─ crypto/              ← 信封加密（多組密碼共用一份密文）
│  ├─ envelope.py       ← 每次發布重新產生 salt / IV / CEK
│  ├─ credentials.py    ← 只知道去哪裡讀，本身沒有任何密碼
│  ├─ shell.py / shell.html  ← WebCrypto 解鎖殼 + sessionStorage
├─ render/              ← 產明文 HTML
│  ├─ page.py           ← 四個分頁；**沒有單一的「最後更新時間」**
│  ├─ svg.py            ← inline SVG，頻率決定畫法
│  └─ lint.py           ← 命中行動字眼就讓發布失敗
└─ app/                 ← 桌面 TTK
   ├─ main.py           ← 組裝根，**唯一**能同時認得 storage 與 datasources 的地方
   ├─ presenters/       ← load() 不打網路、refresh() 才打
   └─ views/            ← 只認 Presenter

tests/                  ← 鏡射 src/ 結構
├─ test_layer_boundary.py       ← AST：表現層不得 import storage/
├─ test_repository_contract.py  ← 同一組測試餵兩個 adapter
├─ domain/                      ← 純函式測試，離線、秒級
└─ datasources/                 ← 用錄下來的回應，不打真的 API

tools/                  ← 一次性腳本與驗收（不進 src/）
```

### 本機共用資料層（不在任何 repo 內）

```
%STOCKDATA_ROOT%\           預設 D:\Research\_stockdata
├─ market.db                ← SQLite：價格、總經、評分歷史、快取
├─ price_raw\<YYYY-MM-DD>\  ← 當天抓到什麼就存什麼，append-only 稽核軌跡
├─ price_current\           ← 最新完整序列，允許被覆寫，計算用
├─ runlog\<YYYY-MM>.jsonl   ← 每次跑完 append 一筆
├─ build\                   ← 明文 HTML 落地處
└─ secrets\                 ← 憑證（機器綁定加密）
```

**為什麼價格要存兩份**：yfinance 會回頭改寫歷史（分割、除權息），而且改了不一定會說 —— `0050.TW` 的 `Stock Splits` 欄位是空的，但序列明顯被調整過。只留一份「最新」就永遠證明不了它改過。

---

## Setup & run

```powershell
# 1. 環境（Python 3.13）
conda create -n barometer python=3.13 -y
conda activate barometer
pip install -e ".[tw,dev]"

# 2. 資料根目錄與 schema
$env:STOCKDATA_ROOT = "D:\Research\_stockdata"
python tools/init_db.py            # 驗收：列出六張表

# 3. 憑證（Shioaji，選配；沒有它只是不做交叉比對）
python tools/setup_secrets.py

# 4. 抓資料
python tools/fetch_day24.py        # 六個標的的一年日線
python tools/fetch_macro.py        # 24 項總經指標
python tools/fetch_chips.py        # 市場級籌碼面（T86／融資融券／台指期／PCR）
python tools/crosscheck_tw.py      # 台股 shioaji × yfinance 交叉比對

# 5. 算分數與發布
python tools/score_index.py        # 逐日回算 + 五日加權
python tools/publish.py            # 明文 → 加密 → docs/（資料沒變就不動）
python tools/verify_publish.py     # 發布驗收，十項

# 6. 桌面程式
python -m barometer.app.main

# 7. 測試（每天收工前要全綠）
pytest -q

# 8. 排程：把上面這一串變成每天自己跑
powershell -NoProfile -ExecutionPolicy Bypass -File tools\register_tasks.ps1
```

`register_tasks.ps1` 是整份時刻表的唯一宣告處（六班：09:00 美股、09:05 總經、18:00 台股、18:05 籌碼、22:30 融資融券、22:40 發布），跑一次就在 Windows 工作排程器裡建好，換一台機器也是跑這一支。註冊前會先把現有任務匯出備份，路徑印在畫面上。

最後那一班 `Barometer-Publish` 呼叫的是 `tools/publish_and_push.ps1`：`publish.py` → 有變才 `git add -- docs` → commit → push → Actions 部署 Pages。它只動得到 `docs/` 底下那一份密文，每次都在 `%STOCKDATA_ROOT%\runlog\publish_push.log` 留一行。

> ⚠️ **`conda activate` 在某些 PowerShell 環境會靜默失效。** 如果 shell 沒有被 `conda init` 過（作者這台就是），`conda activate barometer` 會回傳 exit 0 然後什麼都沒做 —— `python` 仍然指向 base，**不會有任何錯誤訊息**，直到後面某個套件找不到才爆出來。
>
> 確認方式：`conda activate` 之後跑 `python -c "import sys; print(sys.executable)"`，路徑裡要有 `envs\barometer`。不是的話，改用 `conda run -n barometer python ...`，或先掛 hook：
>
> ```powershell
> (& "C:\Users\Alex\anaconda3\Scripts\conda.exe" shell.powershell hook) | Out-String | Invoke-Expression
> conda activate barometer
> ```


### 驗收腳本

| 腳本 | 驗的是什麼 |
|---|---|
| `tools/init_db.py` | 七張表齊備 |
| `tools/fetch_day24.py` | 六個標的落地、筆數對得上 |
| `tools/fetch_macro.py` | 24 項指標都有值或明確失敗原因、資料日期各自不同 |
| `tools/fetch_chips.py` | 籌碼面欄位名都帶單位；沒公布的日子不落地成 0 |
| `tools/crosscheck_tw.py` | 衝突筆數有數字、`remaining_bytes` 進了 run log |
| `tools/verify_compare.py` | 故意改一格 → 旗標亮起**且資料沒被自動改掉** |
| `tools/score_index.py` | 六個標的都有五日評分序列與加權平均 |
| `tools/compare_groups.py` | 三組對照差值有數字；每次都印出 0050 追蹤的是臺灣 50 不是加權指數 |
| `tools/publish.py` | 每組憑證逐一解得開、槽位代號沒錯位 |
| `tools/verify_publish.py` | §5.5 那十項（salt/IV 不重複、密文裡沒有密碼、明文沒有行動字眼…） |
| `tools/full_reconcile.py` | 撰稿前全量比對，確認數字沒被回頭改過 |
| `tools/drill_failure.py` | 打壞一個資料源：其他格照常、失敗那格說明停在哪一天、通知有送出 |
| `tools/quota_report.py` | 各來源用量、repo 與 docs/ 體積、Shioaji 剩餘流量 |
| `tools/refetch.py` | **手動**全序列重抓（自動修復一律不做） |

---

## Dependencies

| 套件 | 用途 |
|---|---|
| `yfinance` | 價格與市場類總經指標 |
| `shioaji` | 台股交叉比對（選配，`[tw]`） |
| `pandas` / `numpy` | 序列處理 |
| `requests` | FRED 官方 API 與台灣政府開放資料 |
| `cryptography` | 頁面信封加密 |
| `pynacl` | 憑證的機器綁定加密（隨 shioaji 一起來） |
| `pytest` | 測試（`[dev]`） |

Domain 層**刻意不依賴**上述任何一個 —— 它是純 Python，這由 `test_layer_boundary.py` 守著。

---

## Configuration

| 項目 | 值 |
|---|---|
| `STOCKDATA_ROOT` | 資料根目錄，預設 `D:\Research\_stockdata` |
| FRED | 金鑰放 `Key\FRED API Key.txt` 或環境變數 `FRED_API_KEY`（**選配**）。有金鑰走官方 API（120 req/min），沒有就退回 `fredgraph.csv` 免金鑰端點（30 req/min） |
| Shioaji | 憑證放 `%STOCKDATA_ROOT%\secrets\shioaji.json`，以主機名稱 + 使用者 + MAC 衍生金鑰加密 |

### 速率限制（不得調低）

| 來源 | 本專案規範 |
|---|---|
| FRED | 固定節流 1 秒/次（有金鑰時只用一半額度）；失敗退避 3 秒、重試上限 1 次；**必須用 requests 預設 UA**；**錯誤訊息一律過 `redact()`**，金鑰在 query string 裡 |
| Shioaji | 日流量 500MB；每次跑完呼叫 `api.usage()` 把 `remaining_bytes` 記進 run log |
| yfinance | 批次之間 sleep 1 秒；**禁用 `threads=True`** |
| 國發會 / 主計總處 | 同一輪更新共用一次下載，記憶體快取 1 小時 |
| EIA | 週報一週更新一次，節流 1 秒/次；免金鑰 |

**不要偽裝 User-Agent** —— FRED 實測過：偽裝 Mozilla 反而因 TLS 指紋不符被擋，用預設 UA 才放行。

**Shioaji 超流量的後果不是報錯，是行情查詢直接回空值** —— 程式會以為「那天沒資料」。所以 `remaining_bytes` 必須進 run log。

---

## 免責

本專案的輸出是量測結果，**不構成投資建議**。單次執行的觀察一律是定性觀察，不是統計證據。

# 交棒文件

給半年後的自己，或給接手的人。README 講的是「這個專案是什麼」，這份講的是
「要動它的時候，手要放在哪裡」。

驗收標準只有一句：**照著第 3 節做一次，真的能加成功一條新指標。**

---

## 1. 資料字典

### 1.1 SQLite（`%STOCKDATA_ROOT%\market.db`，七張表）

| 表 | 一列代表 | 主鍵 | 誰寫的 |
|---|---|---|---|
| `price_daily` | 一檔標的的一根日 K | (symbol, date) | `pipeline/fetch_prices.py` |
| `price_conflict` | 一次 shioaji × yfinance 對不上 | (symbol, date, field, as_of) | `tools/crosscheck_tw.py` |
| `macro_cache` | 一條總經序列的最新快取 | key | `pipeline/run_macro.py` |
| `chip_daily` | 一天的市場級籌碼面 | date | `pipeline/run_chips.py` |
| `score_history` | 一個標的某一天的分數 | (scope, symbol, as_of) | `pipeline/run_scores.py` |
| `adjustment_event` | 一次手動重抓 | (symbol, detected_at) | `tools/refetch.py` |
| `run_log` | 一次執行 | run_id | 每一支 pipeline |

### 1.2 單位 —— 這裡最容易出事

系統裡同時存在**四種**單位。它們互不換算，沒有一條「乘以 1000」可以通吃。

| 單位 | 出現在哪 | 欄位字尾 |
|---|---|---|
| **股** | `price_daily.volume_shares`、T86 三大法人買賣超 | `_shares` |
| **張** | TWSE MI_MARGN 融資融券餘額、台股**顯示層** | `_lots` |
| **口** | 台指期未平倉 | `_contracts` |
| **%** | put/call ratio、各種比率 | `_pct` |

規矩兩條：

1. **內部一律存「股」，只在顯示層換算成「張」**（`config.display_volume()` 是
   唯一的換算點）。既有專案出過「標題寫張、資料其實是股」的 bug。
2. **一口台指期不是 1000 股任何東西。** 融資融券的「張」與 K 線量的「張」是
   同一個單位，但融資融券那張表跟 T86 那張表**單位不同** —— 兩份都是 TWSE 的
   盤後資料，都在同一支 adapter 裡。所以欄位名自己帶單位，有測試守著。

### 1.3 兩個容易誤讀的欄位

| 欄位 | 陷阱 |
|---|---|
| `chip_daily.margin_lots` | 這是 MI_MARGN 的「**今日**餘額」，是**暫定值**。TWSE 自己說「請以前日餘額為準」—— D 這天的定稿要等 D+1 抓回來的 `margin_prev_lots` |
| `score_history.price_version` | 分割或除權息之後所有價格型指標都會變，**昨天的分數今天算會不一樣**。這一欄記的是用哪一版價格算的，不記就分不出差異來自市場還是來自資料被改寫 |

### 1.4 CSV（`%STOCKDATA_ROOT%`，不進任何 repo）

- `price_raw\<YYYY-MM-DD>\<symbol>.csv` —— 當天抓到什麼就存什麼，**append-only**。
  同一天重跑會附加，不覆寫。這是稽核軌跡，是唯一能證明「來源改過歷史」的東西。
- `price_current\<symbol>.csv` —— 最新完整序列，允許被覆寫，計算用。

`^TWII` 這種代號會被存成 `IDX_TWII.csv`（`csv_audit._safe_name`）。

---

## 2. 一張圖：資料怎麼流

```
外部 API ──▶ datasources/（節流在這一層，繞不過去）
                 │
                 ▼
            pipeline/（抓 → 比對 → 落地 → 算分）
                 │            │
                 │            └──▶ storage/ ──▶ market.db + CSV
                 ▼
            domain/（純規則，零 I/O，不知道 SQLite 存在）
                 │
                 ▼
   build_page.py（界線在這裡轉一次）
                 │
                 ▼
            render/ ──▶ 明文 HTML ──▶ build\（永遠不進 git）
                                          │
                                          ▼
                              crypto/envelope.py（每次換 salt/IV/CEK）
                                          │
                                          ▼
                                     docs/index.html（只有密文）
                                          │
                                          ▼
                              GitHub Actions（只部署，不抓資料）
```

**本機是唯一的寫入者，Actions 只是 renderer。**

---

## 3. 要加一條新的總經指標，動哪三個檔案

以「加一條美國零售銷售 `RSAFS`（FRED，月頻）」為例。

### 檔案一：`src/barometer/domain/macro_spec.py`

在 `WORLD`（進評分）或 `OBSERVE`（只顯示）加一列：

```python
Indicator("retail", "美國零售銷售", "每月", "fred", "RSAFS",
          "{:,.0f}", False, "world",
          note="月頻，與 CPI 同一批公布"),
```

七個位置參數的意思：`key / 顯示名 / 頻率 / 來源 / series id / 格式 / 是否用百分點`，
再加 `layer`。`freq` 決定 `render/svg.py` 畫連續線還是階梯線，也決定
`domain/freshness.py` 用哪個容忍天數 —— **寫錯頻率，圖會說謊、警示會誤報**。

### 檔案二：`src/barometer/domain/scoring_macro.py`

只有進評分的才要。寫一個 `alert_retail(s) -> Verdict` 並掛進 `ALERT_FUNCS`：

```python
def alert_retail(s: Series) -> Verdict:
    v = _need(s, 2)
    if not v:
        return False, INSUFFICIENT
    mom = (v[-1] / v[-2] - 1) * 100
    if mom < -1.0:
        return True, f"零售銷售 MoM {mom:+.2f}% < -1%"
    return False, f"零售銷售 MoM {mom:+.2f}%"
```

三條規矩：

- 資料不足**回 `INSUFFICIENT`**，不要回 `False` 假裝沒事 —— 回 False 會讓它被
  算進分母，變成一個「沒有警示」的假票。
- 判定要看**有沒有變**，不要看**值本身**。央行重貼現率那張表是歷次調整紀錄，
  相鄰兩列必然不同，拿值去比會永遠亮燈。
- 理由字串要**帶數字**。「零售銷售警示」沒有用，「MoM -1.4% < -1%」才有。

### 檔案三：`tests/domain/test_scoring_macro.py`

先寫測試，跑一次確認它**紅**，再回頭寫上面那個函式（先測試後實作）。至少三條：
超標會警示、沒超標不會、資料不足回 `INSUFFICIENT`。

### 然後

```powershell
pytest -q                        # 全綠
python tools/fetch_macro.py      # 新指標有值、資料日期正確
python tools/publish.py          # 頁面上多一列，而且它有自己的資料日期
```

> **不用動的**：`fred_src.py`（同一個來源已經接好）、`render/page.py`
> （它從 `macro_spec` 讀清單）、`app/`（Presenter 也從 `macro_spec` 讀）。
> 這三個地方不用改，就是分層有做對的證據。

**換一個新來源**（不是 FRED）才要多動兩個地方：寫一支 `datasources/<name>_src.py`，
然後在 `run_macro._fetch_one()` 加一個 `if ind.source == "<name>"` 分支。
`eia_src.py` 是最近一個例子，它還示範了一件事：**來源回的不一定是時間序列**。
WPSR 給的是一張比較表（本週／上週／去年同期），所以那支 adapter 回的是一個
快照型別，再由 `as_series()` 給顯示層兩個真實的點，中間不補。

---

## 4. 要加一檔新標的

`config.py` 的 `TW_ETFS` / `US_ETFS` 加一個代號，然後：

```powershell
python tools/fetch_day24.py
python tools/score_index.py
```

**先確認它的歷史夠長**。`scoring_index.LOOKBACK_MIN` 是 200 根 —— 不夠的話
波動度與回撤那兩個維度會是「資料不足」，分數照樣算得出來（分母變成 3），
看起來毫無異狀，但它跟其他標的量的不是同一組東西。SPCX 就是這一格。

---

## 5. 每天實際會發生什麼

| 時間 | 誰 | 做什麼 |
|---|---|---|
| 09:00 | `Barometer-Daily-US` | 抓美股三檔 |
| 18:00 | `Barometer-Daily-TW` | 抓台股三檔（實測 18:00:01 就有當天收盤） |
| 18:05 | `Barometer-Chips-TW` | 三大法人 T86 + 台指期 + put/call（T86 約 17:30 公布） |
| 22:30 | `Barometer-Chips-TW-Late` | **只補融資融券**（約 21:30 才公布，18:00 那班不去問它） |
| 手動 | 人 | `fetch_macro` → `score_index` → `publish` |
| push 之後 | GitHub Actions | 部署 Pages |

四個排程任務都勾了「錯過時間後盡快啟動」。**2026-09-07 實測過**：09:00 那次
機器在睡，15:34 醒來後 15:38 自動補跑，`LastResult=0`，run log 留下第 10 筆。

---

## 6. 出事的時候先看哪裡

| 症狀 | 先看 |
|---|---|
| 頁面停在昨天 | `%STOCKDATA_ROOT%\ALERT.md`（有東西就是有失敗），再看 `runlog\<YYYY-MM>.jsonl` |
| 某一格數字很奇怪 | `tools/full_reconcile.py` 看它是不是被回頭改過 |
| 發布之後 Pages 沒更新 | 先確認 `docs/index.html` 真的變了 —— **明文沒變就不會動 docs/**，那是設計不是故障 |
| 排程沒跑 | `Get-ScheduledTaskInfo -TaskName Barometer-Daily-TW` 看 `LastTaskResult` |
| 分數突然全部變了 | `adjustment_event` 有沒有新的一列；有的話是重抓過，`score_history` 要重算 |
| exe 打開沒反應 | 那是 PyInstaller 的錯誤對話框藏在別的視窗後面，不是當掉 |

---

## 6.5 金鑰放在哪

| 金鑰 | 放哪 | 沒有它會怎樣 |
|---|---|---|
| FRED | `Key\FRED API Key.txt`（repo 根目錄，`.gitignore` 擋著），或環境變數 `FRED_API_KEY` | 自動退回免金鑰的 `fredgraph.csv` 端點，只是額度從 120 降到 30 req/min |
| Shioaji | `%STOCKDATA_ROOT%\secrets\shioaji.json`（機器綁定加密），原始的在 `Key\Shioaji API Key.txt` | 台股不做 shioaji × yfinance 交叉比對，其餘照跑 |
| EIA 原油庫存 | **不需要金鑰** —— 走每週石油狀況報告的公開 CSV | 那一項變成「抓取失敗」，其餘照跑 |
| 發布密碼 | `%STOCKDATA_ROOT%\secrets\publish.json` | **發布會直接中止** —— 不會退而求其次發一份沒鎖的 |

`Key\` 這個資料夾兩個 repo 底下各有一份，**都被 `.gitignore` 擋著**
（`git status` 看不到它，`git check-ignore` 驗過）。

**FRED 的金鑰會出現在 query string 裡**，而 requests 的例外訊息會把整個 URL
印出來。所以 `fred_src` 裡所有對外的字串都先過 `redact()`。改那支檔案的時候，
任何新的 `raise`／`log.note`／`print` 都要記得過一次，有測試守著這件事。

---

## 7. 不要做的事

1. **不要讓任何自動化去修歷史資料。** 比對是煙霧偵測器，重抓永遠是手動的。
   半夜自己重寫歷史卻沒人知道，比壞掉還糟。
2. **不要把密碼或金鑰放進任何 repo 的追蹤範圍。** 兩個都是 public，進了版控就撤不回來。`Key\` 已被 ignore，不要用 `git add -f` 繞過它。
3. **不要在發布腳本裡寫死 salt 或 IV。** AES-GCM 重用 IV 可以直接還原明文。
4. **不要在 market-barometer 產生買賣建議。** 輸出層有 lint 擋著，但別去繞它。
5. **不要把「最後一次抓取」寫成「資料更新時間」。** 標頭那一行是**管線執行**
   的時間，可以顯示；但那 21 條序列有七八種資料日期，把它講成資料日期就是
   在說謊。每一列的資料日期仍然各自標在該列。這件事寫成了測試，會擋下來。
6. **不要為了讓測試快而調低 PBKDF2 的正式迭代數。** 測試自己 patch 就好，
   有一條守門測試對照 patch 之前的值。

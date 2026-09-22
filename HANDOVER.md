# 交棒文件

給半年後的自己，或給接手的人。README 講的是「這個專案是什麼」，這份講的是
「要動它的時候，手要放在哪裡」。

驗收標準只有一句：**照著第 3 節做一次，真的能加成功一條新指標。**

---

## 1. 資料字典

### 1.0 官方台股資料端點實測（2026-09-20）

`tools/probe_twse_endpoints.py` 於 2026-09-20 以 2026-09-18 交易日（除權息另用 2025-06-10 至 2025-06-25）向官方端點各送一次 GET。以下是實際回應，不是依端點名稱推測。九個端點均回 HTTP 200、JSON，回應位元組均可用 UTF-8 解碼；有些 `Content-Type` 未宣告 charset。探測只印欄位與筆數，不把原始行情寫進 repo。

| 資料 | 實測 URL | 回應日期／筆數 | 實際欄位 | 上櫃 8299 |
|---|---|---|---|---|
| 每日收盤 `STOCK_DAY_ALL` | `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` | `1150918`／1,377 | `Date`, `Code`, `Name`, `TradeVolume`, `TradeValue`, `OpeningPrice`, `HighestPrice`, `LowestPrice`, `ClosingPrice`, `Change`, `Transaction` | 無 |
| 官方估值 `BWIBBU_ALL` | `https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL` | `1150918`／1,078 | `Date`, `Code`, `Name`, `PEratio`, `DividendYield`, `PBratio` | 無 |
| 漲跌家數 `MI_INDEX` | `https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260918&type=ALLBUT0999&response=json` | `20260918`／「漲跌證券數合計」5 列 | 該表為 `類型`, `整體市場`, `股票`；`股票` 欄的上漲 748、下跌 251 | 無 |
| 上市月營收 | `https://openapi.twse.com.tw/v1/opendata/t187ap05_L` | `出表日期=1150917`, `資料年月=11508`／1,086 | `出表日期`, `資料年月`, `公司代號`, `公司名稱`, `產業別`, `營業收入-當月營收`, `營業收入-上月營收`, `營業收入-去年當月營收`, `營業收入-上月比較增減(%)`, `營業收入-去年同月增減(%)`, `累計營業收入-當月累計營收`, `累計營業收入-去年累計營收`, `累計營業收入-前期比較增減(%)`, `備註` | 無 |
| 逐檔外資及陸資持股 `MI_QFIIS` | `https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?date=20260918&response=json&selectType=ALLBUT0999` | `20260918`／1,362 | `證券代號`, `證券名稱`, `國際證券編碼`, `發行股數`, `外資及陸資尚可投資股數`, `全體外資及陸資持有股數`, `外資及陸資尚可投資比率`, `全體外資及陸資持股比率`, `外資及陸資共用法令投資上限比率`, `陸資法令投資上限比率`, `與前日異動原因(註)`, `最近一次上市公司申報外資及陸資持股異動日期` | 無 |
| 逐檔當沖 `TWTB4U` | `https://www.twse.com.tw/exchangeReport/TWTB4U?date=20260918&response=json&selectType=All` | `20260918`／逐檔表 1,234 列 | 總量表：`當日沖銷交易總成交股數`, `當日沖銷交易總成交股數占市場比重%`, `當日沖銷交易總買進成交金額`, `當日沖銷交易總買進成交金額占市場比重%`, `當日沖銷交易總賣出成交金額`, `當日沖銷交易總賣出成交金額占市場比重%`；逐檔表：`證券代號`, `證券名稱`, `暫停現股賣出後現款買進當沖註記`, `當日沖銷交易成交股數`, `當日沖銷交易買進成交金額`, `當日沖銷交易賣出成交金額` | 無 |
| 融券／借券賣出餘額 `TWT93U` | `https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date=20260918&response=json` | `20260918`／1,302 | `代號`, `名稱`, `前日餘額`, `賣出`, `買進`, `現券`, `今日餘額`, `次一營業日限額`, `前日餘額`, `當日賣出`, `當日還券`, `當日調整`, `當日餘額`, `次一營業日可限額`, `備註` | 無 |
| 除權息結果 `TWT49U` | `https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate=20250610&endDate=20250625&response=json` | `114年06月10日` 起／167 | `資料日期`, `股票代號`, `股票名稱`, `除權息前收盤價`, `除權息參考價`, `權值+息值`, `權/息`, `漲停價格`, `跌停價格`, `開盤競價基準`, `減除股利參考價`, `詳細資料`, `最近一次申報資料 季別/日期`, `最近一次申報每股 (單位)淨值`, `最近一次申報每股 (單位)盈餘` | 無 |
| 集保戶股權分散表 | `https://openapi.tdcc.com.tw/v1/opendata/1-5` | `20260918`／69,139 | `證券代號`, `占集保庫存數比例%`, `人數`, `\ufeff資料日期`, `股數`, `持股分級` | 有 |

回應口徑注意事項：

- TWSE OpenAPI 的 `MI_INDEX` 只有指數列；上表要用的真實漲跌家數在 TWSE 每日報表 JSON 的「漲跌證券數合計」表，且應讀 `股票` 欄，不能把包含其他商品的 `整體市場` 欄當成上市公司家數。`opendata/twtazu_od` 在實測當日仍停於 `1150605`，不可拿來當新鮮日資料。
- TWSE OpenAPI 的 `MI_QFIIS_cat` 是類股彙總，不是逐檔持股；上表的 `MI_QFIIS` 每列有 `證券代號`。TWSE OpenAPI 的 `TWTB4U` 在實測時僅回 `Date`, `Code`, `Name`, `Suspension` 且日期為 `1150921`，不含當沖成交量；上表使用每日報表 JSON。
- `TWT93U` 有兩組重名的 `前日餘額`，不可用 `dict(zip(fields, row))`，否則前一組會被覆蓋。索引 2–7 為融券，8–13 為借券賣出；借券賣出餘額是索引 12 的 `當日餘額`。所有數值單位應在正式 adapter 再核對報表註解。
- `TWT49U` 的 2025-06-10 至 2025-06-25 回應沒有 `0050` 列，不能據此宣稱它已涵蓋 `0050` 的 1:4 分割。後續 4-3 須另找可驗證該事件的官方公告來源；這裡沒有把缺列當成「沒有分割」。
- TDCC 的 `證券代號` 是固定寬度字串，例如 `8299  `，比對前要 `strip()`；日期欄實際鍵名含前置 U+FEFF。TWSE 的上述端點都沒有上櫃 `8299`，TDCC 有。ROC 日期至少有 `1150918`、`11508`、`114年06月10日`，不要當成同一種格式；TDCC 是西元 `20260918`。

### 1.1 SQLite（`%STOCKDATA_ROOT%\market.db`，十四張表）

| 表 | 一列代表 | 主鍵 | 誰寫的 |
|---|---|---|---|
| `price_daily` | 一檔標的的一根日 K | (symbol, date) | `pipeline/fetch_prices.py` |
| `price_conflict` | Shioaji 對帳差異或近期價格修訂；近期修訂另存 `old_value` / `new_value` | (symbol, date, field, as_of) | `tools/crosscheck_tw.py`、`pipeline/fetch_prices.py` |
| `macro_cache` | 一條總經序列的最新快取 | key | `pipeline/run_macro.py` |
| `chip_daily` | 一天的市場級籌碼面 | date | `pipeline/run_chips.py` |
| `score_history` | 一個標的某一天的分數 | (scope, symbol, as_of) | `pipeline/run_scores.py` |
| `adjustment_event` | 一次手動重抓或證交所公告確認的分割旗標 | (symbol, detected_at) | `tools/refetch.py`、`pipeline/fetch_prices.py` |
| `run_log` | 一次執行 | run_id | 每一支 pipeline |
| `stock_chip_daily` | 一天一檔的 T86 法人買賣超，缺值記 `null` | (date, symbol) | `research/datasources/chips_tw.py` |
| `price_adjusted` | 一檔標的的一根完整 OHLC 還原日 K，指標計算用，不進 `price_raw` | (symbol, date) | `pipeline/fetch_prices.py` |
| `tw_stock_daily` | 一天一檔的官方 A/E/F/G/H 原始欄位 | (date, symbol) | 後續 3-1、3-5～3-7 |
| `tw_market_daily` | 一天的官方 B 漲跌家數 | date | 後續 3-2 |
| `tw_stock_weekly` | 一週一檔的 TDCC D 股權分散 | (date, symbol) | 後續 3-4 |
| `tw_stock_monthly` | 一個月份一檔的 C 月營收 | (period, symbol) | 後續 3-3 |
| `us_stock_local` | 一天一檔的一種美股本地維度 | (date, symbol, dimension) | 後續 5-1～5-3 |

新表皆有資料日期（`date` 或 `data_date`）與抓取時間 `as_of`。`tw_stock_monthly` 額外以 `period` 表示營收所屬月份。`score_history` 新增 `comparable`、`native`、`strength` 三個實欄位與索引，可直接排序；舊分數列三欄為 `NULL`。2026-09-20 已先用 SQLite online backup 建立 `%STOCKDATA_ROOT%\market_pre_schema_20260920.db`，再升級實際資料庫；逐表以升級前的欄位比對筆數與 SHA-256 指紋，七張舊表的 5,672 列均保持相同。

**`adjustment_event` 是 0 列，這是對的、不是壞掉。** 這張表只在「整段固定倍數 + 證交所公告核對得上」時才寫一列（`pipeline/fetch_prices.py`）。正式庫的 `price_daily` 最早只到 2025-09-04，0050 那次 4:1 分割在 2025-06-18 —— 事件落在價格史起點之前，這條路從來沒有機會跑到。**空表代表期間內沒有分割事件，不代表偵測沒在運作**；要看它真的會動，跑 `tests/pipeline/test_recheck_split_replay.py`，那一份用 2025-06 的真實收盤價（`tests/fixtures/split_0050_202506.json`）在隔離資料庫裡重放整段。⚠️ **不要為了讓這張表有資料而回填歷史價格。**

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

### 1.4 0050 `kbars` 價格口徑實測（2026-09-20）

用 `tools/probe_0050_adjustment.py` 查 Shioaji `kbars`、Yahoo Finance `history(auto_adjust=False, actions=True)`、證交所 `STOCK_DAY`，各取 0050 跨事件的前後交易日。證交所[分割公告](https://wwwc.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d696b406fc0196ce27c2e90063.pdf)確認 2025-06-11～17 暫停交易、2025-06-18 以 4:1 分割後恢復買賣；證交所[配息清單](https://www.twse.com.tw/en/ETFortune-institute/dividendList?endDate=2025&startDate=2025&stkNo=0050)確認 2025-07-21 除息 0.36 元。

| 事件 | 來源 | 前交易日收盤 | 事件日收盤 | 直接價差 |
|---|---|---:|---:|---:|
| 4:1 分割，06-10 → 06-18 | Shioaji `kbars` | 188.65 | 47.57 | −141.08 |
| 同上 | TWSE `STOCK_DAY` | 188.65 | 47.57 | −141.08 |
| 同上 | Yahoo `Close` | 47.1625 | 47.57 | +0.4075 |
| 除息，07-18 → 07-21 | Shioaji `kbars` | 51.45 | 50.90 | −0.55 |
| 同上 | TWSE `STOCK_DAY` | 51.45 | 50.90 | −0.55 |
| 同上 | Yahoo `Close` | 51.45 | 50.90 | −0.55 |

**結論：0050 的 Shioaji `kbars` 在這兩個事件的歷史日 K 是未還原價格。** 分割前的 188.65 與證交所原始收盤價一致；Yahoo 即使 `auto_adjust=False`，分割前的 `Close` 也已除以 4。`188.65 / 4 = 47.1625`，因此 Shioaji 與 Yahoo 的直接跨期價差不可相比。除息日的 Shioaji 收盤價也與證交所原始價一致，沒有把 0.36 元加回；Yahoo 的 `Adj Close` 另有股息調整。此實測只證明 0050 這兩個事件的口徑，不能直接推論其他標的或其他事件。三方成交量略有差異，本節只用收盤價判定還原口徑。

查詢時 Shioaji 共回 27 根日 K、`usage().remaining_bytes` 為 507,472,195；Yahoo 回 32 根、證交所四個指定交易日均有資料。探測工具只印事件附近四日數值，不把價格原始序列或憑證寫入 repo。

### 1.5 CSV（`%STOCKDATA_ROOT%`，不進任何 repo）

- `price_raw\<YYYY-MM-DD>.jsonl.gz` —— 當天所有標的的抓取結果寫進同一個 gzip JSONL；同一天重跑會附加 gzip member，不覆寫舊紀錄。每列仍有 `symbol`, `date`, OHLCV, `source`, `as_of`, `stale`，是來源改寫歷史時的稽核對照。
- `csv_audit.read_raw(date)` 會同時讀新格式與尚未搬移的 `price_raw\<YYYY-MM-DD>\<symbol>.csv`。`tools/migrate_price_raw.py` 先寫暫存 gzip、逐列驗證，再替換目的檔與刪除已轉換的 CSV。2026-09-20 已將 222 個舊 CSV 的 66,520 列轉成 12 個每日檔，逐列與 `price_raw_legacy_20260920.zip` 原檔備份比對相同。
- `price_current\<symbol>.csv` —— 最新未還原序列，供比對與頁面來源標註使用；有變才合併寫入，近 `config.PRICE_REVISABLE_SESSIONS` 個交易日可更新，較早的差異僅記旗標；本機獨有的日期保留，整條覆寫只留給手動 `tools/refetch.py`。
- `price_current\.cache_meta.json` —— `CachedSource` 只存版本與最近檢查時間，不另存一份價格；TTL 內直接讀既有 `price_current` 與 SQLite `price_adjusted`，到期由最後交易日起重疊 7 個日曆日抓尾段，還原序列的重疊段若變動則重抓整段以涵蓋除息重估。
- 美股的當日日 K 在紐約時間 16:30 前視為盤中暫定列，不落地至 `price_current`、`price_daily` 或 `price_adjusted`；不維護假日日曆，Yahoo 未回傳的交易日保持缺資料。

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
| 09:05 | `Barometer-Macro` | 抓總經（FRED / 國發會沒有固定公布時刻，跟著美股那班跑） |
| 18:00 | `Barometer-Daily-TW` | 抓台股三檔（實測 18:00:01 就有當天收盤） |
| 18:05 | `Barometer-Chips-TW` | 三大法人 T86 + 台指期 + put/call（T86 約 17:30 公布） |
| 21:45 | `Barometer-Chips-TW-Late` | **只補融資融券**（約 21:30 才公布，18:00 那班不去問它） |
| 21:50 | `Barometer-Publish` | `publish.py` → 有變才 commit + push `docs/` |
| push 之後 | GitHub Actions | 部署 Pages |

**發布排在一天的最後**：當天的資料全部落地了才產頁面，所以一天只 push 一次。中間任何一班失敗，最壞的情況是頁面停在昨天，不會出現半天份的頁面。

六個排程任務都勾了「錯過時間後盡快啟動」，而且明寫了「電池上照跑、跑到一半拔電源不停」—— `New-ScheduledTaskSettingsSet` 這兩個預設值都是相反的，不明寫的話任務會在沒插電的時候安靜地不跑。整份時刻表宣告在 `tools/register_tasks.ps1`，換一台機器跑一次就重建得回來。

**2026-09-07 實測過補跑**：09:00 那次機器在睡，15:34 醒來後 15:38 自動補跑，`LastResult=0`，run log 留下第 10 筆。

**注意「有變才 commit」實際的判準。** 閘門比的是明文指紋，而明文裡有一行是「最後抓取時間」（`last_fetch_at()`，來源是 run log 不是 `now()`）。所以只要當天的抓取真的跑過，那一行就變了，頁面也就會發布 —— 即使價格一格都沒動。閘門真正擋掉的是「抓取沒跑」與「同一天重複發布」這兩種情形，不是「收盤價沒變」。

---

## 6. 出事的時候先看哪裡

| 症狀 | 先看 |
|---|---|
| 頁面停在昨天 | `%STOCKDATA_ROOT%\ALERT.md`（有東西就是有失敗），再看 `runlog\<YYYY-MM>.jsonl` |
| 某一格數字很奇怪 | `tools/full_reconcile.py` 看它是不是被回頭改過 |
| 發布之後 Pages 沒更新 | 先確認 `docs/index.html` 真的變了 —— **明文沒變就不會動 docs/**，那是設計不是故障 |
| 自動 push 沒發生 | `%STOCKDATA_ROOT%\runlog\publish_push.log` —— 每次都留一行，`END docs unchanged` 是正常、`ABORT ...` 才是故障。**push 失敗時 commit 已經在本機了**，補一次 `git push` 即可 |
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

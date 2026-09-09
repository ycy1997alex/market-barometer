# CLAUDE.md

給 Claude Code 在這個 repo 裡工作時看的。**動任何東西之前先看這份。**

| 文件 | 給誰看 | 內容 |
|---|---|---|
| `README.md` | 人 | 這是什麼、怎麼跑 |
| **`CLAUDE.md`（這份）** | Claude Code | 動它的時候要注意什麼 |
| `HANDOVER.md` | 接手的人 | 資料字典與交棒細節 |
| `UI_README.md` | 要改介面的人 | 畫面怎麼組起來、事件怎麼流、狀態放在哪 |
| `使用者指引.html` | **終端使用者** | 隨 `.exe` 一起交付。**裡面不得出現任何開發脈絡** —— 不提檔名、路徑、程式、指令、開發工具 |

## 這是什麼

世界與台灣總經、台股與美股大盤及 ETF 的**本機資料管線**。抓取、計算、加密都在本機完成，只有加密後的頁面推上 GitHub Pages。

**這是一支氣壓計，不是一支羅盤。** 它輸出分數與指標，不輸出任何買賣建議。

## 環境與指令

這台機器（MSI-Alex）**有 conda**（26.1.1，已在 PATH 上），這個專案用 **`barometer`** 環境（`C:\Users\Alex\anaconda3\envs\barometer`，Python 3.13.15）。

⚠️ **但 `conda activate` 在這台的 PowerShell 裡不會生效。** 這台沒有 conda init 過的 PowerShell profile，所以 `conda activate barometer` 會**回傳 exit 0 然後什麼都沒做** —— `CONDA_PREFIX` 是空的，`python` 仍然指向 base 的 `C:\Users\Alex\anaconda3\python.exe`。**它不報錯，只是安靜地用錯環境**，而 base 裡沒有 cryptography 與 pyinstaller，錯誤會在很後面才浮出來。

三條可行的路，擇一：

```powershell
# 1) 絕對路徑 —— 最省事，不必管 shell 狀態（底下的指令都用這個）
$py = "C:\Users\Alex\anaconda3\envs\barometer\python.exe"

# 2) conda run —— 單一指令，不必先 activate
conda run -n barometer python -m pytest -q

# 3) 真的要 activate：先把 hook 掛上
(& "C:\Users\Alex\anaconda3\Scripts\conda.exe" shell.powershell hook) | Out-String | Invoke-Expression
conda activate barometer
```

```powershell
$py = "C:\Users\Alex\anaconda3\envs\barometer\python.exe"   # Python 3.13.15
$env:STOCKDATA_ROOT = "D:\Research\_stockdata"              # 已設在使用者層級

& $py -m pytest -q                          # 測試，收工前要全綠
& $py tools/fetch_macro.py                  # 24 項總經指標
& $py tools/fetch_chips.py                  # 市場級籌碼面
& $py tools/score_index.py                  # 逐日回算 + 五日加權
& $py tools/publish.py                      # 明文 → 加密 → docs/
& $py tools/verify_publish.py               # 發布驗收，十項
& $py -m barometer.app.main                 # 桌面程式
& $py -m PyInstaller --clean --noconfirm packaging/barometer.spec
```

**跑任何會印中文的腳本都要加 `PYTHONIOENCODING=utf-8`** —— 這台機器的 console 走 cp950，中文會變亂碼，emoji 會直接讓腳本 crash。工具的輸出裡不要放 emoji。

## 紅線（違反任一條，這套東西就沒有意義了）

1. **不產生買賣建議。** 0050 與 SPY 是具名可交易標的，建議落在投顧業務範圍。這條線畫在**內容本身**，不畫在鎖上。`render/lint.py` 會掃描產出，命中行動字眼就讓發布失敗 —— 不要為了通過而繞過它。
2. **密碼與金鑰不進 repo。** 這是 public repo。`secrets/`、`Key/` 已被 `.gitignore` 擋著，不要用 `git add -f` 繞過。**也不要把金鑰印出來** —— FRED 的金鑰在 query string 裡，`fred_src` 所有對外字串都要過 `redact()`。
3. **明文 HTML 不進 git。** 只寫進 `%STOCKDATA_ROOT%\build\`，只有密文進 `docs/`。
4. **每次發布重新產生 salt / IV / CEK。** AES-GCM 重用 IV 可以直接還原明文。 `crypto/envelope.py` 裡不得出現任何常數 salt 或 iv。
5. **原始價格序列不進任何 repo**，連加密的也不放（yfinance 的條款）。
6. **自動修復歷史資料一律不做。** 比對只記旗標，重抓永遠是手動的（`tools/refetch.py`）。半夜自己重寫歷史卻沒人知道，比壞掉還糟。
7. **表現層不得 import `storage/` 或 `datasources/`。** `tests/test_layer_boundary.py` 用 AST 掃描守著。

## 寫程式的規矩

**先寫測試，再寫實作。** 每一項需求的「驗收句」就是規格，測試跟著規格先寫。跑一次確認它紅過，才有意義。

**算不出來就說算不出來。** 這個專案最常出現的判斷是「這一格沒有資料」，處置一律是回 `INSUFFICIENT` / `None` 並附上原因，**絕不回 0**。 0 會被平均進去，把「不知道」變成「很糟」。

**但「怎麼說」分兩種，取決於有沒有人正在看著**（2026-09-08 定案）：

| | 處置 | 為什麼 |
|---|---|---|
| **UI**（`presenters/`） | 回 `None`，標「資料不足（N/5 天）」 | 使用者切個分頁，畫面不該整頁掛掉 |
| **管線**（`pipeline/`） | **直接 raise** | 安靜產出一份少了幾檔的結果，比整支失敗糟得多 —— 沒有人會去比對「今天怎麼少了兩檔」 |

管線報錯時**訊息要說出是哪一檔、幾天、哪幾天**。`weighting` 自己的錯誤只說「收到 3 個」，15 檔跑到一半炸掉時那句話沒有任何幫助。

**而且中止時要記完 runlog 再重拋。** `run()` 原本只有 `try/finally`， `record_run()` 與 `log.append()` 都在 `try` 的尾巴 —— 一往上拋就全部跳過，失敗的那一次在 runlog 裡完全不存在。**沒有紀錄的失敗，事後跟「排程根本沒觸發」長得一模一樣。**

**判定看變化，不看水位。** 央行重貼現率那張表是歷次調整紀錄，相鄰兩列必然不同，拿值去比會永遠亮燈。同一個錯在外資期貨、融資餘額上都會再出現一次。

**邊界規則寫成測試，不寫成註解。** 註解半年後只是一段沒人看的文字。

## 這裡最容易出事的地方

**單位有五種，互不換算**：股（`_shares`）、張（`_lots`）、口（`_contracts`）、百分比（`_pct`）、百萬桶（`_mbbl`）。欄位名一律帶單位字尾，有測試守著。內部一律存「股」，只在顯示層換算成「張」（`config.display_volume()` 是唯一入口）。

**兩個市場的日期不會對齊。** 台股一年 243~244 根、美股 252 根；2026-09-07 是美國勞動節，台股照常。任何假設兩市場對齊的程式碼都會安靜地錯位 —— 對齊集中在 `domain/windows.py`，由測試守著。

**時間有兩種，不能混成一個。** 「最後一次抓取」是管線執行時間，「資料日期」是那條序列的值屬於哪一天。24 條序列有 9 種資料日期，把它們壓成一個時間戳就是在說謊。

**打包成功不等於跑得起來。** 驗收是「建置日誌零個 `Library not found`」加上「實際啟動 exe，視窗真的出現」。`excludes` 清單會過期，過期的方式是「打得起來、跑不起來」。

## Git

**`docs/` 由排程自動 commit + push；其他一律作者發動。**

`tools/publish_and_push.ps1`（排程任務 `Barometer-Publish`，每天 22:40）跑完 `publish.py` 之後會自己 `git add -- docs` → commit → `git push origin HEAD`，push 進 master 就觸發 Actions 部署 Pages。這是刻意開的例外，撐著它的是三件事：

1. **它動得到的只有 `docs/` 底下那一份密文。** 只 stage `docs/`，不用 `git add -A`、不用 `git add .`、永遠不用 `-f`（`-f` 會繞過 `.gitignore`，而 `secrets/`、`Key/` 正是靠它擋著）。
2. **進來時 index 不是空的就中止。** 作者手上 staged 的東西，排程不碰、也不替他 reset 掉。
3. **紅線由 `tests/test_publish_push.py` 守著**，不是靠自律 —— 自動 push 與手動 push 的差別就是沒有人在按 Enter 之前看一眼 diff。

**其他任何檔案的 commit / push 仍然一律由作者發動。** 工作到了 commit 點就說一句，然後把指令印出來（`/git-commit`）—— 印出指令就是交付，執行是作者的事。

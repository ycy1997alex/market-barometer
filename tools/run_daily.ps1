# 每日排程的實際進入點（ToDo §9 Day 24 第 10 項）。
#
# Windows 工作排程器呼叫這支，而不是直接呼叫 python —— 這樣排程設定裡
# 就不必塞一長串參數，而且環境變數集中在一個地方。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools\run_daily.ps1 -Market tw
#   powershell -ExecutionPolicy Bypass -File tools\run_daily.ps1 -Market us

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("tw", "us", "macro", "chips", "chips-late")]
    [string]$Market
)

$ErrorActionPreference = "Stop"

$Python = "C:\Users\Alex\anaconda3\envs\barometer\python.exe"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:STOCKDATA_ROOT = "D:\Research\_stockdata"
$env:PYTHONPATH = Join-Path $RepoRoot "src"
$env:PYTHONIOENCODING = "utf-8"

# 籌碼面分兩班：三大法人約 17:30 公布（18:00 抓得到），
# 融資融券約 21:30 才公布（所以 18:00 那班根本不去問它）。
$module = switch ($Market) {
    "tw"         { "barometer.pipeline.run_tw" }
    "us"         { "barometer.pipeline.run_us" }
    "macro"      { "barometer.pipeline.run_macro" }
    "chips"      { "barometer.pipeline.run_chips_tw" }
    "chips-late" { "barometer.pipeline.run_chips_tw" }
}
$moduleArgs = if ($Market -eq "chips-late") { @("late") } else { @() }

# 這個 wrapper 自己的訊息一律用 ASCII —— 排程任務的 stdout 走系統 ACP（950），
# 中文會變成亂碼。Python 那一側已經設了 PYTHONIOENCODING=utf-8，中文由它印。
Write-Output "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') START $Market ==="
& $Python -m $module @moduleArgs
$code = $LASTEXITCODE
Write-Output "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') END $Market exit=$code ==="

# 排程任務的成敗以這個為準。partial（單一標的失敗）在 run_*.py 裡已經
# 算成 0 —— 任何單一標的的失敗都不得讓整批看起來像壞了。
exit $code

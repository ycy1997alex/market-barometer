# 發布 → commit → push：排程鏈的後半段（ToDo §1 第 4、6 條、§9 Day 28 第 3 項）。
#
#   抓資料（run_daily.ps1）→ 發布（publish.py 寫 docs/）→ 【這支：commit + push】
#   → GitHub Actions 部署 Pages
#
# **為什麼這一支可以自動 push。**
# `publish.py` 的閘門比的是**明文的指紋**，不是密文：明文沒變就連 docs/ 都不碰
# （密文每次都換 salt/IV/CEK 是刻意的，拿它去比會每天多一筆只有隨機數不同的
# commit）。所以「資料沒變就不 commit」是閘門保證的事實，不是這支腳本在猜。
# 它動得到的東西也只有 docs/ 底下那一份密文。
#
# 三條紅線寫死在下面，`tests/test_publish_push.py` 守著：
#   1. 只 stage `docs/` —— 不用 `git add -A`、不用 `git add .`、永遠不用 `-f`
#   2. 進來時 index 不是空的就中止 —— 作者手上 staged 的東西，排程不碰
#   3. stage 完再驗一次：出現 docs/ 以外的路徑就中止，不 commit
#
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\publish_and_push.ps1
#   ... -Force   # 明文沒變也重發一次（手動補救用，排程不帶這個）

param([switch]$Force)

$ErrorActionPreference = "Stop"

# 排程跑的時候沒有人在看 stdout，所以這支自己留一份紀錄。
# 沒有紀錄的失敗，事後跟「排程根本沒觸發」長得一模一樣。
$Python = "C:\Users\Alex\anaconda3\envs\barometer\python.exe"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:STOCKDATA_ROOT = "D:\Research\_stockdata"
$env:PYTHONPATH = Join-Path $RepoRoot "src"
$env:PYTHONIOENCODING = "utf-8"

$LogDir = Join-Path $env:STOCKDATA_ROOT "runlog"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogPath = Join-Path $LogDir "publish_push.log"

# 訊息一律 ASCII —— 排程任務的 stdout 走系統 ACP（950），中文會變成亂碼。
# Python 那一側已經設了 PYTHONIOENCODING=utf-8，中文由它印。
function Say([string]$msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [market-barometer] $msg"
    Write-Output $line
    Add-Content -Path $LogPath -Value $line -Encoding utf8
}

Say "START publish_and_push"

# --- 1. 發布：明文沒變的話，這一步連 docs/ 都不會碰 ---
$publishArgs = @()
if ($Force) { $publishArgs += "--force" }
& $Python (Join-Path $RepoRoot "tools\publish.py") @publishArgs
if ($LASTEXITCODE -ne 0) {
    Say "ABORT publish.py exit=$LASTEXITCODE, nothing committed"
    exit $LASTEXITCODE
}

# --- 2. docs/ 真的變了嗎 ---
$dirty = & git -C $RepoRoot status --porcelain -- docs
if ($LASTEXITCODE -ne 0) { Say "ABORT git status failed"; exit 1 }
if (-not $dirty) {
    Say "END docs unchanged, no commit"
    exit 0
}

# --- 3. 紅線：docs/ 底下不得有資料檔（pages.yml 也擋，但那是 push 之後了） ---
$leaked = Get-ChildItem -Path (Join-Path $RepoRoot "docs") -Recurse -File |
          Where-Object { $_.Extension -in ".csv", ".db", ".json", ".sqlite" }
if ($leaked) {
    Say "ABORT data files under docs/:"
    foreach ($f in $leaked) { Say ("  " + $f.FullName) }
    exit 1
}

# --- 4. 紅線：作者手上 staged 的東西，排程不碰 ---
$preStaged = & git -C $RepoRoot diff --cached --name-only
if ($LASTEXITCODE -ne 0) { Say "ABORT git diff --cached failed"; exit 1 }
if ($preStaged) {
    Say "ABORT index is not empty, leaving it alone:"
    foreach ($p in $preStaged) { Say ("  " + $p) }
    exit 1
}

# --- 5. stage、再驗一次 ---
& git -C $RepoRoot add -- docs
if ($LASTEXITCODE -ne 0) { Say "ABORT git add failed"; exit 1 }

$staged = & git -C $RepoRoot diff --cached --name-only
$stray = $staged | Where-Object { $_ -notlike "docs/*" }
if ($stray) {
    Say "ABORT staged path outside docs/:"
    foreach ($p in $stray) { Say ("  " + $p) }
    exit 1
}
Say ("staged " + ($staged -join ", "))

# --- 6. commit + push ---
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
& git -C $RepoRoot commit -m "🔧 chore(publish): update docs/ ($stamp)"
if ($LASTEXITCODE -ne 0) { Say "ABORT git commit failed"; exit 1 }

& git -C $RepoRoot push origin HEAD
if ($LASTEXITCODE -ne 0) {
    Say "ABORT git push failed exit=$LASTEXITCODE (commit is local, retry by hand)"
    exit 1
}

$sha = & git -C $RepoRoot rev-parse --short HEAD
Say "END pushed $sha, Actions will deploy Pages"
exit 0

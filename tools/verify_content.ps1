# Scheduled entry point for the day-over-day content review (R-3).
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$Python = "C:\Users\Alex\anaconda3\envs\barometer\python.exe"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:STOCKDATA_ROOT = "D:\Repo\_stockdata"
$env:PYTHONPATH = Join-Path $RepoRoot "src"
$env:PYTHONIOENCODING = "utf-8"
$logDir = Join-Path $env:STOCKDATA_ROOT "runlog"
if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
Set-Location -LiteralPath (Join-Path $env:STOCKDATA_ROOT "runlog")

Write-Output "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') START verify-content ==="
& $Python (Join-Path $PSScriptRoot "verify_content.py")
$code = $LASTEXITCODE
Write-Output "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') END verify-content exit=$code ==="
# 這份報告是給人讀的，不阻擋發布（2-5）—— 比對結果不得變成排程的失敗碼。
exit 0

# Scheduled entry point for the Shioaji TW crosscheck.
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

Write-Output "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') START crosscheck-tw ==="
& $Python (Join-Path $PSScriptRoot "crosscheck_tw.py")
$code = $LASTEXITCODE
Write-Output "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') END crosscheck-tw exit=$code ==="
exit $code

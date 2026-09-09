# 把整條鏈的排程宣告在一個地方（ToDo §1 第 3 條、§9 Day 24 第 10 項）。
#
# 原本四個任務是手動在工作排程器 UI 裡開的，所以「每天到底跑什麼」只存在於
# 那台機器的登錄檔裡 —— 換一台機器就得憑記憶重建一次。這支把它變成程式碼。
#
# **執行前會先把現有任務的定義匯出備份**，路徑印在畫面上。
#
# 用法（要用有權限的身分跑，一般使用者即可，任務用 InteractiveToken）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\register_tasks.ps1
#
# 驗證：`Get-ScheduledTaskInfo -TaskName Barometer-Publish`，看 NextRunTime。

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $RepoRoot "tools"

# 時刻表的理由都寫在這裡，不要只留一個數字：
#   09:00 美股 —— 美股收盤是台北清晨，早上抓到的是昨夜收盤
#   09:05 總經 —— FRED / 國發會沒有固定時刻，跟著美股那班一起跑就好
#   18:00 台股 —— 實測 18:00:01 跑完就有當天收盤
#   18:05 籌碼 —— 三大法人 T86 約 17:30 公布
#   22:30 籌碼補班 —— 融資融券約 21:30 才公布，18:00 那班根本不去問它
#   22:40 發布 —— 排在最後：當天的資料全部落地了才產頁面，一天只 push 一次
$Tasks = @(
    @{ Name = "Barometer-Daily-US";      At = "09:00"; Script = "run_daily.ps1";         Extra = @("-Market", "us");         Desc = "market-barometer daily us fetch" },
    @{ Name = "Barometer-Macro";         At = "09:05"; Script = "run_daily.ps1";         Extra = @("-Market", "macro");      Desc = "market-barometer macro fetch" },
    @{ Name = "Barometer-Daily-TW";      At = "18:00"; Script = "run_daily.ps1";         Extra = @("-Market", "tw");         Desc = "market-barometer daily tw fetch" },
    @{ Name = "Barometer-Chips-TW";      At = "18:05"; Script = "run_daily.ps1";         Extra = @("-Market", "chips");      Desc = "market-barometer tw chips (T86 + futures)" },
    @{ Name = "Barometer-Chips-TW-Late"; At = "22:30"; Script = "run_daily.ps1";         Extra = @("-Market", "chips-late"); Desc = "market-barometer tw margin trading (late)" },
    @{ Name = "Barometer-Publish";       At = "22:40"; Script = "publish_and_push.ps1";  Extra = @();                        Desc = "market-barometer publish + push docs/" }
)

# --- 備份現有定義 ---
$backupDir = Join-Path $env:STOCKDATA_ROOT "runlog"
if (-not $env:STOCKDATA_ROOT) { $backupDir = $env:TEMP }
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }
$backup = Join-Path $backupDir ("scheduled_tasks_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".xml")

$existing = @()
foreach ($t in $Tasks) {
    try { $existing += (Export-ScheduledTask -TaskName $t.Name -ErrorAction Stop) } catch { }
}
if ($existing) {
    Set-Content -Path $backup -Value ($existing -join "`r`n") -Encoding utf8
    Write-Output "backup: $backup ($($existing.Count) task(s))"
} else {
    Write-Output "backup: nothing to back up (no task registered yet)"
}

# --- 註冊 ---
# 這是筆電：電池上也要跑，跑到一半拔電源也不要停 —— New-ScheduledTaskSettingsSet
# 的預設值兩個都相反，不明寫的話任務會在沒插電的時候安靜地不跑。
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive

foreach ($t in $Tasks) {
    $script = Join-Path $Tools $t.Script
    if (-not (Test-Path $script)) { throw "missing script: $script" }

    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + $script + '"')) + $t.Extra
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($argList -join " ")
    $trigger = New-ScheduledTaskTrigger -Daily -At $t.At

    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Description $t.Desc -Force | Out-Null
    Write-Output ("registered {0,-26} {1}  {2} {3}" -f $t.Name, $t.At, $t.Script, ($t.Extra -join " "))
}

Write-Output ""
Get-ScheduledTask -TaskName ($Tasks | ForEach-Object { $_.Name }) |
    ForEach-Object {
        $i = $_ | Get-ScheduledTaskInfo
        "{0,-26} State={1,-8} Next={2}" -f $_.TaskName, $_.State, $i.NextRunTime
    }

# 현재 사용자로 실행하는 Windows 예약입니다. API 키·DB 비밀번호를 작업 인수에 넣지 않습니다.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$taskName = 'LunchTravelNewsDaily1600'
if (-not (Test-Path $pythonPath)) { throw 'Run 13_OpenAI first to install Python dependencies.' }
# Windows의 작업 시각은 로컬 시간입니다. 한국·일본은 모두 UTC+9입니다.
if ((Get-TimeZone).Id -notin @('Korea Standard Time', 'Tokyo Standard Time')) {
    throw 'Set Windows timezone to Korea Standard Time before registering the 16:00 task.'
}
Push-Location $projectRoot
try {
    $rawStatus = & $pythonPath -m news_service.automation --status
    if ($LASTEXITCODE -ne 0) { throw 'Run 15_Notion setup first.' }
    $config = ($rawStatus -join "`n") | ConvertFrom-Json
    if (-not $config.enabled) { throw 'Automation is disabled. Run 15_Notion setup first.' }
    $action = New-ScheduledTaskAction -Execute $pythonPath -Argument '-m news_service.automation --run-due' -WorkingDirectory $projectRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At '16:00'
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $userName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $userName -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Get-ScheduledTaskInfo -TaskName $taskName | Select-Object NextRunTime, LastRunTime, LastTaskResult
    Write-Host 'Registered: daily 16:00 KST. Keep this PC signed in, awake and MySQL running.'
} finally {
    Pop-Location
}

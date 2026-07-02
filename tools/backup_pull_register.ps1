# 백업 pull 작업 스케줄러 등록 (참고용 — 이 PC에서는 정책상 Register-ScheduledTask/ONLOGON 거부됨)
# 실제 등록 상태(2026-07-02): schtasks /SC DAILY /ST 14:00 "MoneyMilestone DB Backup Pull" ✅
#   schtasks /Create /TN "MoneyMilestone DB Backup Pull" /TR "powershell.exe ... backup_pull.ps1" /SC DAILY /ST 14:00
# PC 꺼진 날 = 미실행이지만 서버가 30일 보존 → 다음 14:00 pull이 밀린 파일 자동 수거.
# 로그온 트리거를 추가하고 싶으면 관리자 PowerShell에서 이 스크립트 실행.

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "backup_pull.ps1"
$taskName   = "MoneyMilestone DB Backup Pull"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

$triggers = @(
    (New-ScheduledTaskTrigger -AtLogOn),
    (New-ScheduledTaskTrigger -Daily -At 14:00)
)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers `
    -Settings $settings -Force | Out-Null

Write-Host "등록 완료: $taskName"
Write-Host "확인: Get-ScheduledTask -TaskName '$taskName'"

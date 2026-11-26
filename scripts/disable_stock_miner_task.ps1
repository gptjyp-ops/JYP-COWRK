$ErrorActionPreference = 'Stop'
$taskName = 'Stock Miner Daily Upload'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "예약 작업 없음: $taskName"
    exit 0
}
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Disable-ScheduledTask -TaskName $taskName | Out-Null
$state = (Get-ScheduledTask -TaskName $taskName).State
Write-Host "중지 완료: $taskName / 상태: $state"

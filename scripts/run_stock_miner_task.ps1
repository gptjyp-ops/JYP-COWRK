param([Parameter(Mandatory = $true)][string]$Python)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logs = Join-Path $repo 'stock-miner-logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$log = Join-Path $logs ('upload-' + (Get-Date -Format 'yyyy-MM-dd-HHmmss') + '.log')
Start-Transcript -Path $log | Out-Null
try {
    Set-Location $repo
    & $Python (Join-Path $PSScriptRoot 'publish_stock_miner.py')
    if ($LASTEXITCODE -ne 0) { throw "Stock Miner 업로드 실패 (종료 코드 $LASTEXITCODE)" }
} finally {
    Stop-Transcript | Out-Null
}

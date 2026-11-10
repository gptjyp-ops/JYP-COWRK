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
    if ($LASTEXITCODE -ne 0) {
        $statusPath = Join-Path $repo 'data\stock-miner-collector-status.json'
        try {
            if (Test-Path $statusPath) {
                $health = Get-Content $statusPath -Raw | ConvertFrom-Json
                if ($health.status -eq 'ip_not_registered') {
                    Start-Process -FilePath "$env:SystemRoot\System32\msg.exe" -ArgumentList @('*', 'Stock Miner: Kiwoom allowed IP needs updating.') -WindowStyle Hidden
                }
            }
        } catch {}
        throw "Stock Miner 업로드 실패 (종료 코드 $LASTEXITCODE)"
    }
} finally {
    Stop-Transcript | Out-Null
}

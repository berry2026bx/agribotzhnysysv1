[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pidFile = Join-Path $projectRoot 'docs/dayuwriter/baseline/live-yolo-dashboard.pid'
if (Test-Path -LiteralPath $pidFile) {
    $pidValue = [int](Get-Content -LiteralPath $pidFile -Raw)
    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($null -ne $process) { Stop-Process -Id $pidValue -Force }
    Remove-Item -LiteralPath $pidFile -Force
    Write-Host "Stopped YOLO dashboard PID $pidValue. Reconfirm physical P0 before another motion run."
} else {
    Write-Host 'No recorded YOLO dashboard PID. No process was stopped.'
}

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$PythonPath,

    [Parameter(Mandatory)]
    [ValidatePattern('^COM\d+$')]
    [string]$Port,

    [Parameter(Mandatory)]
    [double]$BaselineX,

    [Parameter(Mandatory)]
    [double]$BaselineY,

    [ValidateRange(1, 500)]
    [double]$Feed = 500,

    [ValidateNotNullOrEmpty()]
    [string]$DashboardUrl = 'http://127.0.0.1:8765/state.json'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python interpreter was not found: $PythonPath"
}

Set-Location $projectRoot
Write-Host 'Armed automatic XY follow is starting from the captured P0 visual baseline.'
Write-Host 'The current red square is the P0 arm point; it must not move until the program reports it is armed.'
Write-Host 'After a new stable target appears, the machine moves in XY, holds 10 seconds, and returns to P0.'
Write-Host 'Press Ctrl+C in this window to stop. A stop can leave the pen away from P0.'

& $PythonPath -m communication.dayuwriter.visual_follow `
    --dashboard-url $DashboardUrl `
    --port $Port `
    --baseline-x $BaselineX `
    --baseline-y $BaselineY `
    --continuous `
    --wait-for-target-change `
    --until-stopped `
    --return-to-p0 `
    --hold-at-target-seconds 10 `
    --feed $Feed `
    --execute `
    --physical-preflight

exit $LASTEXITCODE

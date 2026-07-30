[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$PythonPath,

    [Parameter(Mandatory)]
    [ValidatePattern('^COM\d+$')]
    [string]$Port
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python interpreter was not found: $PythonPath"
}

Set-Location $projectRoot
Write-Host "Starting GRBL monitor for $Port."
Write-Host 'The monitor starts disconnected. Only connect after the physical checks are complete.'

& $PythonPath -m communication.dayuwriter.grbl_monitor --port $Port

exit $LASTEXITCODE

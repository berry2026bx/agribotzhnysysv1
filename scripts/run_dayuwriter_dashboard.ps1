[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$PythonPath,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$CameraSerial,

    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python interpreter was not found: $PythonPath"
}

Set-Location $projectRoot
Write-Host "Starting display-only D435i dashboard for camera $CameraSerial on port $Port."
Write-Host "Close this window or press Ctrl+C to stop the dashboard and release the camera."

& $PythonPath -m vision.realsense.live_red_target_dashboard `
    --serial $CameraSerial `
    --aruco-reference-board `
    --reference-registration docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json `
    --port $Port

exit $LASTEXITCODE

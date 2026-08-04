[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$Model,
    [Parameter(Mandatory)] [string]$ClassName,
    [string]$Serial = '231122070403',
    [int]$Port = 8765,
    [switch]$ArmMotion,
    [switch]$ZDropPreflight,
    [double]$ZDropMm = 0.0
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $projectRoot
if (-not (Test-Path -LiteralPath $Model -PathType Leaf)) { throw "YOLO model not found: $Model" }
if ($ZDropMm -lt 0 -or $ZDropMm -gt 1) { throw 'ZDropMm must be within 0 to 1 mm' }
if ($ZDropMm -gt 0 -and -not $ZDropPreflight) { throw 'A positive ZDropMm requires -ZDropPreflight' }
$python = (Get-Command python -ErrorAction Stop).Source
$dashboardLog = Join-Path $projectRoot 'docs/dayuwriter/baseline/live-yolo-dashboard.stdout.log'
$dashboardErr = Join-Path $projectRoot 'docs/dayuwriter/baseline/live-yolo-dashboard.stderr.log'
$dashboard = Start-Process -FilePath $python -ArgumentList @('-m','vision.realsense.live_yolo_dashboard','--serial',$Serial,'--model',(Resolve-Path $Model).Path,'--class-name',$ClassName,'--port',$Port) -WorkingDirectory $projectRoot -RedirectStandardOutput $dashboardLog -RedirectStandardError $dashboardErr -PassThru
$dashboard.Id | Set-Content -LiteralPath (Join-Path $projectRoot 'docs/dayuwriter/baseline/live-yolo-dashboard.pid')
Start-Process "http://127.0.0.1:$Port/"
Write-Host "YOLO dashboard started in display-only mode (PID $($dashboard.Id))."
if (-not $ArmMotion) {
    Write-Host 'No motion armed. Confirm fixed physical P0, 12 V, hovering tip, clear XY path, and Z clearance before rerunning with -ArmMotion.'
    exit 0
}
$ports = Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'USB-SERIAL CH340|USB-SERIAL CH341' -and $_.Name -match '\(COM\d+\)' } | ForEach-Object { if ($_.Name -match '\((COM\d+)\)') { $Matches[1] } }
$ports = @($ports | Sort-Object -Unique)
if ($ports.Count -ne 1) { throw "Expected exactly one CH340 port; found $($ports -join ', ')" }
Write-Host "Detected one CH340: $($ports[0])."
$followArgs = @('-m','communication.dayuwriter.visual_follow','--dashboard-url',"http://127.0.0.1:$Port/state.json",'--class-name',$ClassName,'--port',$ports[0],'--baseline-x','0','--baseline-y','0','--execute','--physical-preflight','--feed','500','--continuous','--max-moves','1','--max-observations','120','--return-to-p0','--hold-at-target-seconds','10')
if ($ZDropMm -gt 0) { $followArgs += @('--z-drop-mm',([string]$ZDropMm),'--z-drop-preflight') }
& $python @followArgs
exit $LASTEXITCODE

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [switch]$ArmAtP0,

    [string]$PythonPath,
    [string]$CameraSerial,

    [ValidateRange(1, 65535)]
    [int]$DashboardPort = 8765,

    [ValidateRange(10, 180)]
    [int]$ReadyTimeoutSeconds = 90,

    [ValidateRange(1, 500)]
    [double]$Feed = 500
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Test-DayuWriterPython {
    param([string]$Candidate)

    if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
        return $false
    }
    & $Candidate -c "import serial, numpy, pyrealsense2, cv2; assert hasattr(cv2, 'aruco')" 2>$null
    return $LASTEXITCODE -eq 0
}

function Resolve-DayuWriterPython {
    param([string]$RequestedPath)

    $candidates = [System.Collections.Generic.List[string]]::new()
    if ($RequestedPath) {
        $candidates.Add($RequestedPath)
    }
    if ($env:DAYUWRITER_PYTHON) {
        $candidates.Add($env:DAYUWRITER_PYTHON)
    }
    $candidates.Add((Join-Path $env:USERPROFILE '.conda\envs\dayuwriter-control\python.exe'))

    $conda = Get-Command conda -ErrorAction SilentlyContinue
    if ($conda) {
        try {
            $environmentList = (& $conda.Source env list --json | ConvertFrom-Json).envs
            foreach ($environmentPath in $environmentList) {
                if ((Split-Path $environmentPath -Leaf) -eq 'dayuwriter-control') {
                    $candidates.Add((Join-Path $environmentPath 'python.exe'))
                }
            }
        }
        catch {
            Write-Warning 'Conda environments could not be enumerated; trying the standard path only.'
        }
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-DayuWriterPython $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw 'No usable dayuwriter-control Python interpreter was found. Create the environment first, or pass -PythonPath / set DAYUWRITER_PYTHON.'
}

function Get-UniqueCh340Port {
    $ports = @(
        Get-CimInstance Win32_SerialPort |
            Where-Object { $_.Name -match 'CH340|CH341|USB-SERIAL' -or $_.PNPDeviceID -match 'VID_1A86' }
    )
    if ($ports.Count -eq 1) {
        return $ports[0].DeviceID
    }
    if ($ports.Count -eq 0) {
        throw 'No CH340 serial port was found. Connect the writer USB and close other serial programs.'
    }
    $ports | Select-Object DeviceID, Name, PNPDeviceID | Format-Table | Out-Host
    throw 'More than one possible CH340 port was found. Disconnect extras or identify the correct COMx before automatic follow.'
}

function Wait-ForP0Baseline {
    param(
        [string]$StateUrl,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $state = Invoke-RestMethod $StateUrl
            if (
                $state.state -eq 'ready' -and
                $state.mapping_state -eq 'available' -and
                $null -ne $state.machine_xy_mm -and
                $null -ne $state.target
            ) {
                return [pscustomobject]@{
                    X = [double]$state.machine_xy_mm.x
                    Y = [double]$state.machine_xy_mm.y
                }
            }
        }
        catch {
            # The dashboard child process may still be starting; retry until the deadline.
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Dashboard did not become ready with a red target within $TimeoutSeconds seconds. Do not arm automatic follow."
}

function Start-VisiblePowerShellScript {
    param(
        [string]$ScriptPath,
        [string]$Arguments
    )

    $argumentLine = '-NoExit -NoProfile -ExecutionPolicy Bypass -File "{0}" {1}' -f $ScriptPath, $Arguments
    Start-Process -FilePath 'powershell.exe' -ArgumentList $argumentLine
}

$python = Resolve-DayuWriterPython $PythonPath
$safeLauncher = Join-Path $PSScriptRoot 'start_dayuwriter_session.ps1'

Write-Host 'ArmAtP0 accepted: dashboard will capture the current red-square coordinate as P0.'
Write-Host 'Keep the red square centered on physical P0 until the automatic-follow window opens.'
& $safeLauncher -PythonPath $python -CameraSerial $CameraSerial -DashboardPort $DashboardPort -NoMonitor

$stateUrl = "http://127.0.0.1:$DashboardPort/state.json"
$baseline = Wait-ForP0Baseline -StateUrl $stateUrl -TimeoutSeconds $ReadyTimeoutSeconds
$port = Get-UniqueCh340Port

$runner = Join-Path $PSScriptRoot 'run_dayuwriter_continuous_follow.ps1'
$runnerArguments = '-PythonPath "{0}" -Port "{1}" -BaselineX {2:F6} -BaselineY {3:F6} -Feed {4} -DashboardUrl "{5}"' -f `
    $python, $port, $baseline.X, $baseline.Y, $Feed, $stateUrl
Start-VisiblePowerShellScript $runner $runnerArguments

Write-Host ("Captured P0 visual baseline: X={0:F3} mm, Y={1:F3} mm" -f $baseline.X, $baseline.Y)
Write-Host 'Automatic follow is being armed in its own visible terminal. Do not move the red square until that window reports it is armed.'

[CmdletBinding()]
param(
    [string]$PythonPath,
    [string]$CameraSerial,
    [ValidateRange(1, 65535)]
    [int]$DashboardPort = 8765,
    [switch]$NoMonitor
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

function Get-ConnectedRealSenseSerials {
    param([string]$Interpreter)

    $code = @'
import pyrealsense2 as rs
context = rs.context()
for device in context.devices:
    if device.get_info(rs.camera_info.name).lower() != "platform camera":
        print(device.get_info(rs.camera_info.serial_number))
'@
    $serials = @(& $Interpreter -c $code | Where-Object { $_ -match '^\d+$' })
    if ($LASTEXITCODE -ne 0) {
        throw 'RealSense device enumeration failed. Check the USB 3.x connection and close Viewer or other camera programs.'
    }
    return $serials
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
        Write-Warning 'No CH340 serial port was found. Dashboard will start, but the GRBL monitor will not be opened.'
    }
    else {
        Write-Warning 'More than one possible CH340 port was found. Dashboard will start, but the GRBL monitor will not be opened.'
        $ports | Select-Object DeviceID, Name, PNPDeviceID | Format-Table | Out-Host
    }
    return $null
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
$connectedSerials = Get-ConnectedRealSenseSerials $python
if ($CameraSerial) {
    if ($connectedSerials -notcontains $CameraSerial) {
        throw "Requested D435i serial $CameraSerial is not connected. Detected: $($connectedSerials -join ', ')"
    }
}
elseif ($connectedSerials.Count -eq 1) {
    $CameraSerial = $connectedSerials[0]
}
else {
    throw "Expected exactly one RealSense camera. Detected: $($connectedSerials -join ', '). Re-run with -CameraSerial <serial>."
}

$listener = Get-NetTCPConnection -LocalPort $DashboardPort -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    throw "Port $DashboardPort is already occupied by PID $($listener[0].OwningProcess). Close the existing dashboard before starting a new one."
}

$dashboardScript = Join-Path $PSScriptRoot 'run_dayuwriter_dashboard.ps1'
Start-VisiblePowerShellScript $dashboardScript ('-PythonPath "{0}" -CameraSerial "{1}" -Port {2}' -f $python, $CameraSerial, $DashboardPort)

if (-not $NoMonitor) {
    $port = Get-UniqueCh340Port
    if ($port) {
        $monitorScript = Join-Path $PSScriptRoot 'run_dayuwriter_grbl_monitor.ps1'
        Start-VisiblePowerShellScript $monitorScript ('-PythonPath "{0}" -Port "{1}"' -f $python, $port)
    }
}

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:$DashboardPort/"
Write-Host 'Started only the display dashboard and the disconnected GRBL monitor.'
Write-Host 'No visual-follow command, GRBL Jog, Z drop, or motor motion was started.'

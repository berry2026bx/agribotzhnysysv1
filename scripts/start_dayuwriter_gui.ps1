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
    $candidates = [System.Collections.Generic.List[string]]::new()
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
            # The normal user-profile path remains available as the fallback.
        }
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-DayuWriterPython $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }
    throw 'No complete dayuwriter-control environment was found. Create it before starting DayuWriter.'
}

try {
    $python = Resolve-DayuWriterPython
    Start-Process -FilePath $python -ArgumentList @('-m', 'communication.dayuwriter.simple_launcher') -WorkingDirectory $projectRoot -WindowStyle Hidden
}
catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'DayuWriter startup failed') | Out-Null
    exit 1
}

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Write-Error @'
This legacy automatic-follow script has been retired because it captured the
first red-square coordinate as P0. Use scripts\start_dayuwriter_gui.cmd instead.
The corrected desktop GUI keeps the physical P0 fixed at X=0, Y=0.
'@
exit 1

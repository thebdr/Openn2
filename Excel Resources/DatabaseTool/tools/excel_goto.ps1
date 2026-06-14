<#
  excel_goto.ps1 - open an Excel workbook and jump to a specific cell.

  Used by gui.py so a log line like "CAUSE&EFFECT MATRIX!F7" is clickable and
  lands the user on that exact cell. Reuses an already-running Excel instance
  (Marshal::GetActiveObject, available in Windows PowerShell 5.1) so repeated
  clicks don't spawn new Excel processes; only starts one if none is running.
  Run via:  powershell.exe -NoProfile -ExecutionPolicy Bypass -File excel_goto.ps1
            -Path <xlsx> -Sheet "<sheet>" -Cell <A1>
#>
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Sheet,
    [Parameter(Mandatory = $true)][string]$Cell
)
$ErrorActionPreference = 'Stop'

$full = (Resolve-Path -LiteralPath $Path).Path

function Get-Excel {
    # reuse the running instance if there is one, else start a fresh Excel
    try { return [Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application') }
    catch { return New-Object -ComObject Excel.Application }
}

$xl = Get-Excel
$xl.Visible = $true

# find the workbook if it is already open (case-insensitive full-path match)
$wb = $null
foreach ($b in $xl.Workbooks) {
    if ($b.FullName -ieq $full) { $wb = $b; break }
}
if (-not $wb) { $wb = $xl.Workbooks.Open($full) }

$ws = $wb.Worksheets.Item($Sheet)
$ws.Activate()
$xl.Goto($ws.Range($Cell), $true)   # $true = scroll so the cell is top-left

# bring the window forward (xlNormal = -4143)
try { if ($xl.WindowState -eq -4140) { $xl.WindowState = -4143 } } catch {}
try { $xl.ActiveWindow.Activate() } catch {}

# release our reference; the user keeps the visible Excel window
$xl = $null
[System.GC]::Collect()

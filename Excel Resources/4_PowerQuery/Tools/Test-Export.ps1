# Test-Export.ps1 - proves the export path end-to-end against a CLEAN input
# (zero Error findings): refresh, ExportAllSilent, then verify the files were
# written with the expected format-2 shape. Run Setup-SafetyDB.ps1 -TestParams
# and New-TestInputs.py <TestInput> clean first (Run-AllTests.ps1 does both).
param([string]$Root = (Split-Path $PSScriptRoot -Parent))
$ErrorActionPreference = 'Stop'
$out = Join-Path $Root 'Output\TEST01'
$failures = 0
function Check([string]$n, [bool]$ok) { Write-Output ("{0}  {1}" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $n); if (-not $ok) { $script:failures++ } }

if (Test-Path $out) { Remove-Item $out -Recurse -Force }

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false; $excel.DisplayAlerts = $false; $excel.AutomationSecurity = 1
try {
    $wb = $excel.Workbooks.Open((Join-Path $Root 'SafetyDB.xlsm'))
    $excel.Run('PrepareAllInputsSilent')
    foreach ($q in @('Issues','OutStations','OutModules','OutIoTags','OutDiagnosis','OutBlockInstances','OutCustomDb','OutInterface')) {
        [void]$wb.Worksheets.Item($q).ListObjects.Item(1).QueryTable.Refresh($false)
    }
    $gate = $excel.Run('ExportGateErrors')
    Check "clean input has 0 Error findings (gate=$gate)" ($gate -eq 0)

    $excel.Run('ExportAllSilent')
    Check 'Stations.csv written'  (Test-Path (Join-Path $out 'Stations.csv'))
    Check 'Modules.csv written'   (Test-Path (Join-Path $out 'Modules.csv'))
    Check 'IoTags.csv written'    (Test-Path (Join-Path $out 'IoTags.csv'))
    Check 'Diagnosis.csv written' (Test-Path (Join-Path $out 'Diagnosis.csv'))

    $stations = Get-Content (Join-Path $out 'Stations.csv')
    Check 'Stations.csv has #!format=2 header' ($stations[0] -eq '#!format=2')
    Check 'Stations.csv is semicolon-delimited' ($stations[1] -like '*;*')
    $dataLines = $stations | Where-Object { $_ -and -not $_.StartsWith('#') }
    # clean input: CPU (Plc) + one IM155 (IoDevice) = 2 stations
    Check 'Stations.csv has 2 data rows' ($dataLines.Count -eq 2)
    Check 'Stations.csv first data row is the Plc' ($dataLines[0] -like 'Plc;*')

    # block source text files (TextPerRow)
    Check 'DB block text written' (Test-Path (Join-Path $out 'Blocks\DB_E.db'))
    if (Test-Path (Join-Path $out 'Blocks\DB_E.db')) {
        $db = Get-Content (Join-Path $out 'Blocks\DB_E.db') -Raw
        Check 'DB block has DATA_BLOCK header' ($db -like '*DATA_BLOCK*')
    }
    Write-Output '--- exported files ---'
    Get-ChildItem $out -Recurse -File | ForEach-Object { Write-Output ("  {0} ({1} bytes)" -f $_.FullName.Substring($out.Length+1), $_.Length) }
}
finally { if ($wb) { $wb.Close($false) }; $excel.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel) }
Write-Output $(if ($failures -eq 0) { 'ALL CHECKS PASS' } else { "$failures CHECK(S) FAILED" })
exit $(if ($failures -eq 0) { 0 } else { 1 })

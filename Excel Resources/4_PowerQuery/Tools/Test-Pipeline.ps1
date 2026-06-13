# Test-Pipeline.ps1 - end-to-end smoke test of SafetyDB.xlsm against the
# synthetic inputs: stages the documents (strikethrough pre-pass), refreshes
# all queries, dumps the ISSUES report and checks the expected findings and
# the export gate.
param([string]$Root = (Split-Path $PSScriptRoot -Parent))
$ErrorActionPreference = 'Stop'
$WorkbookPath = Join-Path $Root 'SafetyDB.xlsm'

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$excel.AutomationSecurity = 1 # allow the workbook's own macros
$failures = 0
function Check([string]$name, [bool]$ok) {
    Write-Output ("{0}  {1}" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $name)
    if (-not $ok) { $script:failures++ }
}

try {
    $wb = $excel.Workbooks.Open($WorkbookPath)

    Write-Output '--- staging inputs (strikethrough pre-pass) ---'
    $excel.Run('PrepareAllInputsSilent')
    Check 'staged files written' ((Test-Path (Join-Path $Root 'Input\_staged\IoList_staged.xlsx')) -and (Test-Path (Join-Path $Root 'Input\_staged\CE_staged.xlsx')))

    Write-Output '--- refreshing queries ---'
    foreach ($q in @('Issues','OutStations','OutModules','OutIoTags','OutDiagnosis','OutBlockInstances','OutCustomDb','OutInterface')) {
        $lo = $wb.Worksheets.Item($q).ListObjects.Item(1)
        try {
            [void]$lo.QueryTable.Refresh($false)
            Write-Output "refreshed: $q"
        } catch {
            Write-Output ("REFRESH FAILED: {0} -> {1}" -f $q, $_.Exception.Message)
            $script:failures++
        }
    }

    Write-Output '--- ISSUES report ---'
    $issues = $wb.Worksheets.Item('Issues').ListObjects.Item(1)
    $ruleCounts = @{}
    $errorCount = 0
    if ($issues.DataBodyRange) {
        $data = $issues.DataBodyRange.Value2
        for ($r = 1; $r -le $data.GetLength(0); $r++) {
            $severity = [string]$data[$r, 1]; $rule = [string]$data[$r, 2]
            $doc = [string]$data[$r, 4]; $msg = [string]$data[$r, 7]
            Write-Output ("{0,-8} {1,-5} {2,-7} {3}" -f $severity, $rule, $doc, $msg)
            $ruleCounts[$rule] = 1 + $(if ($ruleCounts.ContainsKey($rule)) { $ruleCounts[$rule] } else { 0 })
            if ($severity -eq 'Error') { $errorCount++ }
        }
    }

    Write-Output '--- expectations ---'
    foreach ($expected in @('V101','V102','V103','V104','V105','V108','V201','V203','V301','V302','V303')) {
        Check "finds $expected" ($ruleCounts.ContainsKey($expected))
    }
    Check 'no unexpected rules fired' (($ruleCounts.Keys | Where-Object { $_ -notin @('V101','V102','V103','V104','V105','V108','V201','V203','V301','V302','V303') }).Count -eq 0)
    Check "error count = 8 (found $errorCount)" ($errorCount -eq 8)

    $gate = $excel.Run('ExportGateErrors')
    Check "export gate blocks ($gate errors)" ($gate -gt 0)

    Write-Output '--- output row counts ---'
    foreach ($q in @('OutStations','OutModules','OutIoTags','OutDiagnosis','OutBlockInstances','OutCustomDb','OutInterface')) {
        $lo = $wb.Worksheets.Item($q).ListObjects.Item(1)
        $n = if ($lo.DataBodyRange) { $lo.DataBodyRange.Rows.Count } else { 0 }
        Write-Output ("{0,-18} {1} row(s)" -f $q, $n)
    }
    $st = $wb.Worksheets.Item('OutStations').ListObjects.Item(1)
    Check 'OutStations has 3 stations' ($st.DataBodyRange -and $st.DataBodyRange.Rows.Count -eq 3)

    # verify the format-2 csv shape that Openn2 will load
    $stHdr = $st.HeaderRowRange.Value2
    Check 'OutStations columns match format 2' ([string]$stHdr.GetValue(1,1) -eq 'Role' -and [string]$stHdr.GetValue(1,8) -eq 'Group')
    # E (S31001, 2 ch -> 1 device) + DI (S40001, 2 ch -> 1) + KQ (K50001, 1) = 3 templated devices
    $bi = $wb.Worksheets.Item('OutBlockInstances').ListObjects.Item(1)
    Check 'block instances: 3 (paired channels collapsed)' ($bi.DataBodyRange -and $bi.DataBodyRange.Rows.Count -eq 3)

    Write-Output $(if ($failures -eq 0) { 'ALL CHECKS PASS' } else { "$failures CHECK(S) FAILED" })
}
finally {
    # Close without saving - refresh results are disposable, and Save()/Close($true)
    # via COM can hang on this machine (the same quirk that makes SaveAs a no-op).
    if ($wb) { $wb.Close($false) }
    $excel.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
}
exit $(if ($failures -eq 0) { 0 } else { 1 })

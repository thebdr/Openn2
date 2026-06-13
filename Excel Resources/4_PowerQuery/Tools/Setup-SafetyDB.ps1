# Setup-SafetyDB.ps1 - builds SafetyDB.xlsm from the .pq/.bas text files via
# Excel COM: config tables (prefilled), all queries, result sheets, VBA modules.
# -TestParams fills PARAMS/paths for the synthetic test inputs (Tools\New-TestInputs.py).
param(
    [string]$Root = (Split-Path $PSScriptRoot -Parent),
    [switch]$TestParams
)
$ErrorActionPreference = 'Stop'
$WorkbookPath = Join-Path $Root 'SafetyDB.xlsm'
$missing = [System.Reflection.Missing]::Value

# VBA project access must be trusted for the module import (HKCU, reversible)
foreach ($ver in @('16.0')) {
    $key = "HKCU:\Software\Microsoft\Office\$ver\Excel\Security"
    if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
    Set-ItemProperty -Path $key -Name 'AccessVBOM' -Value 1 -Type DWord
}

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {
    # NOTE: on this machine Excel silently ignores SaveAs/Save via COM (policy or
    # build issue) - only SaveCopyAs writes files. SaveCopyAs keeps the format of
    # the open workbook, so we build inside an opened empty .xlsm seed and copy out.
    $seedPath = Join-Path $Root 'Templates\Seed.xlsm'
    $wb = $excel.Workbooks.Open($seedPath)
    while ($wb.Worksheets.Count -gt 1) { $wb.Worksheets.Item(2).Delete() }

    function Add-Table($ws, [int]$row, [int]$col, [string]$name, [string[]]$headers, $rows) {
        for ($c = 0; $c -lt $headers.Count; $c++) { $ws.Cells.Item($row, $col + $c).Value2 = $headers[$c] }
        $r = $row + 1
        foreach ($dataRow in $rows) {
            for ($c = 0; $c -lt $dataRow.Count; $c++) { $ws.Cells.Item($r, $col + $c).Value2 = [string]$dataRow[$c] }
            $r++
        }
        $lastRow = [Math]::Max($r - 1, $row + 1) # at least one (possibly empty) data row
        $range = $ws.Range($ws.Cells.Item($row, $col), $ws.Cells.Item($lastRow, $col + $headers.Count - 1))
        $lo = $ws.ListObjects.Add(1, $range, $missing, 1) # xlSrcRange, xlYes
        $lo.DisplayName = $name
        $lo.TableStyle = 'TableStyleLight8'
    }

    # ---------- PARAMS sheet (PARAMS + EXPORTS) ----------
    $wsParams = $wb.Worksheets.Item(1)
    $wsParams.Name = 'PARAMS'
    $testInput = Join-Path $Root 'TestInput'
    $staged = Join-Path $Root 'Input\_staged'
    New-Item -ItemType Directory -Force $staged | Out-Null
    $repoHwConfig = Join-Path (Split-Path (Split-Path $Root -Parent) -Parent) 'HardwareConfig\DeviceTypesDatabase.csv'

    $paramRows = @(
        @('ProjectCode',        $(if ($TestParams) { 'TEST01' } else { '' }),                              'project identifier'),
        @('MachineType',        $(if ($TestParams) { 'SORTER' } else { '' }),                              'row of MACHINE_TYPES'),
        @('AreaList',           $(if ($TestParams) { 'S1;S2' } else { '' }),                               '; separated'),
        @('SafetyNets',         '192.168.50;192.168.51',                                                   '; separated IP prefixes'),
        @('StrikeHandling',     'Exclude',                                                                 'Exclude or Flag'),
        @('IoListSourcePath',   $(if ($TestParams) { Join-Path $testInput 'IoList_test.xlsx' } else { '' }), 'customer I/O List'),
        @('IoListSheetName',    'IO List', ''),
        @('IoListHeaderRow',    '2', ''),
        @('IoListStagedPath',   (Join-Path $staged 'IoList_staged.xlsx'), 'written by PrepareInputs'),
        @('CESourcePath',       $(if ($TestParams) { Join-Path $testInput 'CE_test.xlsx' } else { '' }),   'customer C&E matrix'),
        @('CESheetName',        'C&E', ''),
        @('CEHeaderRow',        '2', ''),
        @('CEStagedPath',       (Join-Path $staged 'CE_staged.xlsx'), 'written by PrepareInputs'),
        @('DeviceTypesCsvPath', $repoHwConfig, 'Openn2 model database'),
        @('OutputFolder',       (Join-Path $Root 'Output\TEST01'), 'export target')
    )
    Add-Table $wsParams 1 1 'PARAMS' @('Name', 'Value', 'Note') $paramRows

    $exportRows = @(
        @('OutStations', 'Stations.csv', 'Format2Csv'),
        @('OutModules', 'Modules.csv', 'Format2Csv'),
        @('OutIoTags', 'IoTags.csv', 'Csv'),
        @('OutDiagnosis', 'Diagnosis.csv', 'Csv'),
        @('OutBlockInstances', 'BlockInstances.csv', 'Csv'),
        @('OutCustomDb', '', 'TextPerRow'),
        @('OutInterface', '', 'TextPerRow')
    )
    Add-Table $wsParams 1 6 'EXPORTS' @('Source', 'FileName', 'Format') $exportRows

    # ---------- CONFIG sheet (SIGNAL_TYPES + VALIDATION_RULES + MACHINE_TYPES + INTERFACE_DATA) ----------
    $wsConfig = $wb.Worksheets.Add($missing, $wsParams)
    $wsConfig.Name = 'CONFIG'
    $typeRows = @(
        @('A',     'Alarm',                            'Diag',   '',    '',  '',                   'TRUE',  'FALSE'),
        @('W',     'Warning',                          'Diag',   '',    '',  '',                   'TRUE',  'FALSE'),
        @('PA',    'Fieldbus Alarm',                   'Diag',   '',    '',  '',                   'TRUE',  'FALSE'),
        @('PW',    'Fieldbus Warning',                 'Diag',   '',    '',  '',                   'TRUE',  'FALSE'),
        @('E1/2',  'Emergency Push Button',            'Safety', 'E',   '1', '02_EM Push Button',  'FALSE', 'FALSE'),
        @('E2/2',  'Emergency Push Button',            'Safety', 'E',   '2', '02_EM Push Button',  'FALSE', 'FALSE'),
        @('B1/2',  'Safety Breaker',                   'Safety', 'B',   '1', '04_ESTOP',           'FALSE', 'FALSE'),
        @('B2/2',  'Safety Breaker',                   'Safety', 'B',   '2', '04_ESTOP',           'FALSE', 'FALSE'),
        @('ENC1/2','Safety Encoder',                   'Safety', 'ENC', '1', '07_Speed Control',   'FALSE', 'FALSE'),
        @('ENC2/2','Safety Encoder',                   'Safety', 'ENC', '2', '07_Speed Control',   'FALSE', 'FALSE'),
        @('DI1/2', 'Door Closed Safety Input',         'Safety', 'DI',  '1', '08_Gate Manager',    'FALSE', 'FALSE'),
        @('DI2/2', 'Door Closed Safety Input',         'Safety', 'DI',  '2', '08_Gate Manager',    'FALSE', 'FALSE'),
        @('DD',    'Door Closed Diag Input',           'Diag',   '',    '',  '08_Gate Manager',    'TRUE',  'FALSE'),
        @('DR',    'Door Reset Input',                 'Std',    '',    '',  '08_Gate Manager',    'FALSE', 'FALSE'),
        @('DL',    'Door Lamp Output',                 'Std',    '',    '',  '08_Gate Manager',    'FALSE', 'FALSE'),
        @('DQ',    'Door Unlock Output',               'Std',    '',    '',  '08_Gate Manager',    'FALSE', 'FALSE'),
        @('KI',    'Contactor Feedback Input',         'Safety', '',    '',  '06_Feedback Error',  'FALSE', 'FALSE'),
        @('KQ',    'Contactor Output',                 'Safety', '',    '',  '05_Output Feedback', 'FALSE', 'FALSE'),
        @('RES',   'Emergency Reset',                  'Safety', '',    '',  '',                   'FALSE', 'FALSE'),
        @('FA#',   'Emergency Status Feedback Area #', 'Safety', '',    '',  '',                   'FALSE', 'TRUE')
    )
    Add-Table $wsConfig 1 1 'SIGNAL_TYPES' @('TypeId','Description','Category','PairKey','Channel','BlockTemplate','InDiagnosis','IsPattern') $typeRows

    $ruleRows = @(
        @('V101','Unknown device type','Error','TRUE'),
        @('V102','Duplicate identity in I/O List','Error','TRUE'),
        @('V103','Node/bit collision','Error','TRUE'),
        @('V104','Device tag naming pattern','Warning','TRUE'),
        @('V105','Profinet IP outside safety nets','Error','TRUE'),
        @('V106','Diagnosis data without type','Warning','TRUE'),
        @('V107','Struck row still typed','Warning','TRUE'),
        @('V108','Diagnosis Bit outside 0..63','Error','TRUE'),
        @('V201','Malformed C&E address','Error','TRUE'),
        @('V202','Invalid validation status','Error','TRUE'),
        @('V203','BYPASS without note','Error','TRUE'),
        @('V204','Duplicate address in matrix','Error','TRUE'),
        @('V301','C&E device missing in I/O List','Error','TRUE'),
        @('V302','Safety device missing in matrix','Warning','TRUE'),
        @('V303','Unknown area','Warning','TRUE'),
        @('V906','Stale correction','Warning','TRUE')
    )
    Add-Table $wsConfig 1 11 'VALIDATION_RULES' @('RuleId','Description','Severity','Enabled') $ruleRows

    Add-Table $wsConfig 1 17 'MACHINE_TYPES' @('MachineType','InterfaceTemplate') @(
        ,@('SORTER', (Join-Path $Root 'Templates\Interface_Sorter.txt')))
    Add-Table $wsConfig 1 21 'INTERFACE_DATA' @('Token','Value') @(
        @('LineSpeed','2.5'), @('PlcName','plc1'), @('HmiStation','hmi1'))

    # ---------- COLUMN_MAP sheet ----------
    $wsMap = $wb.Worksheets.Add($missing, $wsConfig)
    $wsMap.Name = 'COLUMN_MAP'
    $mapRows = @(
        @('IoList','Description Module','DescriptionModule','TRUE'),
        @('IoList','Manufacturer','Manufacturer','FALSE'),
        @('IoList','Part No.','PartNo','TRUE'),
        @('IoList','Cod. Fives','CodFives','FALSE'),
        @('IoList','Slot','Slot','FALSE'),
        @('IoList','ID','IdNode','TRUE'),
        @('IoList','Bit','Bit','TRUE'),
        @('IoList','Normal condition','NormalCondition','FALSE'),
        @('IoList','Connector','Connector','FALSE'),
        @('IoList','Pin No.','PinNo','FALSE'),
        @('IoList','Description language 1','DescriptionL1','FALSE'),
        @('IoList','Description language 2','DescriptionL2','FALSE'),
        @('IoList','Functional unit','FunctionalUnit','TRUE'),
        @('IoList','Location','Location','TRUE'),
        @('IoList','Device','Device','TRUE'),
        @('IoList','Drawing name','DrawingName','FALSE'),
        @('IoList','Sheet','Sheet','FALSE'),
        @('IoList','T.S. ref.','TsRef','FALSE'),
        @('IoList','Profinet IP','ProfinetIp','FALSE'),
        @('IoList','Profinet name','ProfinetName','FALSE'),
        @('IoList','Mnemonic','Mnemonic','FALSE'),
        @('IoList','Alarm filter','AlarmFilter','FALSE'),
        @('IoList','Tag filter','TagFilter','FALSE'),
        @('IoList','Type','Type','TRUE'),
        @('IoList','Diagnosis Cabinet','DiagCabinet','FALSE'),
        @('IoList','Diagnosis Bit','DiagBit','FALSE'),
        @('CE','PLC-F','PlcF','FALSE'),
        @('CE','VALIDATED','Validated','TRUE'),
        @('CE','POSITION','Position','FALSE'),
        @('CE','NOTE','Note','FALSE'),
        @('CE','MODULE','ModuleAddress','FALSE'),
        @('CE','BIT (ADDRESS)','BitAddress','TRUE'),
        @('CE','SLOT','SlotDevice','FALSE'),
        @('CE','PIN No.','PinNo','FALSE'),
        @('CE','DESCRIPTION','Description','FALSE'),
        @('CE','FUNCTIONAL UNIT','FunctionalUnit','FALSE'),
        @('CE','LOCATION','Location','FALSE'),
        @('CE','DEVICE','Device','TRUE'),
        @('CE','AREA','Area','FALSE')
    )
    Add-Table $wsMap 1 1 'COLUMN_MAP' @('Document','SourceHeader','CanonicalName','Required') $mapRows

    # ---------- CORRECTIONS sheet ----------
    $wsCorr = $wb.Worksheets.Add($missing, $wsMap)
    $wsCorr.Name = 'CORRECTIONS'
    Add-Table $wsCorr 1 1 'CORRECTIONS' @('Document','RowKey','Column','NewValue','Reason','Author','Date','Status') @(
        ,@('IoList','(example)','Device','', 'example row - keep Status Resolved','', '', 'Resolved'))

    # ---------- queries ----------
    Get-ChildItem (Join-Path $Root 'Queries') -Filter '*.pq' -Recurse | Sort-Object DirectoryName, Name | ForEach-Object {
        $name = [IO.Path]::GetFileNameWithoutExtension($_.Name)
        $formula = Get-Content $_.FullName -Raw -Encoding UTF8
        $wb.Queries.Add($name, $formula) | Out-Null
    }

    # ---------- result sheets for the loaded queries ----------
    foreach ($q in @('Issues','OutStations','OutModules','OutIoTags','OutDiagnosis','OutBlockInstances','OutCustomDb','OutInterface')) {
        $ws = $wb.Worksheets.Add($missing, $wb.Worksheets.Item($wb.Worksheets.Count))
        $ws.Name = $q
        $conn = 'OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;Location=' + $q
        $lo = $ws.ListObjects.Add(0, $conn, $missing, 1, $ws.Range('A1')) # xlSrcExternal, xlYes
        $lo.DisplayName = $q
        $qt = $lo.QueryTable
        $qt.CommandType = 2 # xlCmdSql
        $qt.CommandText = "SELECT * FROM [$q]"
        $qt.BackgroundQuery = $false
        $qt.RefreshStyle = 1 # xlOverwriteCells avoids row-shift surprises
    }

    # ---------- VBA modules ----------
    foreach ($module in @('PrepareInputs.bas', 'ExportOutputs.bas')) {
        $wb.VBProject.VBComponents.Import((Join-Path $Root "VBA\$module")) | Out-Null
    }

    if (Test-Path $WorkbookPath) { Remove-Item $WorkbookPath -Force }
    $wb.SaveCopyAs($WorkbookPath) # seed is xlsm, so the copy is a valid xlsm
    Write-Output "workbook created: $WorkbookPath"
    Write-Output "exists on disk:   $(Test-Path $WorkbookPath)"
}
finally {
    if ($wb) { $wb.Close($false) }
    $excel.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
}

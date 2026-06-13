Attribute VB_Name = "PrepareInputs"
'------------------------------------------------------------------------------
' PrepareInputs - snapshots the customer documents into staged copies that
' Power Query can fully understand.
'
' WHY: strikethrough text in the customer files means "predisposition / not
' used", but Power Query cannot see FORMATTING - only values. This pre-pass
' copies the used range AS VALUES and adds an "IsStruck" column (TRUE when the
' row's Device or Type cell carries strikethrough, fully or partially), so the
' queries can handle struck rows explicitly (StrikeHandling parameter).
'
' Reads from the PARAMS sheet:
'   IoListSourcePath, IoListSheetName, IoListStagedPath
'   CESourcePath,     CESheetName,     CEStagedPath
'   IoListHeaderRow / CEHeaderRow (the IsStruck header lands on that row)
' Run: PrepareAllInputs (button on the HOME sheet)
'------------------------------------------------------------------------------
Option Explicit

Public Sub PrepareAllInputs()
    PrepareAllInputsSilent
    MsgBox "Inputs staged. Now refresh the queries (Data > Refresh All).", vbInformation
End Sub

'no message box - callable from automation/tests
Public Sub PrepareAllInputsSilent()
    StageOne Param("IoListSourcePath"), Param("IoListSheetName"), _
             Param("IoListStagedPath"), CLng(Param("IoListHeaderRow"))
    StageOne Param("CESourcePath"), Param("CESheetName"), _
             Param("CEStagedPath"), CLng(Param("CEHeaderRow"))
    SetPathParameters
End Sub

'Writes the native Power Query path/sheet parameters from the PARAMS table.
'The queries read external files only through these parameters (the firewall
'treats them as constants), so the values must be pushed in before any refresh.
Public Sub SetPathParameters()
    SetParam "pIoListStaged", Param("IoListStagedPath")
    SetParam "pIoListSheet", Param("IoListSheetName")
    SetParam "pCEStaged", Param("CEStagedPath")
    SetParam "pCESheet", Param("CESheetName")
    SetParam "pDeviceTypesCsv", Param("DeviceTypesCsvPath")
    SetParam "pInterfaceTemplate", ResolveInterfaceTemplate(Param("MachineType"))
End Sub

'Rewrites one native parameter query's formula to a text constant.
'M text literals do not escape backslashes, only doubled quotes - so a Windows
'path goes in verbatim between quotes.
Private Sub SetParam(ByVal queryName As String, ByVal value As String)
    Dim formula As String
    formula = """" & Replace(value, """", """""") & """ meta [IsParameterQuery=true, Type=""Text"", IsParameterQueryRequired=true]"
    ThisWorkbook.Queries(queryName).formula = formula
End Sub

'Looks up the interface template path for the machine type in MACHINE_TYPES.
Private Function ResolveInterfaceTemplate(ByVal machineType As String) As String
    Dim t As ListObject, r As ListRow
    Set t = ThisWorkbook.Worksheets("CONFIG").ListObjects("MACHINE_TYPES")
    For Each r In t.ListRows
        If StrComp(Trim$(CStr(r.Range.Cells(1, 1).Value & "")), machineType, vbTextCompare) = 0 Then
            ResolveInterfaceTemplate = CStr(r.Range.Cells(1, 2).Value & "")
            Exit Function
        End If
    Next r
    ResolveInterfaceTemplate = "" 'unknown machine type - OutInterface will error visibly
End Function

Private Sub Trace(ByVal message As String)
    Dim f As Integer
    f = FreeFile
    Open ThisWorkbook.Path & "\stage.log" For Append As #f
    Print #f, Format$(Now, "hh:nn:ss") & "  " & message
    Close #f
End Sub

Private Sub StageOne(ByVal sourcePath As String, ByVal sheetName As String, _
                     ByVal stagedPath As String, ByVal headerRow As Long)
    Dim src As Workbook, dst As Workbook
    Dim ws As Worksheet, out As Worksheet
    Dim used As Range
    Dim r As Long, lastCol As Long
    Dim struckCol As Long

    Trace "StageOne start: " & sourcePath
    Application.ScreenUpdating = False
    Set src = Workbooks.Open(sourcePath, ReadOnly:=True, UpdateLinks:=0)
    Trace "  source opened"
    Set ws = src.Worksheets(sheetName)
    Set used = ws.UsedRange

    Set dst = Workbooks.Add(xlWBATWorksheet)
    Set out = dst.Worksheets(1)
    out.Name = sheetName

    'values only - formulas, links and formatting stay behind
    out.Range("A1").Resize(used.Rows.Count, used.Columns.Count).Value = used.Value
    Trace "  values copied (" & used.Rows.Count & " x " & used.Columns.Count & ")"

    'IsStruck column at the end; header on the configured header row
    On Error GoTo StrikeError
    lastCol = used.Columns.Count
    struckCol = lastCol + 1
    Trace "  struck col = " & struckCol & ", rows " & (headerRow + 1) & ".." & used.Rows.Count
    out.Cells(headerRow, struckCol).Value = "IsStruck"
    For r = headerRow + 1 To used.Rows.Count
        out.Cells(r, struckCol).Value = RowIsStruck(ws, used, r)
    Next r
    On Error GoTo 0
    Trace "  strike column written"
    GoTo StrikeDone
StrikeError:
    Trace "  STRIKE ERROR at row " & r & ": #" & Err.Number & " " & Err.Description
    Err.Raise Err.Number, , Err.Description
StrikeDone:

    'SaveCopyAs instead of SaveAs: on some machines/policies Excel silently
    'ignores SaveAs from automation; SaveCopyAs always writes. The copy gets the
    'workbook's default format, so force xlsx while it is written.
    Dim previousFormat As Long
    previousFormat = Application.DefaultSaveFormat
    Application.DefaultSaveFormat = xlOpenXMLWorkbook 'xlsx, no macros
    Application.DisplayAlerts = False
    If Len(Dir$(stagedPath)) > 0 Then Kill stagedPath
    dst.SaveCopyAs stagedPath
    Application.DisplayAlerts = True
    Application.DefaultSaveFormat = previousFormat
    Trace "  staged copy saved: " & stagedPath
    dst.Close SaveChanges:=False
    src.Close SaveChanges:=False
    Application.ScreenUpdating = True
    Trace "StageOne done"
End Sub

'A row counts as struck when any inspected cell has full or PARTIAL
'strikethrough (partial returns Null from Font.Strikethrough).
'Error cells (#NAME? etc.) are inspected too - IsError guards the read.
Private Function RowIsStruck(ByVal ws As Worksheet, ByVal used As Range, ByVal rowIndex As Long) As Boolean
    Dim c As Long, v As Variant, cellValue As Variant, hasContent As Boolean
    For c = 1 To used.Columns.Count
        cellValue = used.Cells(rowIndex, c).Value2
        'VBA Or does not short-circuit: the error check must stand alone
        If IsError(cellValue) Then
            hasContent = True
        Else
            hasContent = Len(CStr(cellValue & "")) > 0
        End If
        If hasContent Then
            v = used.Cells(rowIndex, c).Font.Strikethrough
            If IsNull(v) Then
                RowIsStruck = True 'partially struck cell
                Exit Function
            ElseIf v = True Then
                RowIsStruck = True
                Exit Function
            End If
        End If
    Next c
    RowIsStruck = False
End Function

Private Function Param(ByVal name As String) As String
    Dim t As ListObject, r As ListRow
    Set t = ThisWorkbook.Worksheets("PARAMS").ListObjects("PARAMS")
    For Each r In t.ListRows
        If Trim$(CStr(r.Range.Cells(1, 1).Value & "")) = name Then
            Param = CStr(r.Range.Cells(1, 2).Value & "")
            Exit Function
        End If
    Next r
    Err.Raise vbObjectError + 513, , "Parameter not found in PARAMS: " & name
End Function

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
    StageOne Param("IoListSourcePath"), Param("IoListSheetName"), _
             Param("IoListStagedPath"), CLng(Param("IoListHeaderRow"))
    StageOne Param("CESourcePath"), Param("CESheetName"), _
             Param("CEStagedPath"), CLng(Param("CEHeaderRow"))
    MsgBox "Inputs staged. Now refresh the queries (Data > Refresh All).", vbInformation
End Sub

Private Sub StageOne(ByVal sourcePath As String, ByVal sheetName As String, _
                     ByVal stagedPath As String, ByVal headerRow As Long)
    Dim src As Workbook, dst As Workbook
    Dim ws As Worksheet, out As Worksheet
    Dim used As Range
    Dim r As Long, lastCol As Long
    Dim struckCol As Long

    Application.ScreenUpdating = False
    Set src = Workbooks.Open(sourcePath, ReadOnly:=True, UpdateLinks:=0)
    Set ws = src.Worksheets(sheetName)
    Set used = ws.UsedRange

    Set dst = Workbooks.Add(xlWBATWorksheet)
    Set out = dst.Worksheets(1)
    out.Name = sheetName

    'values only - formulas, links and formatting stay behind
    out.Range("A1").Resize(used.Rows.Count, used.Columns.Count).Value = used.Value

    'IsStruck column at the end; header on the configured header row
    lastCol = used.Columns.Count
    struckCol = lastCol + 1
    out.Cells(headerRow, struckCol).Value = "IsStruck"
    For r = headerRow + 1 To used.Rows.Count
        out.Cells(r, struckCol).Value = RowIsStruck(ws, used, r)
    Next r

    Application.DisplayAlerts = False
    dst.SaveAs stagedPath, FileFormat:=xlOpenXMLWorkbook 'xlsx, no macros
    Application.DisplayAlerts = True
    dst.Close SaveChanges:=False
    src.Close SaveChanges:=False
    Application.ScreenUpdating = True
End Sub

'A row counts as struck when any inspected cell has full or PARTIAL
'strikethrough (partial returns Null from Font.Strikethrough).
Private Function RowIsStruck(ByVal ws As Worksheet, ByVal used As Range, ByVal rowIndex As Long) As Boolean
    Dim c As Long, v As Variant
    For c = 1 To used.Columns.Count
        If Len(CStr(used.Cells(rowIndex, c).Value2 & "")) > 0 Then
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

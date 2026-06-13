Attribute VB_Name = "ExportOutputs"
'------------------------------------------------------------------------------
' ExportOutputs - writes the OUT_* query result tables to files. This is the
' only thing Power Query cannot do itself (M does not write files), so it is
' the one piece of VBA in the pipeline besides PrepareInputs.
'
' GATE: export refuses to run while the ISSUES table contains any finding with
' Severity = "Error" - send the report to the document owner or add a row to
' CORRECTIONS first.
'
' Driven by the EXPORTS table (sheet PARAMS): Source | FileName | Format
'   Source   = name of the loaded query table (e.g. OutStations)
'   FileName = file name inside the OutputFolder parameter (e.g. Stations.csv)
'   Format   = Format2Csv  -> ;-separated csv with the #!format=2 header (UTF-8 BOM)
'              Csv         -> plain ;-separated csv with a # header row
'              TextPerRow  -> one file per row: columns FileName/DbName + Content
'------------------------------------------------------------------------------
Option Explicit

Public Sub ExportAll()
    Dim errorCount As Long
    errorCount = CountIssueErrors()
    If errorCount > 0 Then
        MsgBox "Export blocked: the ISSUES table contains " & errorCount & _
               " finding(s) with Severity = Error." & vbCrLf & _
               "Fix the documents (or add CORRECTIONS rows) and refresh first.", vbExclamation
        Exit Sub
    End If
    ExportAllSilent
    MsgBox "Export complete -> " & Param("OutputFolder"), vbInformation
End Sub

'no message boxes - callable from automation/tests; raises when gated
Public Sub ExportAllSilent()
    Dim errorCount As Long
    errorCount = CountIssueErrors()
    If errorCount > 0 Then
        Err.Raise vbObjectError + 517, , "Export blocked: " & errorCount & " Error finding(s) in ISSUES"
    End If

    Dim exports As ListObject, r As ListRow
    Set exports = ThisWorkbook.Worksheets("PARAMS").ListObjects("EXPORTS")
    For Each r In exports.ListRows
        ExportOne CStr(r.Range.Cells(1, 1).Value), CStr(r.Range.Cells(1, 2).Value), CStr(r.Range.Cells(1, 3).Value)
    Next r
End Sub

'for automation: how many Error findings currently gate the export
Public Function ExportGateErrors() As Long
    ExportGateErrors = CountIssueErrors()
End Function

Private Sub ExportOne(ByVal sourceTable As String, ByVal fileName As String, ByVal fileFormat As String)
    Dim t As ListObject
    Set t = FindTable(sourceTable)
    If t Is Nothing Then Err.Raise vbObjectError + 514, , "Query table not found (load the query to a sheet first): " & sourceTable

    Select Case LCase$(fileFormat)
        Case "format2csv": WriteCsv t, fileName, True
        Case "csv":        WriteCsv t, fileName, False
        Case "textperrow": WriteTextPerRow t
        Case Else: Err.Raise vbObjectError + 515, , "Unknown export format: " & fileFormat
    End Select
End Sub

Private Sub WriteCsv(ByVal t As ListObject, ByVal fileName As String, ByVal format2 As Boolean)
    Dim lines As Collection: Set lines = New Collection
    Dim header As String, line As String
    Dim r As Long, c As Long

    If format2 Then lines.Add "#!format=2"
    header = "# "
    For c = 1 To t.ListColumns.Count
        header = header & t.ListColumns(c).Name & IIf(c < t.ListColumns.Count, ";", "")
    Next c
    lines.Add header

    If Not t.DataBodyRange Is Nothing Then
        For r = 1 To t.DataBodyRange.Rows.Count
            line = ""
            For c = 1 To t.ListColumns.Count
                line = line & EscapeCsv(CStr(t.DataBodyRange.Cells(r, c).Value2 & "")) & _
                       IIf(c < t.ListColumns.Count, ";", "")
            Next c
            lines.Add line
        Next r
    End If

    WriteUtf8File JoinPath(Param("OutputFolder"), fileName), lines
End Sub

'one file per row: needs a name column (FileName or DbName) and a Content column
Private Sub WriteTextPerRow(ByVal t As ListObject)
    Dim nameCol As Long, contentCol As Long, c As Long, r As Long
    For c = 1 To t.ListColumns.Count
        Select Case t.ListColumns(c).Name
            Case "FileName", "DbName": nameCol = c
            Case "Content": contentCol = c
        End Select
    Next c
    If nameCol = 0 Or contentCol = 0 Then Err.Raise vbObjectError + 516, , "TextPerRow needs FileName/DbName + Content columns"

    If t.DataBodyRange Is Nothing Then Exit Sub
    Dim lines As Collection, fileName As String
    For r = 1 To t.DataBodyRange.Rows.Count
        Set lines = New Collection
        lines.Add CStr(t.DataBodyRange.Cells(r, contentCol).Value2 & "")
        fileName = SanitizeFileName(CStr(t.DataBodyRange.Cells(r, nameCol).Value2 & ""))
        If InStr(fileName, ".") = 0 Then fileName = fileName & ".db"
        WriteUtf8File JoinPath(JoinPath(Param("OutputFolder"), "Blocks"), fileName), lines
    Next r
End Sub

'Replaces characters that are illegal in a Windows file name with '_'.
Private Function SanitizeFileName(ByVal name As String) As String
    Dim bad As Variant, ch As Variant
    bad = Array("\", "/", ":", "*", "?", """", "<", ">", "|")
    For Each ch In bad
        name = Replace(name, ch, "_")
    Next ch
    SanitizeFileName = name
End Function

Private Sub WriteUtf8File(ByVal fullPath As String, ByVal lines As Collection)
    EnsureFolder Left$(fullPath, InStrRev(fullPath, "\") - 1)
    Dim stream As Object, item As Variant
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 2 'text
    stream.Charset = "utf-8" 'ADODB writes the BOM
    stream.Open
    For Each item In lines
        stream.WriteText CStr(item) & vbCrLf
    Next item
    stream.SaveToFile fullPath, 2 'overwrite
    stream.Close
End Sub

Private Function CountIssueErrors() As Long
    Dim t As ListObject, r As Long
    Set t = FindTable("Issues")
    If t Is Nothing Or t.DataBodyRange Is Nothing Then Exit Function
    For r = 1 To t.DataBodyRange.Rows.Count
        If UCase$(CStr(t.DataBodyRange.Cells(r, 1).Value2 & "")) = "ERROR" Then
            CountIssueErrors = CountIssueErrors + 1
        End If
    Next r
End Function

Private Function FindTable(ByVal tableName As String) As ListObject
    Dim ws As Worksheet, t As ListObject
    For Each ws In ThisWorkbook.Worksheets
        For Each t In ws.ListObjects
            If StrComp(t.Name, tableName, vbTextCompare) = 0 Or _
               StrComp(t.Name, "Table_" & tableName, vbTextCompare) = 0 Then
                Set FindTable = t
                Exit Function
            End If
        Next t
    Next ws
End Function

Private Function EscapeCsv(ByVal value As String) As String
    If InStr(value, ";") > 0 Or InStr(value, """") > 0 Then
        EscapeCsv = """" & Replace(value, """", """""") & """"
    Else
        EscapeCsv = value
    End If
End Function

Private Function JoinPath(ByVal folder As String, ByVal file As String) As String
    JoinPath = IIf(Right$(folder, 1) = "\", folder, folder & "\") & file
End Function

Private Sub EnsureFolder(ByVal path As String)
    If Len(Dir$(path, vbDirectory)) = 0 Then
        Dim fso As Object
        Set fso = CreateObject("Scripting.FileSystemObject")
        BuildFolders fso, path
    End If
End Sub

Private Sub BuildFolders(ByVal fso As Object, ByVal path As String)
    If Not fso.FolderExists(path) Then
        BuildFolders fso, fso.GetParentFolderName(path)
        fso.CreateFolder path
    End If
End Sub

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

// ValCross — cross-checks BETWEEN the two input documents.
// The I/O List is the master for existence; the C&E matrix is the master for
// safety logic membership.
let
    Io = StgIoList,
    Ce = StgCE,
    EmptyIssues = #table({"RuleId", "Document", "SourceRow", "RowKey", "Message"}, {}),

    // device tag sets (normalized to upper case for the joins)
    IoDevices = List.Buffer(List.Transform(
        List.RemoveNulls(Table.SelectRows(Io, each [TypeInfo] <> null)[Device]), Text.Upper)),
    CeDevices = List.Buffer(List.Transform(List.RemoveNulls(Ce[Device]), Text.Upper)),

    // V301 C&E row whose device does not exist in the I/O List
    V301 = List.Transform(Table.ToRecords(Table.SelectRows(Ce, each
            [Device] <> null and not List.Contains(IoDevices, Text.Upper(Text.From([Device]))))),
        each fnIssue("V301", "CE", [SourceRow], [RowKey],
            "Device " & Text.From([Device]) & " is in the C&E matrix but not in the I/O List")),

    // V302 safety-typed I/O row missing from the C&E matrix (warning by default)
    SafetyRows = Table.SelectRows(Io, each [TypeInfo] <> null and [TypeInfo][Category] = "Safety" and [Device] <> null),
    V302 = List.Transform(Table.ToRecords(Table.SelectRows(SafetyRows, each
            not List.Contains(CeDevices, Text.Upper(Text.From([Device]))))),
        each fnIssue("V302", "IoList", [SourceRow], [RowKey],
            "Safety device " & Text.From([Device]) & " (" & Text.From([Type]) & ") is not present in the C&E matrix")),

    // V303 area named in the C&E but not declared in the AreaList parameter
    Areas = List.Buffer(List.Transform(Text.Split(Text.From(fnParam("AreaList")), ";"), each Text.Upper(Text.Trim(_)))),
    V303 = if not Table.HasColumns(Ce, "Area") then {}
        else List.Transform(Table.ToRecords(Table.SelectRows(Ce, each
                [Area] <> null and not List.Contains(Areas, Text.Upper(Text.From([Area]))))),
            each fnIssue("V303", "CE", [SourceRow], [RowKey],
                "Area """ & Text.From([Area]) & """ is not in the declared AreaList")),

    // V906 stale corrections: Active rows whose RowKey no longer matches anything
    IoKeys = List.Buffer(Io[RowKey]),
    CeKeys = List.Buffer(Ce[RowKey]),
    ActiveFixes = Table.SelectRows(Corrections, each Text.Lower(Text.From([Status])) = "active"),
    V906 = List.Transform(Table.ToRecords(Table.SelectRows(ActiveFixes, each
            not List.Contains(if [Document] = "IoList" then IoKeys else CeKeys, [RowKey]))),
        each fnIssue("V906", [Document], null, [RowKey],
            "Stale correction: RowKey no longer exists (document revision may already contain the fix)")),

    AllFindings = V301 & V302 & V303 & V906,
    Result = if List.IsEmpty(AllFindings) then EmptyIssues
             else Table.Combine({EmptyIssues, Table.FromRecords(AllFindings)})
in
    Result

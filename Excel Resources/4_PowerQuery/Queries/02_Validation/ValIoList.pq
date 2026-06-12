// ValIoList — coherence rules INSIDE the I/O List.
// Output columns: RuleId, Document, SourceRow, RowKey, Message.
let
    S = StgIoList,
    EmptyIssues = #table({"RuleId", "Document", "SourceRow", "RowKey", "Message"}, {}),
    Issue = (rule, row, msg) => fnIssue(rule, "IoList", row[SourceRow], row[RowKey], msg),

    // V101 unknown device type (not in SIGNAL_TYPES, patterns included)
    V101 = List.Transform(Table.ToRecords(Table.SelectRows(S, each [Type] <> null and [TypeInfo] = null)),
        each Issue("V101", _, "Unknown device type """ & Text.From([Type]) & """")),

    // V102 duplicate identity (same FunctionalUnit/Location/Device/Id/Bit)
    DupGroups = Table.SelectRows(Table.Group(S, {"RowKey"}, {{"N", Table.RowCount, Int64.Type}}), each [N] > 1),
    V102 = List.Transform(Table.ToRecords(DupGroups),
        each fnIssue("V102", "IoList", null, [RowKey], "Identity appears " & Text.From([N]) & " times")),

    // V103 node id/bit collision: two signal rows on the same node and bit
    Signals = Table.SelectRows(S, each [TypeInfo] <> null and [IdNode] <> null and [Bit] <> null),
    BitGroups = Table.SelectRows(
        Table.Group(Signals, {"IdNode", "Bit"}, {{"N", Table.RowCount, Int64.Type}, {"Rows", each _}}),
        each [N] > 1),
    V103 = List.Transform(Table.ToRecords(BitGroups),
        each fnIssue("V103", "IoList", null, Text.From([IdNode]) & "|" & Text.From([Bit]),
            "Node " & Text.From([IdNode]) & " bit " & Text.From([Bit]) & " used by " & Text.From([N]) & " rows")),

    // V104 device tag naming pattern (=FU +Location -Device)
    V104 = List.Transform(Table.ToRecords(Table.SelectRows(S, each [Device] <> null and not Text.StartsWith(Text.From([Device]), "-"))),
        each Issue("V104", _, "Device tag """ & Text.From([Device]) & """ does not start with ""-""")),

    // V105 Profinet IP outside the declared safety nets (SafetyNets parameter, ';' separated prefixes)
    Nets = List.Transform(Text.Split(Text.From(fnParam("SafetyNets")), ";"), Text.Trim),
    WithIp = Table.SelectRows(S, each [ProfinetIp] <> null),
    V105 = List.Transform(Table.ToRecords(Table.SelectRows(WithIp, each
            not List.AnyTrue(List.Transform(Nets, (n) => Text.StartsWith(Text.From([ProfinetIp]), n))))),
        each Issue("V105", _, "Profinet IP " & Text.From([ProfinetIp]) & " is outside the declared safety nets")),

    // V106 signal row without a type while a diag address is present
    V106 = List.Transform(Table.ToRecords(Table.SelectRows(S, each [Type] = null and ([DiagCabinet] <> null or [DiagBit] <> null))),
        each Issue("V106", _, "Row has diagnosis data but no device Type")),

    // V107 struck (predisposition) rows still carrying a Type - only reported when StrikeHandling = Flag
    V107 = if Text.Lower(Text.From(fnParam("StrikeHandling"))) <> "flag" or not Table.HasColumns(S, "IsStruck") then {}
        else List.Transform(Table.ToRecords(Table.SelectRows(S, each Text.Lower(Text.From([IsStruck] ?? "false")) = "true" and [Type] <> null)),
            each Issue("V107", _, "Struck-through (predisposition) row still has Type """ & Text.From([Type]) & """ - excluded from outputs")),

    Result = Table.Combine({EmptyIssues,
        Table.FromRecords(V101 & V102 & V103 & V104 & V105 & V106 & V107)})
in
    Result

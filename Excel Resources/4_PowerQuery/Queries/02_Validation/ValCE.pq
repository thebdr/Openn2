// ValCE — coherence rules INSIDE the Cause & Effect matrix.
let
    S = StgCE,
    EmptyIssues = #table({"RuleId", "Document", "SourceRow", "RowKey", "Message"}, {}),
    Issue = (rule, row, msg) => fnIssue(rule, "CE", row[SourceRow], row[RowKey], msg),

    // V201 malformed bit address (expected I/Q + number.number, e.g. I41.0 or Q.1051.0)
    IsAddress = (a) => a <> null and (Text.StartsWith(Text.From(a), "I") or Text.StartsWith(Text.From(a), "Q")),
    V201 = List.Transform(Table.ToRecords(Table.SelectRows(S, each [BitAddress] <> null and not IsAddress([BitAddress]))),
        each Issue("V201", _, "Malformed address """ & Text.From([BitAddress]) & """")),

    // V202 validation status not in the allowed set
    AllowedStatus = {"OK", "BYPASS", "N/A", ""},
    V202 = List.Transform(Table.ToRecords(Table.SelectRows(S, each
            not List.Contains(AllowedStatus, Text.Upper(Text.From([Validated] ?? ""))))),
        each Issue("V202", _, "Validation status """ & Text.From([Validated]) & """ is not OK/BYPASS/N/A")),

    // V203 BYPASS without a note (a bypass must always be justified)
    V203 = List.Transform(Table.ToRecords(Table.SelectRows(S, each
            Text.Upper(Text.From([Validated] ?? "")) = "BYPASS" and [Note] = null)),
        each Issue("V203", _, "BYPASS without a justification note")),

    // V204 duplicate address inside the matrix
    DupGroups = Table.SelectRows(
        Table.Group(Table.SelectRows(S, each [BitAddress] <> null), {"BitAddress"}, {{"N", Table.RowCount, Int64.Type}}),
        each [N] > 1),
    V204 = List.Transform(Table.ToRecords(DupGroups),
        each fnIssue("V204", "CE", null, Text.From([BitAddress]), "Address appears " & Text.From([N]) & " times in the matrix")),

    Result = Table.Combine({EmptyIssues,
        Table.FromRecords(V201 & V202 & V203 & V204)})
in
    Result

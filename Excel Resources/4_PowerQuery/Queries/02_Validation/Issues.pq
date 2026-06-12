// Issues — THE validation report: every finding from every rule set, joined
// with VALIDATION_RULES for severity and enablement. Load this query to the
// ISSUES sheet; filter and send it to the document owner, or absorb findings
// via the CORRECTIONS table. The CSV export macro refuses to export while any
// enabled rule with Severity = Error has findings.
let
    All = Table.Combine({ValIoList, ValCE, ValCross}),

    Rules = Table.TransformColumnTypes(Excel.CurrentWorkbook(){[Name = "VALIDATION_RULES"]}[Content], {
        {"RuleId", type text}, {"Description", type text},
        {"Severity", type text}, {"Enabled", type logical}
    }),

    Joined = Table.NestedJoin(All, {"RuleId"}, Rules, {"RuleId"}, "Rule", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Joined, "Rule", {"Description", "Severity", "Enabled"}),

    // unknown rule ids default to enabled Errors - misconfiguration must be loud
    Defaulted = Table.TransformColumns(Table.ReplaceValue(Expanded, null, "Error", Replacer.ReplaceValue, {"Severity"}),
        {{"Enabled", each if _ = null then true else _, type logical}}),

    EnabledOnly = Table.SelectRows(Defaulted, each [Enabled] = true),
    Sorted = Table.Sort(EnabledOnly, {
        {"Severity", Order.Ascending}, {"RuleId", Order.Ascending}, {"SourceRow", Order.Ascending}}),
    Final = Table.SelectColumns(Sorted,
        {"Severity", "RuleId", "Description", "Document", "SourceRow", "RowKey", "Message"})
in
    Final

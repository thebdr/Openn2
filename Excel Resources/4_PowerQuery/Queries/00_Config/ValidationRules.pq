// ValidationRules — the VALIDATION_RULES table as a workbook-source leaf, so
// Issues can reference it (query ref) instead of reading the workbook directly
// while also combining the file-based Val* queries (firewall rule).
let
    Source = Excel.CurrentWorkbook(){[Name = "VALIDATION_RULES"]}[Content],
    Typed = Table.TransformColumnTypes(Source, {
        {"RuleId", type text}, {"Description", type text},
        {"Severity", type text}, {"Enabled", type logical}
    })
in
    Typed

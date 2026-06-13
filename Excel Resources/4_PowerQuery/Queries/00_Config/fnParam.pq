// fnParam — reads one named value from the Cfg leaf query (NOT Excel.CurrentWorkbook
// directly). Going through Cfg keeps every caller firewall-safe: a combiner that
// calls fnParam is only *referencing* the Cfg query, not directly accessing the
// workbook, so it may still reference file-based queries in the same step.
// Usage: fnParam("StrikeHandling")
(parameterName as text) as any =>
let
    Match = Table.SelectRows(Cfg, each [Name] = parameterName),
    Value =
        if Table.IsEmpty(Match) then
            error Error.Record("ParameterMissing", "Parameter not found in PARAMS table: " & parameterName)
        else
            Match{0}[Value]
in
    Value

// fnParam — reads one named value from the PARAMS table (sheet PARAMS).
// Usage: fnParam("IoListStagedPath")
(parameterName as text) as any =>
let
    ParamsTable = Excel.CurrentWorkbook(){[Name = "PARAMS"]}[Content],
    Match = Table.SelectRows(ParamsTable, each Text.Trim(Text.From([Name])) = parameterName),
    Value =
        if Table.IsEmpty(Match) then
            error Error.Record("ParameterMissing", "Parameter not found in PARAMS table: " & parameterName)
        else
            Match{0}[Value]
in
    Value

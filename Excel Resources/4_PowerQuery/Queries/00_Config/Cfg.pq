// Cfg — the PARAMS table as a single workbook-source leaf query.
// fnParam reads from THIS (a query reference) instead of calling
// Excel.CurrentWorkbook itself, so combiner queries that need parameters never
// directly touch the workbook while also referencing file-based queries - the
// Power Query firewall forbids a query from doing both (direct source access +
// query references) in one step.
let
    Source = Excel.CurrentWorkbook(){[Name = "PARAMS"]}[Content],
    Trimmed = Table.TransformColumns(Source, {{"Name", each Text.Trim(Text.From(_)), type text}})
in
    Trimmed

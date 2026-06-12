// fnLoadStagedSheet — loads one sheet of a STAGED input file (produced by the
// PrepareInputs macro, which snapshots the customer file and adds the IsStruck
// column - Power Query cannot see strikethrough formatting itself).
// Renames source headers to canonical names via COLUMN_MAP and keeps only
// mapped columns + IsStruck.
(filePathParam as text, sheetNameParam as text, headerRowParam as text, documentName as text) as table =>
let
    HeaderRow = Number.From(fnParam(headerRowParam)),
    Source = Excel.Workbook(File.Contents(fnParam(filePathParam)), null, true),
    Sheet = Source{[Item = fnParam(sheetNameParam), Kind = "Sheet"]}[Data],
    SkippedTop = Table.Skip(Sheet, HeaderRow - 1),
    Promoted = Table.PromoteHeaders(SkippedTop, [PromoteAllScalars = true]),

    Map = Table.SelectRows(ColumnMap, each [Document] = documentName),
    Present = Table.SelectRows(Map, each Table.HasColumns(Promoted, [SourceHeader])),
    Renamed = Table.RenameColumns(Promoted,
        List.Transform(Table.ToRecords(Present), each {[SourceHeader], [CanonicalName]}),
        MissingField.Ignore),

    KeepColumns = List.Distinct(Present[CanonicalName] &
        (if Table.HasColumns(Renamed, "IsStruck") then {"IsStruck"} else {})),
    Selected = Table.SelectColumns(Renamed, KeepColumns, MissingField.UseNull),

    // text hygiene: trim every text column, normalize empties to null
    TextColumns = List.Select(Table.ColumnNames(Selected), each _ <> "IsStruck"),
    Trimmed = Table.TransformColumns(Selected,
        List.Transform(TextColumns, (name) => {name,
            each if _ = null then null
                 else if Text.Trim(Text.From(_)) = "" then null
                 else Text.Trim(Text.From(_)), type any})),

    // a source row index for error reporting (header row offset restored)
    Indexed = Table.AddIndexColumn(Trimmed, "SourceRow", HeaderRow + 1, 1, Int64.Type)
in
    Indexed

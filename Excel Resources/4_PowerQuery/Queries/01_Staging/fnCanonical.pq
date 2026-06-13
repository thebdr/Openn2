// fnCanonical — turns a raw staged sheet (from RawIoList / RawCE) into canonical
// columns. REFERENCE-ONLY: it operates on an already-loaded table and references
// the ColumnMap leaf; it never accesses a data source directly, so it is
// firewall-safe even though its callers also reference file-based queries.
//  - skips to the configured header row and promotes headers
//  - renames the present source headers to canonical names via COLUMN_MAP
//  - keeps mapped columns (+ IsStruck), trims text, normalizes empties to null
//  - adds SourceRow (the original Excel row) for issue reporting
(rawSheet as table, headerRow as number, documentName as text) as table =>
let
    SkippedTop = Table.Skip(rawSheet, headerRow - 1),
    Promoted = Table.PromoteHeaders(SkippedTop, [PromoteAllScalars = true]),

    Map = Table.SelectRows(ColumnMap, each [Document] = documentName),
    Present = Table.SelectRows(Map, each Table.HasColumns(Promoted, [SourceHeader])),
    Renamed = Table.RenameColumns(Promoted,
        List.Transform(Table.ToRecords(Present), each {[SourceHeader], [CanonicalName]}),
        MissingField.Ignore),

    KeepColumns = List.Distinct(Present[CanonicalName] &
        (if Table.HasColumns(Renamed, "IsStruck") then {"IsStruck"} else {})),
    Selected = Table.SelectColumns(Renamed, KeepColumns, MissingField.UseNull),

    TextColumns = List.Select(Table.ColumnNames(Selected), each _ <> "IsStruck"),
    Trimmed = Table.TransformColumns(Selected,
        List.Transform(TextColumns, (name) => {name,
            each if _ = null then null
                 else if Text.Trim(Text.From(_)) = "" then null
                 else Text.Trim(Text.From(_)), type any})),

    Indexed = Table.AddIndexColumn(Trimmed, "SourceRow", headerRow + 1, 1, Int64.Type)
in
    Indexed

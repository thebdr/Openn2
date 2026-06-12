// ColumnMap — maps the source document headers to canonical column names
// (COLUMN_MAP table: Document, SourceHeader, CanonicalName, Required).
// The customer can rename/reorder columns between revisions; only this table
// needs to follow.
let
    Source = Excel.CurrentWorkbook(){[Name = "COLUMN_MAP"]}[Content],
    Typed = Table.TransformColumnTypes(Source, {
        {"Document", type text}, {"SourceHeader", type text},
        {"CanonicalName", type text}, {"Required", type logical}
    })
in
    Typed

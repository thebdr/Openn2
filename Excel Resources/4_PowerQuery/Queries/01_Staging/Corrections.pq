// Corrections — local fixes applied over the customer documents WITHOUT touching
// the source files (CORRECTIONS table: Document, RowKey, Column, NewValue,
// Reason, Author, Date, Status). Only Status = "Active" rows are applied.
// When the document owner ships a fixed revision, set Status to "Resolved";
// rule V906 reports corrections that no longer match anything (stale).
let
    Source = Excel.CurrentWorkbook(){[Name = "CORRECTIONS"]}[Content],
    Typed = Table.TransformColumnTypes(Source, {
        {"Document", type text}, {"RowKey", type text}, {"Column", type text},
        {"NewValue", type text}, {"Reason", type text}, {"Author", type text},
        {"Date", type any}, {"Status", type text}
    })
in
    Typed

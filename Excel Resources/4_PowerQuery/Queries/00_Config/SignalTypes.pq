// SignalTypes — the device/signal type catalog from the SIGNAL_TYPES table.
// Columns: TypeId, Description, Category (Safety/Diag/Std), PairKey, Channel,
//          BlockTemplate, InDiagnosis, IsPattern.
// IsPattern = TRUE rows match by regex-like prefix (e.g. TypeId "FA#" matches FA1, FA2, ...).
let
    Source = Excel.CurrentWorkbook(){[Name = "SIGNAL_TYPES"]}[Content],
    Typed = Table.TransformColumnTypes(Source, {
        {"TypeId", type text}, {"Description", type text}, {"Category", type text},
        {"PairKey", type text}, {"Channel", type text}, {"BlockTemplate", type text},
        {"InDiagnosis", type logical}, {"IsPattern", type logical}
    }),
    Trimmed = Table.TransformColumns(Typed, {{"TypeId", each Text.Trim(Text.From(_)), type text}})
in
    Trimmed

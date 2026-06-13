// InterfaceData — the INTERFACE_DATA token table as a workbook-source leaf
// (Token -> Value), referenced by OutInterface.
let
    Source = Excel.CurrentWorkbook(){[Name = "INTERFACE_DATA"]}[Content],
    Typed = Table.TransformColumnTypes(Source, {{"Token", type text}, {"Value", type text}})
in
    Typed

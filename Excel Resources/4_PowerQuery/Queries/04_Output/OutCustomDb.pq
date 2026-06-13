// OutCustomDb — the custom data block entries (SCL/DB source text). One DB per
// signal category; each device contributes one entry "Name : Bool;" with its
// description as comment. The export macro writes each DbName group to
// Output\Blocks\<DbName>.db as plain text (SCL/STL stay text, per the workflow).
let
    Devices = DbDevicesPaired,

    // group by the physical device type: PairKey when the type is paired
    // (E1/2 + E2/2 -> "E"), otherwise the TypeId - then strip characters that
    // are illegal in a file name ("/" in E1/2, DI1/2, ... would break the export)
    SafeName = (text) => Text.Combine(List.Transform(Text.ToList(Text.From(text ?? "")),
        each if List.Contains({"/", "\", ":", "*", "?", """", "<", ">", "|"}, _) then "_" else _)),

    Built = Table.FromRecords(List.Transform(Table.ToRecords(Devices), each [
        DbName = "DB_" & SafeName(if [PairKey] <> null and [PairKey] <> "" then [PairKey] else [TypeId]),
        Line = "   " & Text.Replace(Text.Replace(Text.From([TagName] ?? ""), ".", "_"), "+", "_") &
               " : Bool;   // " & Text.From([Description] ?? "")
    ])),

    // assemble one text blob per DB (the macro writes one file per row)
    Grouped = Table.Group(Built, {"DbName"}, {{"Lines", each Text.Combine([Line], "#(lf)"), type text}}),
    WithBody = Table.AddColumn(Grouped, "Content", each
        "DATA_BLOCK """ & [DbName] & """" & "#(lf)" &
        "{ S7_Optimized_Access := 'TRUE' }" & "#(lf)" &
        "VERSION : 0.1" & "#(lf)" &
        "   STRUCT" & "#(lf)" &
        [Lines] & "#(lf)" &
        "   END_STRUCT;" & "#(lf)" &
        "BEGIN" & "#(lf)" &
        "END_DATA_BLOCK;", type text),
    Final = Table.SelectColumns(WithBody, {"DbName", "Content"})
in
    Final

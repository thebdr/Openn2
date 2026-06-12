// OutInterface — the machine interface: a per-machine-type template (text file
// in Templates\, chosen via the MachineType parameter and the MACHINE_TYPES
// table) with {Token} placeholders replaced from the INTERFACE_DATA table plus
// the generated counts. Project-specific data rows go to INTERFACE_DATA.
let
    MachineTypes = Table.TransformColumnTypes(Excel.CurrentWorkbook(){[Name = "MACHINE_TYPES"]}[Content],
        {{"MachineType", type text}, {"InterfaceTemplate", type text}}),
    Selected = Table.SelectRows(MachineTypes, each [MachineType] = Text.From(fnParam("MachineType"))),
    TemplatePath = if Table.IsEmpty(Selected)
        then error Error.Record("MachineTypeUnknown", "MachineType parameter not found in MACHINE_TYPES")
        else Selected{0}[InterfaceTemplate],

    TemplateText = Text.FromBinary(File.Contents(TemplatePath), TextEncoding.Utf8),

    // tokens: INTERFACE_DATA rows + generated values
    UserTokens = Table.TransformColumnTypes(Excel.CurrentWorkbook(){[Name = "INTERFACE_DATA"]}[Content],
        {{"Token", type text}, {"Value", type text}}),
    Generated = #table({"Token", "Value"}, {
        {"ProjectCode", Text.From(fnParam("ProjectCode"))},
        {"DeviceCount", Text.From(Table.RowCount(DbDevicesPaired))},
        {"SignalCount", Text.From(Table.RowCount(DbSignals))},
        {"AreaList", Text.From(fnParam("AreaList"))}
    }),
    AllTokens = Table.Combine({Generated, UserTokens}), // user rows override generated ones last

    Replaced = List.Accumulate(Table.ToRecords(AllTokens), TemplateText,
        (state, t) => Text.Replace(state, "{" & t[Token] & "}", t[Value])),

    Final = #table({"FileName", "Content"}, {{"Interface_" & Text.From(fnParam("ProjectCode")) & ".txt", Replaced}})
in
    Final

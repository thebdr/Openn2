// OutInterface — the machine interface: a per-machine-type template (read by the
// RawInterfaceTemplate leaf, chosen via pInterfaceTemplate) with {Token}
// placeholders replaced from the InterfaceData leaf plus generated counts.
// Reference-only: it never touches a data source directly (template via the leaf,
// tables via leaves), so it is firewall-safe.
let
    TemplateText = RawInterfaceTemplate,

    // tokens: generated values first, then user rows (InterfaceData) override
    Generated = #table({"Token", "Value"}, {
        {"ProjectCode", Text.From(fnParam("ProjectCode"))},
        {"DeviceCount", Text.From(Table.RowCount(DbDevicesPaired))},
        {"SignalCount", Text.From(Table.RowCount(DbSignals))},
        {"AreaList", Text.From(fnParam("AreaList"))}
    }),
    AllTokens = Table.Combine({Generated, InterfaceData}),

    Replaced = List.Accumulate(Table.ToRecords(AllTokens), TemplateText,
        (state, t) => Text.Replace(state, "{" & t[Token] & "}", t[Value])),

    Final = #table({"FileName", "Content"}, {{"Interface_" & Text.From(fnParam("ProjectCode")) & ".txt", Replaced}})
in
    Final

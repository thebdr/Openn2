// OutBlockInstances — the data feed for LAD/FBD block generation: one row per
// physical device that has a BlockTemplate assigned (E -> 02_EM Push Button,
// DI/DD/DR/DL/DQ -> 08_Gate Manager, ... per the SIGNAL_TYPES table). The XML
// template engine (1_SwPlc flow / Openn2 block import) consumes these rows to
// instantiate the template per device: instance name, both channel addresses,
// description, areas.
// Custom DB entries (the old "DB Entry" columns) are derived from the same rows.
let
    Devices = Table.SelectRows(DbDevicesPaired, each [BlockTemplate] <> null and [BlockTemplate] <> ""),

    Built = Table.FromRecords(List.Transform(Table.ToRecords(Devices), each [
        BlockTemplate = [BlockTemplate],
        InstanceName = Text.Replace(Text.Replace(Text.From([TagName] ?? ""), ".", "_"), "+", "_"),
        TagName = [TagName],
        TypeId = [TypeId],
        Description = Text.From([Description] ?? ""),
        Ch1_Address = if [Ch1_Node] = null or [Ch1_Bit] = null then "" else "%I" & Text.From([Ch1_Node]) & "." & Text.From([Ch1_Bit]),
        Ch2_Address = if [Ch2_Node] = null or [Ch2_Bit] = null then "" else "%I" & Text.From([Ch2_Node]) & "." & Text.From([Ch2_Bit]),
        FunctionalUnit = Text.From([FunctionalUnit] ?? ""),
        Location = Text.From([Location] ?? ""),
        DeviceTag = Text.From([DeviceTag] ?? "")
    ])),

    Sorted = Table.Sort(Built, {{"BlockTemplate", Order.Ascending}, {"InstanceName", Order.Ascending}})
in
    Sorted

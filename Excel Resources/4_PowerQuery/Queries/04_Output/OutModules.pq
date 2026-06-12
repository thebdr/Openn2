// OutModules — Modules.csv rows for Openn2, FORMAT 2:
// Station Name;Slot;Module Name;Model Id;I Addr;Q Addr;Custom Parameters
// Plugged modules (model type IoDeviceCard) grouped under their head station
// by node id; Slot = plug order. I/Q start addresses come straight from the
// I/O List addressing; custom parameters use the '|' separated syntax
// ([Item(i).][Ch(i).]Name=Value) and can be refined per model in Openn2.
let
    Hw = DbHardware,
    Heads = Table.SelectRows(Hw, each [ModelType] = "IoDevice" or [ModelType] = "Plc" or [ModelType] = "PlcCardCm"),
    Cards = Table.SelectRows(Hw, each [ModelType] = "IoDeviceCard"),

    // station lookup: node id -> station name
    HeadByNode = Table.Distinct(Table.SelectColumns(Heads, {"IdNode", "ProfinetName", "Device"}), {"IdNode"}),
    Joined = Table.NestedJoin(Cards, {"IdNode"}, HeadByNode, {"IdNode"}, "Head", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Joined, "Head", {"ProfinetName", "Device"}, {"HeadName", "HeadDevice"}),

    // plug order per station, by source slot then row order
    Sorted = Table.Sort(Expanded, {{"IdNode", Order.Ascending}, {"Slot", Order.Ascending}, {"SourceRow", Order.Ascending}}),
    Grouped = Table.Group(Sorted, {"IdNode"}, {{"Rows", each Table.AddIndexColumn(_, "PlugOrder", 1, 1, Int64.Type), type table}}),
    Reassembled = Table.Combine(Grouped[Rows]),

    Built = Table.FromRecords(List.Transform(Table.ToRecords(Reassembled), each [
        #"Station Name" = Text.Lower(Text.From([HeadName] ?? [HeadDevice] ?? "")),
        Slot = Text.From([PlugOrder]),
        #"Module Name" = Text.From([Device] ?? ""),
        #"Model Id" = [ModelId],
        #"I Addr" = "",
        #"Q Addr" = "",
        #"Custom Parameters" = ""
    ]))
in
    Built

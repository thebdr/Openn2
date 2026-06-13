// DbHardware — the PROFINET hardware structure extracted from the I/O List:
// the rows that describe modules (Part No. + node) become stations and plugged
// modules. Part numbers are resolved against the existing model database
// (DeviceTypesCsvPath -> HardwareConfig\DeviceTypesDatabase.csv of Openn2);
// unknown part numbers surface as a column for validation/extension.
let
    // module rows: have a part number and a node id (the signal rows reference them)
    Hw = Table.SelectRows(StgIoList, each [PartNo] <> null and [IdNode] <> null),

    // model database of Openn2 via the RawDeviceTypes leaf (reference, not direct read)
    DevTypesNamed = RawDeviceTypes,

    // the model id convention: part number without spaces (e.g. 6ES7517-3FP00-0AB0)
    WithModelId = Table.AddColumn(Hw, "ModelId", each Text.Replace(Text.From([PartNo]), " ", ""), type text),
    Joined = Table.NestedJoin(WithModelId, {"ModelId"}, DevTypesNamed, {"ModelId"}, "Model", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Joined, "Model", {"DeviceType", "Comment"}, {"ModelType", "ModelComment"}),

    // station = head module rows (the model is a Plc / PlcCardCm / IoDevice);
    // plugged module rows reference their head by node id
    Final = Table.SelectColumns(Expanded, {
        "SourceRow", "RowKey", "Module", "Manufacturer", "PartNo", "ModelId", "ModelType", "ModelComment",
        "Slot", "IdNode", "FunctionalUnit", "Location", "Device", "ProfinetIp", "ProfinetName"
    }, MissingField.UseNull)
in
    Final

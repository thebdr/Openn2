// DbSignals — the normalized signal database. One row per typed I/O List row,
// with the SIGNAL_TYPES attributes expanded and the channel-pair identity:
// E1/2 + E2/2 of the same device are two channels of ONE physical device,
// identified by DeviceKey = Location|Device + PairKey.
// This single table replaces the per-type sheets (_PB, _KQ, _KF, ...) of the
// old workbook: filter by TypeId/Category instead.
let
    S = Table.SelectRows(StgIoList, each [TypeInfo] <> null),

    Expanded = Table.AddColumn(S, "TypeId", each [TypeInfo][TypeId], type text),
    WithCategory = Table.AddColumn(Expanded, "Category", each [TypeInfo][Category], type text),
    WithPair = Table.AddColumn(WithCategory, "PairKey", each [TypeInfo][PairKey], type text),
    WithChannel = Table.AddColumn(WithPair, "Channel", each [TypeInfo][Channel], type text),
    WithTemplate = Table.AddColumn(WithChannel, "BlockTemplate", each [TypeInfo][BlockTemplate], type text),
    WithDiagFlag = Table.AddColumn(WithTemplate, "InDiagnosis", each [TypeInfo][InDiagnosis], type logical),

    // one identity per physical device: paired channels share it
    WithDeviceKey = Table.AddColumn(WithDiagFlag, "DeviceKey", each
        Text.Combine({Text.From([Location] ?? ""), Text.From([Device] ?? "")}, "|") &
        (if [PairKey] <> null and [PairKey] <> "" then "|" & [PairKey] else ""), type text),

    // PLC tag name: =FU+Location-Device convention, normalized
    WithTagName = Table.AddColumn(WithDeviceKey, "TagName", each Text.Combine(
        List.RemoveNulls({[FunctionalUnit], [Location], [Device]}), ""), type text),

    Final = Table.SelectColumns(WithTagName, {
        "SourceRow", "RowKey", "DeviceKey", "TagName", "TypeId", "Category", "PairKey", "Channel",
        "BlockTemplate", "InDiagnosis", "Module", "PartNo", "Slot", "IdNode", "Bit",
        "NormalCondition", "DescriptionL1", "DescriptionL2", "FunctionalUnit", "Location", "Device",
        "ProfinetIp", "ProfinetName", "Mnemonic", "DiagCabinet", "DiagBit"
    }, MissingField.UseNull)
in
    Final

// DbDevicesPaired — one row per PHYSICAL device: paired channel types
// (E1/2+E2/2, B1/2+B2/2, ENC1/2+ENC2/2, DI1/2+DI2/2) collapse into a single
// device row with both channel addresses; single-channel types pass through.
// This is the instance list that feeds block generation (one block instance
// per device, not per channel).
let
    S = DbSignals,

    Grouped = Table.Group(S, {"DeviceKey"}, {
        {"Rows", each _, type table},
        {"ChannelCount", Table.RowCount, Int64.Type}
    }),

    Pick = (rows as table, channel as text, column as text) as any =>
        let M = Table.SelectRows(rows, each Text.From([Channel] ?? "") = channel)
        in if Table.IsEmpty(M) then null else Table.Column(M, column){0},

    First = (rows as table, column as text) as any => Table.Column(rows, column){0},

    Built = Table.AddColumn(Grouped, "Device", each
        let r = [Rows]
        in [
            TagName = First(r, "TagName"),
            TypeId = First(r, "TypeId"),
            PairKey = First(r, "PairKey"),
            Category = First(r, "Category"),
            BlockTemplate = First(r, "BlockTemplate"),
            InDiagnosis = First(r, "InDiagnosis"),
            FunctionalUnit = First(r, "FunctionalUnit"),
            Location = First(r, "Location"),
            DeviceTag = First(r, "Device"),
            Description = First(r, "DescriptionL1"),
            // single-channel types: channel 1 = the row itself
            Ch1_Node = if [ChannelCount] = 1 then First(r, "IdNode") else Pick(r, "1", "IdNode"),
            Ch1_Bit = if [ChannelCount] = 1 then First(r, "Bit") else Pick(r, "1", "Bit"),
            Ch2_Node = Pick(r, "2", "IdNode"),
            Ch2_Bit = Pick(r, "2", "Bit"),
            DiagCabinet = First(r, "DiagCabinet"),
            DiagBit = First(r, "DiagBit"),
            ChannelCount = [ChannelCount]
        ]),

    Expanded = Table.ExpandRecordColumn(Table.SelectColumns(Built, {"DeviceKey", "Device"}), "Device",
        {"TagName", "TypeId", "PairKey", "Category", "BlockTemplate", "InDiagnosis", "FunctionalUnit",
         "Location", "DeviceTag", "Description", "Ch1_Node", "Ch1_Bit", "Ch2_Node", "Ch2_Bit",
         "DiagCabinet", "DiagBit", "ChannelCount"})
in
    Expanded

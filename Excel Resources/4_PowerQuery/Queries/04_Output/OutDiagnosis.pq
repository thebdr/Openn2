// OutDiagnosis — flat diagnosis export (csv): documented bits from the I/O List
// (DiagCabinet/DiagBit) plus the generated entries, ready for the diagnosis
// blocks/HMI import.
let
    D = DbDiagnosis,
    Built = Table.SelectColumns(D,
        {"Origin", "DeviceKey", "TagName", "TypeId", "Location", "Device", "DescriptionL1", "DiagCabinet", "DiagBit"},
        MissingField.UseNull),
    Sorted = Table.Sort(Built, {{"DiagCabinet", Order.Ascending}, {"DiagBit", Order.Ascending}})
in
    Sorted

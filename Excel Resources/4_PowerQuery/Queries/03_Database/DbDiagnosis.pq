// DbDiagnosis — the diagnosis data set. Two sources, as per the workflow:
//   1. the I/O List part: rows whose type has InDiagnosis = TRUE and that carry
//      DiagCabinet / DiagBit columns;
//   2. the generated part: per-device diagnosis entries derived from the present
//      devices and the DIAG_PARAMS table (e.g. one entry per cabinet, per area
//      feedback FA#). The generation rules are project-specific - extend the
//      Generated step below when the machine type needs more.
let
    // part 1: documented diagnosis bits
    FromIoList = Table.SelectColumns(
        Table.SelectRows(DbSignals, each [InDiagnosis] = true and ([DiagCabinet] <> null or [DiagBit] <> null)),
        {"DeviceKey", "TagName", "TypeId", "Location", "Device", "DescriptionL1", "DiagCabinet", "DiagBit"},
        MissingField.UseNull),
    Part1 = Table.AddColumn(FromIoList, "Origin", each "IoList", type text),

    // part 2: generated entries - one per distinct cabinet (extend per project)
    Cabinets = Table.Distinct(Table.SelectColumns(
        Table.SelectRows(DbSignals, each [DiagCabinet] <> null), {"DiagCabinet"})),
    Part2 = Table.AddColumn(Table.AddColumn(Table.AddColumn(Table.AddColumn(Table.AddColumn(Table.AddColumn(Table.AddColumn(
        Table.RenameColumns(Cabinets, {{"DiagCabinet", "DiagCabinetSrc"}}),
        "DeviceKey", each "GEN|" & Text.From([DiagCabinetSrc]), type text),
        "TagName", each "Diag_" & Text.From([DiagCabinetSrc]), type text),
        "TypeId", each "GEN", type text),
        "Location", each null), "Device", each null),
        "DescriptionL1", each "Generated cabinet diagnosis: " & Text.From([DiagCabinetSrc]), type text),
        "DiagBit", each null),
    Part2Final = Table.AddColumn(Table.RenameColumns(Part2, {{"DiagCabinetSrc", "DiagCabinet"}}),
        "Origin", each "Generated", type text),

    Result = Table.Combine({Part1, Table.SelectColumns(Part2Final, Table.ColumnNames(Part1))})
in
    Result

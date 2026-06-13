// StgCE — the validated-input Cause & Effect matrix rows: staged file ->
// canonical columns -> corrections -> struck rows handled.
// Canonical columns (COLUMN_MAP, Document = "CE"): PlcF, Validated, Position,
// Note, ModuleAddress, BitAddress, SlotDevice, PinNo, Description,
// FunctionalUnit, Location, Device, Area.
// RowKey = BitAddress|Device (the address is the stable identity in the matrix).
let
    Loaded = fnCanonical(RawCE, Number.From(fnParam("CEHeaderRow")), "CE"),

    NonEmpty = Table.SelectRows(Loaded, each [BitAddress] <> null or [Device] <> null),

    WithKey = Table.AddColumn(NonEmpty, "RowKey", each Text.Combine({
        Text.From([BitAddress] ?? ""), Text.From([Device] ?? "")
    }, "|"), type text),

    Corrected = fnApplyCorrections(WithKey, "CE"),

    StrikeHandling = Text.Lower(Text.From(fnParam("StrikeHandling"))),
    Struck = if not Table.HasColumns(Corrected, "IsStruck") then Corrected
             else if StrikeHandling = "exclude"
             then Table.SelectRows(Corrected, each [IsStruck] <> true and Text.Lower(Text.From([IsStruck] ?? "false")) <> "true")
             else Corrected
in
    Struck

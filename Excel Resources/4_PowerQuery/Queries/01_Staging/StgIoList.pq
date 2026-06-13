// StgIoList — the validated-input I/O List: staged file -> canonical columns ->
// corrections applied -> struck rows handled per the StrikeHandling parameter
// ("Exclude" drops them here; "Flag" keeps them and validation reports them).
// RowKey = FunctionalUnit|Location|Device|IdNode|Bit - the stable identity used
// by CORRECTIONS and by the ISSUES report.
let
    Loaded = fnCanonical(RawIoList, Number.From(fnParam("IoListHeaderRow")), "IoList"),

    // drop fully empty rows (no device, no module, no description)
    NonEmpty = Table.SelectRows(Loaded, each
        [Device] <> null or [Module] <> null or [DescriptionModule] <> null),

    WithKey = Table.AddColumn(NonEmpty, "RowKey", each Text.Combine({
        Text.From([FunctionalUnit] ?? ""), Text.From([Location] ?? ""),
        Text.From([Device] ?? ""), Text.From([IdNode] ?? ""), Text.From([Bit] ?? "")
    }, "|"), type text),

    Corrected = fnApplyCorrections(WithKey, "IoList"),

    StrikeHandling = Text.Lower(Text.From(fnParam("StrikeHandling"))),
    Struck = if not Table.HasColumns(Corrected, "IsStruck") then Corrected
             else if StrikeHandling = "exclude"
             then Table.SelectRows(Corrected, each [IsStruck] <> true and Text.Lower(Text.From([IsStruck] ?? "false")) <> "true")
             else Corrected,

    WithTypeInfo = Table.AddColumn(Struck, "TypeInfo", each fnTypeInfo(try Text.From([Type]) otherwise null))
in
    WithTypeInfo

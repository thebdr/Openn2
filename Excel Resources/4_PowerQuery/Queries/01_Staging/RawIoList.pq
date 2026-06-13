// RawIoList — leaf that opens the staged I/O List workbook and returns its sheet
// untouched. Directly accesses ONE data source (the file) and references only
// native parameters (pIoListStaged / pIoListSheet), which the firewall folds as
// constants - so this stays a clean single-source leaf that combiner queries may
// reference. All shaping happens downstream in StgIoList (reference-only).
let
    book = Excel.Workbook(File.Contents(pIoListStaged), null, true),
    sheet = book{[Item = pIoListSheet, Kind = "Sheet"]}[Data]
in
    sheet

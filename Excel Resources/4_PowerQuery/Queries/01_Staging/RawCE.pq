// RawCE — leaf that opens the staged C&E matrix workbook and returns its sheet
// untouched. Single file source + native parameters only (see RawIoList).
let
    book = Excel.Workbook(File.Contents(pCEStaged), null, true),
    sheet = book{[Item = pCESheet, Kind = "Sheet"]}[Data]
in
    sheet

// pIoListSheet — sheet name inside the staged I/O List workbook (native parameter,
// set by the PrepareInputs macro). Needed alongside pIoListStaged so the leaf
// reader can open the workbook without reading any other source.
"IO List" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]

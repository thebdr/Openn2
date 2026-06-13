// pIoListStaged — native Power Query parameter holding the absolute path of the
// staged I/O List workbook. The firewall treats native parameters as constants,
// so a leaf query can open this file AND reference the parameter without tripping
// the "may not directly access a data source" rule. The PrepareInputs macro
// rewrites this value from the PARAMS table on every staging run.
"" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]

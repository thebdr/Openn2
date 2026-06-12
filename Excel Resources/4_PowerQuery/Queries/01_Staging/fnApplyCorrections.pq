// fnApplyCorrections — applies the Active rows of CORRECTIONS for one document
// to a staged table. Rows are matched by the RowKey column (built in staging);
// the named column gets the corrected value.
(stagedTable as table, documentName as text) as table =>
let
    Active = Table.SelectRows(Corrections, each
        [Document] = documentName and Text.Lower(Text.From([Status])) = "active"),
    Result = List.Accumulate(Table.ToRecords(Active), stagedTable, (state, fix) =>
        if not Table.HasColumns(state, fix[Column]) then state
        else Table.FromRecords(List.Transform(Table.ToRecords(state), (row) =>
            if row[RowKey] = fix[RowKey]
            then Record.TransformFields(row, {{fix[Column], each fix[NewValue]}})
            else row)))
in
    Result

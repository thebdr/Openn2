// fnTypeInfo — resolves a raw Type cell value to its SIGNAL_TYPES row, or null
// when the type is unknown. Handles pattern types: a row with IsPattern = TRUE
// and TypeId "FA#" matches FA1, FA2, FA10, ... ("#" stands for one or more digits).
(rawType as nullable text) as nullable record =>
let
    CleanType = if rawType = null then "" else Text.Trim(rawType),
    Exact = Table.SelectRows(SignalTypes, each [IsPattern] <> true and Comparer.OrdinalIgnoreCase([TypeId], CleanType) = 0),
    PatternRows = Table.SelectRows(SignalTypes, each [IsPattern] = true),
    PatternMatch = Table.SelectRows(PatternRows, each
        let
            prefix = Text.BeforeDelimiter([TypeId], "#"),
            rest = if Text.StartsWith(CleanType, prefix, Comparer.OrdinalIgnoreCase)
                   then Text.Range(CleanType, Text.Length(prefix))
                   else null
        in
            rest <> null and Text.Length(rest) > 0 and
            List.AllTrue(List.Transform(Text.ToList(rest), (c) => c >= "0" and c <= "9"))),
    Result =
        if CleanType = "" then null
        else if not Table.IsEmpty(Exact) then Exact{0}
        else if not Table.IsEmpty(PatternMatch) then PatternMatch{0}
        else null
in
    Result

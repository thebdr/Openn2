// OutIoTags — the PLC tag table (TIA import layout): Name, Path (tag table),
// Data Type, Logical Address, Comment, plus the HMI accessibility flags.
// One tag per signal channel; the address is built from the I/O List node/bit.
let
    S = DbSignals,

    Address = (node as any, bit as any, category as text) as text =>
        // safety inputs -> %Ix.y ; outputs (KQ, DQ, DL) -> %Qx.y - refine per project
        let prefix = if List.Contains({"KQ", "DQ", "DL"}, category) then "%Q" else "%I"
        in if node = null or bit = null then "" else prefix & Text.From(node) & "." & Text.From(bit),

    Built = Table.FromRecords(List.Transform(Table.ToRecords(S), each [
        Name = [TagName],
        Path = "IO_" & Text.From([TypeId]),
        #"Data Type" = "Bool",
        #"Logical Address" = Address([IdNode], [Bit], Text.From([TypeId])),
        Comment = Text.Combine(List.RemoveNulls({[DescriptionL1], [DescriptionL2]}), " / "),
        #"Hmi Visible" = "True",
        #"Hmi Accessible" = "True",
        #"Hmi Writeable" = "False"
    ]))
in
    Built

// OutStations — Stations.csv rows for Openn2, FORMAT 2:
// Role;Station Name;Model Id;IP Address;PN Number;Subnet;Custom Parameters;Group
// Head modules (model type Plc / PlcCardCm / IoDevice) become stations; the
// PROFINET name/IP come from the I/O List; Group = FunctionalUnit (editable
// later in the Openn2 hardware editor). The export macro writes the csv with
// the #!format=2 header and refuses to run while validation Errors exist.
let
    Heads = Table.SelectRows(DbHardware, each
        [ModelType] = "Plc" or [ModelType] = "PlcCardCm" or [ModelType] = "IoDevice"),

    SubnetOfNet = (ip as nullable text) as text =>
        if ip = null then "" else "Subnet" & Text.BeforeDelimiter(Text.AfterDelimiter(Text.From(ip), ".", 1), "."),

    Built = Table.FromRecords(List.Transform(Table.ToRecords(Heads), each [
        Role = [ModelType],
        #"Station Name" = Text.Lower(Text.From([ProfinetName] ?? [Device] ?? "")),
        #"Model Id" = [ModelId],
        #"IP Address" = Text.From([ProfinetIp] ?? ""),
        #"PN Number" = "",
        Subnet = SubnetOfNet([ProfinetIp]),
        #"Custom Parameters" = "",
        Group = Text.From([FunctionalUnit] ?? "")
    ]))
in
    Built

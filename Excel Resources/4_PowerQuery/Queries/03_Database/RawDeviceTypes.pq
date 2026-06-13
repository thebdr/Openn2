// RawDeviceTypes — leaf reading the Openn2 model database csv (semicolon, UTF-8).
// Single file source + the pDeviceTypesCsv native parameter only, so DbHardware
// can reference it without a firewall violation.
let
    Raw = Csv.Document(File.Contents(pDeviceTypesCsv), [Delimiter = ";", Encoding = 65001]),
    NoComments = Table.SelectRows(Raw, each not Text.StartsWith(Text.From([Column1] ?? ""), "#")),
    Named = Table.RenameColumns(NoComments, {
        {"Column1", "ModelId"}, {"Column2", "DeviceType"}, {"Column3", "TiaIdentifier"}, {"Column4", "Comment"}},
        MissingField.Ignore)
in
    Named

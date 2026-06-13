// RawInterfaceTemplate — leaf reading the machine interface template text file
// (UTF-8). Single file source + the pInterfaceTemplate native parameter only, so
// OutInterface can reference it firewall-safe.
Text.FromBinary(File.Contents(pInterfaceTemplate), TextEncoding.Utf8)

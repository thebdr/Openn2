// MachineTypes — the MACHINE_TYPES table as a workbook-source leaf
// (MachineType -> InterfaceTemplate path). Referenced by OutInterface.
let
    Source = Excel.CurrentWorkbook(){[Name = "MACHINE_TYPES"]}[Content],
    Typed = Table.TransformColumnTypes(Source, {{"MachineType", type text}, {"InterfaceTemplate", type text}})
in
    Typed

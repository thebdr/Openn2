using System;
using System.Collections.Generic;
using System.Linq;

namespace Openn._00_Contract
{
    /// <summary>Where a kind lives in the TIA project tree.</summary>
    public enum InputArea
    {
        /// <summary>Project-level hardware: "Devices &amp; networks".</summary>
        Hardware,
        /// <summary>Per-PLC software: the VCI folders under the PLC.</summary>
        Software,
        /// <summary>Carried for humans, never imported.</summary>
        Documentation
    }

    /// <summary>How OpennN handles a kind (the import route it is dispatched to).</summary>
    public enum ImportRoute
    {
        /// <summary>Not imported (documentation / manual aid).</summary>
        None,
        /// <summary>Loaded as reference data for another route.</summary>
        Reference,
        /// <summary>Hardware generation (HardwareConfigLoader + CreateDevices).</summary>
        HardwareGeneration,
        /// <summary>PlcBlockGroup.Blocks.Import (code and data block XML).</summary>
        ImportBlockXml,
        /// <summary>TypeGroup.Types.Import.</summary>
        ImportTypeXml,
        /// <summary>TagTableGroup.TagTables.Import.</summary>
        ImportTagTableXml,
        /// <summary>BlockXmlGenerator.Generate, then ImportBlockXml.</summary>
        GenerateThenImport,
        /// <summary>PlcBlockComposition.CreateInstanceDB per csv row.</summary>
        CreateInstanceDbs,
        /// <summary>ExternalSources.CreateFromFile + GenerateBlocksFromSource.</summary>
        GenerateFromSource,
        /// <summary>Referenced by sw/block-gen csvs; never imported by itself.</summary>
        Template
    }

    /// <summary>
    /// Every kind of file OpennN manages: the inputs it imports into TIA (produced by
    /// Pipeline5 or hand-maintained) and the same kinds when it exports them back.
    /// The kind is declared by the file's header ("kind: hw/stations", see OpennHeader);
    /// the folder a file sits in only decides WHERE in the TIA tree it lands.
    /// Contract: Shared\PL5_OP5_contract.md.
    /// </summary>
    public enum InputKind
    {
        Unknown = 0,

        //--- hardware (project level) ---
        HwDeviceTypes,
        HwStations,
        HwModules,

        //--- software (per PLC) ---
        SwCodeBlock,
        SwDataBlock,
        SwInstanceDb,
        SwBlockGen,
        SwSource,
        SwUdt,
        SwTagTable,
        SwBlockTemplate,

        //--- documentation (never imported) ---
        DocPlcTagsWorkbook,
        DocOther
    }

    /// <summary>Static description of one kind: id, placement, formats, route and import rank.</summary>
    public sealed class InputKindInfo
    {
        public InputKind Kind { get; }
        /// <summary>The id written in the header: "&lt;area&gt;/&lt;object&gt;".</summary>
        public string Id { get; }
        public string Title { get; }
        public InputArea Area { get; }
        /// <summary>The TIA tree / VCI folder the kind lives in ("Program blocks", "PLC tags", ...); null = anywhere.</summary>
        public string VciFolder { get; }
        /// <summary>Accepted file extensions, lower case with the dot; empty = any.</summary>
        public string[] Extensions { get; }
        public ImportRoute Route { get; }
        /// <summary>Import rank: kinds are imported in ascending order (dependencies first).</summary>
        public int ImportOrder { get; }
        /// <summary>The schema version this build reads (a header's "schema" must not be newer).</summary>
        public int SupportedSchema { get; }
        public string Description { get; }

        private InputKindInfo(InputKind kind, string id, string title, InputArea area, string vciFolder, string[] extensions,
            ImportRoute route, int importOrder, int supportedSchema, string description)
        {
            Kind = kind; Id = id; Title = title; Area = area; VciFolder = vciFolder; Extensions = extensions;
            Route = route; ImportOrder = importOrder; SupportedSchema = supportedSchema; Description = description;
        }

        public bool AcceptsExtension(string extension) =>
            Extensions.Length == 0 || Extensions.Contains((extension ?? string.Empty).ToLowerInvariant());

        public override string ToString() => Id;

        /// <summary>The complete taxonomy, in import order.</summary>
        public static readonly IReadOnlyList<InputKindInfo> All = new[]
        {
            new InputKindInfo(InputKind.HwDeviceTypes, "hw/device-types", "Device type database", InputArea.Hardware, WorkspaceLayout.HardwareFolder,
                new[] { ".csv" }, ImportRoute.Reference, 0, 1,
                "Model database (order number -> TIA type identifier, device type, default custom parameters). Hand-maintained, shared by both apps."),
            new InputKindInfo(InputKind.HwStations, "hw/stations", "Stations", InputArea.Hardware, WorkspaceLayout.HardwareFolder,
                new[] { ".csv" }, ImportRoute.HardwareGeneration, 10, 2,
                "One row per station: Plc / PlcCardCm controllers and IoDevice stations with IP, PN number, subnet, custom parameters, group."),
            new InputKindInfo(InputKind.HwModules, "hw/modules", "Modules", InputArea.Hardware, WorkspaceLayout.HardwareFolder,
                new[] { ".csv" }, ImportRoute.HardwareGeneration, 11, 2,
                "One row per plugged module, referencing its station: slot order, model, I/Q addresses, custom parameters."),

            new InputKindInfo(InputKind.SwUdt, "sw/udt", "PLC data type", InputArea.Software, WorkspaceLayout.PlcDataTypes,
                new[] { ".xml" }, ImportRoute.ImportTypeXml, 20, 1,
                "One TIA Openness XML (SW.Types.PlcStruct) per user data type."),
            new InputKindInfo(InputKind.SwTagTable, "sw/tag-table", "PLC tag table", InputArea.Software, WorkspaceLayout.PlcTags,
                new[] { ".xml" }, ImportRoute.ImportTagTableXml, 30, 1,
                "One TIA Openness XML (SW.Tags.PlcTagTable) per tag table."),
            new InputKindInfo(InputKind.SwDataBlock, "sw/data-block", "Global data block", InputArea.Software, WorkspaceLayout.ProgramBlocks,
                new[] { ".xml" }, ImportRoute.ImportBlockXml, 40, 1,
                "TIA Openness XML of a global DB (SW.Blocks.GlobalDB), F-DBs included."),
            new InputKindInfo(InputKind.SwInstanceDb, "sw/instance-db", "Instance DB list", InputArea.Software, WorkspaceLayout.ProgramBlocks,
                new[] { ".csv" }, ImportRoute.CreateInstanceDbs, 50, 1,
                "Csv list of single-instance DBs (Name, InstanceOf, Number, Folder) created directly through the API."),
            new InputKindInfo(InputKind.SwBlockGen, "sw/block-gen", "Block generation list", InputArea.Software, WorkspaceLayout.ProgramBlocks,
                new[] { ".csv" }, ImportRoute.GenerateThenImport, 60, 1,
                "Template-driven generation csv ($ template directive, % key row, @ data rows): expanded into block XML, then imported."),
            new InputKindInfo(InputKind.SwCodeBlock, "sw/code-block", "Code block", InputArea.Software, WorkspaceLayout.ProgramBlocks,
                new[] { ".xml" }, ImportRoute.ImportBlockXml, 61, 1,
                "TIA Openness XML of an OB / FB / FC."),
            new InputKindInfo(InputKind.SwSource, "sw/source", "External source", InputArea.Software, WorkspaceLayout.ProgramBlocks,
                new[] { ".scl", ".awl", ".db", ".udt", ".st" }, ImportRoute.GenerateFromSource, 62, 1,
                "Text source (SCL / STL / DB / UDT) compiled by TIA through an external source; its blocks land in the Program blocks root."),
            new InputKindInfo(InputKind.SwBlockTemplate, "sw/block-template", "Block template", InputArea.Software, null,
                new[] { ".xml", ".scl", ".db" }, ImportRoute.Template, 90, 1,
                "Template export referenced by sw/block-gen csvs (TEMPLATE--vX.Y--Name). Hand-maintained; never imported by itself."),

            new InputKindInfo(InputKind.DocPlcTagsWorkbook, "doc/plc-tags-workbook", "PLC tags workbook", InputArea.Documentation, WorkspaceLayout.PlcTags,
                new[] { ".xlsx" }, ImportRoute.None, 100, 1,
                "TIA 'PLC Tags' workbook for manual import in the TIA GUI only; OpennN imports the tag-table XML instead."),
            new InputKindInfo(InputKind.DocOther, "doc/other", "Documentation", InputArea.Documentation, null,
                new string[0], ImportRoute.None, 101, 1,
                "Anything carried for humans (reports, workbooks, readme files). Listed, never imported."),
        };

        private static readonly Dictionary<string, InputKindInfo> byId =
            All.ToDictionary(k => k.Id, k => k, StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<InputKind, InputKindInfo> byKind =
            All.ToDictionary(k => k.Kind, k => k);

        /// <summary>The kind behind a header id ("hw/stations"), or null when unknown.</summary>
        public static InputKindInfo ById(string id)
        {
            if (string.IsNullOrWhiteSpace(id)) return null;
            InputKindInfo info;
            return byId.TryGetValue(id.Trim(), out info) ? info : null;
        }

        /// <summary>The description of a kind; null for Unknown.</summary>
        public static InputKindInfo For(InputKind kind)
        {
            InputKindInfo info;
            return byKind.TryGetValue(kind, out info) ? info : null;
        }
    }
}

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Xml;

namespace Openn._00_Contract
{
    /// <summary>
    /// The folder shape of the handoff workspace (BuilderData): a TIA Version Control
    /// Interface workspace plus one project-level hardware folder.
    ///
    ///   BuilderData\
    ///     .openn\workspace.openn.config            workspace header (contract, project, producer, generated)
    ///     .openn\import.openn5.config              Openn5's Import ticks (WorkspaceImportSettings; optional, written by Openn5)
    ///     Devices &amp; networks\                      hw/* csv (project level - VCI has no hardware)
    ///     Templates\                               sw/block-template (referenced by block-gen csvs; not a TIA folder)
    ///     &lt;PLC name&gt;\Program blocks\&lt;group&gt;\...   sw/code-block, sw/data-block, sw/block-gen, sw/instance-db, sw/source
    ///     &lt;PLC name&gt;\PLC data types\              sw/udt
    ///     &lt;PLC name&gt;\PLC tags\                    sw/tag-table (+ the manual PLCTags.xlsx)
    ///
    /// The legacy BuilderData layout (HardwareConfiguration, SoftwareBlocks\CreationInfo,
    /// SoftwareBlocks\ImportReady, PlcTags, UserDataTypes, DataBlocks) is recognized only to name it:
    /// its files are mapped for display but never imported (legacy acceptance retired 2026-10-09).
    /// </summary>
    public static class WorkspaceLayout
    {
        public const string ConfigFolder = ".openn";
        public const string ConfigFile = "workspace.openn.config";
        /// <summary>Openn5's own file in the config folder: the files whose Import box the user unticked (WorkspaceImportSettings).</summary>
        public const string ImportSettingsFile = "import.openn5.config";
        public const string VciConfigFolder = ".vci";

        public const string HardwareFolder = "Devices & networks";
        /// <summary>Block templates referenced by sw/block-gen csvs (workspace root; not a TIA folder).</summary>
        public const string TemplatesFolder = "Templates";
        public const string ProgramBlocks = "Program blocks";
        public const string PlcTags = "PLC tags";
        public const string PlcDataTypes = "PLC data types";

        /// <summary>The TIA tree folders a VCI workspace can hold under a PLC (V18/V19 names).</summary>
        public static readonly string[] VciFolders =
            { ProgramBlocks, PlcTags, PlcDataTypes, "Technology objects", "External source files", "Watch and force tables", "Software units" };

        public const string LegacyHardware = "HardwareConfiguration";
        public const string LegacySoftwareBlocks = "SoftwareBlocks";
        public const string LegacyCreationInfo = "CreationInfo";
        public const string LegacyImportReady = "ImportReady";
        public const string LegacyPlcTags = "PlcTags";
        public const string LegacyUserDataTypes = "UserDataTypes";
        public const string LegacyDataBlocks = "DataBlocks";

        public static bool IsVciFolder(string name) =>
            VciFolders.Any(f => f.Equals(name, StringComparison.OrdinalIgnoreCase));

        public static bool IsLegacyRoot(string firstSegment) =>
            new[] { LegacyHardware, LegacySoftwareBlocks, LegacyPlcTags, LegacyUserDataTypes, LegacyDataBlocks }
                .Any(f => f.Equals(firstSegment, StringComparison.OrdinalIgnoreCase));
    }

    public enum ItemStatus
    {
        /// <summary>Valid header, known kind, placement consistent - importable.</summary>
        Ready,
        /// <summary>Recognized by legacy markers only (format tag, $ template directive, % key row, XML root), header missing - NOT imported (legacy acceptance retired 2026-10-09).</summary>
        Legacy,
        /// <summary>Classified by extension / location only, header missing - NOT imported.</summary>
        NeedsHeader,
        /// <summary>Header present but invalid, or contradicting the file's location - not imported.</summary>
        Invalid,
        /// <summary>Valid header, but its run differs from the workspace's run: a leftover of an older generation - not imported.</summary>
        Stale,
        /// <summary>Nothing recognizable - not imported.</summary>
        Unclassified,
        /// <summary>Sidecars, workspace config, temp files, documentation - listed, never imported.</summary>
        Ignored
    }

    /// <summary>One file of the workspace: where it is, what it is, how it was classified.</summary>
    public sealed class WorkspaceItem
    {
        public string Path { get; set; }
        /// <summary>Relative to the workspace root, '/' separated.</summary>
        public string RelativePath { get; set; }
        /// <summary>The PLC folder the file sits under; null = project level or legacy layout (the project's single PLC).</summary>
        public string Plc { get; set; }
        /// <summary>The TIA tree folder: "Program blocks", "PLC tags", "PLC data types", "Devices &amp; networks"; "" when undetermined.</summary>
        public string Category { get; set; } = string.Empty;
        /// <summary>Block group path below the category ('/' separated); "" = category root.</summary>
        public string GroupPath { get; set; } = string.Empty;
        /// <summary>True when placed through the legacy BuilderData folder names.</summary>
        public bool LegacyPlacement { get; set; }
        /// <summary>True when the folder path gives no usable TIA target (root file, directly under a PLC, unknown TIA folder).</summary>
        public bool Misplaced { get; set; }
        public InputKind Kind { get; set; } = InputKind.Unknown;
        public InputKindInfo KindInfo => InputKindInfo.For(Kind);
        public OpennHeader Header { get; set; }
        public ItemStatus Status { get; set; } = ItemStatus.Unclassified;
        public IList<string> Notes { get; } = new List<string>();

        /// <summary>True for the one status the importer accepts: a valid header, consistent placement, current run.</summary>
        public bool Importable => Status == ItemStatus.Ready
                                  && KindInfo != null && KindInfo.Route != ImportRoute.None && KindInfo.Route != ImportRoute.Template;

        /// <summary>"PLC / Category/Group" for display.</summary>
        public string Placement
        {
            get
            {
                if (Kind == InputKind.Unknown && Status == ItemStatus.Ignored) return "-";
                string owner = Plc ??
                    (Category == WorkspaceLayout.HardwareFolder || Category == WorkspaceLayout.TemplatesFolder ? "<workspace>" :
                     KindInfo != null && KindInfo.Area == InputArea.Hardware ? "<project>" : "<default PLC>");
                return owner + (Category.Length > 0 ? " / " + Category : string.Empty) + (GroupPath.Length > 0 ? "/" + GroupPath : string.Empty);
            }
        }

        public override string ToString() =>
            "[" + Status + "] " + (KindInfo != null ? KindInfo.Id : "?") + "  " + RelativePath;
    }

    /// <summary>
    /// Scans a workspace folder and classifies every file: header first (the kind it declares),
    /// legacy markers and extension second, placement from the folder path, consistency between
    /// the two. Siemens-free: runs without TIA, from the UI or a script.
    /// </summary>
    public sealed class WorkspaceCatalog
    {
        public string Root { get; private set; }
        public bool Exists { get; private set; }
        /// <summary>True when any file was placed through the legacy folder names.</summary>
        public bool LegacyLayout { get; private set; }
        /// <summary>The .openn\workspace.openn.config header; null when absent.</summary>
        public OpennHeader Config { get; private set; }
        public IList<WorkspaceItem> Items { get; } = new List<WorkspaceItem>();

        private static readonly string[] TempNames = { "desktop.ini", "thumbs.db" };

        public static WorkspaceCatalog Scan(string root)
        {
            var catalog = new WorkspaceCatalog { Root = System.IO.Path.GetFullPath(root).TrimEnd('\\', '/') };
            if (!Directory.Exists(catalog.Root)) return catalog;
            catalog.Exists = true;

            string configPath = System.IO.Path.Combine(catalog.Root, WorkspaceLayout.ConfigFolder, WorkspaceLayout.ConfigFile);
            if (File.Exists(configPath))
                catalog.Config = OpennHeader.FromDirectiveLines(OpennHeader.ReadDirectiveLines(configPath, HeaderSyntax.Csv), OpennHeader.WorkspaceRequiredKeys);

            IEnumerable<string> files = Directory.GetFiles(catalog.Root, "*", SearchOption.AllDirectories)
                .Select(f => new { Full = f, Rel = f.Substring(catalog.Root.Length).TrimStart('\\', '/').Replace('\\', '/') })
                .OrderBy(f => f.Rel, StringComparer.OrdinalIgnoreCase)
                .Select(f => f.Full);

            foreach (string file in files)
            {
                var item = new WorkspaceItem
                {
                    Path = file,
                    RelativePath = file.Substring(catalog.Root.Length).TrimStart('\\', '/').Replace('\\', '/')
                };
                catalog.Items.Add(item);

                string[] segments = item.RelativePath.Split('/');
                string name = segments[segments.Length - 1];
                string ext = (System.IO.Path.GetExtension(name) ?? string.Empty).ToLowerInvariant();

                if (IsIgnored(segments, name, ext, item)) { item.Status = ItemStatus.Ignored; continue; }

                Place(item, segments);
                if (item.LegacyPlacement) catalog.LegacyLayout = true;

                item.Header = OpennHeader.Read(file);
                Classify(item, name, ext);
                CheckConsistency(item);
                CheckStale(catalog, item);
                if (item.Misplaced && item.Importable) item.Status = ItemStatus.Invalid; //no usable TIA target (the Place note says why)
            }
            return catalog;
        }

        /// <summary>
        /// A Ready item whose header "run" differs from the workspace config's "run" is a leftover
        /// of an earlier generation (the producer did not sweep it) - flagged, not imported.
        /// </summary>
        private static void CheckStale(WorkspaceCatalog catalog, WorkspaceItem item)
        {
            if (item.Status != ItemStatus.Ready || catalog.Config == null) return;
            string workspaceRun = catalog.Config.Run, fileRun = item.Header.Run;
            if (string.IsNullOrEmpty(workspaceRun) || string.IsNullOrEmpty(fileRun)) return;
            if (workspaceRun.Equals(fileRun, StringComparison.OrdinalIgnoreCase)) return;
            item.Status = ItemStatus.Stale;
            item.Notes.Add("run '" + fileRun + "' differs from the workspace run '" + workspaceRun + "' - leftover of an older generation");
        }

        /// <summary>Importable items in import order: kind rank, then PLC, then path (00_, 01_, ... prefixes keep working).</summary>
        public IEnumerable<WorkspaceItem> InImportOrder() => OrderForImport(Items.Where(i => i.Importable));

        /// <summary>
        /// Any set of items (e.g. a selection) in import order - the same keys as InImportOrder: kind rank
        /// (unknown kinds last), then PLC, then path.
        /// </summary>
        public static IEnumerable<WorkspaceItem> OrderForImport(IEnumerable<WorkspaceItem> items) =>
            (items ?? Enumerable.Empty<WorkspaceItem>())
                 .OrderBy(i => i.KindInfo != null ? i.KindInfo.ImportOrder : int.MaxValue)
                 .ThenBy(i => i.Plc ?? string.Empty, StringComparer.OrdinalIgnoreCase)
                 .ThenBy(i => i.RelativePath, StringComparer.OrdinalIgnoreCase);

        /// <summary>Human-readable report of the scan, one line per entry (for the log).</summary>
        public IEnumerable<string> Summary()
        {
            yield return "Workspace scan: " + Root;
            if (!Exists) { yield return "  folder not found"; yield break; }
            yield return "  layout: " + (LegacyLayout ? "legacy BuilderData folders (HardwareConfiguration, SoftwareBlocks, PlcTags, ...) - NOT importable: regenerate with Pipeline5 5.0+ (VCI shape)"
                                                        : "VCI shape (<PLC>/Program blocks | PLC tags | PLC data types + Devices & networks)");
            yield return "  workspace config: " + (Config == null ? "missing (" + WorkspaceLayout.ConfigFolder + "\\" + WorkspaceLayout.ConfigFile + ")"
                : Config.Status + (Config.Contract != null ? ", contract " + Config.Contract : string.Empty) +
                  (Config.Project != null ? ", project " + Config.Project : string.Empty) +
                  (Config.Producer != null ? ", producer " + Config.Producer : string.Empty) +
                  (Config.Run != null ? ", run " + Config.Run : string.Empty) +
                  (Config.Problems.Count > 0 ? " - " + string.Join("; ", Config.Problems) : string.Empty));

            var classified = Items.Where(i => i.Status != ItemStatus.Ignored && i.Kind != InputKind.Unknown).ToList();
            yield return "  " + Items.Count + " file(s): " + classified.Count + " classified, " +
                         Items.Count(i => i.Status == ItemStatus.Unclassified) + " unclassified, " +
                         Items.Count(i => i.Status == ItemStatus.Ignored) + " ignored";

            foreach (var group in classified.GroupBy(i => i.KindInfo).OrderBy(g => g.Key.ImportOrder))
            {
                yield return "  " + group.Key.Id.PadRight(22) + group.Count().ToString().PadLeft(4) + " file(s)" +
                             "   ready " + group.Count(i => i.Status == ItemStatus.Ready) +
                             ", legacy " + group.Count(i => i.Status == ItemStatus.Legacy) +
                             ", needs-header " + group.Count(i => i.Status == ItemStatus.NeedsHeader) +
                             ", invalid " + group.Count(i => i.Status == ItemStatus.Invalid) +
                             ", stale " + group.Count(i => i.Status == ItemStatus.Stale);
            }

            var attention = Items.Where(i => i.Status == ItemStatus.Invalid || i.Status == ItemStatus.Unclassified || i.Status == ItemStatus.Stale).ToList();
            if (attention.Count > 0)
            {
                yield return "  needs attention:";
                foreach (WorkspaceItem i in attention)
                    yield return "    [" + i.Status + "] " + i.RelativePath + (i.Notes.Count > 0 ? " - " + string.Join("; ", i.Notes) : string.Empty);
            }
            var unheadered = Items.Where(i => i.Status == ItemStatus.Legacy || i.Status == ItemStatus.NeedsHeader).ToList();
            if (unheadered.Count > 0)
                yield return "  " + unheadered.Count + " file(s) without a #!openn header (legacy / extension classification) - NOT imported: " +
                             "contract v1 requires the header (legacy acceptance retired 2026-10-09).";
        }

        #region Classification

        private static bool IsIgnored(string[] segments, string name, string ext, WorkspaceItem item)
        {
            if (segments[0].Equals(WorkspaceLayout.ConfigFolder, StringComparison.OrdinalIgnoreCase)) { item.Notes.Add(name.Equals(WorkspaceLayout.ImportSettingsFile, StringComparison.OrdinalIgnoreCase) ? "Openn5 import settings - the files whose Import box is unticked (written by Openn5)" : "workspace config"); return true; }
            if (segments[0].Equals(WorkspaceLayout.VciConfigFolder, StringComparison.OrdinalIgnoreCase)) { item.Notes.Add("TIA VCI workspace config"); return true; }
            if (ext == OpennHeader.SidecarExtension) { item.Notes.Add("header sidecar of " + name.Substring(0, name.Length - ext.Length)); return true; }
            if (name.StartsWith("~$", StringComparison.Ordinal) || TempNames.Contains(name.ToLowerInvariant())) { item.Notes.Add("temporary file"); return true; }
            return false;
        }

        /// <summary>PLC / category / group from the folder path (VCI shape, project hardware folder, or legacy folders).</summary>
        private static void Place(WorkspaceItem item, string[] segments)
        {
            if (segments.Length == 1)
            {
                item.Misplaced = true;
                item.Notes.Add("file at the workspace root - expected under Devices & networks, Templates or a PLC folder");
                return;
            }

            string first = segments[0];
            if (first.Equals(WorkspaceLayout.HardwareFolder, StringComparison.OrdinalIgnoreCase) ||
                first.Equals(WorkspaceLayout.TemplatesFolder, StringComparison.OrdinalIgnoreCase))
            {
                item.Category = first.Equals(WorkspaceLayout.HardwareFolder, StringComparison.OrdinalIgnoreCase) ? WorkspaceLayout.HardwareFolder : WorkspaceLayout.TemplatesFolder;
                item.GroupPath = Join(segments, 1, segments.Length - 1);
                return;
            }

            if (WorkspaceLayout.IsLegacyRoot(first))
            {
                item.LegacyPlacement = true;
                item.Misplaced = true;
                item.Notes.Add("legacy BuilderData folder '" + first + "' - Openn5 reads only the VCI shape (<PLC>/Program blocks | PLC tags | PLC data types, Devices & networks, Templates): regenerate the workspace with Pipeline5 5.0+");
                if (first.Equals(WorkspaceLayout.LegacyHardware, StringComparison.OrdinalIgnoreCase)) item.Category = WorkspaceLayout.HardwareFolder;
                else if (first.Equals(WorkspaceLayout.LegacyPlcTags, StringComparison.OrdinalIgnoreCase)) item.Category = WorkspaceLayout.PlcTags;
                else if (first.Equals(WorkspaceLayout.LegacyUserDataTypes, StringComparison.OrdinalIgnoreCase)) item.Category = WorkspaceLayout.PlcDataTypes;
                else item.Category = WorkspaceLayout.ProgramBlocks; //SoftwareBlocks\CreationInfo|ImportReady, DataBlocks
                int groupStart = first.Equals(WorkspaceLayout.LegacySoftwareBlocks, StringComparison.OrdinalIgnoreCase) ? 2 : 1;
                item.GroupPath = Join(segments, groupStart, segments.Length - 1);
                return;
            }

            item.Plc = first;
            if (segments.Length == 2)
            {
                item.Misplaced = true;
                item.Notes.Add("file directly under the PLC folder - expected a TIA folder (" + string.Join(", ", WorkspaceLayout.VciFolders.Take(3)) + ")");
                return;
            }
            item.Category = segments[1];
            if (!WorkspaceLayout.IsVciFolder(item.Category))
            {
                item.Misplaced = true;
                item.Notes.Add("'" + item.Category + "' is not a TIA folder name (" + string.Join(", ", WorkspaceLayout.VciFolders) + ")");
            }
            item.GroupPath = Join(segments, 2, segments.Length - 1);
        }

        private static string Join(string[] segments, int start, int endExclusive) =>
            start >= endExclusive ? string.Empty : string.Join("/", segments, start, endExclusive - start);

        private static void Classify(WorkspaceItem item, string name, string ext)
        {
            OpennHeader h = item.Header;
            foreach (string remark in h.Remarks) item.Notes.Add(remark);

            if (h.Status == HeaderStatus.Ok)
            {
                item.Kind = h.KindInfo.Kind;
                item.Status = item.KindInfo.Route == ImportRoute.None ? ItemStatus.Ignored : ItemStatus.Ready;
                if (!item.KindInfo.AcceptsExtension(ext))
                    item.Notes.Add("extension '" + ext + "' is unusual for " + item.KindInfo.Id + " (expected " + string.Join(" ", item.KindInfo.Extensions) + ")");
                return;
            }

            bool byMarker;
            InputKind sniffed = Sniff(item.Path, name, ext, out byMarker);

            if (h.Status == HeaderStatus.Invalid)
            {
                item.Kind = h.KindInfo != null ? h.KindInfo.Kind : sniffed;
                item.Status = ItemStatus.Invalid;
                foreach (string problem in h.Problems) item.Notes.Add(problem);
                return;
            }

            item.Kind = sniffed;
            if (sniffed == InputKind.Unknown)
            {
                item.Status = ItemStatus.Unclassified;
                item.Notes.Add("no #!openn header and nothing recognizable in name, extension or content");
                return;
            }
            if (item.KindInfo.Route == ImportRoute.None)
            {
                item.Status = ItemStatus.Ignored;
                item.Notes.Add("documentation - not imported");
                return;
            }

            item.Status = (byMarker || h.Status == HeaderStatus.Legacy) ? ItemStatus.Legacy : ItemStatus.NeedsHeader;
            item.Notes.Add((h.Status == HeaderStatus.Legacy
                ? "legacy #!format=" + h.LegacyFormat + " tag only"
                : "no #!openn header (classified by " + (byMarker ? "content" : "extension / location") + " for display)") +
                " - NOT imported: contract v1 requires the #!openn header; regenerate with Pipeline5 5.0+ or add the header");
        }

        /// <summary>Legacy classification: file name, csv markers, XML root object, extension.</summary>
        private static InputKind Sniff(string path, string name, string ext, out bool byMarker)
        {
            byMarker = true;
            switch (ext)
            {
                case ".csv":
                    if (name.Equals("Stations.csv", StringComparison.OrdinalIgnoreCase)) return InputKind.HwStations;
                    if (name.Equals("Modules.csv", StringComparison.OrdinalIgnoreCase)) return InputKind.HwModules;
                    if (name.Equals("DeviceTypesDatabase.csv", StringComparison.OrdinalIgnoreCase)) return InputKind.HwDeviceTypes;
                    return SniffCsv(path);

                case ".xml":
                    return SniffXml(path, name);

                case ".scl": case ".awl": case ".st": case ".udt":
                    byMarker = false;
                    return InputKind.SwSource;

                case ".db":
                    byMarker = false;
                    return name.Contains("!!") ? InputKind.SwBlockTemplate : InputKind.SwSource;

                case ".xlsx":
                    byMarker = false;
                    return name.Equals("PLCTags.xlsx", StringComparison.OrdinalIgnoreCase) ? InputKind.DocPlcTagsWorkbook : InputKind.DocOther;

                case ".xlsm": case ".xls": case ".pdf": case ".docx": case ".md": case ".txt": case ".html": case ".aml": case ".log":
                    byMarker = false;
                    return InputKind.DocOther;

                default:
                    byMarker = false;
                    return InputKind.Unknown;
            }
        }

        /// <summary>A "$ ... template=" directive = block generation; a "%" key row with Name + InstanceOf/FB = instance DBs.</summary>
        private static InputKind SniffCsv(string path)
        {
            try
            {
                int n = 0;
                foreach (string raw in File.ReadLines(path))
                {
                    if (++n > 100) break;
                    string line = raw.Trim();
                    if (line.StartsWith("$", StringComparison.Ordinal) && line.IndexOf("template=", StringComparison.OrdinalIgnoreCase) >= 0)
                        return InputKind.SwBlockGen;
                    if (line.StartsWith("%", StringComparison.Ordinal))
                    {
                        var cells = line.Split(',', ';', '\t').Select(c => c.Trim()).ToList();
                        bool hasName = cells.Any(c => c.Equals("Name", StringComparison.OrdinalIgnoreCase));
                        bool hasFb = cells.Any(c => c.Equals("InstanceOf", StringComparison.OrdinalIgnoreCase) ||
                                                    c.Equals("InstanceOfFB", StringComparison.OrdinalIgnoreCase) ||
                                                    c.Equals("FB", StringComparison.OrdinalIgnoreCase));
                        if (hasName && hasFb) return InputKind.SwInstanceDb;
                    }
                }
            }
            catch { }
            return InputKind.Unknown;
        }

        /// <summary>TEMPLATE-- names / placeholders = template; else the first SW.* element decides.</summary>
        private static InputKind SniffXml(string path, string name)
        {
            if (name.StartsWith("TEMPLATE--", StringComparison.OrdinalIgnoreCase) || name.Contains("!!")) return InputKind.SwBlockTemplate;

            string element = FirstSwObjectElement(path);
            if (element == "SW.Blocks.GlobalDB") return InputKind.SwDataBlock;
            if (element == "SW.Blocks.OB" || element == "SW.Blocks.FB" || element == "SW.Blocks.FC") return InputKind.SwCodeBlock;
            if (element.StartsWith("SW.Types.", StringComparison.Ordinal)) return InputKind.SwUdt;
            if (element == "SW.Tags.PlcTagTable") return InputKind.SwTagTable;
            return InputKind.Unknown;
        }

        /// <summary>The first SW.Blocks.* / SW.Types.* / SW.Tags.* element name of a TIA export xml, or "".</summary>
        public static string FirstSwObjectElement(string path)
        {
            try
            {
                var settings = new XmlReaderSettings { IgnoreComments = true, IgnoreWhitespace = true, DtdProcessing = DtdProcessing.Ignore };
                using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                using (var reader = XmlReader.Create(stream, settings))
                    while (reader.Read())
                        if (reader.NodeType == XmlNodeType.Element &&
                            (reader.Name.StartsWith("SW.Blocks.", StringComparison.Ordinal) ||
                             reader.Name.StartsWith("SW.Types.", StringComparison.Ordinal) ||
                             reader.Name.StartsWith("SW.Tags.", StringComparison.Ordinal)))
                            return reader.Name;
            }
            catch { }
            return string.Empty;
        }

        /// <summary>A Ready item must sit where its kind belongs, and its header's plc/target must match the location.</summary>
        private static void CheckConsistency(WorkspaceItem item)
        {
            if (item.Status != ItemStatus.Ready) return;
            InputKindInfo kind = item.KindInfo;
            if (kind.Route == ImportRoute.Template) return; //templates may sit anywhere (Templates\, beside their csv, Shared)
            OpennHeader h = item.Header;
            var problems = new List<string>();

            if (kind.Area == InputArea.Hardware && item.Plc != null)
                problems.Add(kind.Id + " belongs in '" + WorkspaceLayout.HardwareFolder + "' at the workspace root, not under PLC '" + item.Plc + "'");
            if (kind.Area == InputArea.Software && item.Plc == null && !item.LegacyPlacement)
                problems.Add(kind.Id + " belongs under a PLC folder (<PLC>/" + (kind.VciFolder ?? WorkspaceLayout.ProgramBlocks) + "/...)");
            if (!item.LegacyPlacement && kind.VciFolder != null && item.Category.Length > 0 &&
                !item.Category.Equals(kind.VciFolder, StringComparison.OrdinalIgnoreCase))
                problems.Add(kind.Id + " belongs in '" + kind.VciFolder + "', found in '" + item.Category + "'");

            if (!string.IsNullOrEmpty(h.Plc) && item.Plc != null && !h.Plc.Equals(item.Plc, StringComparison.OrdinalIgnoreCase))
                problems.Add("header plc '" + h.Plc + "' but the file sits under PLC folder '" + item.Plc + "'");
            if (!string.IsNullOrEmpty(h.Target) && !item.LegacyPlacement && item.Category.Length > 0)
            {
                string location = item.Category + (item.GroupPath.Length > 0 ? "/" + item.GroupPath : string.Empty);
                string target = h.Target.Replace('\\', '/').Trim('/');
                if (!target.Equals(location, StringComparison.OrdinalIgnoreCase))
                    problems.Add("header target '" + h.Target + "' but the file's location is '" + location + "'");
            }

            if (problems.Count == 0) return;
            item.Status = ItemStatus.Invalid;
            foreach (string p in problems) item.Notes.Add(p);
        }

        #endregion Classification
    }
}

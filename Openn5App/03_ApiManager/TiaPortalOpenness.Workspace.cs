using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW;
using Siemens.Engineering.SW.Tags;
using Siemens.Engineering.SW.Types;
using Openn._00_Contract;
using Openn._01_Constructor;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._03_ApiManager
{
    /// <summary>What happened to one catalog item in a workspace import run.</summary>
    public enum WorkspaceImportOutcome
    {
        /// <summary>The item's route ran to completion.</summary>
        Imported,
        /// <summary>Nothing to run for the item by itself (reference data, covered by another item's run).</summary>
        NothingToDo,
        /// <summary>Not imported: not importable, blocked by its folder, or skipped by the user (Ignore) after an error.</summary>
        Skipped,
        /// <summary>The route failed, or the user chose Abort on its error.</summary>
        Failed,
        /// <summary>Not run (or stopped half-way): the operation was cancelled or aborted.</summary>
        Cancelled
    }

    /// <summary>One line of the workspace import report (the Workspace tab shows it in the "Last result" column).</summary>
    public sealed class WorkspaceImportResult
    {
        public WorkspaceItem Item { get; }
        public WorkspaceImportOutcome Outcome { get; }
        public string Message { get; }

        public WorkspaceImportResult(WorkspaceItem item, WorkspaceImportOutcome outcome, string message)
        {
            Item = item;
            Outcome = outcome;
            Message = message ?? string.Empty;
        }
    }

    /// <summary>
    /// Catalog-driven import - the engine behind the Workspace tab. Takes catalog items (a selection, or
    /// everything importable), sorts them into import order (kind rank, PLC, path - WorkspaceCatalog.OrderForImport)
    /// and dispatches each one through its kind's existing route:
    ///
    ///   hw/stations, hw/modules    HardwareGeneration  -> HardwareConfigLoader.LoadAll(folder) + CreateDevices (once per folder;
    ///                                                     the pair is generated in one run, the controller mode is the caller's)
    ///   hw/device-types            Reference           -> nothing by itself (the loader reads it beside Stations/Modules)
    ///   sw/udt                     ImportTypeXml       -> TypeGroup[.group].Types.Import (Override)
    ///   sw/tag-table               ImportTagTableXml   -> TagTableGroup[.group].TagTables.Import (Override)
    ///   sw/data-block, code-block  ImportBlockXml      -> BlockGroup[.group].Blocks.Import (Override)
    ///   sw/instance-db             CreateInstanceDbs   -> CreateInstanceDbsCore (its own per-DB Retry/Abort/Ignore)
    ///   sw/block-gen               GenerateThenImport  -> BlockXmlGenerator.Generate + Blocks.Import
    ///   sw/source                  GenerateFromSource  -> ExternalSources.CreateFromFile + GenerateBlocksFromSource (root)
    ///
    /// The TIA group comes from the item's GroupPath (find-or-create, like the import queue), the PLC from its PLC folder
    /// (null = the project's single PLC). Items that are not importable (Invalid / Stale / Unclassified / Ignored) are
    /// reported and skipped - never imported. Routes without internal error handling get the Retry/Abort/Ignore prompt
    /// per file; cancellation is checked between items (and inside the routes, as before). Nothing is saved.
    /// </summary>
    public partial class TiaPortalOpenness
    {
        private const string WorkspaceImportContext = "Workspace import";

        /// <summary>
        /// Imports the given catalog items in import order and returns one result per item (in that order).
        /// createNewIoControllers is the hardware generation's controller mode (false = use the existing controllers).
        /// </summary>
        public IList<WorkspaceImportResult> ImportWorkspaceItems(WorkspaceCatalog catalog, IList<WorkspaceItem> items, bool createNewIoControllers, bool wirePorts = false)
        {
            var results = new List<WorkspaceImportResult>();
            if (catalog == null || items == null || items.Count == 0)
            {
                Log("Workspace import: nothing selected");
                return results;
            }
            if (project == null)
            {
                Log("Can't import: No Tia Project Attached");
                return results;
            }

            List<WorkspaceItem> ordered = WorkspaceCatalog.OrderForImport(items).ToList();
            Log("=== Workspace import: " + ordered.Count + " item(s), " + ordered.Count(i => i.Importable) + " importable, from " + catalog.Root +
                " - I/O controllers: " + (createNewIoControllers ? "create new" : "use existing") + " ===");

            var plcCache = new Dictionary<string, Tuple<PlcSoftware, string>>(StringComparer.OrdinalIgnoreCase);
            var hardwareRuns = new Dictionary<string, WorkspaceImportResult>(StringComparer.OrdinalIgnoreCase);
            bool stopped = false;

            foreach (WorkspaceItem item in ordered)
            {
                if (!stopped && Cancelled())
                {
                    Log("Workspace import CANCELLED before " + item.RelativePath + " (project not saved)");
                    stopped = true;
                }
                if (stopped)
                {
                    results.Add(new WorkspaceImportResult(item, WorkspaceImportOutcome.Cancelled, "not run - the import stopped before this item"));
                    continue;
                }

                bool abort;
                WorkspaceImportResult result;
                try
                {
                    result = ImportWorkspaceItem(catalog, item, createNewIoControllers, wirePorts, plcCache, hardwareRuns, out abort);
                }
                catch (Exception e)
                {
                    //a route that escaped its own handling: report it and carry on with the next item (nothing is saved)
                    Log("ERROR importing " + item.RelativePath + " \n" + e.Message);
                    result = new WorkspaceImportResult(item, WorkspaceImportOutcome.Failed, e.Message);
                    abort = false;
                }
                results.Add(result);
                if (abort) stopped = true;
            }

            Log("=== Workspace import done: " + results.Count(r => r.Outcome == WorkspaceImportOutcome.Imported) + " imported, " +
                results.Count(r => r.Outcome == WorkspaceImportOutcome.NothingToDo) + " nothing to do, " +
                results.Count(r => r.Outcome == WorkspaceImportOutcome.Skipped) + " skipped, " +
                results.Count(r => r.Outcome == WorkspaceImportOutcome.Failed) + " failed, " +
                results.Count(r => r.Outcome == WorkspaceImportOutcome.Cancelled) + " cancelled / not run (project not saved) ===");
            return results;
        }

        private WorkspaceImportResult ImportWorkspaceItem(WorkspaceCatalog catalog, WorkspaceItem item, bool createNewIoControllers, bool wirePorts,
            Dictionary<string, Tuple<PlcSoftware, string>> plcCache, Dictionary<string, WorkspaceImportResult> hardwareRuns, out bool abort)
        {
            abort = false;

            if (!item.Importable)
            {
                string why = "[" + item.Status + "] " + (item.KindInfo != null ? item.KindInfo.Id : "unknown kind") +
                             (item.Notes.Count > 0 ? " - " + string.Join("; ", item.Notes) : string.Empty);
                Log("SKIPPED " + item.RelativePath + " - not importable " + why);
                return new WorkspaceImportResult(item, WorkspaceImportOutcome.Skipped, "not importable " + why);
            }

            InputKindInfo kind = item.KindInfo;
            switch (kind.Route)
            {
                case ImportRoute.Reference:
                    Log(item.RelativePath + ": reference data (" + kind.Id + ") - read by the hardware generation of its folder, nothing to import by itself");
                    return new WorkspaceImportResult(item, WorkspaceImportOutcome.NothingToDo, "reference data - read by the hardware generation of its folder");

                case ImportRoute.HardwareGeneration:
                    return ImportWorkspaceHardware(catalog, item, createNewIoControllers, wirePorts, hardwareRuns, out abort);

                default:
                    return ImportWorkspaceSoftware(item, plcCache, out abort);
            }
        }

        /// <summary>
        /// Hardware generation for the item's folder - once per folder: Stations.csv and Modules.csv are one
        /// configuration, so the second file of the pair reports the outcome of the run the first one started.
        /// The loader reads the whole folder, so every hardware file in it must be importable.
        /// </summary>
        private WorkspaceImportResult ImportWorkspaceHardware(WorkspaceCatalog catalog, WorkspaceItem item, bool createNewIoControllers, bool wirePorts,
            Dictionary<string, WorkspaceImportResult> hardwareRuns, out bool abort)
        {
            abort = false;
            string folder = Path.GetDirectoryName(item.Path) ?? string.Empty;

            WorkspaceImportResult earlier;
            if (hardwareRuns.TryGetValue(folder, out earlier))
            {
                Log(item.RelativePath + ": covered by the hardware generation run of its folder (" + earlier.Item.RelativePath + " - " + earlier.Outcome + ")");
                return new WorkspaceImportResult(item, earlier.Outcome, "same generation run as " + Path.GetFileName(earlier.Item.Path) + ": " + earlier.Message);
            }

            List<WorkspaceItem> folderItems = catalog.Items
                .Where(i => i.KindInfo != null && i.KindInfo.Area == InputArea.Hardware && i.Status != ItemStatus.Ignored &&
                            (Path.GetDirectoryName(i.Path) ?? string.Empty).Equals(folder, StringComparison.OrdinalIgnoreCase))
                .ToList();

            string problem = null;
            List<WorkspaceItem> blockers = folderItems.Where(i => !i.Importable).ToList();
            if (blockers.Count > 0)
                problem = "the folder holds non-importable hardware file(s): " +
                          string.Join(", ", blockers.Select(b => Path.GetFileName(b.Path) + " [" + b.Status + "]")) + " - fix them first (see their notes)";
            else if (!folderItems.Any(i => i.Kind == InputKind.HwStations && HasFileName(i, HardwareConfigLoader.StationsFileName)) ||
                     !folderItems.Any(i => i.Kind == InputKind.HwModules && HasFileName(i, HardwareConfigLoader.ModulesFileName)))
                problem = "hardware generation needs " + HardwareConfigLoader.StationsFileName + " (hw/stations) and " + HardwareConfigLoader.ModulesFileName +
                          " (hw/modules) side by side in the folder - the loader reads them by name";

            WorkspaceImportResult result;
            if (problem != null)
            {
                Log("SKIPPED hardware generation of " + folder + " - " + problem);
                result = new WorkspaceImportResult(item, WorkspaceImportOutcome.Skipped, problem);
            }
            else
            {
                Log("--- Hardware generation from " + folder + " (" + (createNewIoControllers ? "create new" : "use existing") + " I/O controllers) ---");
                try
                {
                    if (!HardwareConfigLoader.LoadAll(folder))
                        result = new WorkspaceImportResult(item, WorkspaceImportOutcome.Failed, "hardware configuration did not load (see the log) - nothing generated");
                    else if (CreateDevices(createNewIoControllers, wirePorts))
                        result = new WorkspaceImportResult(item, WorkspaceImportOutcome.Imported, "hardware generation run completed (stations already in the project were skipped - see the log)");
                    else if (Cancelled())
                        result = new WorkspaceImportResult(item, WorkspaceImportOutcome.Cancelled, "hardware generation cancelled");
                    else
                        result = new WorkspaceImportResult(item, WorkspaceImportOutcome.Failed, "hardware generation stopped early (see the log)");
                }
                catch (Exception e)
                {
                    Log("ERROR in the hardware generation from " + folder + " \n" + e.Message);
                    result = new WorkspaceImportResult(item, WorkspaceImportOutcome.Failed, e.Message);
                }
                if (Cancelled()) abort = true;
            }

            hardwareRuns[folder] = result;
            return result;
        }

        private static bool HasFileName(WorkspaceItem item, string fileName) =>
            Path.GetFileName(item.Path).Equals(fileName, StringComparison.OrdinalIgnoreCase);

        /// <summary>One software item into the PLC its folder names (or the single PLC), with the per-file Retry/Abort/Ignore prompt.</summary>
        private WorkspaceImportResult ImportWorkspaceSoftware(WorkspaceItem item, Dictionary<string, Tuple<PlcSoftware, string>> plcCache, out bool abort)
        {
            abort = false;
            InputKindInfo kind = item.KindInfo;

            string plcError;
            PlcSoftware sw = ResolvePlcSoftware(item.Plc, plcCache, out plcError);
            if (sw == null)
            {
                Log("SKIPPED " + item.RelativePath + " - " + plcError);
                return new WorkspaceImportResult(item, WorkspaceImportOutcome.Failed, plcError);
            }

            string label = item.RelativePath + (item.Plc != null ? " [" + item.Plc + "]" : string.Empty) +
                           (item.GroupPath.Length > 0 ? " -> " + item.Category + "/" + item.GroupPath : string.Empty);

            if (kind.Route == ImportRoute.CreateInstanceDbs)
            {
                //has its own per-DB Retry/Abort/Ignore prompt - no second prompt here
                switch (CreateInstanceDbsCore(item.Path, item.GroupPath, sw))
                {
                    case BatchOutcome.Completed:
                        return new WorkspaceImportResult(item, WorkspaceImportOutcome.Imported, "instance DBs created (count in the log)");
                    case BatchOutcome.Failed:
                        return new WorkspaceImportResult(item, WorkspaceImportOutcome.Failed, "instance DB csv has errors (see the log) - nothing created");
                    default:
                        abort = true;
                        return new WorkspaceImportResult(item, WorkspaceImportOutcome.Cancelled, "instance DB creation aborted / cancelled");
                }
            }

            while (true) //repeated while the user chooses Retry
            {
                string error = RunSoftwareRoute(sw, item, kind);
                if (error == null)
                {
                    Log("Imported " + kind.Id + ": " + label);
                    return new WorkspaceImportResult(item, WorkspaceImportOutcome.Imported, RouteDoneMessage(kind.Route));
                }

                System.Windows.Forms.DialogResult decision = AskFileDecision(item.RelativePath, error, WorkspaceImportContext);
                if (decision == System.Windows.Forms.DialogResult.Retry)
                {
                    Log("Retrying " + item.RelativePath);
                    continue;
                }
                if (decision == System.Windows.Forms.DialogResult.Ignore)
                {
                    Log("SKIPPED " + label + " - " + error);
                    return new WorkspaceImportResult(item, WorkspaceImportOutcome.Skipped, "skipped by the user after an error: " + error);
                }
                Log("Workspace import ABORTED by the user at " + item.RelativePath + " (project not saved) \n" + error);
                abort = true;
                return new WorkspaceImportResult(item, WorkspaceImportOutcome.Failed, "aborted by the user: " + error);
            }
        }

        /// <summary>Runs one software item through its kind's route into the given PLC. Returns null on success, else the error text.</summary>
        private string RunSoftwareRoute(PlcSoftware sw, WorkspaceItem item, InputKindInfo kind)
        {
            try
            {
                switch (kind.Route)
                {
                    case ImportRoute.ImportTypeXml:
                        GetOrCreateTypeGroup(sw.TypeGroup, item.GroupPath).Types.Import(new FileInfo(item.Path), ImportOptions.Override);
                        return null;

                    case ImportRoute.ImportTagTableXml:
                        GetOrCreateTagTableGroup(sw.TagTableGroup, item.GroupPath).TagTables.Import(new FileInfo(item.Path), ImportOptions.Override);
                        return null;

                    case ImportRoute.ImportBlockXml:
                        ImportXmlInto(GetOrCreateBlockGroup(sw.BlockGroup, item.GroupPath), item.Path);
                        return null;

                    case ImportRoute.GenerateThenImport:
                        string versionTag = "V" + OpennessSetup.SelectedInstallation.PortalVersion.Major;
                        string xml = Openn._02_Converter.BlockXmlGenerator.Generate(item.Path, versionTag, Path.Combine(appBaseDir, "GeneratedBlocks"), null);
                        if (xml == null) return "block generation failed (see the log)";
                        ImportXmlInto(GetOrCreateBlockGroup(sw.BlockGroup, item.GroupPath), xml);
                        return null;

                    case ImportRoute.GenerateFromSource:
                        if (item.GroupPath.Length > 0)
                            Log("NOTE: " + item.RelativePath + " - blocks generated from a source land in the Program blocks root (TIA limitation); group '" +
                                item.GroupPath + "' is not applied");
                        GenerateFromExternalSource(sw, item.Path);
                        return null;

                    default:
                        return "no import route for kind " + kind.Id + " (" + kind.Route + ")";
                }
            }
            catch (Exception e)
            {
                return e.Message;
            }
        }

        private static string RouteDoneMessage(ImportRoute route)
        {
            switch (route)
            {
                case ImportRoute.ImportTypeXml: return "UDT imported (Override)";
                case ImportRoute.ImportTagTableXml: return "tag table imported (Override)";
                case ImportRoute.ImportBlockXml: return "block imported (Override)";
                case ImportRoute.GenerateThenImport: return "block generated from its template and imported (Override)";
                case ImportRoute.GenerateFromSource: return "external source created, blocks generated (Program blocks root)";
                default: return route.ToString();
            }
        }

        #region PLC and group resolution

        /// <summary>
        /// The PLC software an item targets: without a PLC folder (legacy layout, project level) the project's single
        /// PLC (GetPlcSoftware); with one, the device - or CPU device item - named like the folder, anywhere in the
        /// project. Resolved once per PLC per run; a PLC that is not in the project fails every item under it (nothing
        /// silent, no fallback to another PLC).
        /// </summary>
        private PlcSoftware ResolvePlcSoftware(string plcName, Dictionary<string, Tuple<PlcSoftware, string>> cache, out string error)
        {
            string key = plcName ?? string.Empty;
            Tuple<PlcSoftware, string> cached;
            if (!cache.TryGetValue(key, out cached))
            {
                PlcSoftware sw;
                string problem = null;
                if (plcName == null)
                {
                    sw = GetPlcSoftware(project);
                    if (sw == null) problem = "no Plc Software found in the project (the file has no PLC folder, so the project's single PLC is its target)";
                }
                else
                {
                    sw = FindPlcSoftware(plcName);
                    if (sw == null) problem = "PLC '" + plcName + "' (the file's PLC folder) is not in the project - generate the hardware first, or name the folder after the PLC station";
                }
                cached = Tuple.Create(sw, problem);
                cache[key] = cached;
            }
            error = cached.Item2;
            return cached.Item1;
        }

        /// <summary>The PLC software of the device (or of the CPU device item) named plcName, anywhere in the project (device groups included).</summary>
        private PlcSoftware FindPlcSoftware(string plcName)
        {
            foreach (Device device in CollectAllDevices())
            {
                bool deviceMatches = device.Name.Equals(plcName, StringComparison.OrdinalIgnoreCase);
                PlcSoftware sw = FindPlcSoftware(device.DeviceItems, plcName, deviceMatches);
                if (sw != null) return sw;
            }
            return null;
        }

        private static PlcSoftware FindPlcSoftware(DeviceItemComposition items, string plcName, bool deviceMatches)
        {
            foreach (DeviceItem item in items)
            {
                SoftwareContainer container = item.GetService<SoftwareContainer>();
                if (container != null)
                {
                    var sw = container.Software as PlcSoftware;
                    if (sw != null && (deviceMatches || item.Name.Equals(plcName, StringComparison.OrdinalIgnoreCase))) return sw;
                }
                PlcSoftware nested = FindPlcSoftware(item.DeviceItems, plcName, deviceMatches);
                if (nested != null) return nested;
            }
            return null;
        }

        /// <summary>Finds or creates the nested type-group path under the PLC's data types ("A/B"); empty = the root group.</summary>
        private static PlcTypeGroup GetOrCreateTypeGroup(PlcTypeGroup root, string folderPath)
        {
            PlcTypeGroup current = root;
            foreach (string name in GroupPathParts(folderPath))
                current = current.Groups.Find(name) ?? current.Groups.Create(name);
            return current;
        }

        /// <summary>Finds or creates the nested tag-table-group path under the PLC's tags ("A/B"); empty = the root group.</summary>
        private static PlcTagTableGroup GetOrCreateTagTableGroup(PlcTagTableGroup root, string folderPath)
        {
            PlcTagTableGroup current = root;
            foreach (string name in GroupPathParts(folderPath))
                current = current.Groups.Find(name) ?? current.Groups.Create(name);
            return current;
        }

        private static IEnumerable<string> GroupPathParts(string folderPath) =>
            (folderPath ?? string.Empty).Split('/', '\\').Select(p => p.Trim()).Where(p => p.Length > 0);

        #endregion PLC and group resolution
    }
}

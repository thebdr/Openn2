using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW;
using Siemens.Engineering.SW.Blocks;
using Siemens.Engineering.SW.ExternalSources;
using Siemens.Engineering.SW.Types;
using Openn._10_StandardFunctions;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Program block operations: listing the whole block tree (used by the block
    /// search window), exporting a block to xml and importing an xml block file.
    /// </summary>
    public partial class TiaPortalOpenness
    {
        /// <summary>
        /// Exports the named block (or data type) into the Shared export sink
        /// (AppPaths.ExportedBlocksDir) in
        /// the requested format: "xml" works for everything (Openness Export); the
        /// source formats only apply where the object's language matches —
        /// "scl" (SCL blocks), "awl" (STL blocks), "db" (data blocks), "udt" (UDTs) —
        /// and are produced via the external-source generator. A non-applicable
        /// format is skipped with a reason, not an error. The object is searched in
        /// the whole block tree and the type tree, subfolders included.
        /// "auto" resolves to each object's own native source language (or is skipped
        /// when the object has no textual source form, e.g. LAD/FBD).
        /// </summary>
        public void ExportBlock(string blockName, string format = "xml")
        {
            if (project == null)
            {
                Log("Can't export: No Tia Project Attached");
                return;
            }
            PlcSoftware plcSoftware = GetPlcSoftware(project);
            if (plcSoftware == null)
            {
                Log("Can't export: no Plc Software found in the project");
                return;
            }

            //a block or a data type can carry the same name space; blocks are tried first
            PlcBlock plcBlock = FindBlock(plcSoftware.BlockGroup, blockName);
            PlcType plcType = plcBlock == null ? FindType(plcSoftware.TypeGroup.Types, plcSoftware.TypeGroup.Groups, blockName) : null;
            if (plcBlock == null && plcType == null)
            {
                Log("ERROR Exporting \nBlock or type not found: " + blockName);
                return;
            }

            string name = plcBlock != null ? plcBlock.Name : plcType.Name;
            string extension = (format ?? "xml").Trim().ToLowerInvariant();

            if (extension == "auto")
            {
                extension = NativeSourceExtension(plcBlock, plcType);
                if (extension == null)
                {
                    string lang = plcBlock != null ? plcBlock.ProgrammingLanguage.ToString() : "UDT";
                    Log("Export skipped: " + name + " - " + lang + " has no textual source form, use XML");
                    return;
                }
            }

            try
            {
                var exportFile = new FileInfo(Path.Combine(AppPaths.ExportedBlocksDir, name + "." + extension));
                exportFile.Directory.Create(); //no-op when it already exists

                if (extension == "xml")
                {
                    if (plcBlock != null) plcBlock.Export(exportFile, ExportOptions.WithDefaults);
                    else plcType.Export(exportFile, ExportOptions.WithDefaults);
                    Log("Exported " + Describe(plcBlock, plcType) + " as XML: " + exportFile.FullName);
                    return;
                }

                string reason;
                if (!IsSourceFormatApplicable(plcBlock, plcType, extension, out reason))
                {
                    Log("Export skipped: " + name + " - " + reason);
                    return;
                }

                //PlcBlock and PlcType both implement IGenerateSource
                var source = (IGenerateSource)plcBlock ?? plcType;
                plcSoftware.ExternalSourceGroup.GenerateSource(new[] { source }, exportFile, GenerateOptions.None);
                Log("Exported " + Describe(plcBlock, plcType) + " as " + extension.ToUpperInvariant() + ": " + exportFile.FullName);
            }
            catch (Exception e)
            {
                Log("ERROR Exporting " + name + " as " + extension + " \n" + e.Message);
            }
        }

        /// <summary>
        /// Whether a source export format matches the object's native language.
        /// Source generation produces the block's own language only - it cannot, for
        /// example, turn a LAD block into SCL - so the format must match.
        /// </summary>
        private static bool IsSourceFormatApplicable(PlcBlock block, PlcType type, string extension, out string reason)
        {
            reason = null;
            string actual = block != null ? block.ProgrammingLanguage.ToString() : "UDT";

            switch (extension)
            {
                case "udt":
                    if (type != null) return true;
                    reason = "UDT export only applies to PLC data types (this is " + actual + ")";
                    return false;
                case "scl":
                    if (block != null && block.ProgrammingLanguage == ProgrammingLanguage.SCL) return true;
                    reason = "SCL source only applies to SCL blocks (this is " + actual + ") - use XML";
                    return false;
                case "awl":
                    if (block != null && (block.ProgrammingLanguage == ProgrammingLanguage.STL || block.ProgrammingLanguage == ProgrammingLanguage.F_STL)) return true;
                    reason = "AWL/STL source only applies to STL blocks (this is " + actual + ") - use XML";
                    return false;
                case "db":
                    if (block is DataBlock) return true;
                    reason = "DB source only applies to data blocks (this is " + actual + ") - use XML";
                    return false;
                default:
                    reason = "unknown format \"" + extension + "\" (use xml, scl, awl, db or udt)";
                    return false;
            }
        }

        /// <summary>
        /// The object's native source extension, or null when it has no textual
        /// source form (LAD/FBD/GRAPH and the like are XML-only). Data blocks are
        /// matched by type first, so instance/global/array DBs all map to "db".
        /// </summary>
        private static string NativeSourceExtension(PlcBlock block, PlcType type)
        {
            if (type != null) return "udt";
            if (block is DataBlock) return "db";
            switch (block.ProgrammingLanguage)
            {
                case ProgrammingLanguage.SCL: return "scl";
                case ProgrammingLanguage.STL:
                case ProgrammingLanguage.F_STL: return "awl";
                default: return null;
            }
        }

        private static string Describe(PlcBlock block, PlcType type) =>
            block != null ? "block " + block.Name + " (" + block.ProgrammingLanguage + ")" : "data type " + type.Name;

        /// <summary>
        /// Creates many single-instance DBs in one pass directly via the Openness
        /// CreateInstanceDB API (no template/XML, so none of the XML import pitfalls -
        /// IDs, namespaces, version, culture - apply). Reads the instance-DB list csv
        /// (InstanceDbListParser), resolves/creates the target folders, and creates
        /// each DB. Cancellable between DBs; a name conflict pops Retry/Abort/Ignore
        /// like the hardware generator. Numbers are auto-assigned when the csv leaves
        /// Number empty. Nothing is saved.
        /// </summary>
        public void CreateInstanceDbs(string csvPath)
        {
            CreateInstanceDbsCore(csvPath, "");
        }

        /// <summary>
        /// Shared worker behind the standalone button and the import queue. baseFolder
        /// (the queue's mirrored subfolder; "" standalone) is prepended to each spec's
        /// Folder. Returns Completed, Failed (parse errors - nothing created) or Aborted
        /// (cancel or user Abort) so the queue can stop.
        /// </summary>
        private BatchOutcome CreateInstanceDbsCore(string csvPath, string baseFolder)
        {
            if (project == null)
            {
                Log("Can't create instance DBs: No Tia Project Attached");
                return BatchOutcome.Failed;
            }
            PlcSoftware plcSoftware = GetPlcSoftware(project);
            if (plcSoftware == null)
            {
                Log("Can't create instance DBs: no Plc Software found in the project");
                return BatchOutcome.Failed;
            }

            var parseErrors = new List<string>();
            IList<Openn._02_Converter.InstanceDbSpec> specs = Openn._02_Converter.InstanceDbListParser.Parse(csvPath, parseErrors);
            if (parseErrors.Count > 0)
            {
                foreach (string error in parseErrors)
                    Log("Instance DB error: " + error);
                Log("Instance DB creation ABORTED - nothing created (" + parseErrors.Count + " error(s))");
                return BatchOutcome.Failed;
            }

            int created = 0;
            foreach (Openn._02_Converter.InstanceDbSpec spec in specs)
            {
                if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                {
                    Log("Instance DB creation CANCELLED - " + created + " of " + specs.Count + " created (project not saved)");
                    return BatchOutcome.Aborted;
                }

                string folder = CombineFolder(baseFolder, spec.Folder);
                PlcBlockGroup group = GetOrCreateBlockGroup(plcSoftware.BlockGroup, folder);

                while (true) //repeated while the user chooses Retry
                {
                    try
                    {
                        if (group.Blocks.Find(spec.Name) != null)
                            throw new Exception("a block named \"" + spec.Name + "\" already exists" +
                                (folder.Length > 0 ? " in folder " + folder : " at the root"));

                        group.Blocks.CreateInstanceDB(spec.Name, spec.Number == null, spec.Number ?? 1, spec.InstanceOf);
                        created++;
                        break;
                    }
                    catch (Exception e)
                    {
                        var decision = AskCreateDecision(spec.Name, spec.InstanceOf, e.Message);
                        if (decision == System.Windows.Forms.DialogResult.Retry)
                        {
                            Log("Retrying instance DB " + spec.Name + " (line " + spec.LineNumber + ")");
                            continue;
                        }
                        if (decision == System.Windows.Forms.DialogResult.Ignore)
                        {
                            Log("SKIPPED instance DB " + spec.Name + " (line " + spec.LineNumber + ") \n" + e.Message);
                            break;
                        }
                        Log("Instance DB creation ABORTED by the user at " + spec.Name + " (line " + spec.LineNumber + ") - " +
                            created + " of " + specs.Count + " created \n" + e.Message);
                        return BatchOutcome.Aborted;
                    }
                }
            }

            Log("Instance DB creation Ok: " + created + " of " + specs.Count + " instance DB(s) created (project not saved)");
            return BatchOutcome.Completed;
        }

        /// <summary>Outcome of one batch step: drives the import-queue's continue/stop/prompt decision.</summary>
        private enum BatchOutcome { Completed, Failed, Aborted }

        /// <summary>Joins two block-group path fragments with '/', trimming slashes; either may be empty.</summary>
        private static string CombineFolder(string a, string b)
        {
            a = (a ?? "").Trim().Trim('/', '\\');
            b = (b ?? "").Trim().Trim('/', '\\');
            if (a.Length == 0) return b;
            if (b.Length == 0) return a;
            return a + "/" + b;
        }

        /// <summary>Finds or creates the nested block-group path (e.g. "A/B/C"); empty = the root group.</summary>
        private PlcBlockGroup GetOrCreateBlockGroup(PlcBlockGroup root, string folderPath)
        {
            PlcBlockGroup current = root;
            if (string.IsNullOrWhiteSpace(folderPath)) return current;

            foreach (string part in folderPath.Split('/', '\\'))
            {
                string name = part.Trim();
                if (name.Length == 0) continue;
                current = current.Groups.Find(name) ?? current.Groups.Create(name);
            }
            return current;
        }

        /// <summary>Conflict/error decision popup (UI thread; worker waits): Retry / Abort / Ignore.</summary>
        private static System.Windows.Forms.DialogResult AskCreateDecision(string blockName, string instanceOf, string errorMessage)
        {
            var application = System.Windows.Application.Current;
            if (application == null) return System.Windows.Forms.DialogResult.Abort; //no UI: fail safe

            return application.Dispatcher.Invoke(() =>
                System.Windows.Forms.MessageBox.Show(
                    "Could not create instance DB \"" + blockName + "\" (of FB \"" + instanceOf + "\"):\n\n" +
                    errorMessage + "\n\n" +
                    "Retry  -  try again (e.g. after deleting the existing block in TIA)\n" +
                    "Abort  -  stop creating instance DBs (project stays unsaved)\n" +
                    "Ignore -  skip this one and continue",
                    "Openn2 - Create Instance DB",
                    System.Windows.Forms.MessageBoxButtons.AbortRetryIgnore,
                    System.Windows.Forms.MessageBoxIcon.Warning));
        }

        #region Import queue (batch)

        private enum QueueRoute { GenerateImport, InstanceDb, ImportXml, Unknown }

        /// <summary>
        /// Batch-processes every .csv/.xml file under the queue folder in relative-path
        /// order (the user prefixes 01_,02_,... to sequence FBs before the instance DBs
        /// that reference them). Each file's route is auto-detected; its subfolder under
        /// the queue mirrors into a TIA block group (find-or-create). A failed file pops
        /// Retry/Abort/Ignore. Cancellable between files; nothing is saved.
        /// </summary>
        public void RunImportQueue(string queueFolder)
        {
            if (project == null)
            {
                Log("Can't run import queue: No Tia Project Attached");
                return;
            }
            PlcSoftware plcSoftware = GetPlcSoftware(project);
            if (plcSoftware == null)
            {
                Log("Can't run import queue: no Plc Software found in the project");
                return;
            }
            if (!Directory.Exists(queueFolder))
            {
                Log("Import queue folder not found: " + queueFolder);
                return;
            }

            string root = Path.GetFullPath(queueFolder).TrimEnd('\\', '/');
            List<string> files = Directory.GetFiles(root, "*.*", SearchOption.AllDirectories)
                .Where(f => { string e = Path.GetExtension(f).ToLowerInvariant(); return e == ".csv" || e == ".xml"; })
                .OrderBy(f => f.Substring(root.Length).TrimStart('\\', '/'), StringComparer.OrdinalIgnoreCase)
                .ToList();

            if (files.Count == 0)
            {
                Log("Import queue: no .csv or .xml files in " + root);
                return;
            }

            Log("Import queue: " + files.Count + " file(s) in " + root);
            int processed = 0;
            foreach (string file in files)
            {
                if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                {
                    Log("Import queue CANCELLED - " + processed + " of " + files.Count + " processed (project not saved)");
                    return;
                }

                string rel = file.Substring(root.Length).TrimStart('\\', '/');
                string relFolder = (Path.GetDirectoryName(rel) ?? "").Replace('\\', '/');
                PlcBlockGroup group = GetOrCreateBlockGroup(plcSoftware.BlockGroup, relFolder);

                while (true) //repeated while the user chooses Retry
                {
                    string error;
                    BatchOutcome outcome = DispatchQueueFile(file, group, relFolder, out error);

                    if (outcome == BatchOutcome.Completed) { processed++; break; }
                    if (outcome == BatchOutcome.Aborted)
                    {
                        Log("Import queue ABORTED - " + processed + " of " + files.Count + " processed (project not saved)");
                        return;
                    }

                    //Failed: let the user decide
                    var decision = AskFileDecision(rel, error);
                    if (decision == System.Windows.Forms.DialogResult.Retry) { Log("Retrying " + rel); continue; }
                    if (decision == System.Windows.Forms.DialogResult.Ignore) { Log("SKIPPED " + rel + (error != null ? " - " + error : "")); break; }
                    Log("Import queue ABORTED by the user at " + rel + " - " + processed + " of " + files.Count + " processed");
                    return;
                }
            }

            Log("Import queue done: " + processed + " of " + files.Count + " file(s) processed (project not saved)");
        }

        /// <summary>Runs one queue file through its detected route, importing into the mirrored group.</summary>
        private BatchOutcome DispatchQueueFile(string file, PlcBlockGroup group, string relFolder, out string error)
        {
            error = null;
            string label = Path.GetFileName(file) + (relFolder.Length > 0 ? " -> " + relFolder : "");

            switch (DetectQueueRoute(file))
            {
                case QueueRoute.GenerateImport:
                    string versionTag = "V" + OpennessSetup.SelectedInstallation.PortalVersion.Major;
                    string outputFolder = Path.Combine(appBaseDir, "GeneratedBlocks");
                    string xml = Openn._02_Converter.BlockXmlGenerator.Generate(file, versionTag, outputFolder, null);
                    if (xml == null) { error = "block generation failed (see log)"; return BatchOutcome.Failed; }
                    try { ImportXmlInto(group, xml); }
                    catch (Exception e) { error = e.Message; return BatchOutcome.Failed; }
                    Log("Import queue: generated + imported " + label);
                    return BatchOutcome.Completed;

                case QueueRoute.InstanceDb:
                    BatchOutcome outcome = CreateInstanceDbsCore(file, relFolder);
                    if (outcome == BatchOutcome.Failed) error = "instance DB csv has errors (see log)";
                    return outcome;

                case QueueRoute.ImportXml:
                    try { ImportXmlInto(group, file); }
                    catch (Exception e) { error = e.Message; return BatchOutcome.Failed; }
                    Log("Import queue: imported " + label);
                    return BatchOutcome.Completed;

                default:
                    error = "unrecognized csv (no template= directive and no Name/InstanceOf key columns)";
                    return BatchOutcome.Failed;
            }
        }

        /// <summary>
        /// Detects the route from extension/content without a full parse: .xml = direct
        /// import; .csv with a template= directive = generate-then-import; .csv whose %
        /// key row has Name + InstanceOf/FB = instance DB; otherwise unknown.
        /// </summary>
        private static QueueRoute DetectQueueRoute(string path)
        {
            string ext = Path.GetExtension(path).ToLowerInvariant();
            if (ext == ".xml") return QueueRoute.ImportXml;
            if (ext != ".csv") return QueueRoute.Unknown;

            string[] lines;
            try { lines = File.ReadAllLines(path); }
            catch { return QueueRoute.Unknown; }

            //a generate template can have its key row too, so the template directive wins
            foreach (string raw in lines)
            {
                string line = raw.Trim();
                if (line.StartsWith("$", StringComparison.Ordinal) && line.IndexOf("template=", StringComparison.OrdinalIgnoreCase) >= 0)
                    return QueueRoute.GenerateImport;
            }
            foreach (string raw in lines)
            {
                string line = raw.Trim();
                if (!line.StartsWith("%", StringComparison.Ordinal)) continue;
                var cells = line.Split(',', ';', '\t').Select(c => c.Trim()).ToList();
                bool hasName = cells.Any(c => c.Equals("Name", StringComparison.OrdinalIgnoreCase));
                bool hasFb = cells.Any(c => c.Equals("InstanceOf", StringComparison.OrdinalIgnoreCase) ||
                                            c.Equals("InstanceOfFB", StringComparison.OrdinalIgnoreCase) ||
                                            c.Equals("FB", StringComparison.OrdinalIgnoreCase));
                if (hasName && hasFb) return QueueRoute.InstanceDb;
                break; //first key row decides
            }
            return QueueRoute.Unknown;
        }

        /// <summary>Per-file failure decision in the import queue (UI thread; worker waits): Retry / Abort / Ignore.</summary>
        private static System.Windows.Forms.DialogResult AskFileDecision(string fileLabel, string error)
        {
            var application = System.Windows.Application.Current;
            if (application == null) return System.Windows.Forms.DialogResult.Abort; //no UI: fail safe

            return application.Dispatcher.Invoke(() =>
                System.Windows.Forms.MessageBox.Show(
                    "Import queue step failed for \"" + fileLabel + "\":\n\n" + (error ?? "see the log for details") + "\n\n" +
                    "Retry  -  process this file again\n" +
                    "Abort  -  stop the import queue (project stays unsaved)\n" +
                    "Ignore -  skip this file and continue",
                    "Openn2 - Import Queue",
                    System.Windows.Forms.MessageBoxButtons.AbortRetryIgnore,
                    System.Windows.Forms.MessageBoxIcon.Warning));
        }

        #endregion Import queue (batch)

        /// <summary>
        /// Imports an xml block file into the root block group of the Plc program,
        /// overriding an existing block with the same name.
        /// </summary>
        public void ImportPlcBlock(string fileName)
        {
            try
            {
                PlcSoftware plcSoftware = GetPlcSoftware(project);
                ImportXmlInto(plcSoftware.BlockGroup, fileName);
                Log("Plc Source Block : " + fileName + " imported successfully");
            }
            catch (Exception e)
            {
                Log("ERROR Importing Plc Block \n" + e.Message);
            }
        }

        /// <summary>Raw XML block import into a specific group (overrides same-named blocks). No logging.</summary>
        private void ImportXmlInto(PlcBlockGroup group, string fileName)
        {
            group.Blocks.Import(new FileInfo(fileName), ImportOptions.Override);
        }

        /// <summary>
        /// All program blocks of the attached project, including blocks inside
        /// block groups (subfolders) at any depth, sorted by display text.
        /// </summary>
        public IList<PlcBlockInfo> GetAllBlocks()
        {
            var blocks = new List<PlcBlockInfo>();

            if (project == null)
            {
                Log("Can't read blocks: No Tia Project Attached");
                return blocks;
            }
            PlcSoftware plcSoftware = GetPlcSoftware(project);
            if (plcSoftware == null)
            {
                Log("Can't read blocks: no Plc Software found in the project");
                return blocks;
            }

            CollectBlocks(plcSoftware.BlockGroup, "", blocks);
            CollectTypes(plcSoftware.TypeGroup.Types, plcSoftware.TypeGroup.Groups, "", blocks);
            blocks.Sort((a, b) => string.Compare(a.DisplayText, b.DisplayText, StringComparison.OrdinalIgnoreCase));

            Log("Software blocks list refreshed: found " + blocks.Count + " block(s) / type(s)");
            return blocks;
        }

        /// <summary>Depth-first walk of a block group, accumulating blocks with folder path + language.</summary>
        private void CollectBlocks(PlcBlockGroup group, string groupPath, List<PlcBlockInfo> blocks)
        {
            foreach (PlcBlock block in group.Blocks)
                blocks.Add(new PlcBlockInfo(block.Name, block.GetType().Name, groupPath, block.ProgrammingLanguage.ToString()));

            foreach (PlcBlockUserGroup subGroup in group.Groups)
                CollectBlocks(subGroup, groupPath.Length == 0 ? subGroup.Name : groupPath + "/" + subGroup.Name, blocks);
        }

        /// <summary>Depth-first walk of the type tree, accumulating UDTs (so they can be exported as .udt/.xml).</summary>
        private void CollectTypes(PlcTypeComposition types, PlcTypeUserGroupComposition groups, string groupPath, List<PlcBlockInfo> blocks)
        {
            foreach (PlcType type in types)
                blocks.Add(new PlcBlockInfo(type.Name, "UDT", groupPath, "", isType: true));

            foreach (PlcTypeUserGroup subGroup in groups)
                CollectTypes(subGroup.Types, subGroup.Groups, groupPath.Length == 0 ? subGroup.Name : groupPath + "/" + subGroup.Name, blocks);
        }

        /// <summary>Finds a block by name anywhere in the program blocks tree (names are unique per Plc).</summary>
        private PlcBlock FindBlock(PlcBlockGroup group, string blockName)
        {
            PlcBlock block = group.Blocks.Find(blockName);
            if (block != null) return block;

            foreach (PlcBlockUserGroup subGroup in group.Groups)
            {
                block = FindBlock(subGroup, blockName);
                if (block != null) return block;
            }
            return null;
        }

        /// <summary>Finds a data type (UDT) by name anywhere in the type tree.</summary>
        private PlcType FindType(PlcTypeComposition types, PlcTypeUserGroupComposition groups, string typeName)
        {
            foreach (PlcType type in types)
                if (type.Name == typeName) return type;

            foreach (PlcTypeUserGroup subGroup in groups)
            {
                PlcType type = FindType(subGroup.Types, subGroup.Groups, typeName);
                if (type != null) return type;
            }
            return null;
        }

        /// <summary>
        /// The Plc program of the first device in the project that exposes a
        /// software container (this tool targets single-Plc projects).
        /// </summary>
        private PlcSoftware GetPlcSoftware(Project _project)
        {
            PlcSoftware plcSoftware = null;
            foreach (Device device in _project.Devices)
            {
                DeviceItemComposition deviceItemComposition = device.DeviceItems;
                foreach (DeviceItem _deviceItem in deviceItemComposition)
                {
                    SoftwareContainer softwareContainer = _deviceItem.GetService<SoftwareContainer>();
                    if (softwareContainer != null)
                    {
                        Software softwareBase = softwareContainer.Software;
                        plcSoftware = softwareBase as PlcSoftware;
                        if (plcSoftware != null)
                        {
                            break;
                        }
                    }
                }
                break; //only the first device is inspected
            }
            return plcSoftware;
        }
    }
}

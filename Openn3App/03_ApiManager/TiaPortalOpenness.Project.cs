using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Xml;
using Siemens.Engineering;
using Siemens.Engineering.Cax;
using Siemens.Engineering.SW;
using Siemens.Engineering.SW.Blocks;
using Siemens.Engineering.SW.ExternalSources;
using Siemens.Engineering.SW.Tags;
using Siemens.Engineering.SW.Types;
using Openn._10_StandardFunctions;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Whole-project import / export for the Pipeline3 round-trip (the "Project" tab).
    ///
    ///   Import: Shared\...\BuilderData\*   ->  builds the attached TIA project
    ///   Export: the attached TIA project   ->  Shared\...\ExportedData\*  (XML; hardware as CAx/AML)
    ///
    /// Reuses the per-feature primitives in the other partials (GetPlcSoftware, ImportXmlInto,
    /// CreateDevices, CreateInstanceDbs, DetectQueueRoute, BlockXmlGenerator) and the shared
    /// cancellation (TiaWorker.CurrentCancellation) - so these orchestrators stay thin. All paths
    /// come from AppPaths; nothing is ever saved (a run is rolled back by closing TIA unsaved).
    /// </summary>
    public partial class TiaPortalOpenness
    {
        // ============================== EXPORT (TIA -> ExportedData) ==============================

        /// <summary>Software blocks (FB/FC/OB/...) as XML, mirroring the TIA group tree.</summary>
        public void ExportSoftwareBlocks() =>
            RunBlockExport(b => !(b is DataBlock), AppPaths.ExportedBlocksDir, "software block");

        /// <summary>Data blocks as XML, mirroring the TIA group tree.</summary>
        public void ExportDataBlocks() =>
            RunBlockExport(b => b is DataBlock, AppPaths.ExportedDataBlocksDir, "data block");

        private void RunBlockExport(Func<PlcBlock, bool> match, string targetRoot, string label)
        {
            PlcSoftware sw = RequireSoftware("export " + label + "s");
            if (sw == null) return;
            SweepDir(targetRoot, "*.xml");
            bool cancelled = false;
            int n = ExportBlockTree(sw.BlockGroup, "", match, targetRoot, ref cancelled);
            Log((cancelled ? "Export CANCELLED - " : "Exported ") + n + " " + label + "(s) -> " + targetRoot);
        }

        private int ExportBlockTree(PlcBlockGroup group, string groupPath, Func<PlcBlock, bool> match, string targetRoot, ref bool cancelled)
        {
            int count = 0;
            foreach (PlcBlock block in group.Blocks)
            {
                if (Cancelled()) { cancelled = true; return count; }
                if (!match(block)) continue;
                try { ExportToXml(file => block.Export(file, ExportOptions.WithDefaults), targetRoot, groupPath, block.Name); count++; }
                catch (Exception e) { Log("ERROR exporting block " + block.Name + " \n" + e.Message); }
            }
            foreach (PlcBlockUserGroup sub in group.Groups)
            {
                count += ExportBlockTree(sub, Join(groupPath, sub.Name), match, targetRoot, ref cancelled);
                if (cancelled) return count;
            }
            return count;
        }

        /// <summary>User data types (UDTs) as XML, mirroring the TIA type-group tree.</summary>
        public void ExportUserDataTypes()
        {
            PlcSoftware sw = RequireSoftware("export UDTs");
            if (sw == null) return;
            SweepDir(AppPaths.ExportedUserDataTypesDir, "*.xml");
            bool cancelled = false;
            int n = ExportTypeTree(sw.TypeGroup.Types, sw.TypeGroup.Groups, "", ref cancelled);
            Log((cancelled ? "Export CANCELLED - " : "Exported ") + n + " UDT(s) -> " + AppPaths.ExportedUserDataTypesDir);
        }

        private int ExportTypeTree(PlcTypeComposition types, PlcTypeUserGroupComposition groups, string groupPath, ref bool cancelled)
        {
            int count = 0;
            foreach (PlcType type in types)
            {
                if (Cancelled()) { cancelled = true; return count; }
                try { ExportToXml(file => type.Export(file, ExportOptions.WithDefaults), AppPaths.ExportedUserDataTypesDir, groupPath, type.Name); count++; }
                catch (Exception e) { Log("ERROR exporting UDT " + type.Name + " \n" + e.Message); }
            }
            foreach (PlcTypeUserGroup sub in groups)
            {
                count += ExportTypeTree(sub.Types, sub.Groups, Join(groupPath, sub.Name), ref cancelled);
                if (cancelled) return count;
            }
            return count;
        }

        /// <summary>PLC tag tables, one XML per table, mirroring the TIA tag-group tree.</summary>
        public void ExportTagTables()
        {
            PlcSoftware sw = RequireSoftware("export tag tables");
            if (sw == null) return;
            SweepDir(AppPaths.ExportedTagTablesDir, "*.xml");
            bool cancelled = false;
            int n = ExportTagTree(sw.TagTableGroup.TagTables, sw.TagTableGroup.Groups, "", ref cancelled);
            Log((cancelled ? "Export CANCELLED - " : "Exported ") + n + " tag table(s) -> " + AppPaths.ExportedTagTablesDir);
        }

        private int ExportTagTree(PlcTagTableComposition tables, PlcTagTableUserGroupComposition groups, string groupPath, ref bool cancelled)
        {
            int count = 0;
            foreach (PlcTagTable table in tables)
            {
                if (Cancelled()) { cancelled = true; return count; }
                try { ExportToXml(file => table.Export(file, ExportOptions.WithDefaults), AppPaths.ExportedTagTablesDir, groupPath, table.Name); count++; }
                catch (Exception e) { Log("ERROR exporting tag table " + table.Name + " \n" + e.Message); }
            }
            foreach (PlcTagTableUserGroup sub in groups)
            {
                count += ExportTagTree(sub.TagTables, sub.Groups, Join(groupPath, sub.Name), ref cancelled);
                if (cancelled) return count;
            }
            return count;
        }

        /// <summary>
        /// Hardware configuration via TIA's CAx export: one project-wide AutomationML (.aml) file.
        /// CAx is the supported "structured hardware as XML" surface; a CaxProvider service is
        /// fetched from the attached project.
        /// </summary>
        public void ExportHardwareCax()
        {
            if (project == null) { Log("Can't export hardware: No Tia Project Attached"); return; }
            try
            {
                CaxProvider cax = project.GetService<CaxProvider>();
                if (cax == null) { Log("Can't export hardware: CAx service unavailable for this project"); return; }

                Directory.CreateDirectory(AppPaths.ExportedHardwareDir);
                string stem = SafeName(project.Name);
                var aml = new FileInfo(Path.Combine(AppPaths.ExportedHardwareDir, stem + ".aml"));
                var log = new FileInfo(Path.Combine(AppPaths.ExportedHardwareDir, stem + ".cax.log"));
                if (aml.Exists) aml.Delete();
                if (log.Exists) log.Delete();

                bool ok = cax.Export(project, aml, log);
                Log((ok ? "Exported hardware (CAx/AML): " : "Hardware CAx export reported issues (see .cax.log): ") + aml.FullName);
            }
            catch (Exception e)
            {
                Log("ERROR exporting hardware (CAx) \n" + e.Message);
            }
        }

        /// <summary>Exports the whole attached project to ExportedData (blocks, DBs, UDTs, tags, hardware).</summary>
        public void ExportFullProject()
        {
            if (project == null) { Log("Can't export: No Tia Project Attached"); return; }
            Log("=== Export Full Project: start ===");
            ExportSoftwareBlocks(); if (Cancelled()) { Log("=== Export Full Project: CANCELLED ==="); return; }
            ExportDataBlocks();     if (Cancelled()) { Log("=== Export Full Project: CANCELLED ==="); return; }
            ExportUserDataTypes();  if (Cancelled()) { Log("=== Export Full Project: CANCELLED ==="); return; }
            ExportTagTables();      if (Cancelled()) { Log("=== Export Full Project: CANCELLED ==="); return; }
            ExportHardwareCax();
            Log("=== Export Full Project: done -> " + AppPaths.ExportedDataDir + " ===");
        }

        // ============================== IMPORT (BuilderData -> TIA) ==============================

        /// <summary>1. Hardware: load the BuilderData csv config, then build it (the existing, tested generator).</summary>
        public void ImportHardware(bool createNewIoControllers)
        {
            if (project == null) { Log("Can't import hardware: No Tia Project Attached"); return; }
            if (!Openn._01_Constructor.HardwareConfigLoader.LoadAll(AppPaths.HardwareConfigDir))
            {
                Log("Import hardware ABORTED - hardware configuration did not load from " + AppPaths.HardwareConfigDir);
                return;
            }
            CreateDevices(createNewIoControllers);
        }

        /// <summary>2. User data types: import one XML per UDT (no-op until Pipeline3 emits them).</summary>
        public void ImportUserDataTypes() =>
            ImportXmlFolder("UDT", AppPaths.UserDataTypesImportDir, (sw, file) => sw.TypeGroup.Types.Import(file, ImportOptions.Override));

        /// <summary>3. IO tags: import one XML per tag table (the PLCTags.xlsx beside them is ignored - manual TIA import only).</summary>
        public void ImportIoTags() =>
            ImportXmlFolder("tag table", AppPaths.PlcTagsDir, (sw, file) => sw.TagTableGroup.TagTables.Import(file, ImportOptions.Override));

        /// <summary>4. Data blocks: F_DB/global-DB XML (Blocks.Import) + .db external sources (generate blocks).</summary>
        public void ImportDataBlocks()
        {
            PlcSoftware sw = RequireSoftware("import data blocks");
            if (sw == null) return;
            string folder = AppPaths.ImportReadyBlocksDir;
            if (!Directory.Exists(folder)) { Log("Import data blocks: folder not found (" + folder + ") - skipped"); return; }

            List<string> dbXml = OrderedFiles(folder, "*.xml").Where(IsGlobalDbXml).ToList();
            List<string> dbSrc = OrderedFiles(folder, "*.db").ToList();
            int done = 0, total = dbXml.Count + dbSrc.Count;
            if (total == 0) { Log("Import data blocks: nothing in " + folder + " - skipped"); return; }

            foreach (string f in dbXml)
            {
                if (Cancelled()) { Log("Import data blocks CANCELLED - " + done + " of " + total); return; }
                try { ImportXmlInto(sw.BlockGroup, f); done++; Log("Imported data block (xml): " + Path.GetFileName(f)); }
                catch (Exception e) { Log("ERROR importing " + Path.GetFileName(f) + " \n" + e.Message); }
            }
            foreach (string f in dbSrc)
            {
                if (Cancelled()) { Log("Import data blocks CANCELLED - " + done + " of " + total); return; }
                try { GenerateFromExternalSource(sw, f); done++; Log("Imported data block (.db source): " + Path.GetFileName(f)); }
                catch (Exception e) { Log("ERROR importing " + Path.GetFileName(f) + " \n" + e.Message); }
            }
            Log("Import data blocks done: " + done + " of " + total);
        }

        /// <summary>5. Instance DBs: the existing CreationInfo\InstanceDBs.csv route (Retry/Abort/Ignore).</summary>
        public void ImportInstanceDbs()
        {
            string csv = Path.Combine(AppPaths.BlocksCreationDir, "InstanceDBs.csv");
            if (!File.Exists(csv)) { Log("Import instance DBs: " + csv + " not found - skipped"); return; }
            CreateInstanceDbs(csv);
        }

        /// <summary>
        /// 6. Software blocks: generate from the CreationInfo block-gen csvs (template route only,
        /// skipping InstanceDBs.csv), then import the code-block XMLs (non-DB) and .scl/.awl sources.
        /// </summary>
        public void ImportSoftwareBlocks()
        {
            PlcSoftware sw = RequireSoftware("import software blocks");
            if (sw == null) return;

            string versionTag = "V" + OpennessSetup.SelectedInstallation.PortalVersion.Major;
            string genOut = Path.Combine(AppPaths.AppBaseDir, "GeneratedBlocks");
            int done = 0;

            if (Directory.Exists(AppPaths.BlocksCreationDir))
                foreach (string csv in OrderedFiles(AppPaths.BlocksCreationDir, "*.csv"))
                {
                    if (Cancelled()) { Log("Import software blocks CANCELLED - " + done + " imported"); return; }
                    if (DetectQueueRoute(csv) != QueueRoute.GenerateImport) continue; //InstanceDBs.csv etc. handled elsewhere
                    try
                    {
                        string xml = Openn._02_Converter.BlockXmlGenerator.Generate(csv, versionTag, genOut, null);
                        if (xml == null) { Log("Block generation failed (see log): " + Path.GetFileName(csv)); continue; }
                        ImportXmlInto(sw.BlockGroup, xml);
                        done++; Log("Generated + imported: " + Path.GetFileName(csv));
                    }
                    catch (Exception e) { Log("ERROR generating/importing " + Path.GetFileName(csv) + " \n" + e.Message); }
                }

            if (Directory.Exists(AppPaths.ImportReadyBlocksDir))
            {
                foreach (string f in OrderedFiles(AppPaths.ImportReadyBlocksDir, "*.xml").Where(p => !IsGlobalDbXml(p)))
                {
                    if (Cancelled()) { Log("Import software blocks CANCELLED - " + done + " imported"); return; }
                    try { ImportXmlInto(sw.BlockGroup, f); done++; Log("Imported block (xml): " + Path.GetFileName(f)); }
                    catch (Exception e) { Log("ERROR importing " + Path.GetFileName(f) + " \n" + e.Message); }
                }
                foreach (string f in OrderedFiles(AppPaths.ImportReadyBlocksDir, "*.*").Where(IsTextSource))
                {
                    if (Cancelled()) { Log("Import software blocks CANCELLED - " + done + " imported"); return; }
                    try { GenerateFromExternalSource(sw, f); done++; Log("Imported source: " + Path.GetFileName(f)); }
                    catch (Exception e) { Log("ERROR importing " + Path.GetFileName(f) + " \n" + e.Message); }
                }
            }
            Log("Import software blocks done: " + done + " block source(s)");
        }

        /// <summary>Builds the whole project from BuilderData in the fixed order; cancellable between phases.</summary>
        public void ImportFullProject(bool createNewIoControllers)
        {
            if (project == null) { Log("Can't import: No Tia Project Attached"); return; }
            Log("=== Import Full Project: start ===");
            Log("--- 1/6 Hardware ---");        ImportHardware(createNewIoControllers); if (StopFull()) return;
            Log("--- 2/6 User Data Types ---"); ImportUserDataTypes();                  if (StopFull()) return;
            Log("--- 3/6 IO Tags ---");         ImportIoTags();                         if (StopFull()) return;
            Log("--- 4/6 Data Blocks ---");     ImportDataBlocks();                     if (StopFull()) return;
            Log("--- 5/6 Instance DBs ---");    ImportInstanceDbs();                    if (StopFull()) return;
            Log("--- 6/6 Software Blocks ---"); ImportSoftwareBlocks();                 if (StopFull()) return;
            Log("=== Import Full Project: done (project not saved) ===");
        }

        private static bool StopFull()
        {
            if (!Cancelled()) return false;
            Log("=== Import Full Project: CANCELLED ===");
            return true;
        }

        // ============================== helpers ==============================

        private static bool Cancelled() => TiaWorker.CurrentCancellation.IsCancellationRequested;

        private PlcSoftware RequireSoftware(string action)
        {
            if (project == null) { Log("Can't " + action + ": No Tia Project Attached"); return null; }
            PlcSoftware sw = GetPlcSoftware(project);
            if (sw == null) Log("Can't " + action + ": no Plc Software found in the project");
            return sw;
        }

        /// <summary>Imports every *.xml of a folder through one Openness Import call; no-op when empty/absent.</summary>
        private void ImportXmlFolder(string label, string folder, Action<PlcSoftware, FileInfo> import)
        {
            PlcSoftware sw = RequireSoftware("import " + label + "s");
            if (sw == null) return;
            if (!Directory.Exists(folder)) { Log("Import " + label + "s: folder not found (" + folder + ") - skipped"); return; }

            List<string> files = OrderedFiles(folder, "*.xml").ToList();
            if (files.Count == 0) { Log("Import " + label + "s: no .xml in " + folder + " - skipped"); return; }

            int done = 0;
            foreach (string f in files)
            {
                if (Cancelled()) { Log("Import " + label + "s CANCELLED - " + done + " of " + files.Count); return; }
                try { import(sw, new FileInfo(f)); done++; Log("Imported " + label + ": " + Path.GetFileName(f)); }
                catch (Exception e) { Log("ERROR importing " + Path.GetFileName(f) + " \n" + e.Message); }
            }
            Log("Import " + label + "s done: " + done + " of " + files.Count);
        }

        /// <summary>Creates an external source (.db/.scl/.awl) and generates its blocks (keeping partial results on error).</summary>
        private void GenerateFromExternalSource(PlcSoftware sw, string path)
        {
            PlcExternalSource source = sw.ExternalSourceGroup.ExternalSources.CreateFromFile(Path.GetFileName(path), path);
            source.GenerateBlocksFromSource(GenerateBlockOption.KeepOnError);
        }

        /// <summary>Exports one object to &lt;targetRoot&gt;\&lt;groupPath&gt;\&lt;name&gt;.xml (the export deletes a stale same-named file first).</summary>
        private static void ExportToXml(Action<FileInfo> export, string targetRoot, string groupPath, string name)
        {
            string dir = groupPath.Length == 0 ? targetRoot : Path.Combine(targetRoot, groupPath.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(dir);
            var file = new FileInfo(Path.Combine(dir, SafeName(name) + ".xml"));
            if (file.Exists) file.Delete();
            export(file);
        }

        /// <summary>Files of one pattern in name order (so 00_,01_,... sequence FBs before their instance DBs).</summary>
        private static IEnumerable<string> OrderedFiles(string folder, string pattern) =>
            Directory.GetFiles(folder, pattern).OrderBy(Path.GetFileName, StringComparer.OrdinalIgnoreCase);

        private static bool IsTextSource(string path)
        {
            string e = Path.GetExtension(path).ToLowerInvariant();
            return e == ".scl" || e == ".awl";
        }

        /// <summary>True when the export XML's first SW object is a global data block (the F_DB / safe-DB form).</summary>
        private static bool IsGlobalDbXml(string path) => FirstSwObjectElement(path) == "SW.Blocks.GlobalDB";

        /// <summary>The first &lt;SW.Blocks.*&gt; / &lt;SW.Types.*&gt; element name in a TIA export xml (e.g. SW.Blocks.FB), or "".</summary>
        private static string FirstSwObjectElement(string path)
        {
            try
            {
                using (var reader = XmlReader.Create(path, new XmlReaderSettings { IgnoreComments = true, IgnoreWhitespace = true, DtdProcessing = DtdProcessing.Ignore }))
                    while (reader.Read())
                        if (reader.NodeType == XmlNodeType.Element &&
                            (reader.Name.StartsWith("SW.Blocks.", StringComparison.Ordinal) || reader.Name.StartsWith("SW.Types.", StringComparison.Ordinal)))
                            return reader.Name;
            }
            catch { }
            return "";
        }

        private static void SweepDir(string dir, string pattern)
        {
            if (!Directory.Exists(dir)) { Directory.CreateDirectory(dir); return; }
            foreach (string f in Directory.GetFiles(dir, pattern, SearchOption.AllDirectories))
                try { File.Delete(f); } catch { }
        }

        private static string Join(string a, string b) => a.Length == 0 ? b : a + "/" + b;

        private static string SafeName(string name) => string.Join("_", name.Split(Path.GetInvalidFileNameChars()));
    }
}

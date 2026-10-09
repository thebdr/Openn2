using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Siemens.Engineering;
using Siemens.Engineering.Cax;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW;
using Siemens.Engineering.SW.Blocks;
using Siemens.Engineering.SW.ExternalSources;
using Siemens.Engineering.SW.Tags;
using Siemens.Engineering.SW.Types;
using Openn._00_Contract;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Project export for the Pipeline5 round-trip (Workspace tab, "Export"): the attached TIA project into an
    /// export root shaped like the handoff workspace (contract v1, VCI shape), every file stamped with the header:
    ///
    ///   &lt;exportRoot&gt;\.openn\workspace.openn.config               contract, producer, generated, run, project, plcs
    ///   &lt;exportRoot&gt;\&lt;PLC&gt;\Program blocks\&lt;group&gt;\&lt;Block&gt;.xml   sw/code-block, sw/data-block (TIA XML + header comment)
    ///   &lt;exportRoot&gt;\&lt;PLC&gt;\PLC data types\&lt;group&gt;\&lt;UDT&gt;.xml     sw/udt
    ///   &lt;exportRoot&gt;\&lt;PLC&gt;\PLC tags\&lt;group&gt;\&lt;Table&gt;.xml        sw/tag-table
    ///   &lt;exportRoot&gt;\Devices &amp; networks\&lt;project&gt;.aml           CAx / AutomationML (+ .cax.log, + .aml.openn sidecar: doc/other)
    ///
    /// The export root is the caller's (the workspace's sibling ExportedData - AppPaths.ExportRootFor). The PLC folder
    /// is the CPU device item's name, the name Pipeline5 uses for its PLC folder too. A full export sweeps the PLC's
    /// three folders first; a single-kind export only overwrites same-named files - the run stamp tells a consumer
    /// which files are leftovers. Every step is cancellable between objects (TiaWorker.CurrentCancellation);
    /// nothing is ever saved. (The legacy whole-project IMPORT of this file is gone: the Workspace tab imports by
    /// catalog - TiaPortalOpenness.Workspace.cs.)
    /// </summary>
    public partial class TiaPortalOpenness
    {
        /// <summary>One export run: root, run id, project name, producer, and the stamping of every written file.</summary>
        private sealed class ExportRun
        {
            public string Root { get; }
            public string RunId { get; }
            public string ProjectName { get; }
            public string Producer { get; }
            public DateTime GeneratedUtc { get; }
            public HashSet<string> Plcs { get; } = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            public int Written { get; private set; }

            public ExportRun(string root, string projectName)
            {
                Root = root;
                ProjectName = projectName;
                GeneratedUtc = DateTime.UtcNow;
                RunId = GeneratedUtc.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + "-" + Guid.NewGuid().ToString("N").Substring(0, 6);
                Producer = "Openn5 " + typeof(ExportRun).Assembly.GetName().Version.ToString(3) + " (export)";
            }

            /// <summary>Inserts the header comment right after the XML declaration of a file TIA just exported (its UTF-8 BOM is kept).</summary>
            public void StampXml(FileInfo file, InputKindInfo kind, string plc, string target, string name)
            {
                OpennHeader h = Header(kind);
                h.Set("plc", plc);
                h.Set("target", target);
                h.Set("name", name);
                h.Set("source", "TIA export");

                bool bom = HasBom(file.FullName);
                string text = File.ReadAllText(file.FullName, Encoding.UTF8);
                string block = h.Render(HeaderSyntax.Xml);
                int declarationEnd = text.StartsWith("<?xml", StringComparison.Ordinal) ? text.IndexOf("?>", StringComparison.Ordinal) + 2 : 0;
                string stamped = declarationEnd > 0
                    ? text.Substring(0, declarationEnd) + "\r\n" + block + text.Substring(declarationEnd).TrimStart('\r', '\n')
                    : block + text;
                File.WriteAllText(file.FullName, stamped, new UTF8Encoding(bom));
                Written++;
            }

            /// <summary>The "&lt;file&gt;.openn" sidecar of a non-XML export (the CAx AML).</summary>
            public void WriteSidecar(string path, InputKindInfo kind, string name)
            {
                OpennHeader h = Header(kind);
                h.Set("name", name);
                h.Set("source", "TIA CAx export");
                File.WriteAllText(path + OpennHeader.SidecarExtension, h.Render(HeaderSyntax.Csv), new UTF8Encoding(false));
                Written++;
            }

            /// <summary>.openn\workspace.openn.config of the export root: contract, producer, generated, run, project, plcs.</summary>
            public void WriteWorkspaceConfig()
            {
                var h = new OpennHeader();
                h.Set("contract", OpennHeader.CurrentContract.ToString(CultureInfo.InvariantCulture));
                h.Set("producer", Producer);
                h.Set("generated", Iso(GeneratedUtc));
                h.Set("run", RunId);
                h.Set("project", ProjectName);
                h.Set("plcs", string.Join(", ", Plcs.OrderBy(p => p, StringComparer.OrdinalIgnoreCase)));
                string dir = Path.Combine(Root, WorkspaceLayout.ConfigFolder);
                Directory.CreateDirectory(dir);
                File.WriteAllText(Path.Combine(dir, WorkspaceLayout.ConfigFile), h.Render(HeaderSyntax.Csv), new UTF8Encoding(false));
            }

            private OpennHeader Header(InputKindInfo kind)
            {
                OpennHeader h = OpennHeader.Create(kind, Producer, GeneratedUtc);
                h.Set("run", RunId);
                h.Set("project", ProjectName);
                return h;
            }

            private static string Iso(DateTime utc) => utc.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);

            private static bool HasBom(string path)
            {
                using (FileStream s = File.OpenRead(path))
                    return s.Length >= 3 && s.ReadByte() == 0xEF && s.ReadByte() == 0xBB && s.ReadByte() == 0xBF;
            }
        }

        // ============================== EXPORT (TIA -> the workspace's sibling ExportedData) ==============================

        /// <summary>Everything: blocks, UDTs, tag tables, hardware (CAx). Sweeps the PLC's three folders first.</summary>
        public void ExportFullProject(string exportRoot)
        {
            if (project == null) { Log("Can't export: No Tia Project Attached"); return; }
            string plcName;
            PlcSoftware sw = FirstPlc(out plcName);
            if (sw == null) { Log("Can't export: no Plc Software found in the project"); return; }

            var run = new ExportRun(exportRoot, project.Name);
            run.Plcs.Add(plcName);
            Log("=== Export project '" + project.Name + "' -> " + exportRoot + " (run " + run.RunId + ", PLC folder '" + plcName + "') ===");
            foreach (string folder in new[] { WorkspaceLayout.ProgramBlocks, WorkspaceLayout.PlcDataTypes, WorkspaceLayout.PlcTags })
                SweepDir(Path.Combine(exportRoot, plcName, folder), "*.xml");

            bool completed = ExportBlocks(run, sw, plcName, b => true, "block")
                             && ExportTypes(run, sw, plcName)
                             && ExportTags(run, sw, plcName);
            if (completed) ExportCax(run);
            Finish(run, !completed);
        }

        /// <summary>Code blocks (OB/FB/FC) as stamped XML into &lt;PLC&gt;\Program blocks\&lt;group&gt;.</summary>
        public void ExportSoftwareBlocks(string exportRoot) =>
            ExportOne(exportRoot, (run, sw, plc) => ExportBlocks(run, sw, plc, b => !(b is DataBlock), "code block"));

        /// <summary>Data blocks (global, instance, array) as stamped XML into &lt;PLC&gt;\Program blocks\&lt;group&gt;.</summary>
        public void ExportDataBlocks(string exportRoot) =>
            ExportOne(exportRoot, (run, sw, plc) => ExportBlocks(run, sw, plc, b => b is DataBlock, "data block"));

        /// <summary>User data types as stamped XML into &lt;PLC&gt;\PLC data types\&lt;group&gt;.</summary>
        public void ExportUserDataTypes(string exportRoot) => ExportOne(exportRoot, ExportTypes);

        /// <summary>PLC tag tables as stamped XML into &lt;PLC&gt;\PLC tags\&lt;group&gt;.</summary>
        public void ExportTagTables(string exportRoot) => ExportOne(exportRoot, ExportTags);

        /// <summary>Hardware via TIA's CAx export: one project-wide AutomationML file under Devices &amp; networks (+ sidecar).</summary>
        public void ExportHardwareCax(string exportRoot)
        {
            if (project == null) { Log("Can't export hardware: No Tia Project Attached"); return; }
            var run = new ExportRun(exportRoot, project.Name);
            string plcName;
            if (FirstPlc(out plcName) != null) run.Plcs.Add(plcName);
            ExportCax(run);
            Finish(run, false);
        }

        private void ExportOne(string exportRoot, Func<ExportRun, PlcSoftware, string, bool> step)
        {
            if (project == null) { Log("Can't export: No Tia Project Attached"); return; }
            string plcName;
            PlcSoftware sw = FirstPlc(out plcName);
            if (sw == null) { Log("Can't export: no Plc Software found in the project"); return; }

            var run = new ExportRun(exportRoot, project.Name);
            run.Plcs.Add(plcName);
            Log("=== Export -> " + exportRoot + " (run " + run.RunId + ", PLC folder '" + plcName + "') ===");
            bool completed = step(run, sw, plcName);
            Finish(run, !completed);
        }

        /// <summary>Writes the workspace config of the run (so files not rewritten in it read as stale) and logs the outcome.</summary>
        private static void Finish(ExportRun run, bool cancelled)
        {
            try { run.WriteWorkspaceConfig(); }
            catch (Exception e) { Log("ERROR writing the export workspace config \n" + e.Message); }
            Log((cancelled ? "=== Export CANCELLED - " : "=== Export done - ") + run.Written + " file(s) written and stamped (run " + run.RunId + ") -> " + run.Root + " ===");
        }

        /// <summary>Blocks matching the filter into &lt;PLC&gt;\Program blocks\&lt;group&gt; (code and data blocks share the folder, as in TIA). False = cancelled.</summary>
        private bool ExportBlocks(ExportRun run, PlcSoftware sw, string plcName, Func<PlcBlock, bool> match, string label)
        {
            string targetRoot = Path.Combine(run.Root, plcName, WorkspaceLayout.ProgramBlocks);
            bool cancelled = false;
            int n = ExportBlockTree(run, sw.BlockGroup, string.Empty, match, plcName, targetRoot, ref cancelled);
            Log((cancelled ? "Export CANCELLED - " : "Exported ") + n + " " + label + "(s) -> " + targetRoot);
            return !cancelled;
        }

        private int ExportBlockTree(ExportRun run, PlcBlockGroup group, string groupPath, Func<PlcBlock, bool> match, string plcName, string targetRoot, ref bool cancelled)
        {
            int count = 0;
            foreach (PlcBlock block in group.Blocks)
            {
                if (Cancelled()) { cancelled = true; return count; }
                if (!match(block)) continue;
                InputKindInfo kind = InputKindInfo.For(block is DataBlock ? InputKind.SwDataBlock : InputKind.SwCodeBlock);
                try
                {
                    FileInfo file = ExportToXml(f => block.Export(f, ExportOptions.WithDefaults), targetRoot, groupPath, block.Name);
                    run.StampXml(file, kind, plcName, TargetOf(WorkspaceLayout.ProgramBlocks, groupPath), block.Name);
                    count++;
                }
                catch (Exception e) { Log("ERROR exporting block " + block.Name + " \n" + e.Message); }
            }
            foreach (PlcBlockUserGroup sub in group.Groups)
            {
                count += ExportBlockTree(run, sub, Join(groupPath, sub.Name), match, plcName, targetRoot, ref cancelled);
                if (cancelled) return count;
            }
            return count;
        }

        /// <summary>User data types into &lt;PLC&gt;\PLC data types\&lt;group&gt;. False = cancelled.</summary>
        private bool ExportTypes(ExportRun run, PlcSoftware sw, string plcName)
        {
            string targetRoot = Path.Combine(run.Root, plcName, WorkspaceLayout.PlcDataTypes);
            bool cancelled = false;
            int n = ExportTypeTree(run, sw.TypeGroup.Types, sw.TypeGroup.Groups, string.Empty, plcName, targetRoot, ref cancelled);
            Log((cancelled ? "Export CANCELLED - " : "Exported ") + n + " UDT(s) -> " + targetRoot);
            return !cancelled;
        }

        private int ExportTypeTree(ExportRun run, PlcTypeComposition types, PlcTypeUserGroupComposition groups, string groupPath, string plcName, string targetRoot, ref bool cancelled)
        {
            int count = 0;
            InputKindInfo kind = InputKindInfo.For(InputKind.SwUdt);
            foreach (PlcType type in types)
            {
                if (Cancelled()) { cancelled = true; return count; }
                try
                {
                    FileInfo file = ExportToXml(f => type.Export(f, ExportOptions.WithDefaults), targetRoot, groupPath, type.Name);
                    run.StampXml(file, kind, plcName, TargetOf(WorkspaceLayout.PlcDataTypes, groupPath), type.Name);
                    count++;
                }
                catch (Exception e) { Log("ERROR exporting UDT " + type.Name + " \n" + e.Message); }
            }
            foreach (PlcTypeUserGroup sub in groups)
            {
                count += ExportTypeTree(run, sub.Types, sub.Groups, Join(groupPath, sub.Name), plcName, targetRoot, ref cancelled);
                if (cancelled) return count;
            }
            return count;
        }

        /// <summary>Tag tables into &lt;PLC&gt;\PLC tags\&lt;group&gt;. False = cancelled.</summary>
        private bool ExportTags(ExportRun run, PlcSoftware sw, string plcName)
        {
            string targetRoot = Path.Combine(run.Root, plcName, WorkspaceLayout.PlcTags);
            bool cancelled = false;
            int n = ExportTagTree(run, sw.TagTableGroup.TagTables, sw.TagTableGroup.Groups, string.Empty, plcName, targetRoot, ref cancelled);
            Log((cancelled ? "Export CANCELLED - " : "Exported ") + n + " tag table(s) -> " + targetRoot);
            return !cancelled;
        }

        private int ExportTagTree(ExportRun run, PlcTagTableComposition tables, PlcTagTableUserGroupComposition groups, string groupPath, string plcName, string targetRoot, ref bool cancelled)
        {
            int count = 0;
            InputKindInfo kind = InputKindInfo.For(InputKind.SwTagTable);
            foreach (PlcTagTable table in tables)
            {
                if (Cancelled()) { cancelled = true; return count; }
                try
                {
                    FileInfo file = ExportToXml(f => table.Export(f, ExportOptions.WithDefaults), targetRoot, groupPath, table.Name);
                    run.StampXml(file, kind, plcName, TargetOf(WorkspaceLayout.PlcTags, groupPath), table.Name);
                    count++;
                }
                catch (Exception e) { Log("ERROR exporting tag table " + table.Name + " \n" + e.Message); }
            }
            foreach (PlcTagTableUserGroup sub in groups)
            {
                count += ExportTagTree(run, sub.TagTables, sub.Groups, Join(groupPath, sub.Name), plcName, targetRoot, ref cancelled);
                if (cancelled) return count;
            }
            return count;
        }

        /// <summary>
        /// Hardware via TIA's CAx export: one project-wide AutomationML (.aml) under Devices &amp; networks, with TIA's
        /// .cax.log beside it and an .openn sidecar (doc/other - the AML is not an OpennN input).
        /// </summary>
        private void ExportCax(ExportRun run)
        {
            try
            {
                CaxProvider cax = project.GetService<CaxProvider>();
                if (cax == null) { Log("Can't export hardware: CAx service unavailable for this project"); return; }

                string dir = Path.Combine(run.Root, WorkspaceLayout.HardwareFolder);
                Directory.CreateDirectory(dir);
                string stem = SafeName(project.Name);
                var aml = new FileInfo(Path.Combine(dir, stem + ".aml"));
                var log = new FileInfo(Path.Combine(dir, stem + ".cax.log"));
                if (aml.Exists) aml.Delete();
                if (log.Exists) log.Delete();

                bool ok = cax.Export(project, aml, log);
                if (aml.Exists) run.WriteSidecar(aml.FullName, InputKindInfo.For(InputKind.DocOther), project.Name);
                Log((ok ? "Exported hardware (CAx/AML): " : "Hardware CAx export reported issues (see .cax.log): ") + aml.FullName);
            }
            catch (Exception e)
            {
                Log("ERROR exporting hardware (CAx) \n" + e.Message);
            }
        }

        // ============================== helpers ==============================

        private static bool Cancelled() => TiaWorker.CurrentCancellation.IsCancellationRequested;

        /// <summary>
        /// The project's first PLC software and the name of the CPU device item that owns it (the PLC folder name of
        /// the workspace, the same name Pipeline5 writes). Walks every device of the project, groups included.
        /// </summary>
        private PlcSoftware FirstPlc(out string plcName)
        {
            foreach (Device device in CollectAllDevices())
            {
                PlcSoftware sw = FirstPlc(device.DeviceItems, out plcName);
                if (sw != null) return sw;
            }
            plcName = null;
            return null;
        }

        private static PlcSoftware FirstPlc(DeviceItemComposition items, out string plcName)
        {
            foreach (DeviceItem item in items)
            {
                SoftwareContainer container = item.GetService<SoftwareContainer>();
                var sw = container != null ? container.Software as PlcSoftware : null;
                if (sw != null) { plcName = item.Name; return sw; }
                PlcSoftware nested = FirstPlc(item.DeviceItems, out plcName);
                if (nested != null) return nested;
            }
            plcName = null;
            return null;
        }

        /// <summary>Creates an external source (.db/.scl/.awl) and generates its blocks (keeping partial results on error).</summary>
        private void GenerateFromExternalSource(PlcSoftware sw, string path)
        {
            PlcExternalSource source = sw.ExternalSourceGroup.ExternalSources.CreateFromFile(Path.GetFileName(path), path);
            source.GenerateBlocksFromSource(GenerateBlockOption.KeepOnError);
        }

        /// <summary>Exports one object to &lt;targetRoot&gt;\&lt;groupPath&gt;\&lt;name&gt;.xml (a stale same-named file is deleted first) and returns the file.</summary>
        private static FileInfo ExportToXml(Action<FileInfo> export, string targetRoot, string groupPath, string name)
        {
            string dir = groupPath.Length == 0 ? targetRoot : Path.Combine(targetRoot, groupPath.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(dir);
            var file = new FileInfo(Path.Combine(dir, SafeName(name) + ".xml"));
            if (file.Exists) file.Delete();
            export(file);
            file.Refresh();
            return file;
        }

        /// <summary>The header "target" of an exported object: its TIA folder plus group path ("Program blocks/00_Safety").</summary>
        private static string TargetOf(string category, string groupPath) =>
            groupPath.Length == 0 ? category : category + "/" + groupPath;

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

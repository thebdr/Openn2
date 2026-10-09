using System.Diagnostics;
using System.IO;

namespace Openn._10_StandardFunctions
{
    /// <summary>
    /// Default locations Openn5 shares with Pipeline5 in the _Openn5 monorepo, resolved from the exe
    /// location (never hardcoded). The two apps ship as one package and exchange files through the
    /// <c>Shared</c> handoff tree:
    ///
    ///   Shared\HardwareConfigBuilderData\DeviceTypesDatabase.csv      hand-maintained input, both apps (hw/device-types)
    ///   Shared\OutputTree\TiaPortalProjectInterface\BuilderData\        the default WORKSPACE (Pipeline5 -> Openn5; contract v1,
    ///                                                                   VCI shape: &lt;PLC&gt;\Program blocks | PLC tags | PLC data types,
    ///                                                                   Devices &amp; networks, Templates, .openn\workspace.openn.config)
    ///   Shared\OutputTree\TiaPortalProjectInterface\ExportedData\       the default EXPORT root (Openn5 -> Pipeline5, same shape)
    ///
    /// The Workspace tab can point at any other workspace (a Pipeline5 project's
    /// <c>Output[\&lt;system&gt;]\TiaPortalProjectInterface\BuilderData</c>); exports then go to that
    /// workspace's sibling <c>ExportedData</c> (<see cref="ExportRootFor"/>). The legacy BuilderData
    /// folders (HardwareConfiguration, SoftwareBlocks\..., PlcTags) are no longer addressed anywhere:
    /// since 2026-10-09 Openn5 reads only headered files in the VCI shape.
    ///
    /// Exe-local working dirs (the default new-project folder <c>TiaProjects</c>, <c>GeneratedBlocks</c>,
    /// <c>AttributeDumps</c>, <c>Logs</c>) stay next to the exe - they are not part of the handoff.
    /// </summary>
    public static class AppPaths
    {
        /// <summary>Folder of the running exe.</summary>
        public static string AppBaseDir { get; } =
            Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);

        /// <summary>
        /// The monorepo <c>Shared</c> folder. Found by walking up from the exe until a directory
        /// contains <c>Shared\HardwareConfigBuilderData</c> (committed, so it resolves even before
        /// Pipeline5 has produced any OutputTree). In development the exe sits in
        /// <c>Openn5App\bin\Debug</c>, Shared at the repo root; in a shipped package Shared sits
        /// beside the exe. Falls back to <c>&lt;exe&gt;\Shared</c>.
        /// </summary>
        public static string SharedRoot { get; } = ResolveSharedRoot();

        private static string ResolveSharedRoot()
        {
            for (DirectoryInfo dir = new DirectoryInfo(AppBaseDir); dir != null; dir = dir.Parent)
            {
                string candidate = Path.Combine(dir.FullName, "Shared");
                if (Directory.Exists(Path.Combine(candidate, "HardwareConfigBuilderData")) ||
                    Directory.Exists(Path.Combine(candidate, "OutputTree")))
                    return candidate;
            }
            return Path.Combine(AppBaseDir, "Shared");
        }

        /// <summary>The default workspace: Pipeline5's builtin BuilderData (contract v1, VCI shape).</summary>
        public static string BuilderDataDir =>
            Path.Combine(SharedRoot, "OutputTree", "TiaPortalProjectInterface", "BuilderData");

        /// <summary>The default export root (the sibling of the default workspace), read by Pipeline5's TIA-coverage report (phase 920, deferred).</summary>
        public static string ExportedDataDir =>
            Path.Combine(SharedRoot, "OutputTree", "TiaPortalProjectInterface", "ExportedData");

        /// <summary>
        /// The export root that belongs to a workspace: its sibling folder <c>ExportedData</c>
        /// (<c>...\TiaPortalProjectInterface\BuilderData</c> -> <c>...\TiaPortalProjectInterface\ExportedData</c>).
        /// An empty or unusable root falls back to the default export root.
        /// </summary>
        public static string ExportRootFor(string workspaceRoot)
        {
            if (string.IsNullOrWhiteSpace(workspaceRoot)) return ExportedDataDir;
            string full;
            try { full = Path.GetFullPath(workspaceRoot.Trim()).TrimEnd('\\', '/'); }
            catch { return ExportedDataDir; }
            string parent = Path.GetDirectoryName(full);
            return parent == null ? Path.Combine(full, "ExportedData") : Path.Combine(parent, "ExportedData");
        }

        /// <summary>Where the single-block export tool ("Search / Export Blocks" on the Files tab) writes, under the default export root.</summary>
        public static string ExportedBlocksDir => Path.Combine(ExportedDataDir, "SingleBlocks");

        /// <summary>Where the block generator writes its XML before it is imported (exe-local).</summary>
        public static string GeneratedBlocksDir => Path.Combine(AppBaseDir, "GeneratedBlocks");

        /// <summary>The hand-maintained device-type database shared by both apps.</summary>
        public static string DeviceTypesDatabasePath =>
            Path.Combine(SharedRoot, "HardwareConfigBuilderData", "DeviceTypesDatabase.csv");
    }
}

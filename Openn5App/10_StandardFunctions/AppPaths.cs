using System.Diagnostics;
using System.IO;

namespace Openn._10_StandardFunctions
{
    /// <summary>
    /// Resolves the default input/output locations Openn5 shares with Pipeline5 in the
    /// _Openn2 monorepo. The two apps ship as one package and exchange files through the
    /// <c>Shared</c> handoff tree:
    ///
    ///   Shared\HardwareConfigBuilderData\DeviceTypesDatabase.csv   (hand-maintained input, both apps)
    ///   Shared\OutputTree\TiaPortalProjectInterface\
    ///       BuilderData\HardwareConfiguration\        Stations.csv + Modules.csv   (Pipeline5 -> Openn5)
    ///       BuilderData\SoftwareBlocks\CreationInfo\  block-gen + InstanceDBs csv  (Pipeline5 -> Openn5)
    ///       BuilderData\SoftwareBlocks\ImportReady\   *.xml/.db/.scl               (Pipeline5 -> Openn5)
    ///       BuilderData\PlcTags\                      PLCTags.xlsx                 (Pipeline5 -> Openn5)
    ///       ExportedData\SoftwareBlocks\              *.xml                        (Openn5 export sink)
    ///
    /// All paths are resolved from the exe location, so a relocated/renamed checkout still
    /// lines up without editing the defaults by hand. Openn5-internal working dirs (the TIA
    /// project, GeneratedBlocks, AttributeDumps, Logs) stay next to the exe - they are not
    /// part of the Pipeline5 handoff.
    /// </summary>
    public static class AppPaths
    {
        /// <summary>Folder of the running exe.</summary>
        public static string AppBaseDir { get; } =
            Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);

        /// <summary>
        /// The monorepo <c>Shared</c> folder. Found by walking up from the exe until a
        /// directory contains <c>Shared\HardwareConfigBuilderData</c> (committed, so it
        /// resolves even before Pipeline5 has produced any OutputTree). In development the
        /// exe sits in <c>Openn5App\bin\Debug</c>, Shared at the repo root; in a shipped
        /// package Shared sits beside the exe. Falls back to <c>&lt;exe&gt;\Shared</c>.
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

        /// <summary>The Pipeline5 -> Openn5 import surface (kept byte-stable by contract).</summary>
        public static string BuilderDataDir =>
            Path.Combine(SharedRoot, "OutputTree", "TiaPortalProjectInterface", "BuilderData");

        /// <summary>Generated Stations.csv + Modules.csv (Pipeline5 phase 700).</summary>
        public static string HardwareConfigDir =>
            Path.Combine(BuilderDataDir, "HardwareConfiguration");

        /// <summary>Block-generation csv + InstanceDBs.csv + SoftwareBlocks.xlsm (Pipeline5 phase 800).</summary>
        public static string BlocksCreationDir =>
            Path.Combine(BuilderDataDir, "SoftwareBlocks", "CreationInfo");

        /// <summary>Import-ready program blocks (Pipeline5 phases 520/620/800): *.xml/.db/.scl.</summary>
        public static string ImportReadyBlocksDir =>
            Path.Combine(BuilderDataDir, "SoftwareBlocks", "ImportReady");

        /// <summary>One XML per PLC tag table to import (Pipeline5 phase 510; the PLCTags.xlsx beside them is for manual TIA import only).</summary>
        public static string PlcTagsDir =>
            Path.Combine(BuilderDataDir, "PlcTags");

        /// <summary>One XML per user data type to import (future Pipeline5 output; no-op while empty/absent).</summary>
        public static string UserDataTypesImportDir =>
            Path.Combine(BuilderDataDir, "UserDataTypes");

        /// <summary>Root of the Openn5 project-export sink (read by Pipeline5's TIA-coverage report, phase 920).</summary>
        public static string ExportedDataDir =>
            Path.Combine(SharedRoot, "OutputTree", "TiaPortalProjectInterface", "ExportedData");

        /// <summary>Where Openn5 exports software blocks (FB/FC/OB/...) and single blocks pulled out of TIA.</summary>
        public static string ExportedBlocksDir => Path.Combine(ExportedDataDir, "SoftwareBlocks");

        /// <summary>Where Openn5 exports data blocks.</summary>
        public static string ExportedDataBlocksDir => Path.Combine(ExportedDataDir, "DataBlocks");

        /// <summary>Where Openn5 exports user data types (UDTs).</summary>
        public static string ExportedUserDataTypesDir => Path.Combine(ExportedDataDir, "UserDataTypes");

        /// <summary>Where Openn5 exports PLC tag tables (one XML per table).</summary>
        public static string ExportedTagTablesDir => Path.Combine(ExportedDataDir, "TagTables");

        /// <summary>Where Openn5 exports the hardware config (CAx / AutomationML .aml).</summary>
        public static string ExportedHardwareDir => Path.Combine(ExportedDataDir, "HardwareConfiguration");

        /// <summary>The hand-maintained device-type database shared by both apps.</summary>
        public static string DeviceTypesDatabasePath =>
            Path.Combine(SharedRoot, "HardwareConfigBuilderData", "DeviceTypesDatabase.csv");
    }
}

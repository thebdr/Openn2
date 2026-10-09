using System;
using System.Collections.Generic;
using System.IO;
using Openn._10_StandardFunctions;

namespace Openn._01_Constructor
{
    class HardwareDeviceTypesDatabase
    {
        public struct DeviceInfo
        {
            public string deviceType;
            public string identifier;
            public string comment;
            public string customParameters;
            public string srcFileName;
            public int srcRow;
            public DeviceInfo(string _type, string _identifier, string _comment, string _customParameters, string _srcFileName, int _srcRow)
            {
                deviceType = _type;
                identifier = _identifier;
                comment = _comment;
                customParameters = _customParameters;
                srcFileName = _srcFileName;
                srcRow = _srcRow;
            }
        }

        public const string FileName = "DeviceTypesDatabase.csv";

        /// <summary>
        /// Locates DeviceTypesDatabase.csv for a hardware-config folder. The monorepo splits
        /// the two: Pipeline5 writes Stations.csv + Modules.csv into the BuilderData
        /// HardwareConfiguration folder, while the hand-maintained device database is a shared
        /// input under Shared\HardwareConfigBuilderData. So prefer a copy beside the config
        /// (legacy / self-contained / test layout), else fall back to the shared input.
        /// Returns the in-folder path when neither exists, so a "not found" error names the folder.
        /// </summary>
        public static string ResolvePath(string folder)
        {
            string local = Path.Combine(folder, FileName);
            if (File.Exists(local)) return local;
            return File.Exists(AppPaths.DeviceTypesDatabasePath) ? AppPaths.DeviceTypesDatabasePath : local;
        }

        /// <summary>Device types the generation code understands (canonical casing).</summary>
        public static readonly string[] KnownDeviceTypes =
            { "Plc", "PlcCard", "PlcCardCm", "IoDevice", "IoDeviceCard", "Hmi", TransferAreaDeviceType };

        /// <summary>
        /// Module-row model type for PN/PN coupler / I-device transfer areas: not a
        /// plugged module but a TransferArea created on the station's PROFINET
        /// interface. For this type the "Tia Identifier" column holds the Openness
        /// TransferAreaType name (IN, OUT, IN_OUT, PROFISAFE_IN12_OUT6, ...) instead
        /// of an OrderNumber/GSD identifier.
        /// </summary>
        public const string TransferAreaDeviceType = "TransferArea";

        public static Dictionary<string, DeviceInfo> Identifier;

        /// <summary>
        /// Reads the model database. Problems are appended to <paramref name="errors"/>
        /// with file/line references instead of aborting on the first one.
        /// </summary>
        internal static void Read(string folder, IList<string> errors)
        {
            Identifier = new Dictionary<string, DeviceInfo>();

            string filename = ResolvePath(folder);
            CsvTable table = CsvTable.Read(filename);
            foreach (string tableError in table.Errors)
                errors.Add(tableError);
            CheckHeader(table, filename, errors);

            foreach (CsvRow row in table.Rows)
            {
                if (row.Values.Length < 5)
                {
                    errors.Add(Describe(filename, row) + "expected 5 columns (Model Id,Type,Tia Identifier,Comment,Custom Parameters), found " + row.Values.Length);
                    continue;
                }

                string modelId = row.Get(0);
                if (modelId.Length == 0)
                {
                    errors.Add(Describe(filename, row) + "Model Id (column 1) is empty");
                    continue;
                }
                if (Identifier.ContainsKey(modelId))
                {
                    errors.Add(Describe(filename, row) + "duplicate Model Id: " + modelId);
                    continue;
                }

                string deviceType = CanonicalDeviceType(row.Get(1));
                if (deviceType == null)
                {
                    errors.Add(Describe(filename, row) + "unknown device type \"" + row.Get(1) + "\" (expected: " + string.Join(", ", KnownDeviceTypes) + ")");
                    continue;
                }

                Identifier.Add(modelId, new DeviceInfo(deviceType, row.Get(2), row.Get(3), row.Get(4), filename, row.LineNumber));
            }
        }

        /// <summary>
        /// Contract v1: the database opens with a "#!openn" header of kind hw/device-types - the file is
        /// hand-maintained, so it says itself what it is. No header, the wrong kind or a broken header
        /// is a load error (legacy acceptance retired 2026-10-09).
        /// </summary>
        private static void CheckHeader(CsvTable table, string filename, IList<string> errors)
        {
            Openn._00_Contract.OpennHeader header = table.Header;
            Openn._00_Contract.InputKindInfo expected = Openn._00_Contract.InputKindInfo.For(Openn._00_Contract.InputKind.HwDeviceTypes);
            switch (header.Status)
            {
                case Openn._00_Contract.HeaderStatus.Ok:
                    if (header.KindInfo.Kind != Openn._00_Contract.InputKind.HwDeviceTypes)
                        errors.Add(filename + ": header declares kind " + header.KindId + " - expected " + expected.Id);
                    break;
                case Openn._00_Contract.HeaderStatus.Invalid:
                    foreach (string problem in header.Problems) errors.Add(filename + ": header: " + problem);
                    break;
                default:
                    errors.Add(filename + ": no #!openn header - contract v1 requires one. Add these lines at the top of the file: " +
                               "#!openn | #! kind: " + expected.Id + " | #! schema: " + expected.SupportedSchema +
                               " | #! producer: <who maintains it> | #! generated: <ISO date-time> | #!end");
                    break;
            }
        }

        /// <summary>Returns the known type with canonical casing, or null when unknown.</summary>
        private static string CanonicalDeviceType(string type)
        {
            foreach (string known in KnownDeviceTypes)
            {
                if (known.Equals(type, StringComparison.OrdinalIgnoreCase))
                    return known;
            }
            return null;
        }

        private static string Describe(string filename, CsvRow row) =>
            "File: " + filename + " Line: " + row.LineNumber + " - ";
    }
}

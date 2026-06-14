using System;
using System.Collections.Generic;
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

        /// <summary>Device types the generation code understands (canonical casing).</summary>
        public static readonly string[] KnownDeviceTypes =
            { "Plc", "PlcCard", "PlcCardCm", "IoDevice", "IoDeviceCard", "Hmi" };

        public static Dictionary<string, DeviceInfo> Identifier;

        /// <summary>
        /// Reads the model database. Problems are appended to <paramref name="errors"/>
        /// with file/line references instead of aborting on the first one.
        /// </summary>
        internal static void Read(string folder, IList<string> errors)
        {
            Identifier = new Dictionary<string, DeviceInfo>();

            string filename = folder + "\\" + FileName;
            CsvTable table = CsvTable.Read(filename);
            foreach (string tableError in table.Errors)
                errors.Add(tableError);

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

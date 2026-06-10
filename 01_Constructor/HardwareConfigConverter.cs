using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Openn._10_StandardFunctions;

namespace Openn._01_Constructor
{
    /// <summary>
    /// One-time converter from the legacy hardware csv layout
    /// (IoControllersList.csv + wide-format IoDevicesList.csv) to the format-2
    /// long layout (Stations.csv + Modules.csv). Runs automatically when a
    /// configuration folder contains only the legacy files. Legacy files are
    /// left untouched and are ignored once the new files exist.
    /// </summary>
    internal static class HardwareConfigConverter
    {
        private const string LegacyControllersFileName = "IoControllersList.csv";
        private const string LegacyDevicesFileName = "IoDevicesList.csv";

        //legacy wide format: 5 head columns, then groups of 4 columns per submodule
        private const int LegacyHeadColumns = 5;
        private const int LegacySubmoduleColumns = 4;

        public static bool TryConvertLegacyFiles(string folder, out string note)
        {
            note = string.Empty;

            string stationsFile = Path.Combine(folder, HardwareConfigLoader.StationsFileName);
            string modulesFile = Path.Combine(folder, HardwareConfigLoader.ModulesFileName);
            string legacyControllers = Path.Combine(folder, LegacyControllersFileName);
            string legacyDevices = Path.Combine(folder, LegacyDevicesFileName);

            if (File.Exists(stationsFile) || File.Exists(modulesFile)) return false; //new format already present
            if (!File.Exists(legacyControllers) && !File.Exists(legacyDevices)) return false; //nothing to convert

            var stations = new List<string[]>();
            var modules = new List<string[]>();

            if (File.Exists(legacyControllers))
            {
                CsvTable table = CsvTable.Read(legacyControllers, DetectDelimiter(legacyControllers));
                foreach (CsvRow row in table.Rows)
                {
                    //legacy columns: Name;ModelId;IP;Subnet;CustomParameters
                    stations.Add(new[] { LookupRole(row.Get(1)), row.Get(0), row.Get(1), row.Get(2), "", row.Get(3), NormalizeParameterSeparators(row.Get(4)) });
                }
            }

            if (File.Exists(legacyDevices))
            {
                CsvTable table = CsvTable.Read(legacyDevices, DetectDelimiter(legacyDevices));
                foreach (CsvRow row in table.Rows)
                {
                    //legacy head columns: Name;ModelId;IP;Subnet;CustomParameters
                    string stationName = row.Get(0);
                    stations.Add(new[] { LookupRole(row.Get(1)), stationName, row.Get(1), row.Get(2), "", row.Get(3), NormalizeParameterSeparators(row.Get(4)) });

                    int slot = 1;
                    for (int i = LegacyHeadColumns; i + LegacySubmoduleColumns - 1 < row.Values.Length; i += LegacySubmoduleColumns)
                    {
                        //submodule group: Name;ModelId;Addresses(I&Q);CustomParameters
                        if (row.Get(i).Length == 0) continue;

                        string addresses = row.Get(i + 2);
                        string iAddress = addresses, qAddress = addresses;
                        if (addresses.Contains("&"))
                        {
                            string[] split = addresses.Split('&');
                            iAddress = split[0].Trim();
                            qAddress = split[1].Trim();
                        }

                        modules.Add(new[] { stationName, slot.ToString(), row.Get(i), row.Get(i + 1), iAddress, qAddress, NormalizeParameterSeparators(row.Get(i + 3)) });
                        slot++;
                    }
                }
            }

            WriteCsv(stationsFile,
                "# Role;Station Name;Model Id;IP Address;PN Number;Subnet;Custom Parameters  (PN Number empty = last IP octet; parameters separated by |)",
                stations);
            WriteCsv(modulesFile,
                "# Station Name;Slot;Module Name;Model Id;I Addr;Q Addr;Custom Parameters  (Slot = plug order; parameters separated by |)",
                modules);

            note = "Converted legacy hardware csv files to " + HardwareConfigLoader.StationsFileName + " + " +
                   HardwareConfigLoader.ModulesFileName + " in " + folder + " (legacy files are now ignored)";
            return true;
        }

        private static string LookupRole(string modelId)
        {
            HardwareDeviceTypesDatabase.DeviceInfo info;
            if (HardwareDeviceTypesDatabase.Identifier != null &&
                HardwareDeviceTypesDatabase.Identifier.TryGetValue(modelId, out info))
                return info.deviceType;
            return string.Empty; //unknown model: validation reports it after conversion
        }

        /// <summary>Legacy parameter lists were comma separated; format 2 uses '|'.</summary>
        private static string NormalizeParameterSeparators(string parameters) =>
            parameters.IndexOf(CustomParameterParser.Separator) >= 0
                ? parameters
                : parameters.Replace(CustomParameterParser.LegacySeparator, CustomParameterParser.Separator);

        private static char DetectDelimiter(string filePath)
        {
            foreach (string line in File.ReadLines(filePath))
            {
                if (line.Trim().Length == 0) continue;
                return line.Count(c => c == ',') > line.Count(c => c == ';') ? ',' : ';';
            }
            return ';';
        }

        private static void WriteCsv(string filePath, string headerComment, IEnumerable<string[]> rows)
        {
            var content = new StringBuilder();
            content.AppendLine("#!format=" + HardwareConfigLoader.CurrentFormatVersion);
            content.AppendLine(headerComment);
            foreach (string[] row in rows)
                content.AppendLine(string.Join(";", row.Select(Escape)));

            File.WriteAllText(filePath, content.ToString(), new UTF8Encoding(true));
        }

        private static string Escape(string field) =>
            field.IndexOfAny(new[] { ';', '"' }) >= 0 ? "\"" + field.Replace("\"", "\"\"") + "\"" : field;
    }
}

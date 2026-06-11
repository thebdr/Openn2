using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Openn._10_StandardFunctions;

namespace Openn._01_Constructor
{
    /// <summary>Editable module row of Modules.csv.</summary>
    public sealed class ModuleModel
    {
        public string Slot = "";
        public string Name = "";
        public string ModelId = "";
        public string IAddress = "";
        public string QAddress = "";
        public string CustomParameters = "";

        public string DisplayText => "[" + Slot + "] " + Name + "  (" + ModelId + ")";

        /// <summary>Text the explorer's regex search runs against.</summary>
        public string SearchText =>
            Slot + " " + Name + " " + ModelId + " " + IAddress + " " + QAddress + " " + CustomParameters;

        public ModuleModel Clone() => new ModuleModel
        {
            Slot = Slot,
            Name = Name,
            ModelId = ModelId,
            IAddress = IAddress,
            QAddress = QAddress,
            CustomParameters = CustomParameters,
        };
    }

    /// <summary>Editable station row of Stations.csv, with its modules.</summary>
    public sealed class StationModel
    {
        public string Role = "IoDevice";
        public string Name = "";
        public string ModelId = "";
        public string IpAddress = "";
        public string PnNumber = "";
        public string Subnet = "";
        public string CustomParameters = "";
        public List<ModuleModel> Modules = new List<ModuleModel>();

        public string DisplayText => "[" + Role + "] " + Name + (IpAddress.Length > 0 ? "  (" + IpAddress + ")" : "");

        /// <summary>Text the explorer's regex search runs against.</summary>
        public string SearchText =>
            Role + " " + Name + " " + ModelId + " " + IpAddress + " " + PnNumber + " " + Subnet + " " + CustomParameters;

        /// <summary>Deep copy including all modules.</summary>
        public StationModel Clone()
        {
            var copy = new StationModel
            {
                Role = Role,
                Name = Name,
                ModelId = ModelId,
                IpAddress = IpAddress,
                PnNumber = PnNumber,
                Subnet = Subnet,
                CustomParameters = CustomParameters,
            };
            foreach (ModuleModel module in Modules)
                copy.Modules.Add(module.Clone());
            return copy;
        }
    }

    /// <summary>One model database entry, for the editor's dropdowns and info line.</summary>
    public sealed class ModelInfo
    {
        public string Id = "";
        public string DeviceType = "";
        public string Comment = "";
    }

    /// <summary>
    /// Editable in-memory copy of a hardware configuration folder
    /// (Stations.csv + Modules.csv + the model database for lookups).
    /// Unlike HardwareConfigLoader - which is all-or-nothing for generation -
    /// this document accepts incomplete or invalid rows so they can be fixed
    /// in the editor and saved back to csv (format 2, '|' parameter separator).
    /// </summary>
    public sealed class HardwareConfigDocument
    {
        public string Folder { get; private set; }
        public List<StationModel> Stations { get; } = new List<StationModel>();
        public List<string> LoadWarnings { get; } = new List<string>();

        /// <summary>Model database (read locally; does not disturb the loaded app state).</summary>
        public Dictionary<string, ModelInfo> Models { get; } = new Dictionary<string, ModelInfo>(StringComparer.OrdinalIgnoreCase);

        public int ModuleCount
        {
            get
            {
                int count = 0;
                foreach (StationModel station in Stations) count += station.Modules.Count;
                return count;
            }
        }

        public static HardwareConfigDocument Load(string folder)
        {
            var document = new HardwareConfigDocument { Folder = folder };

            CsvTable database = CsvTable.Read(Path.Combine(folder, HardwareDeviceTypesDatabase.FileName));
            foreach (string error in database.Errors) document.LoadWarnings.Add(error);
            foreach (CsvRow row in database.Rows)
            {
                string id = row.Get(0);
                if (id.Length == 0 || document.Models.ContainsKey(id)) continue;
                document.Models.Add(id, new ModelInfo { Id = id, DeviceType = row.Get(1), Comment = row.Get(3) });
            }

            CsvTable stations = CsvTable.Read(Path.Combine(folder, HardwareConfigLoader.StationsFileName));
            foreach (string error in stations.Errors) document.LoadWarnings.Add(error);
            foreach (CsvRow row in stations.Rows)
            {
                document.Stations.Add(new StationModel
                {
                    Role = row.Get(0),
                    Name = row.Get(1),
                    ModelId = row.Get(2),
                    IpAddress = row.Get(3),
                    PnNumber = row.Get(4),
                    Subnet = row.Get(5),
                    CustomParameters = row.Get(6),
                });
            }

            CsvTable modules = CsvTable.Read(Path.Combine(folder, HardwareConfigLoader.ModulesFileName));
            foreach (string error in modules.Errors) document.LoadWarnings.Add(error);
            foreach (CsvRow row in modules.Rows)
            {
                string stationName = row.Get(0);
                StationModel station = document.Stations.FirstOrDefault(s => s.Name.Equals(stationName, StringComparison.OrdinalIgnoreCase));
                if (station == null)
                {
                    //orphan module row: create a stub station so the row stays visible and editable
                    station = new StationModel { Role = "IoDevice", Name = stationName };
                    document.Stations.Add(station);
                    document.LoadWarnings.Add("Modules.csv line " + row.LineNumber + " references unknown station \"" + stationName + "\" - created a stub station");
                }
                station.Modules.Add(new ModuleModel
                {
                    Slot = row.Get(1),
                    Name = row.Get(2),
                    ModelId = row.Get(3),
                    IAddress = row.Get(4),
                    QAddress = row.Get(5),
                    CustomParameters = row.Get(6),
                });
            }

            return document;
        }

        /// <summary>Writes to a different folder and makes it the document's folder ("save as").</summary>
        public void SaveTo(string folder)
        {
            Folder = folder;
            Save();
        }

        /// <summary>
        /// Writes Stations.csv + Modules.csv (format 2) back to the folder.
        /// Stations keep their list order; module rows are grouped per station.
        /// </summary>
        public void Save()
        {
            var stationsContent = new StringBuilder();
            stationsContent.AppendLine("#!format=" + HardwareConfigLoader.CurrentFormatVersion);
            stationsContent.AppendLine("# Role;Station Name;Model Id;IP Address;PN Number;Subnet;Custom Parameters  (PN Number empty = last IP octet; parameters separated by |)");

            var modulesContent = new StringBuilder();
            modulesContent.AppendLine("#!format=" + HardwareConfigLoader.CurrentFormatVersion);
            modulesContent.AppendLine("# Station Name;Slot;Module Name;Model Id;I Addr;Q Addr;Custom Parameters  (Slot = plug order; parameters separated by |)");

            foreach (StationModel station in Stations)
            {
                stationsContent.AppendLine(JoinCsv(station.Role, station.Name, station.ModelId, station.IpAddress, station.PnNumber, station.Subnet, station.CustomParameters));
                foreach (ModuleModel module in station.Modules)
                    modulesContent.AppendLine(JoinCsv(station.Name, module.Slot, module.Name, module.ModelId, module.IAddress, module.QAddress, module.CustomParameters));
            }

            var encoding = new UTF8Encoding(true);
            File.WriteAllText(Path.Combine(Folder, HardwareConfigLoader.StationsFileName), stationsContent.ToString(), encoding);
            File.WriteAllText(Path.Combine(Folder, HardwareConfigLoader.ModulesFileName), modulesContent.ToString(), encoding);
        }

        /// <summary>"name" if free, otherwise "name_2", "name_3", ...</summary>
        public static string MakeUniqueName(string baseName, IEnumerable<string> existingNames)
        {
            var names = new HashSet<string>(existingNames, StringComparer.OrdinalIgnoreCase);
            if (!names.Contains(baseName)) return baseName;
            for (int i = 2; ; i++)
            {
                string candidate = baseName + "_" + i;
                if (!names.Contains(candidate)) return candidate;
            }
        }

        /// <summary>Next numeric slot after the station's highest one.</summary>
        public static string NextFreeSlot(StationModel station)
        {
            int highest = 0;
            foreach (ModuleModel module in station.Modules)
            {
                int slot;
                if (int.TryParse(module.Slot, out slot) && slot > highest) highest = slot;
            }
            return (highest + 1).ToString();
        }

        private static string JoinCsv(params string[] fields) => string.Join(";", fields.Select(Escape));

        private static string Escape(string field)
        {
            field = field ?? "";
            return field.IndexOfAny(new[] { ';', '"' }) >= 0
                ? "\"" + field.Replace("\"", "\"\"") + "\""
                : field;
        }
    }
}

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Openn._10_StandardFunctions;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._01_Constructor
{
    /// <summary>
    /// Loads a hardware configuration folder (format 2):
    ///   DeviceTypesDatabase.csv - model database
    ///   Stations.csv            - one row per station (Role: Plc / PlcCardCm / IoDevice)
    ///   Modules.csv             - one row per plugged module, referencing its station
    /// Legacy folders (IoControllersList.csv + wide IoDevicesList.csv) are converted
    /// automatically on first load. The whole configuration is validated before the
    /// lists are published: on any error nothing is loaded, so the generation code
    /// never sees a half-valid configuration.
    /// </summary>
    internal static class HardwareConfigLoader
    {
        public const int CurrentFormatVersion = 2;
        public const string StationsFileName = "Stations.csv";
        public const string ModulesFileName = "Modules.csv";

        public static bool LoadAll(string folder)
        {
            var errors = new List<string>();

            HardwareIoControllers.DevicesList = new List<HardwareIoControllers._Controller>();
            HardwareIoDevices.DevicesList = new List<Tuple<HardwareIoDevices._Device, IList<HardwareIoDevices._Submodule>>>();

            HardwareDeviceTypesDatabase.Read(folder, errors);

            string conversionNote;
            if (HardwareConfigConverter.TryConvertLegacyFiles(folder, out conversionNote))
                Log(conversionNote);

            CsvTable stations = CsvTable.Read(Path.Combine(folder, StationsFileName));
            CsvTable modules = CsvTable.Read(Path.Combine(folder, ModulesFileName));
            foreach (string e in stations.Errors) errors.Add(e);
            foreach (string e in modules.Errors) errors.Add(e);
            if (stations.FormatVersion > CurrentFormatVersion)
                errors.Add(StationsFileName + " declares format " + stations.FormatVersion + " but this version of Openn2 supports up to format " + CurrentFormatVersion);
            if (modules.FormatVersion > CurrentFormatVersion)
                errors.Add(ModulesFileName + " declares format " + modules.FormatVersion + " but this version of Openn2 supports up to format " + CurrentFormatVersion);

            var controllers = new List<HardwareIoControllers._Controller>();
            var devices = new List<HardwareIoDevices._Device>();
            ParseStations(stations, errors, controllers, devices);

            var modulesByStation = ParseModules(modules, devices, errors);

            if (errors.Count > 0)
            {
                Log("Hardware configuration NOT loaded - " + errors.Count + " problem(s) found:");
                foreach (string error in errors)
                    Log("  " + error);
                HardwareDeviceTypesDatabase.Identifier = new Dictionary<string, HardwareDeviceTypesDatabase.DeviceInfo>(); //all-or-nothing: block generation
                return false;
            }

            HardwareIoControllers.DevicesList = controllers;
            foreach (HardwareIoDevices._Device device in devices)
            {
                List<HardwareIoDevices._Submodule> deviceModules;
                if (!modulesByStation.TryGetValue(device.name, out deviceModules))
                    deviceModules = new List<HardwareIoDevices._Submodule>();
                deviceModules.Sort((a, b) => int.Parse(a.position).CompareTo(int.Parse(b.position)));
                HardwareIoDevices.DevicesList.Add(new Tuple<HardwareIoDevices._Device, IList<HardwareIoDevices._Submodule>>(device, deviceModules));
            }

            Log("Hardware configuration loaded: " + HardwareDeviceTypesDatabase.Identifier.Count + " device types, " +
                controllers.Count + " controller(s), " + devices.Count + " IO device(s), " +
                modulesByStation.Values.Sum(m => m.Count) + " module(s)");
            return true;
        }

        /// <summary>
        /// Stations.csv columns: Role;Station Name;Model Id;IP Address;PN Number;Subnet;Custom Parameters
        /// </summary>
        private static void ParseStations(CsvTable stations, List<string> errors,
            List<HardwareIoControllers._Controller> controllers, List<HardwareIoDevices._Device> devices)
        {
            var stationNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var usedIps = new HashSet<string>();

            foreach (CsvRow row in stations.Rows)
            {
                string where = Describe(stations.FilePath, row);

                if (row.Values.Length < 6)
                {
                    errors.Add(where + "expected at least 6 columns (Role;Station Name;Model Id;IP Address;PN Number;Subnet;Custom Parameters), found " + row.Values.Length);
                    continue;
                }

                string role = row.Get(0), name = row.Get(1), modelId = row.Get(2),
                       ip = row.Get(3), pnNumber = row.Get(4), subnet = row.Get(5), customParameters = row.Get(6);

                if (name.Length == 0)
                    errors.Add(where + "Station Name is empty");
                else if (!stationNames.Add(name))
                    errors.Add(where + "duplicate Station Name: " + name);

                HardwareDeviceTypesDatabase.DeviceInfo dbInfo;
                bool modelKnown = HardwareDeviceTypesDatabase.Identifier.TryGetValue(modelId, out dbInfo);
                if (!modelKnown)
                    errors.Add(where + "Model Id \"" + modelId + "\" not found in " + HardwareDeviceTypesDatabase.FileName);
                else if (!dbInfo.deviceType.Equals(role, StringComparison.OrdinalIgnoreCase))
                    errors.Add(where + "Role is \"" + role + "\" but the database defines model " + modelId + " as \"" + dbInfo.deviceType + "\"");

                if (Uri.CheckHostName(ip) != UriHostNameType.IPv4)
                    errors.Add(where + "invalid IPv4 address: \"" + ip + "\"");
                else if (!usedIps.Add(ip))
                    errors.Add(where + "duplicate IP address: " + ip);

                if (subnet.Length == 0)
                    errors.Add(where + "Subnet is empty");

                int pnValue;
                if (pnNumber.Length > 0 && (!int.TryParse(pnNumber, out pnValue) || pnValue < 1))
                    errors.Add(where + "PN Number must be a positive integer or empty, found \"" + pnNumber + "\"");

                if (role.Equals("Plc", StringComparison.OrdinalIgnoreCase) || role.Equals("PlcCardCm", StringComparison.OrdinalIgnoreCase))
                {
                    if (pnNumber.Length > 0)
                        errors.Add(where + "PN Number applies to IoDevice stations only");
                    controllers.Add(new HardwareIoControllers._Controller(name, modelId, ip, subnet, customParameters, stations.FilePath, row.LineNumber));
                }
                else if (role.Equals("IoDevice", StringComparison.OrdinalIgnoreCase))
                {
                    devices.Add(new HardwareIoDevices._Device(name, modelId, ip, pnNumber, subnet, customParameters, stations.FilePath, row.LineNumber));
                }
                else
                {
                    errors.Add(where + "unsupported Role \"" + role + "\" (expected: Plc, PlcCardCm or IoDevice)");
                }
            }

            //the generation code attaches PlcCardCm entries to the first controller, which must be the Plc
            controllers.Sort((a, b) => ControllerOrder(a).CompareTo(ControllerOrder(b)));
            if (!controllers.Any(c => ControllerOrder(c) == 0))
                errors.Add(stations.FilePath + " - no station with Role \"Plc\" found; exactly the first controller must be a Plc");

            //each controller spans its own subnet/IO system; names must be unique
            var controllerSubnets = new HashSet<string>();
            foreach (HardwareIoControllers._Controller controller in controllers)
            {
                if (controller.subnetName.Length > 0 && !controllerSubnets.Add(controller.subnetName))
                    errors.Add("File: " + controller.srcFileName + " Line: " + controller.srcRow + " - duplicate controller Subnet \"" + controller.subnetName + "\" (each controller needs its own subnet)");
            }

            //devices must connect to a subnet some controller provides
            foreach (HardwareIoDevices._Device device in devices)
            {
                if (device.subnet.Length > 0 && !controllerSubnets.Contains(device.subnet))
                    errors.Add("File: " + device.srcFileName + " Line: " + device.srcRow + " - Subnet \"" + device.subnet + "\" of station " + device.name + " is not provided by any controller");
            }
        }

        private static int ControllerOrder(HardwareIoControllers._Controller controller)
        {
            HardwareDeviceTypesDatabase.DeviceInfo dbInfo;
            if (HardwareDeviceTypesDatabase.Identifier.TryGetValue(controller.identifier, out dbInfo) && dbInfo.deviceType == "Plc")
                return 0;
            return 1;
        }

        /// <summary>
        /// Modules.csv columns: Station Name;Slot;Module Name;Model Id;I Addr;Q Addr;Custom Parameters
        /// </summary>
        private static Dictionary<string, List<HardwareIoDevices._Submodule>> ParseModules(
            CsvTable modules, List<HardwareIoDevices._Device> devices, List<string> errors)
        {
            var modulesByStation = new Dictionary<string, List<HardwareIoDevices._Submodule>>(StringComparer.OrdinalIgnoreCase);
            var slotsByStation = new Dictionary<string, HashSet<int>>(StringComparer.OrdinalIgnoreCase);
            var deviceNames = new HashSet<string>(devices.Select(d => d.name), StringComparer.OrdinalIgnoreCase);

            foreach (CsvRow row in modules.Rows)
            {
                string where = Describe(modules.FilePath, row);

                if (row.Values.Length < 6)
                {
                    errors.Add(where + "expected at least 6 columns (Station Name;Slot;Module Name;Model Id;I Addr;Q Addr;Custom Parameters), found " + row.Values.Length);
                    continue;
                }

                string station = row.Get(0), slotText = row.Get(1), name = row.Get(2),
                       modelId = row.Get(3), iAddress = row.Get(4), qAddress = row.Get(5), customParameters = row.Get(6);

                if (!deviceNames.Contains(station))
                    errors.Add(where + "Station Name \"" + station + "\" does not match any IoDevice station in " + StationsFileName);

                if (name.Length == 0)
                    errors.Add(where + "Module Name is empty");

                int slot;
                if (!int.TryParse(slotText, out slot) || slot < 1)
                {
                    errors.Add(where + "Slot must be a positive integer, found \"" + slotText + "\"");
                    slot = 0;
                }
                else
                {
                    HashSet<int> usedSlots;
                    if (!slotsByStation.TryGetValue(station, out usedSlots))
                        slotsByStation.Add(station, usedSlots = new HashSet<int>());
                    if (!usedSlots.Add(slot))
                        errors.Add(where + "duplicate Slot " + slot + " for station " + station);
                }

                HardwareDeviceTypesDatabase.DeviceInfo dbInfo;
                if (!HardwareDeviceTypesDatabase.Identifier.TryGetValue(modelId, out dbInfo))
                    errors.Add(where + "Model Id \"" + modelId + "\" not found in " + HardwareDeviceTypesDatabase.FileName);
                else if (dbInfo.deviceType != "IoDeviceCard")
                    errors.Add(where + "model " + modelId + " is of type \"" + dbInfo.deviceType + "\" but modules must be \"IoDeviceCard\"");

                int address;
                if (iAddress.Length > 0 && (!int.TryParse(iAddress, out address) || address < 0))
                    errors.Add(where + "I Addr must be a non-negative integer or empty, found \"" + iAddress + "\"");
                if (qAddress.Length > 0 && (!int.TryParse(qAddress, out address) || address < 0))
                    errors.Add(where + "Q Addr must be a non-negative integer or empty, found \"" + qAddress + "\"");

                List<HardwareIoDevices._Submodule> stationModules;
                if (!modulesByStation.TryGetValue(station, out stationModules))
                    modulesByStation.Add(station, stationModules = new List<HardwareIoDevices._Submodule>());
                stationModules.Add(new HardwareIoDevices._Submodule(name, modelId, slot.ToString(), iAddress, qAddress, customParameters));
            }

            return modulesByStation;
        }

        private static string Describe(string filename, CsvRow row) =>
            "File: " + filename + " Line: " + row.LineNumber + " - ";
    }
}

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Openn._10_StandardFunctions;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._01_Constructor
{
    /// <summary>
    /// Loads a hardware configuration folder (format 2):
    ///   DeviceTypesDatabase.xlsx/.csv - model database (shared input; the xlsx is preferred)
    ///   Stations.csv            - one row per station (Role: Plc / PlcCardCm / IoDevice)
    ///   Modules.csv             - one row per plugged module, referencing its station
    ///                             (a row whose model is of type TransferArea is a PN/PN
    ///                             coupler / I-device transfer area, not a plugged module)
    /// The whole configuration is validated before the lists are published: on any
    /// error nothing is loaded, so the generation code never sees a half-valid
    /// configuration. (Pre-format-2 folders are not supported - the old stable
    /// application version handles those.)
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

            CsvTable stations = CsvTable.Read(Path.Combine(folder, StationsFileName));
            CsvTable modules = CsvTable.Read(Path.Combine(folder, ModulesFileName));
            foreach (string e in stations.Errors) errors.Add(e);
            foreach (string e in modules.Errors) errors.Add(e);
            if (stations.FormatVersion > CurrentFormatVersion)
                errors.Add(StationsFileName + " declares format " + stations.FormatVersion + " but this version of Openn5 supports up to format " + CurrentFormatVersion);
            if (modules.FormatVersion > CurrentFormatVersion)
                errors.Add(ModulesFileName + " declares format " + modules.FormatVersion + " but this version of Openn5 supports up to format " + CurrentFormatVersion);
            CheckHeader(stations, StationsFileName, Openn._00_Contract.InputKind.HwStations, errors);
            CheckHeader(modules, ModulesFileName, Openn._00_Contract.InputKind.HwModules, errors);

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
        /// Contract v1: the csv opens with a "#!openn" header declaring its kind. A valid header of
        /// another kind, a newer schema, the bare legacy "#!format=2" tag or no header at all are
        /// errors (all-or-nothing like every other loader check). Legacy acceptance was retired on
        /// 2026-10-09: Pipeline5 stamps every file it writes, the hardware editor stamps what it saves.
        /// </summary>
        private static void CheckHeader(CsvTable table, string fileName, Openn._00_Contract.InputKind expectedKind, IList<string> errors)
        {
            Openn._00_Contract.OpennHeader header = table.Header;
            Openn._00_Contract.InputKindInfo expected = Openn._00_Contract.InputKindInfo.For(expectedKind);
            switch (header.Status)
            {
                case Openn._00_Contract.HeaderStatus.Ok:
                    if (header.KindInfo.Kind != expectedKind)
                        errors.Add(fileName + " header declares kind " + header.KindId + " - expected " + expected.Id);
                    break;
                case Openn._00_Contract.HeaderStatus.Invalid:
                    foreach (string problem in header.Problems) errors.Add(fileName + " header: " + problem);
                    break;
                case Openn._00_Contract.HeaderStatus.Legacy:
                    errors.Add(fileName + " carries only the legacy #!format=" + header.LegacyFormat + " tag - contract v1 requires a #!openn header (kind: " + expected.Id +
                               "); regenerate it with Pipeline5 5.0+ or add the header (the hardware editor writes it on save)");
                    break;
                default:
                    errors.Add(fileName + " has no #!openn header - contract v1 requires one (kind: " + expected.Id + "); regenerate it with Pipeline5 5.0+ or add the header");
                    break;
            }
        }

        /// <summary>
        /// Stations.csv columns: Role,Station Name,Model Id,IP Address,PN Number,Subnet,Custom Parameters
        /// (+ optional: 8 = Group, a device-group path "folder/sub/..." the generation
        /// find-or-creates in the project tree (empty = ungrouped); 9 = Connector, picking the interface /
        /// IO connector on devices that expose more than one - ignored elsewhere. PL emits the
        /// I/O-List cell VERBATIM there, e.g. "X1-P1 R" = port + direction; the loader extracts
        /// the bare X&lt;n&gt; designation per the coordination brief.)
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
                    errors.Add(where + "expected at least 6 columns (Role,Station Name,Model Id,IP Address,PN Number,Subnet,Custom Parameters), found " + row.Values.Length);
                    continue;
                }

                string role = row.Get(0), name = row.Get(1), modelId = row.Get(2),
                       ip = row.Get(3), pnNumber = row.Get(4), subnet = row.Get(5), customParameters = row.Get(6),
                       group = row.Get(7), connectorCell = row.Get(8), connector = ExtractConnector(connectorCell);

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

                if (connectorCell.Length > 0 && connector.Length == 0)
                    errors.Add(where + "Connector must carry an interface designation like X1 / X01 (the verbatim I/O-List cell, e.g. \"X1-P1 R\", is fine), found \"" + connectorCell + "\"");

                int pnValue;
                if (pnNumber.Length > 0 && (!int.TryParse(pnNumber, out pnValue) || pnValue < 1))
                    errors.Add(where + "PN Number must be a positive integer or empty, found \"" + pnNumber + "\"");

                if (modelKnown)
                    ValidateCustomParameters(dbInfo.customParameters, customParameters, ip, where, errors);

                if (role.Equals("Plc", StringComparison.OrdinalIgnoreCase) || role.Equals("PlcCardCm", StringComparison.OrdinalIgnoreCase))
                {
                    if (pnNumber.Length > 0)
                        errors.Add(where + "PN Number applies to IoDevice stations only");
                    controllers.Add(new HardwareIoControllers._Controller(name, modelId, ip, subnet, connector, group, customParameters, stations.FilePath, row.LineNumber));
                }
                else if (role.Equals("IoDevice", StringComparison.OrdinalIgnoreCase))
                {
                    devices.Add(new HardwareIoDevices._Device(name, modelId, ip, pnNumber, subnet, connector, group, customParameters, stations.FilePath, row.LineNumber));
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

            //PROFINET device numbers must be unique per subnet (explicit PN Number, else the
            //default = the last IP octet). TIA rejects the duplicate only at generation time,
            //so catch the collision here with file/line context instead.
            var pnNumbersBySubnet = new Dictionary<string, Dictionary<int, string>>(StringComparer.OrdinalIgnoreCase);
            foreach (HardwareIoDevices._Device device in devices)
            {
                if (device.subnet.Length == 0 || Uri.CheckHostName(device.IP) != UriHostNameType.IPv4) continue; //already reported
                int pnValue;
                if (device.pnNumber.Length > 0)
                {
                    if (!int.TryParse(device.pnNumber, out pnValue)) continue; //already reported
                }
                else
                {
                    pnValue = int.Parse(device.IP.Split('.')[3]);
                }

                Dictionary<int, string> usedNumbers;
                if (!pnNumbersBySubnet.TryGetValue(device.subnet, out usedNumbers))
                    pnNumbersBySubnet.Add(device.subnet, usedNumbers = new Dictionary<int, string>());
                string otherStation;
                if (usedNumbers.TryGetValue(pnValue, out otherStation))
                    errors.Add("File: " + device.srcFileName + " Line: " + device.srcRow + " - PROFINET device number " + pnValue +
                               " on subnet \"" + device.subnet + "\" is already taken by station " + otherStation +
                               " (PN Number defaults to the last IP octet - set an explicit, unique PN Number)");
                else
                    usedNumbers.Add(pnValue, device.name);
            }
        }

        /// <summary>
        /// The bare X-designation inside a Stations.csv Connector cell. PL emits the I/O-List
        /// cell VERBATIM (e.g. "X1-P1 R" = port + direction; see PL4_OP4_coordination.md) - the
        /// OP side extracts the X&lt;n&gt; token; "" when the cell is empty or carries none.
        /// </summary>
        internal static string ExtractConnector(string raw)
        {
            Match match = Regex.Match(raw ?? "", "(?<![0-9A-Za-z])[Xx][0-9]{1,2}(?![0-9])");
            return match.Success ? match.Value : "";
        }

        private static int ControllerOrder(HardwareIoControllers._Controller controller)
        {
            HardwareDeviceTypesDatabase.DeviceInfo dbInfo;
            if (HardwareDeviceTypesDatabase.Identifier.TryGetValue(controller.identifier, out dbInfo) && dbInfo.deviceType == "Plc")
                return 0;
            return 1;
        }

        /// <summary>
        /// Modules.csv columns: Station Name,Slot,Module Name,Model Id,I Addr,Q Addr,Custom Parameters
        /// </summary>
        private static Dictionary<string, List<HardwareIoDevices._Submodule>> ParseModules(
            CsvTable modules, List<HardwareIoDevices._Device> devices, List<string> errors)
        {
            var modulesByStation = new Dictionary<string, List<HardwareIoDevices._Submodule>>(StringComparer.OrdinalIgnoreCase);
            var slotsByStation = new Dictionary<string, HashSet<int>>(StringComparer.OrdinalIgnoreCase);

            var deviceByName = new Dictionary<string, HardwareIoDevices._Device>(StringComparer.OrdinalIgnoreCase);
            foreach (HardwareIoDevices._Device device in devices)
            {
                if (!deviceByName.ContainsKey(device.name))
                    deviceByName.Add(device.name, device);
            }

            foreach (CsvRow row in modules.Rows)
            {
                string where = Describe(modules.FilePath, row);

                if (row.Values.Length < 6)
                {
                    errors.Add(where + "expected at least 6 columns (Station Name,Slot,Module Name,Model Id,I Addr,Q Addr,Custom Parameters), found " + row.Values.Length);
                    continue;
                }

                string station = row.Get(0), slotText = row.Get(1), name = row.Get(2),
                       modelId = row.Get(3), iAddress = row.Get(4), qAddress = row.Get(5), customParameters = row.Get(6);

                HardwareIoDevices._Device stationDevice;
                bool stationKnown = deviceByName.TryGetValue(station, out stationDevice);
                if (!stationKnown)
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
                bool modelKnown = HardwareDeviceTypesDatabase.Identifier.TryGetValue(modelId, out dbInfo);
                if (!modelKnown)
                    errors.Add(where + "Model Id \"" + modelId + "\" not found in " + HardwareDeviceTypesDatabase.FileName);
                else if (dbInfo.deviceType != "IoDeviceCard" && dbInfo.deviceType != HardwareDeviceTypesDatabase.TransferAreaDeviceType)
                    errors.Add(where + "model " + modelId + " is of type \"" + dbInfo.deviceType + "\" but modules must be \"IoDeviceCard\" or \"" +
                        HardwareDeviceTypesDatabase.TransferAreaDeviceType + "\"");
                else if (dbInfo.deviceType == HardwareDeviceTypesDatabase.TransferAreaDeviceType && dbInfo.identifier.Length == 0)
                    errors.Add(where + "model " + modelId + " is a " + HardwareDeviceTypesDatabase.TransferAreaDeviceType +
                        " but its Tia Identifier (the transfer area type: IN, OUT, IN_OUT, ...) is empty");

                if (modelKnown)
                    ValidateCustomParameters(dbInfo.customParameters, customParameters, stationKnown ? stationDevice.IP : string.Empty, where, errors);

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

        /// <summary>
        /// Parses the merged custom parameters only to surface syntax problems at
        /// load time; the generation code re-parses them when applying.
        /// </summary>
        private static void ValidateCustomParameters(string globalParameters, string specificParameters, string ipAddress, string where, List<string> errors)
        {
            var parameterErrors = new List<string>();
            CustomParameterParser.Parse(globalParameters, specificParameters, ipAddress, parameterErrors);
            foreach (string parameterError in parameterErrors)
                errors.Add(where + "custom parameter: " + parameterError);
        }

        private static string Describe(string filename, CsvRow row) =>
            "File: " + filename + " Line: " + row.LineNumber + " - ";
    }
}

using System;
using System.Collections.Generic;
using System.Linq;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Openn._01_Constructor;
using static Openn._10_StandardFunctions.LogsManager;

using HwDb = Openn._01_Constructor.HardwareDeviceTypesDatabase;
using HwIoC = Openn._01_Constructor.HardwareIoControllers;
using HwIoD = Openn._01_Constructor.HardwareIoDevices;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Hardware generation: builds the PROFINET topology described by the loaded
    /// csv configuration (HardwareConfigLoader) inside the attached project -
    /// I/O controllers (Plc + communication modules), subnets/IO systems, I/O
    /// devices, their plugged modules, I/O addresses and custom parameters.
    /// </summary>
    public partial class TiaPortalOpenness
    {
        #region Hardware generation state

        /// <summary>
        /// The controllers of the current generation run, in configuration order.
        /// Item1 is set for Plc stations, Item2 for plugged communication modules;
        /// index 0 is always the Plc (guaranteed by the loader and CreateDevices).
        /// </summary>
        private IList<Tuple<Device, DeviceItem>> ioControllers = null;

        /// <summary>Subnet + IO system per subnet name; I/O devices connect through this map.</summary>
        private Dictionary<string, Tuple<Subnet, IoSystem>> ioSystems;

        /// <summary>Find-or-created device groups of the current run, by Group path.</summary>
        private Dictionary<string, DeviceUserGroup> deviceGroupCache;

        /// <summary>
        /// The stations the last generation run created, in creation order - their slots on the ONE row Openness puts
        /// them on in the network view ("Re-arrange devices" drags them from there, one row per Stations.csv Group).
        /// Controllers only in create-new mode.
        /// </summary>
        public List<NetworkViewLayout.Station> LastCreatedStations { get; } = new List<NetworkViewLayout.Station>();

        #endregion Hardware generation state

        /// <summary>
        /// Entry point of the hardware generation. Either creates the I/O controllers
        /// from scratch or attaches to controllers that already exist in the project,
        /// then creates all I/O devices and stamps Author/Comment on every device.
        /// Returns true when the run went through to the end, false when it stopped
        /// early (precondition failed, controller missing, cancelled) - every reason is logged.
        /// </summary>
        public bool CreateDevices(bool? CreateNewIoControllers = true, bool wirePorts = false)
        {
            if (project == null)
            {
                Log("ERROR \n TIA PROJECT not attached.");
                return false;
            }

            if (HwIoC.DevicesList == null || HwIoC.DevicesList.Count == 0)
            {
                Log("ERROR \n No I/O Controllers loaded - import a valid hardware configuration first.");
                return false;
            }

            //check if first I/O Controller is of Plc Type
            if (!HwDb.Identifier[HwIoC.DevicesList[0].identifier].deviceType.Equals("Plc", StringComparison.OrdinalIgnoreCase))
            {
                Log("IoController : " + HwIoC.DevicesList[0].name + " is not of \"Plc\" type." + "\n" +
                                "Line: " + HwIoC.DevicesList[0].srcRow.ToString() + " File: " + HwIoC.DevicesList[0].srcFileName + "\n" +
                                "First device in Csv file must be a Plc");
                return false;
            }

            deviceGroupCache = new Dictionary<string, DeviceUserGroup>(StringComparer.OrdinalIgnoreCase);
            LastCreatedStations.Clear();

            //generating while a TIA editor is open re-creates the stale per-device
            //"IO device not connected to an IO system" compile messages - CONFIRMED 2026-07:
            //with the editors closed they are gone for good. Openness has no close-editor API,
            //so the user confirms the tabs are closed; this code never opens the network view -
            //open it manually after the run to inspect the result.
            if (!ConfirmEditorsClosed())
            {
                Log("Hardware generation CANCELLED at the checkpoint - close every TIA Portal editor tab, then generate again (nothing was changed)");
                TiaWorker.CancelCurrentOperation(); //a workspace import reports its hardware run as cancelled and stops
                return false;
            }

            if (CreateNewIoControllers == true)
            {
                if (CreateIoControllers(project) == false)
                    return false;
            }
            else
            {
                if (AttachIoControllers(project) == false)
                    return false;
            }

            CreateIoDevices(HwIoD.DevicesList);

            if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                return false; //the loop that observed the cancel has already logged it

            if (wirePorts)
                WirePorts();
            else if (HwIoC.DevicesList.Any(c => c.topology.Count > 0) || HwIoD.DevicesList.Any(d => d.Item1.topology.Count > 0))
                Log("Topology links in Stations.csv NOT wired - tick \"Wire PROFINET ports\" to apply them");

            foreach (var a in project.UngroupedDevicesGroup.Devices)
            {
                SetAttribute(a.DeviceItems, "Author", "bdragoi");
                SetAttribute(a.DeviceItems, "Comment", "Tia Portal Openness");
            }
            return true;
        }

        #region I/O controllers

        /// <summary>
        /// "Use existing controllers" mode: looks the configured controllers up in
        /// the project (Plc as a device, communication modules as items of the Plc)
        /// and adopts/renames their subnets and IO systems. Returns false when a
        /// configured controller is missing from the project.
        /// </summary>
        private bool AttachIoControllers(Project project)
        {
            ioControllers = new List<Tuple<Device, DeviceItem>>();
            ioSystems = new Dictionary<string, Tuple<Subnet, IoSystem>>();
            NetworkInterface netInterface = null;

            foreach (var ioC in HwIoC.DevicesList)
            {
                if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                {
                    Log("Hardware generation CANCELLED while attaching IO controllers");
                    return false;
                }

                //search for PLCs
                if (HwDb.Identifier[ioC.identifier].deviceType.Equals("Plc", StringComparison.OrdinalIgnoreCase))
                {
                    Device device = FindDevice(ioC.name, project.Devices) ?? FindDeviceInGroups(ioC.name, project.DeviceGroups);
                    if (device != null)
                    {
                        ioControllers.Add(new Tuple<Device, DeviceItem>(device, null));
                        netInterface = FindNetworkInterface(device.DeviceItems, ioC.connector, ioC.name);
                    }
                    else
                    {
                        Log("IoController (Plc) : " + ioC.name + " not found in project" + "\n" +
                            "Line: " + ioC.srcRow.ToString() + " File: " + ioC.srcFileName);
                        return false;
                    }
                }
                //search for I/O Cards (Communication Module)
                else if (HwDb.Identifier[ioC.identifier].deviceType.Equals("PlcCardCm", StringComparison.OrdinalIgnoreCase))
                {
                    DeviceItem device = FindDeviceItem(ioC.name, ioControllers[0].Item1.DeviceItems);
                    if (device != null)
                    {
                        ioControllers.Add(new Tuple<Device, DeviceItem>(null, device));
                        netInterface = FindNetworkInterface(device.DeviceItems, ioC.connector, ioC.name);
                    }
                    else
                    {
                        Log("IoController (PlcCardCm) : " + ioC.name + " not found in project" + "\n" +
                            "Line: " + ioC.srcRow.ToString() + " File: " + ioC.srcFileName);
                        return false;
                    }
                }

                if (netInterface == null)
                {
                    Log("ERROR attaching IoController " + ioC.name + ": no Ethernet network interface found on it" + "\n" +
                        "Line: " + ioC.srcRow.ToString() + " File: " + ioC.srcFileName);
                    return false;
                }
                if (AdoptIoSystem(project, netInterface, ioC) == false)
                    return false;
            }
            return true;
        }

        /// <summary>
        /// "Create new controllers" mode: creates the Plc, plugs the communication
        /// modules into its rack, then creates subnet + IO system per controller and
        /// assigns the configured IP address. Returns false when the generation must
        /// abort (nothing is saved - close the project in TIA without saving to roll back).
        /// </summary>
        private bool CreateIoControllers(Project project)
        {
            ioControllers = new List<Tuple<Device, DeviceItem>>();
            ioSystems = new Dictionary<string, Tuple<Subnet, IoSystem>>();
            NetworkInterface netInterface = null;

            foreach (var c in HwIoC.DevicesList)
            {
                if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                {
                    Log("Hardware generation CANCELLED while creating IO controllers (project not saved - close it in TIA without saving to roll back)");
                    return false;
                }

                if (HwDb.Identifier[c.identifier].deviceType == "Plc") //create Plc
                {
                    DeviceUserGroup plcGroup = ResolveDeviceGroup(project, c.group);
                    var device = (plcGroup != null ? plcGroup.Devices : project.Devices)
                        .CreateWithItem(HwDb.Identifier[c.identifier].identifier, c.name, c.name);
                    ioControllers.Add(new Tuple<Device, DeviceItem>(device, null));
                    LastCreatedStations.Add(new NetworkViewLayout.Station { Name = device.Name, Group = c.group });
                    Log("IoController Creation Ok: device " + device.Name + " (" + HwDb.Identifier[c.identifier].comment + ") created");

                    netInterface = FindNetworkInterface(device.DeviceItems, c.connector, c.name);

                    SetAttribute(device.DeviceItems, "Author", "bdragoi");
                    SetAttribute(device.DeviceItems, "Comment", "Tia Portal Openness");
                }
                else if (HwDb.Identifier[c.identifier].deviceType == "PlcCardCm") //create PlcCard
                {
                    if (ioControllers.Count == 0 || ioControllers[0].Item1 == null)
                    {
                        Log("ERROR Creating PlcCard: no Plc exists \n The top row device in the .Csv file must be of type \"Plc\"");
                        return false;
                    }

                    DeviceItem rail = FindRail(ioControllers[0].Item1.DeviceItems); //get PLC rack identifier
                    if (rail == null)
                    {
                        Log("ERROR Creating PlcCard " + c.name + ": no rack/rail item found on " + ioControllers[0].Item1.Name +
                            " (a TIA project created in another language names the rack differently) - generation ABORTED" + "\n" +
                            "Line: " + c.srcRow.ToString() + " File: " + c.srcFileName);
                        return false;
                    }

                    DeviceItem card = null;
                    for (int i = 1; i <= 20; i++) //plug PlcCard into the first free slot
                    {
                        if (!rail.CanPlugNew(HwDb.Identifier[c.identifier].identifier, c.name, i)) continue;
                        card = rail.PlugNew(HwDb.Identifier[c.identifier].identifier, c.name, i);
                        break;
                    }
                    if (card == null)
                    {
                        Log("ERROR Creating PlcCard " + c.name + " (" + HwDb.Identifier[c.identifier].comment + "): no rack slot 1-20 accepts it - generation ABORTED" + "\n" +
                            "Line: " + c.srcRow.ToString() + " File: " + c.srcFileName);
                        return false;
                    }
                    ioControllers.Add(new Tuple<Device, DeviceItem>(null, card));
                    Log("IoController Creation Ok: device " + card.Name + " (" + HwDb.Identifier[c.identifier].comment + ") created");

                    netInterface = FindNetworkInterface(card.DeviceItems, c.connector, c.name);
                }
                else //no Io Controller
                {
                    Log("No IoController created because no valid type was found in Csv file \n Valid types: Plc, PlcCardCm");
                    return false;
                }

                if (netInterface == null)
                {
                    Log("ERROR Creating IoController " + c.name + ": no Ethernet network interface found on it - generation ABORTED" + "\n" +
                        "Line: " + c.srcRow.ToString() + " File: " + c.srcFileName);
                    return false;
                }

                //create subnet
                Subnet subnet = project.Subnets.Find(c.subnetName);
                if (subnet == null)
                    subnet = project.Subnets.Create("System:Subnet.Ethernet", c.subnetName);

                netInterface.Nodes.First().ConnectToSubnet(subnet);

                if (Uri.CheckHostName(c.IP) != UriHostNameType.IPv4)
                {
                    Log("ERROR on IoController Creation: " + c.name + " (" + HwDb.Identifier[c.identifier].comment + ") \n"
                        + "IPv4 Address not valid: " + c.IP.ToString() + "\n"
                        + "Line: " + c.srcRow.ToString() + " File: " + c.srcFileName);
                }
                else
                {
                    netInterface.Nodes.First().SetAttribute("Address", c.IP);
                }

                //create IoSystem
                var controller = netInterface.IoControllers.First();
                IoSystem ioSystem;
                try
                {
                    ioSystem = controller.CreateIoSystem(c.subnetName);
                }
                catch (Exception e)
                {
                    Log("ERROR Creating IoSystem for " + c.name + " - generation ABORTED \n" + e.Message);
                    return false;
                }

                ioSystems.Add(c.subnetName, new Tuple<Subnet, IoSystem>(subnet, ioSystem));
            }
            return true;
        }

        /// <summary>
        /// Used when attaching to existing controllers: reuses (and renames to the
        /// configured name) the controller's subnet and IO system, creating them only
        /// when missing, then registers them in the ioSystems map. The controller node
        /// is guaranteed to end up connected to exactly the registered subnet, so
        /// devices can never join a subnet whose IO system lives elsewhere. Returns
        /// false when the project state contradicts the configuration.
        /// </summary>
        private bool AdoptIoSystem(Project project, NetworkInterface netInterface, HwIoC._Controller c)
        {
            Node node = netInterface.Nodes.First();

            //resolve the subnet: an existing subnet already carrying the configured name wins,
            //else the node's current subnet is adopted and renamed, else a fresh one is created
            Subnet subnet = project.Subnets.Find(c.subnetName);
            if (subnet == null && node.ConnectedSubnet != null)
            {
                subnet = node.ConnectedSubnet;
                foreach (var registered in ioSystems.Values)
                {
                    if (registered.Item1.Equals(subnet))
                    {
                        Log("ERROR attaching IoController " + c.name + ": it shares subnet \"" + subnet.Name + "\" with another configured controller" + "\n" +
                            "Each controller needs its own subnet - separate them in TIA first" + "\n" +
                            "Line: " + c.srcRow.ToString() + " File: " + c.srcFileName);
                        return false;
                    }
                }
                subnet.Name = c.subnetName;
            }
            if (subnet == null)
            {
                subnet = project.Subnets.Create("System:Subnet.Ethernet", c.subnetName);
            }

            //the node must sit on exactly that subnet (a found-by-name subnet the node is not
            //on would otherwise pair the devices' subnet with an IO system living elsewhere)
            if (node.ConnectedSubnet == null)
            {
                node.ConnectToSubnet(subnet);
            }
            else if (!node.ConnectedSubnet.Equals(subnet))
            {
                Log("ERROR attaching IoController " + c.name + ": its interface is on subnet \"" + node.ConnectedSubnet.Name +
                    "\" while a different subnet already carries the configured name \"" + c.subnetName + "\"" + "\n" +
                    "Move the controller to \"" + c.subnetName + "\" (or delete the stray subnet) in TIA, then retry" + "\n" +
                    "Line: " + c.srcRow.ToString() + " File: " + c.srcFileName);
                return false;
            }

            //set or overwrite IpAddress
            if (Uri.CheckHostName(c.IP) != UriHostNameType.IPv4)
            {
                Log("ERROR on IoController Configuration: " + c.name + " (" + HwDb.Identifier[c.identifier].comment + ") \n"
                    + "IPv4 Address not valid: " + c.IP.ToString() + "\n"
                    + "Line: " + c.srcRow.ToString() + " File: " + c.srcFileName);
            }
            else
            {
                node.SetAttribute("Address", c.IP);
            }

            //associate or create IoSystem (the controller's own IO system is on our subnet by
            //construction - the node connection above is enforced first)
            var controller = netInterface.IoControllers.First();
            IoSystem ioSystem = controller.IoSystem;

            if (ioSystem == null)
            {
                try
                {
                    ioSystem = controller.CreateIoSystem(c.subnetName);
                }
                catch (Exception e)
                {
                    Log("ERROR Creating IoSystem for " + c.name + " - generation ABORTED \n" + e.Message);
                    return false;
                }
            }
            else if (!ioSystem.Name.Equals(c.subnetName))
            {
                ioSystem.Name = c.subnetName;
            }

            ioSystems.Add(c.subnetName, new Tuple<Subnet, IoSystem>(subnet, ioSystem));
            return true;
        }

        #endregion I/O controllers

        #region I/O devices

        /// <summary>
        /// Creates every configured I/O device, connects it to its controller's
        /// subnet/IO system, assigns IP + PROFINET device number and plugs its modules.
        /// A station whose name already exists in the project (ungrouped or in any
        /// device group) is SKIPPED together with all its modules, with a warning -
        /// the correction workflow is: delete the stations to refresh in TIA, then
        /// generate again. Modules are only ever plugged on the run that creates
        /// their station; an existing station is never completed or compared
        /// (no compatibility / slot matching by design).
        /// </summary>
        private void CreateIoDevices(IList<Tuple<HwIoD._Device, IList<HwIoD._Submodule>>> _devicesList)
        {
            //snapshot of the device names already in the project; case-insensitive on
            //purpose (a name differing only in case is skipped rather than risking the
            //TIA name conflict). The loader guarantees unique station names within the
            //configuration, so the set needs no update while creating.
            var existingNames = new HashSet<string>(CollectAllDevices().Select(x => x.Name), StringComparer.OrdinalIgnoreCase);

            int createdCount = 0;
            int skippedCount = 0;
            foreach (var d in _devicesList)
            {
                //cooperative cancel: single Openness calls cannot be interrupted, so we
                //stop between devices; nothing is saved, TIA can roll back via close-without-save
                if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                {
                    Log("Hardware generation CANCELLED - " + createdCount + " of " + _devicesList.Count +
                        " IO device(s) created" + SkippedSuffix(skippedCount) +
                        " (project not saved - close it in TIA without saving to roll back)");
                    return;
                }

                if (existingNames.Contains(d.Item1.name))
                {
                    int moduleCount = d.Item2.Count(s => !string.IsNullOrEmpty(s.name));
                    Log("WARNING: IoDevice " + d.Item1.name + " (" + HwDb.Identifier[d.Item1.identifier].comment + ") already exists in the project - " +
                        "station SKIPPED with its " + moduleCount + " module(s). To refresh it, delete the station in TIA and generate again. \n" +
                        "Line: " + d.Item1.srcRow.ToString() + " File: " + d.Item1.srcFileName);
                    skippedCount++;
                    continue;
                }

                DeviceUserGroup deviceGroup = ResolveDeviceGroup(project, d.Item1.group);
                var _device = (deviceGroup != null ? deviceGroup.Devices : project.UngroupedDevicesGroup.Devices)
                    .CreateWithItem(HwDb.Identifier[d.Item1.identifier].identifier, d.Item1.name, d.Item1.name);

                SetAttribute(_device.DeviceItems, "Author", "bdragoi");
                SetAttribute(_device.DeviceItems, "Comment", "Tia Portal Openness");

                var network = FindNetworkInterface(_device.DeviceItems, d.Item1.connector, d.Item1.name);
                if (network == null)
                {
                    Log("ERROR on IoDevice Creation: " + d.Item1.name + " has no Ethernet network interface - device skipped, check it in TIA" + "\n" +
                        "Line: " + d.Item1.srcRow.ToString() + " File: " + d.Item1.srcFileName);
                    continue;
                }
                if (d.Item1.connector.Length == 0 && (network.Nodes.Count > 1 || network.IoConnectors.Count > 1))
                    Log("WARNING: " + d.Item1.name + " exposes " + network.Nodes.Count + " node(s) / " +
                        network.IoConnectors.Count + " IO connector(s) and no Connector is configured - using the first one (X1)" + "\n" +
                        "Add e.g. X1 / X2 to the station's Connector column to choose explicitly");

                //the Openness-manual device example networks the interface FIRST, then assigns the
                //IO system. The single-call variant (ConnectToIoSystem alone) was tried 2026-07 and
                //V18/V19 REFUSES it: "The io connector is not connected to same subnet (as io system)".
                network.Nodes.First().ConnectToSubnet(ioSystems[d.Item1.subnet].Item1);

                IoConnector connector = PickIoConnector(network, d.Item1.connector, d.Item1.name);
                connector.ConnectToIoSystem(ioSystems[d.Item1.subnet].Item2);

                if (Uri.CheckHostName(d.Item1.IP) != UriHostNameType.IPv4)
                {
                    Log("ERROR on IoDevice Creation: " + d.Item1.name + " (" + HwDb.Identifier[d.Item1.identifier].comment + ") \n"
                        + "IPv4 Address not valid: " + d.Item1.IP.ToString() + "\n"
                        + "Line: " + d.Item1.srcRow.ToString() + " File: " + d.Item1.srcFileName);
                }
                else
                {
                    //explicit PN Number from the configuration wins; default is the last IP octet
                    int pnNumber;
                    if (!int.TryParse(d.Item1.pnNumber, out pnNumber))
                        pnNumber = Int32.Parse(d.Item1.IP.Split('.')[3]);

                    connector.SetAttribute("PnDeviceNumber", pnNumber);
                    network.Nodes.First().SetAttribute("Address", d.Item1.IP);
                }

                PlugSubmodules(_device, d.Item1, d.Item2);

                //station-row custom parameters: paths relative to the device root, for
                //sub-objects auto-created with the station (deep addresses, PrmData, ...).
                //Applied after plugging so the tree matches an attribute dump of a
                //complete station (item indices cannot shift afterwards).
                string stationParameters = CustomParameterApplier.Apply(_device, HwDb.Identifier[d.Item1.identifier].customParameters, d.Item1.customParameters,
                    d.Item1.IP, d.Item1.name);

                Log("IoDevice Creation Ok: IoDevice " + _device.Name + " (" + HwDb.Identifier[d.Item1.identifier].comment + ") created - " + stationParameters);
                createdCount++;
                LastCreatedStations.Add(new NetworkViewLayout.Station { Name = _device.Name, Group = d.Item1.group });
            }

            Log("IoDevice generation finished: " + createdCount + " of " + _devicesList.Count + " IO device(s) created" + SkippedSuffix(skippedCount) +
                (createdCount > 0 ? " - the new stations sit on one row of the network view: Files tab > Re-arrange devices.. lays them out by group" : string.Empty));
        }

        #region PROFINET port interconnections (topology)

        /// <summary>
        /// Wires the port interconnections of the Topology column (Stations.csv column 10; HardwareTopology) once the
        /// stations exist: for every link, this station's X&lt;i&gt;-P&lt;n&gt; port to the partner's X&lt;j&gt;-P&lt;m&gt; port through
        /// NetworkPort.ConnectToPort - the topology view and the online topology diagnostics then match the plant.
        /// A pair already connected is left alone (the partner's row, or an earlier run); a port connected ELSEWHERE
        /// is reported and skipped, never disconnected; a station, interface or port that cannot be found is
        /// reported. Stations the generation skipped (already in the project) are wired too - the links describe
        /// the plant, not the run.
        /// </summary>
        private void WirePorts()
        {
            var links = new List<Tuple<string, TopologyLink>>();
            foreach (HwIoC._Controller c in HwIoC.DevicesList)
                foreach (TopologyLink link in c.topology) links.Add(Tuple.Create(c.name, link));
            foreach (var d in HwIoD.DevicesList)
                foreach (TopologyLink link in d.Item1.topology) links.Add(Tuple.Create(d.Item1.name, link));
            if (links.Count == 0)
            {
                Log("Wire PROFINET ports: no Topology links in Stations.csv - nothing to wire");
                return;
            }

            Log("--- Wiring " + links.Count + " PROFINET port link(s) from the Topology column ---");
            int wired = 0, already = 0, skipped = 0;
            foreach (var entry in links)
            {
                if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                {
                    Log("Port wiring CANCELLED - " + wired + " link(s) wired");
                    return;
                }
                string station = entry.Item1;
                TopologyLink link = entry.Item2;
                string label = station + " " + link.OwnDesignation + " <-> " + link.PartnerStation + " " + link.PartnerDesignation;
                try
                {
                    NetworkPort own = FindPort(station, link.OwnInterface, link.OwnPort, label);
                    NetworkPort partner = FindPort(link.PartnerStation, link.PartnerInterface, link.PartnerPort, label);
                    if (own == null || partner == null)
                    {
                        skipped++;
                        continue;
                    }
                    if (own.ConnectedPorts.Any(p => p.Equals(partner)))
                    {
                        already++;
                        continue;
                    }
                    if (own.ConnectedPorts.Count > 0 || partner.ConnectedPorts.Count > 0)
                    {
                        Log("WARNING: port link " + label + " NOT wired - a port is already connected elsewhere (" + station + " " + link.OwnDesignation + ": " +
                            own.ConnectedPorts.Count + " connection(s), " + link.PartnerStation + " " + link.PartnerDesignation + ": " + partner.ConnectedPorts.Count +
                            " connection(s)) - disconnect it in TIA first");
                        skipped++;
                        continue;
                    }
                    own.ConnectToPort(partner);
                    Log("Port link wired: " + label);
                    wired++;
                }
                catch (Exception e)
                {
                    Log("ERROR wiring port link " + label + " \n" + e.Message);
                    skipped++;
                }
            }
            Log("Port wiring finished: " + wired + " wired, " + already + " already connected, " + skipped + " skipped (see above)");
        }

        /// <summary>The NetworkPort of port P&lt;n&gt; on interface X&lt;i&gt; of a station in the project; null (reported) when anything is missing.</summary>
        private NetworkPort FindPort(string stationName, int interfaceNumber, int portNumber, string label)
        {
            Device device = FindDevice(stationName, project.Devices) ?? FindDevice(stationName, project.UngroupedDevicesGroup.Devices) ?? FindDeviceInGroups(stationName, project.DeviceGroups);
            if (device == null)
            {
                Log("WARNING: port link " + label + " NOT wired - station " + stationName + " is not in the project");
                return null;
            }
            DeviceItem interfaceItem = FindInterfaceItem(device.DeviceItems, interfaceNumber);
            if (interfaceItem == null)
            {
                Log("WARNING: port link " + label + " NOT wired - " + stationName + " has no Ethernet interface X" + interfaceNumber);
                return null;
            }
            DeviceItem portItem = FindPortItem(interfaceItem, portNumber);
            if (portItem == null)
            {
                Log("WARNING: port link " + label + " NOT wired - " + stationName + " X" + interfaceNumber + " has no port P" + portNumber);
                return null;
            }
            return portItem.GetService<NetworkPort>();
        }

        /// <summary>The device item carrying Ethernet interface X&lt;n&gt; (item name token or PositionNumber), depth first.</summary>
        private DeviceItem FindInterfaceItem(DeviceItemComposition devices, int n)
        {
            foreach (DeviceItem device in devices)
            {
                NetworkInterface networkInterface = device.GetService<NetworkInterface>();
                if (networkInterface != null && GetAttribute(device, "InterfaceType") == "Ethernet" && ItemMatchesConnector(device, n))
                    return device;
                DeviceItem nested = FindInterfaceItem(device.DeviceItems, n);
                if (nested != null) return nested;
            }
            return null;
        }

        /// <summary>
        /// Port P&lt;n&gt; of an interface item: among the children carrying the NetworkPort service, the one whose name
        /// says "Port n" / "Pn" or whose PositionNumber is n, else the n-th one in item order.
        /// </summary>
        private DeviceItem FindPortItem(DeviceItem interfaceItem, int n)
        {
            var ports = new List<DeviceItem>();
            foreach (DeviceItem child in interfaceItem.DeviceItems)
            {
                NetworkPort port = null;
                try { port = child.GetService<NetworkPort>(); } catch { }
                if (port != null) ports.Add(child);
            }
            foreach (DeviceItem port in ports)
            {
                if (System.Text.RegularExpressions.Regex.IsMatch(port.Name, "(^|[^0-9A-Za-z])[Pp](ort)?[ _]*0*" + n + "([^0-9]|$)")) return port;
                if (GetAttribute(port, "PositionNumber") == n.ToString()) return port;
            }
            return n >= 1 && n <= ports.Count ? ports[n - 1] : null;
        }

        #endregion PROFINET port interconnections (topology)

        /// <summary>", N SKIPPED (already in project)" for the generation summary lines; "" when nothing was skipped.</summary>
        private static string SkippedSuffix(int skippedCount) =>
            skippedCount > 0 ? ", " + skippedCount + " SKIPPED (already in project)" : string.Empty;

        /// <summary>", I 100, Q 200" of a module row for its created line; "" without configured addresses.</summary>
        private static string AddressSuffix(HwIoD._Submodule s) =>
            (s.I_address.Length > 0 ? ", I " + s.I_address : string.Empty) + (s.Q_address.Length > 0 ? ", Q " + s.Q_address : string.Empty);

        /// <summary>
        /// Plugs each configured module into the first free slot of the device rack
        /// (the configured Slot only defines the order), then writes its custom
        /// parameters and I/O start addresses. A plug error - including "no free slot
        /// accepts the module", which used to skip the module silently - pops a
        /// Retry / Abort / Ignore decision to the user (the worker waits); Ignore
        /// skips the module, Abort cancels the whole generation.
        /// Rows whose model is of type TransferArea are not plugged: they become
        /// transfer areas on the station's PROFINET interface (CreateTransferArea).
        /// </summary>
        private void PlugSubmodules(Device _device, HwIoD._Device _mainDeviceData, IList<HwIoD._Submodule> _Submodules)
        {
            DeviceItem rail = FindRail(_device.DeviceItems);
            if (rail == null && _device.DeviceItems.Count > 0)
            {
                //a TIA project created in another language names the rack differently, so the
                //"Rack"/"Rail" name match can fail: fall back to the first device item, which
                //is the rack on every station shape this generator plugs into
                rail = _device.DeviceItems.First();
                Log("WARNING: no rack/rail found by name on " + _device.Name + " - using its first item \"" + rail.Name + "\" as the rack");
            }
            if (rail == null)
            {
                Log("ERROR: no rack found on " + _device.Name + " - hardware generation ABORTED (project not saved)");
                TiaWorker.CancelCurrentOperation();
                return;
            }

            int lastInsertedSlot = 0;
            foreach (var s in _Submodules)
            {
                if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                {
                    Log("Hardware generation CANCELLED while plugging modules of " + _device.Name);
                    return;
                }
                if (s.name.Equals(string.Empty)) continue;

                //transfer-area rows consume no rack slot: created on the PROFINET interface instead
                if (HwDb.Identifier[s.identifier].deviceType == HwDb.TransferAreaDeviceType)
                {
                    if (!CreateTransferArea(_device, _mainDeviceData, s)) return; //aborted by the user
                    continue;
                }

                bool plugged = false;
                bool skipSubmodule = false;
                while (!plugged && !skipSubmodule) //repeated while the user chooses Retry
                {
                    try
                    {
                        for (int i = lastInsertedSlot; i <= _device.DeviceItems.Count + _Submodules.Count; i++)
                        {
                            if (!rail.CanPlugNew(HwDb.Identifier[s.identifier].identifier, s.name, i)) continue;
                            rail.PlugNew(HwDb.Identifier[s.identifier].identifier, s.name, i);
                            lastInsertedSlot = i;
                            plugged = true;
                            break;
                        }
                        if (!plugged)
                            throw new InvalidOperationException("No free slot accepts the module (slots " + lastInsertedSlot +
                                                                " to " + (_device.DeviceItems.Count + _Submodules.Count) + " scanned)");
                    }
                    catch (Exception e)
                    {
                        var decision = AskPlugDecision(s.name, _device.Name, e.Message);
                        if (decision == System.Windows.Forms.DialogResult.Retry)
                        {
                            Log("Retrying to plug submodule " + s.name + " to device " + _device.Name);
                            continue;
                        }
                        if (decision == System.Windows.Forms.DialogResult.Ignore)
                        {
                            Log("SKIPPED submodule " + s.name + " of device " + _device.Name + " after plug error - check I/O addresses and parameters! \n" + e.Message);
                            skipSubmodule = true;
                            continue;
                        }

                        Log("Hardware generation ABORTED by the user after plug error at " + _device.Name + " / " + s.name + " \n" + e.Message);
                        TiaWorker.CancelCurrentOperation(); //stops the outer loops at their next check
                        return;
                    }
                }
                if (skipSubmodule) continue;

                //write custom parameters & I/O addresses
                DeviceItem T_submodule = FindDeviceItem(s.name, _device.DeviceItems);

                string moduleParameters = CustomParameterApplier.Apply(T_submodule, HwDb.Identifier[s.identifier].customParameters, s.customParameters, _mainDeviceData.IP,
                    _mainDeviceData.name + " / " + s.name);

                WriteIoStartAddresses(T_submodule, s, _mainDeviceData.name);
                Log("Module " + s.name + " (" + HwDb.Identifier[s.identifier].comment + ") plugged in slot " + lastInsertedSlot + " of IoDevice " + _device.Name +
                    AddressSuffix(s) + " - " + moduleParameters);
            }
        }

        /// <summary>
        /// Module row of model type "TransferArea" (PN/PN coupler, I-device): creates a
        /// transfer area on the station's PROFINET interface instead of plugging a
        /// module - transfer areas are not device items (NetworkInterface.TransferAreas).
        /// Module Name = area name, the model's Tia Identifier = the TransferAreaType
        /// name (IN, OUT, IN_OUT, PROFISAFE_IN12_OUT6, ...), Slot = position number.
        /// Then the custom parameters are applied relative to the area (model defaults
        /// + row: Name=Value for its attributes such as LocalToPartnerLength /
        /// PartnerToLocalLength, Addr(i) = LocalAddresses, PartnerAddr(i) =
        /// PartnerAddresses) and the row's I/Q start addresses are written on the
        /// PARTNER side = the address space of the IO controller this interface is
        /// connected to (verified on a 6ES7158-3AD10 V4.2 dump, 2026-10-08: the
        /// PartnerAddresses carry the AddressControllers; the LocalAddresses are the
        /// coupler's other side and stay -1 until that side has a controller; IN areas
        /// use PartnerToLocalLength, OUT areas LocalToPartnerLength). A creation error
        /// pops the module Retry / Abort / Ignore decision. Returns false when the user
        /// aborted the generation.
        /// </summary>
        private bool CreateTransferArea(Device _device, HwIoD._Device _mainDeviceData, HwIoD._Submodule s)
        {
            string context = _device.Name + " / " + s.name;
            string typeName = HwDb.Identifier[s.identifier].identifier;
            TransferAreaType areaType;
            if (!Enum.TryParse(typeName, true, out areaType) || areaType == TransferAreaType.None)
            {
                Log("ERROR: transfer area " + context + " SKIPPED - model " + s.identifier + " has an unknown transfer area type \"" + typeName +
                    "\" (expected one of: " + string.Join(", ", Enum.GetNames(typeof(TransferAreaType))) + ")");
                return true;
            }
            int position = Int32.Parse(s.position); //validated by the loader (positive integer)

            TransferArea area = null;
            while (area == null) //repeated while the user chooses Retry
            {
                try
                {
                    NetworkInterface network = FindNetworkInterface(_device.DeviceItems);
                    if (network == null)
                        throw new InvalidOperationException("the station has no PROFINET interface to create transfer areas on");
                    area = network.TransferAreas.Create(s.name, areaType, position);
                }
                catch (Exception e)
                {
                    var decision = AskPlugDecision(s.name + " (transfer area " + areaType + ", position " + position + ")", _device.Name, e.Message);
                    if (decision == System.Windows.Forms.DialogResult.Retry)
                    {
                        Log("Retrying to create transfer area " + context + " (position " + position + ")");
                        continue;
                    }
                    if (decision == System.Windows.Forms.DialogResult.Ignore)
                    {
                        Log("SKIPPED transfer area " + context + " after creation error - check the I/O addresses! \n" + e.Message);
                        return true;
                    }

                    Log("Hardware generation ABORTED by the user after transfer area error at " + context + " \n" + e.Message);
                    TiaWorker.CancelCurrentOperation(); //stops the outer loops at their next check
                    return false;
                }
            }

            string areaParameters = CustomParameterApplier.Apply(area, HwDb.Identifier[s.identifier].customParameters, s.customParameters, _mainDeviceData.IP, context);
            WriteTransferAreaStartAddresses(area, s, _device.Name);
            Log("Transfer area " + s.name + " (" + areaType + ", position " + position + ") created on IoDevice " + _device.Name + AddressSuffix(s) + " - " + areaParameters);
            return true;
        }

        /// <summary>
        /// Writes the row's I and Q start addresses onto the PARTNER address objects of a
        /// transfer area - the side owned by the IO controller of the interface (for an
        /// area created on the coupler's X1 that is the X1-side PLC): an IN area exposes
        /// one partner Input, an OUT area one partner Output, IN_OUT both. Only where TIA
        /// reports StartAddress as writable; a configured address without a matching
        /// partner address is reported. The coupler's other side (LocalAddresses) is
        /// reachable through Addr(i).StartAddress custom parameters.
        /// </summary>
        private void WriteTransferAreaStartAddresses(TransferArea area, HwIoD._Submodule s, string deviceName)
        {
            bool inputFound = false, outputFound = false;
            foreach (Address y in area.PartnerAddresses)
            {
                string configured;
                bool isInput = y.IoType.ToString() == "Input";
                if (isInput) configured = s.I_address;
                else if (y.IoType.ToString() == "Output") configured = s.Q_address;
                else continue;
                if (configured == "" || !IsAddressReadWrite(y)) continue;
                if (isInput) inputFound = true; else outputFound = true;

                try
                {
                    y.StartAddress = Int32.Parse(configured);
                }
                catch (Exception e)
                {
                    Log("ERROR: write address failed at IoDevice: " + deviceName + " transfer area: " + area.Name + "\n" + e.Message);
                }
            }

            if (s.I_address != "" && !inputFound)
                Log("WARNING: I Addr " + s.I_address + " of transfer area " + deviceName + " / " + area.Name + " NOT written - a " +
                    area.Type + " area has no writable partner Input address (I Addr applies to IN / IN_OUT areas)");
            if (s.Q_address != "" && !outputFound)
                Log("WARNING: Q Addr " + s.Q_address + " of transfer area " + deviceName + " / " + area.Name + " NOT written - a " +
                    area.Type + " area has no writable partner Output address (Q Addr applies to OUT / IN_OUT areas)");
        }

        /// <summary>
        /// Pre-generation checkpoint (Openness cannot close TIA editor tabs itself): the user
        /// confirms all editors - especially the network view - are closed, because generating
        /// under an open editor makes TIA post a per-device warning that persists through every compile.
        /// Without a UI the generation just proceeds (nothing to confirm against).
        /// </summary>
        private static bool ConfirmEditorsClosed()
        {
            var application = System.Windows.Application.Current;
            if (application == null) return true;

            return application.Dispatcher.Invoke(() =>
                System.Windows.Forms.MessageBox.Show(
                    "Close ALL TIA Portal editor tabs now - especially the network view.\n\n" +
                    "Generating while an editor is open makes TIA post a warning per device\n" +
                    "(\"device not assigned to an IO controller\" / \"IO device not connected to an IO system\")\n" +
                    "that persists through every compile.\n\n" +
                    "OK     -  the tabs are closed, generate\n" +
                    "Cancel -  stop (nothing is changed)",
                    "Openn5 - Hardware Generation",
                    System.Windows.Forms.MessageBoxButtons.OKCancel,
                    System.Windows.Forms.MessageBoxIcon.Information)
                == System.Windows.Forms.DialogResult.OK);
        }

        /// <summary>
        /// Plug-error popup, shown on the UI thread while the worker waits:
        /// Retry the plug call (e.g. after closing a blocking TIA dialog),
        /// Abort the whole generation, or Ignore = skip this module (dangerous -
        /// the following I/O addresses and parameters may no longer match).
        /// </summary>
        private static System.Windows.Forms.DialogResult AskPlugDecision(string moduleName, string deviceName, string errorMessage)
        {
            var application = System.Windows.Application.Current;
            if (application == null) return System.Windows.Forms.DialogResult.Abort; //no UI: fail safe

            return application.Dispatcher.Invoke(() =>
                System.Windows.Forms.MessageBox.Show(
                    "Error plugging submodule \"" + moduleName + "\" to device \"" + deviceName + "\":\n\n" +
                    errorMessage + "\n\n" +
                    "Retry  -  try the same plug call again (e.g. after closing a TIA dialog)\n" +
                    "Abort  -  stop the whole hardware generation (project stays unsaved)\n" +
                    "Ignore -  skip this module and continue - DANGEROUS: the following\n" +
                    "          I/O addresses and custom parameters may no longer match",
                    "Openn5 - Plug Module Error",
                    System.Windows.Forms.MessageBoxButtons.AbortRetryIgnore,
                    System.Windows.Forms.MessageBoxIcon.Warning));
        }

        /// <summary>
        /// Writes the configured I and Q start addresses onto the module's address
        /// objects (only where TIA reports the StartAddress attribute as writable).
        /// </summary>
        private void WriteIoStartAddresses(DeviceItem submodule, HwIoD._Submodule s, string deviceName)
        {
            foreach (DeviceItem x in submodule.DeviceItems)
            {
                if (!x.Name.Equals(s.name)) continue;
                foreach (Address y in x.Addresses)
                {
                    if ((y.IoType.ToString() == ("Input")) && s.I_address != "" && IsAddressReadWrite(y))
                    {
                        try
                        {
                            Int32.TryParse(s.I_address, out int T_iByte);
                            y.StartAddress = T_iByte;
                        }
                        catch (Exception e)
                        {
                            Log("ERROR: write address failed at IoDevice: " + deviceName + "Submodule: " + x.Name + "\n" +
                                e.Message);
                        }
                    }
                    else if ((y.IoType.ToString() == ("Output")) && s.Q_address != "" && IsAddressReadWrite(y))
                    {
                        try
                        {
                            Int32.TryParse(s.Q_address, out int T_qByte);
                            y.StartAddress = T_qByte;
                        }
                        catch (Exception e)
                        {
                            Log("ERROR: write address failed at IoDevice: " + deviceName + "Submodule: " + x.Name + "\n" +
                                e.Message);
                        }
                    }
                }
            }
        }

        #endregion I/O devices

        #region Hardware tree helpers

        /// <summary>
        /// The rack/rail item modules are plugged into: the first item anywhere in the tree
        /// whose name contains "Rack" or "Rail" (all siblings are searched at each level
        /// before descending). Localized TIA projects may name the rack differently -
        /// callers fall back to the first device item / abort with a clear message.
        /// </summary>
        private DeviceItem FindRail(DeviceItemComposition devices)
        {
            foreach (var item in devices)
            {
                if (item.Name.IndexOf("Rack") >= 0 || item.Name.IndexOf("Rail") >= 0) return item;
            }
            foreach (var item in devices)
            {
                DeviceItem rail = FindRail(item.DeviceItems);
                if (rail != null) return rail;
            }
            return null;
        }

        private Device FindDevice(String Identifier, DeviceComposition devices)
        {
            foreach (var item in devices)
            {
                if (item.Name.ToString().Equals(Identifier)) return item;
            }
            return null;
        }

        private DeviceItem FindDeviceItem(String Identifier, DeviceItemComposition devices)
        {
            foreach (var item in devices)
            {
                if (item.Name.ToString().Equals(Identifier)) return item;
            }
            return null;
        }

        /// <summary>
        /// The device group of a station's Group path ("folder/sub/..."), find-or-created level
        /// by level under project.DeviceGroups and cached per run; null = ungrouped root.
        /// </summary>
        private DeviceUserGroup ResolveDeviceGroup(Project project, string groupPath)
        {
            if (string.IsNullOrWhiteSpace(groupPath)) return null;
            if (deviceGroupCache.TryGetValue(groupPath, out DeviceUserGroup cached)) return cached;

            DeviceUserGroup group = null;
            foreach (string segment in groupPath.Split(new[] { '/', '\\' }, StringSplitOptions.RemoveEmptyEntries))
            {
                string name = segment.Trim();
                if (name.Length == 0) continue;
                DeviceUserGroupComposition children = group == null ? project.DeviceGroups : group.Groups;
                group = children.Find(name) ?? children.Create(name);
            }
            deviceGroupCache[groupPath] = group;
            return group;
        }

        /// <summary>Recursive device search through the user device groups (grouped stations do not appear in project.Devices).</summary>
        private Device FindDeviceInGroups(String identifier, DeviceUserGroupComposition groups)
        {
            foreach (DeviceUserGroup group in groups)
            {
                Device device = FindDevice(identifier, group.Devices);
                if (device != null) return device;
                device = FindDeviceInGroups(identifier, group.Groups);
                if (device != null) return device;
            }
            return null;
        }

        /// <summary>
        /// First Ethernet network interface (with at least one node) found in the
        /// device item tree, searched recursively.
        /// </summary>
        private NetworkInterface FindNetworkInterface(DeviceItemComposition devices)
        {
            NetworkInterface networkInterface = null;

            foreach (var device in devices)
            {
                if (networkInterface != null) continue;
                networkInterface = device.GetService<NetworkInterface>();
                if (networkInterface != null)
                {
                    if (GetAttribute(device, "InterfaceType") != "Ethernet") networkInterface = null;
                    else if (networkInterface.Nodes == null || networkInterface.Nodes.Count == 0) networkInterface = null;
                }
                if (networkInterface == null) networkInterface = FindNetworkInterface(device.DeviceItems);
            }

            return networkInterface;
        }

        /// <summary>
        /// The 1-based number of a Stations.csv Connector designation; 0 = none. Tolerates the
        /// verbatim I/O-List cell form ("X1-P1 R") the loader also accepts, not just bare "X1".
        /// </summary>
        private static int ConnectorNumber(string connectorSpec)
        {
            var match = System.Text.RegularExpressions.Regex.Match(connectorSpec ?? "", "(?<![0-9A-Za-z])[Xx]([0-9]{1,2})(?![0-9])");
            return match.Success ? int.Parse(match.Groups[1].Value) : 0;
        }

        /// <summary>
        /// The Ethernet interface selected by the station's Connector designation: the interface
        /// item carrying the Xn token in its name (GSD items are literally named "X1") or whose
        /// PositionNumber equals n (Siemens CPUs: the X1/X2/... interfaces). Falls back to the
        /// first interface with a WARNING when nothing matches; no designation = first interface.
        /// </summary>
        private NetworkInterface FindNetworkInterface(DeviceItemComposition devices, string connectorSpec, string stationName)
        {
            int n = ConnectorNumber(connectorSpec);
            if (n == 0) return FindNetworkInterface(devices);
            NetworkInterface match = FindNetworkInterfaceBySpec(devices, n);
            if (match != null) return match;
            Log("WARNING: " + stationName + ": no Ethernet interface matches Connector \"" + connectorSpec + "\" - using the first one");
            return FindNetworkInterface(devices);
        }

        private NetworkInterface FindNetworkInterfaceBySpec(DeviceItemComposition devices, int n)
        {
            foreach (var device in devices)
            {
                NetworkInterface networkInterface = device.GetService<NetworkInterface>();
                if (networkInterface != null && GetAttribute(device, "InterfaceType") == "Ethernet"
                    && networkInterface.Nodes != null && networkInterface.Nodes.Count > 0
                    && ItemMatchesConnector(device, n))
                    return networkInterface;
                NetworkInterface nested = FindNetworkInterfaceBySpec(device.DeviceItems, n);
                if (nested != null) return nested;
            }
            return null;
        }

        /// <summary>The item name carries the Xn token, or its PositionNumber equals n.</summary>
        private bool ItemMatchesConnector(DeviceItem item, int n)
        {
            if (System.Text.RegularExpressions.Regex.IsMatch(item.Name, "(^|[^0-9A-Za-z])[Xx]0*" + n + "([^0-9]|$)")) return true;
            return GetAttribute(item, "PositionNumber") == n.ToString();
        }

        /// <summary>
        /// The IO connector to associate: the Connector designation picks the n-th one on a
        /// multi-connector interface (PN/PN coupler: X1 = first, X2 = second). Without a
        /// designation the FIRST connector is used - X1 on a coupler (user decision 2026-10-09: the
        /// historical Last() dated from the pre-AI single-connector version); CreateIoDevices logs a
        /// WARNING for an unmarked multi-connector station, so the fallback is never silent.
        /// </summary>
        private IoConnector PickIoConnector(NetworkInterface network, string connectorSpec, string stationName)
        {
            int count = network.IoConnectors.Count;
            int n = ConnectorNumber(connectorSpec);
            if (n > 0 && count > 1)
            {
                if (n <= count)
                {
                    Log(stationName + ": Connector " + connectorSpec + " -> IO connector " + n + " of " + count);
                    return network.IoConnectors.ElementAt(n - 1);
                }
                Log("WARNING: " + stationName + ": Connector \"" + connectorSpec + "\" is out of range (the interface has " + count + ") - using the first one");
            }
            return network.IoConnectors.First();
        }

        /// <summary>Reads an attribute as string, or "" when the item does not expose it.</summary>
        private string GetAttribute(DeviceItem device, string attribute)
        {
            var list = device.GetAttributeInfos();
            foreach (var item in list)
            {
                if (item.Name.Equals(attribute))
                {
                    return device.GetAttribute(attribute).ToString();
                }
            }
            return string.Empty;
        }

        /// <summary>
        /// NOTE: longstanding oddity kept for behavioral compatibility - this matches
        /// items whose NAME equals the attribute name (no DeviceItem is named "Author"
        /// or "Comment", so the stamping calls are effectively no-ops). Changing it to
        /// really stamp every item would alter generated projects; decide separately.
        /// </summary>
        private void SetAttribute(DeviceItemComposition devices, string attribute, object value)
        {
            foreach (var d in devices)
            {
                if (d.Name.Equals(attribute))
                {
                    d.SetAttribute(attribute, value);
                }
            }
        }

        /// <summary>True when TIA reports the address' StartAddress attribute as writable.</summary>
        private bool IsAddressReadWrite(Address address)
        {
            var attributeInfos = address.GetAttributeInfos();
            foreach (var info in attributeInfos)
            {
                if (info.Name == "StartAddress")
                {
                    if (info.AccessMode == EngineeringAttributeAccessMode.ReadWrite)
                        return true;
                    else if (info.AccessMode == EngineeringAttributeAccessMode.Read)
                        return false;
                }
            }
            return false;
        }

        #endregion Hardware tree helpers
    }
}

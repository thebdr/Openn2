using System;
using System.Collections.Generic;
using System.Linq;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
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

        #endregion Hardware generation state

        /// <summary>
        /// Entry point of the hardware generation. Either creates the I/O controllers
        /// from scratch or attaches to controllers that already exist in the project,
        /// then creates all I/O devices and stamps Author/Comment on every device.
        /// </summary>
        public void CreateDevices(bool? CreateNewIoControllers = true)
        {
            if (project == null)
            {
                Log("ERROR \n TIA PROJECT not attached.");
                return;
            }

            if (HwIoC.DevicesList == null || HwIoC.DevicesList.Count == 0)
            {
                Log("ERROR \n No I/O Controllers loaded - import a valid hardware configuration first.");
                return;
            }

            //check if first I/O Controller is of Plc Type
            if (!HwDb.Identifier[HwIoC.DevicesList[0].identifier].deviceType.Equals("Plc", StringComparison.OrdinalIgnoreCase))
            {
                Log("IoController : " + HwIoC.DevicesList[0].name + " is not of \"Plc\" type." + "\n" +
                                "Line: " + HwIoC.DevicesList[0].srcRow.ToString() + " File: " + HwIoC.DevicesList[0].srcFileName + "\n" +
                                "First device in Csv file must be a Plc");
                return;
            }

            project.ShowHwEditor(Siemens.Engineering.HW.View.Network); //show the network editor

            if (CreateNewIoControllers == true)
            {
                CreateIoControllers(project);
            }
            else
            {
                if (AttachIoControllers(project) == false)
                    return;
            }

            CreateIoDevices(HwIoD.DevicesList);

            foreach (var a in project.UngroupedDevicesGroup.Devices)
            {
                SetAttribute(a.DeviceItems, "Author", "bdragoi");
                SetAttribute(a.DeviceItems, "Comment", "Tia Portal Openness");
            }
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
                //search for PLCs
                if (HwDb.Identifier[ioC.identifier].deviceType.Equals("Plc", StringComparison.OrdinalIgnoreCase))
                {
                    Device device = FindDevice(ioC.name, project.Devices);
                    if (device != null)
                    {
                        ioControllers.Add(new Tuple<Device, DeviceItem>(device, null));
                        netInterface = FindNetworkInterface(device.DeviceItems);
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
                        netInterface = FindNetworkInterface(device.DeviceItems);
                    }
                    else
                    {
                        Log("IoController (PlcCardCm) : " + ioC.name + " not found in project" + "\n" +
                            "Line: " + ioC.srcRow.ToString() + " File: " + ioC.srcFileName);
                        return false;
                    }
                }

                AdoptIoSystem(project, netInterface, ioC);
            }
            return true;
        }

        /// <summary>
        /// "Create new controllers" mode: creates the Plc, plugs the communication
        /// modules into its rack, then creates subnet + IO system per controller and
        /// assigns the configured IP address.
        /// </summary>
        private void CreateIoControllers(Project project)
        {
            ioControllers = new List<Tuple<Device, DeviceItem>>();
            ioSystems = new Dictionary<string, Tuple<Subnet, IoSystem>>();
            NetworkInterface netInterface = null;

            foreach (var c in HwIoC.DevicesList)
            {
                if (HwDb.Identifier[c.identifier].deviceType == "Plc") //create Plc
                {
                    var device = project.Devices.CreateWithItem(HwDb.Identifier[c.identifier].identifier, c.name, c.name);
                    ioControllers.Add(new Tuple<Device, DeviceItem>(device, null));
                    Log("IoController Creation Ok: device " + device.Name + " (" + HwDb.Identifier[c.identifier].comment + " has been created");

                    netInterface = FindNetworkInterface(device.DeviceItems);

                    SetAttribute(device.DeviceItems, "Author", "bdragoi");
                    SetAttribute(device.DeviceItems, "Comment", "Tia Portal Openness");
                }
                else if (HwDb.Identifier[c.identifier].deviceType == "PlcCardCm") //create PlcCard
                {
                    if (ioControllers[0] == null)
                    {
                        Log("ERROR Creating PlcCard: no Plc exists \n The top row device in the .Csv file must be of type \"Plc\"");
                        return;
                    }

                    DeviceItem rail = FindRail(ioControllers[0].Item1.DeviceItems); //get PLC rack identifier

                    for (int i = 1; i <= 20; i++) //plug PlcCard into the first free slot
                    {
                        if (!rail.CanPlugNew(HwDb.Identifier[c.identifier].identifier, c.name, i)) continue;
                        var device = rail.PlugNew(HwDb.Identifier[c.identifier].identifier, c.name, i);
                        ioControllers.Add(new Tuple<Device, DeviceItem>(null, device));
                        Log("IoController Creation Ok: device " + device.Name + " (" + HwDb.Identifier[c.identifier].comment + "  has been created");

                        netInterface = FindNetworkInterface(device.DeviceItems);
                        break;
                    }
                }
                else //no Io Controller
                {
                    Log("No IoController created because no valid type was found in Csv file \n Valid types: Plc, PlcCardCm");
                    return;
                }

                //create subnet
                Subnet subnet = project.Subnets.Find(c.subnetName);
                if (subnet == null)
                    subnet = project.Subnets.Create("System:Subnet.Ethernet", c.subnetName);

                netInterface.Nodes.First().ConnectToSubnet(project.Subnets.Find(c.subnetName));

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
                    Log("ERROR Creating IoSystem1 \n" + e.Message);
                    return;
                }

                ioSystems.Add(c.subnetName, new Tuple<Subnet, IoSystem>(subnet, ioSystem));
            }
        }

        /// <summary>
        /// Used when attaching to existing controllers: reuses (and renames to the
        /// configured name) the controller's subnet and IO system, creating them
        /// only when missing, then registers them in the ioSystems map.
        /// </summary>
        private void AdoptIoSystem(Project project, NetworkInterface netInterface, HwIoC._Controller c)
        {
            //associate or create subnet
            Subnet subnet = project.Subnets.Find(c.subnetName);
            if (subnet == null)
            {
                if (netInterface.Nodes.First().ConnectedSubnet == null)
                {
                    subnet = project.Subnets.Create("System:Subnet.Ethernet", c.subnetName);
                    netInterface.Nodes.First().ConnectToSubnet(subnet);
                }
                else
                {
                    subnet = netInterface.Nodes.First().ConnectedSubnet;
                    subnet.Name = c.subnetName;
                }
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
                netInterface.Nodes.First().SetAttribute("Address", c.IP);
            }

            //associate or create IoSystem
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
                    Log("ERROR Creating IoSystem1 \n" + e.Message);
                    return;
                }
            }
            else if (!ioSystem.Name.Equals(c.subnetName))
            {
                ioSystem.Name = c.subnetName;
            }

            ioSystems.Add(c.subnetName, new Tuple<Subnet, IoSystem>(subnet, ioSystem));
        }

        #endregion I/O controllers

        #region I/O devices

        /// <summary>
        /// Creates every configured I/O device, connects it to its controller's
        /// subnet/IO system, assigns IP + PROFINET device number and plugs its modules.
        /// </summary>
        private void CreateIoDevices(IList<Tuple<HwIoD._Device, IList<HwIoD._Submodule>>> _devicesList)
        {
            foreach (var d in _devicesList)
            {
                var _device = project.UngroupedDevicesGroup.Devices.CreateWithItem(HwDb.Identifier[d.Item1.identifier].identifier, d.Item1.name, d.Item1.name);

                SetAttribute(_device.DeviceItems, "Author", "bdragoi");
                SetAttribute(_device.DeviceItems, "Comment", "Tia Portal Openness");

                var network = FindNetworkInterface(_device.DeviceItems);

                network.Nodes.Last().ConnectToSubnet(ioSystems[d.Item1.subnet].Item1);
                network.IoConnectors.Last().ConnectToIoSystem(ioSystems[d.Item1.subnet].Item2);

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

                    network.IoConnectors.Last().SetAttribute("PnDeviceNumber", pnNumber);
                    network.Nodes.Last().SetAttribute("Address", d.Item1.IP);
                }

                PlugSubmodules(_device, d.Item1, d.Item2);

                Log("IoDevice Creation Ok: IoDevice " + _device.Name + " (" + HwDb.Identifier[d.Item1.identifier].comment + " has been created");
            }
        }

        /// <summary>
        /// Plugs each configured module into the first free slot of the device rack
        /// (the configured Slot only defines the order), then writes its custom
        /// parameters and I/O start addresses.
        /// </summary>
        private void PlugSubmodules(Device _device, HwIoD._Device _mainDeviceData, IList<HwIoD._Submodule> _Submodules)
        {
            DeviceItem rail = FindRail(_device.DeviceItems);

            int lastInsertedSlot = 0;
            foreach (var s in _Submodules)
            {
                if (s.name.Equals(string.Empty)) continue;
                for (int i = lastInsertedSlot; i <= _device.DeviceItems.Count + _Submodules.Count; i++)
                {
                    try
                    {
                        if (!rail.CanPlugNew(HwDb.Identifier[s.identifier].identifier, s.name, i)) continue;
                        lastInsertedSlot = i;
                        rail.PlugNew(HwDb.Identifier[s.identifier].identifier, s.name, i);
                    }
                    catch (Exception e)
                    {
                        Log("Error Plugging Submodule " + s.name + " to device " + _device.Name + "\n" + e.Message);
                    }

                    //write custom parameters & I/O addresses
                    DeviceItem T_submodule = FindDeviceItem(s.name, _device.DeviceItems);

                    CustomParameterApplier.Apply(T_submodule, HwDb.Identifier[s.identifier].customParameters, s.customParameters, _mainDeviceData.IP,
                        _mainDeviceData.name + " / " + s.name);

                    WriteIoStartAddresses(T_submodule, s, _mainDeviceData.name);
                    break;
                }
            }
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

        /// <summary>The rack/rail item modules are plugged into (searches by item name).</summary>
        private DeviceItem FindRail(DeviceItemComposition devices)
        {
            foreach (var item in devices)
            {
                if (item.Name.IndexOf("Rack") >= 0 || item.Name.IndexOf("Rail") >= 0) return item;
                return FindRail(item.DeviceItems);
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

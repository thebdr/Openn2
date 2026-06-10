using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;

using HwDb = Openn._01_Constructor.HardwareDeviceTypesDatabase;
using HwIoC = Openn._01_Constructor.HardwareIoControllers;
using HwIoD = Openn._01_Constructor.HardwareIoDevices;

using Siemens.Engineering.SW.Blocks;
using Siemens.Engineering.SW;
using System.Linq;
using static Openn._10_StandardFunctions.LogsManager;
using System.Threading.Tasks;

namespace Openn._03_ApiManager
{
    public class TiaPortalOpenness
    {
        #region Vars Declaration

        private readonly string appBaseDir = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);

        private TiaPortal portal = null;
        private Project project = null;
        private IoSystem ioSystem = null;
        private IList<Tuple<Device, DeviceItem>> ioControllers = null;
        private IList<Device> ioDevices = null;
        private Subnet subnet = null;
        private Dictionary<string, Tuple<Subnet, IoSystem>> ioSystems;

        #endregion

        public async Task<string> AttachToProject(string _Path = "")
        {
            bool bCreateNewProject = string.IsNullOrEmpty(_Path); //if no path is specified, create a new project
            string defaultProjectsFolder = appBaseDir + "\\TiaProjects\\";
            string projectName = "openness_project";
            string projectPath = defaultProjectsFolder + projectName;

            if (!bCreateNewProject)
            {
                projectPath = _Path;
                projectName = new DirectoryInfo(projectPath).Name;

                project = TryAttachToOpenProject(projectPath);
                if (project == null)
                    Log("Project is not open");
            }

            try
            {
                if (bCreateNewProject)
                {
                    projectName += "_" + DateTime.Now.ToString("yyyyMMdd_HHmmss");

                    if (Directory.Exists(defaultProjectsFolder + projectName))
                    {
                        try
                        {
                            Directory.Delete(defaultProjectsFolder + projectName, true);
                            Log("TIA PROJECT DELETED: " + defaultProjectsFolder + projectName);
                        }
                        catch (Exception e)
                        {
                            Log("TIA PROJECT DELETE ERROR \n" + e.Message);
                        }
                    }

                    portal = new TiaPortal(TiaPortalMode.WithUserInterface);
                    project = portal.Projects.Create(new DirectoryInfo(defaultProjectsFolder), projectName);

                    Log("Attached to New Tia Project: " + project.Name);
                }
                else if (project == null) //not open in any running instance: open it in a new Tia Portal
                {
                    FileInfo projectFile = FindProjectFile(projectPath);
                    if (projectFile == null)
                    {
                        Log("ERROR Attaching Tia Project \nNo TIA project file (*" +
                            OpennessSetup.SelectedInstallation.ProjectFileExtension + ", *.ap..) found in: " + projectPath);
                        return "";
                    }

                    portal = new TiaPortal(TiaPortalMode.WithUserInterface);
                    project = portal.Projects.Open(projectFile);
                    Log("Opened Tia Project: " + projectFile.Name);
                }

                return project.Name;
            }
            catch (Exception e)
            {
                Log("ERROR Attaching Tia Project \n" + e.Message);
                return "";
            }

        }

        /// <summary>
        /// Attaches to a running Tia Portal instance that has the given project open.
        /// Returns null when no such instance exists.
        /// </summary>
        private Project TryAttachToOpenProject(string projectPath)
        {
            foreach (TiaPortalProcess tiaPortalProcess in TiaPortal.GetProcesses())
            {
                try
                {
                    if (tiaPortalProcess.ProjectPath == null) continue;
                    if (!tiaPortalProcess.ProjectPath.ToString().Contains(projectPath)) continue;

                    portal = TiaPortal.GetProcess(tiaPortalProcess.Id).Attach(); //keep the attached instance referenced
                    foreach (Project openProject in portal.Projects)
                    {
                        Log("Attached to Existing Tia Project: " + openProject.Name);
                        return openProject;
                    }
                }
                catch (Exception e)
                {
                    Log("ERROR attaching to Tia Portal process [" + tiaPortalProcess.Id + "] \n" + e.Message);
                }
            }
            return null;
        }

        /// <summary>
        /// Finds the project file (*.ap18, *.ap19, ...) inside the project folder,
        /// preferring the extension that matches the selected Tia Portal version.
        /// </summary>
        private FileInfo FindProjectFile(string projectDirectory)
        {
            var directory = new DirectoryInfo(projectDirectory);
            if (!directory.Exists) return null;

            var candidates = directory.GetFiles("*.ap*").Where(IsTiaProjectFile).ToList();
            if (candidates.Count == 0) return null;

            string preferredExtension = OpennessSetup.SelectedInstallation.ProjectFileExtension;
            return candidates.FirstOrDefault(f => f.Extension.Equals(preferredExtension, StringComparison.OrdinalIgnoreCase))
                   ?? candidates[0];
        }

        private static bool IsTiaProjectFile(FileInfo file)
        {
            string extension = file.Extension; //".ap18", ".ap15_1", ...
            if (extension.Length <= 3 || !extension.StartsWith(".ap", StringComparison.OrdinalIgnoreCase)) return false;
            return extension.Substring(3).All(c => char.IsDigit(c) || c == '_');
        }

        public string DetachProject()
        {
            if (project == null)
            {
                Log("Can't detach: No Tia Project attached");
            }
            else
            {
                Log("Tia Project detached: " + project.Name);
                project = null;
            }
            return "";
        }

        public void ExportBlock(string blockName)
        {
            PlcSoftware plcSoftware = GetPlcSoftware(project);

            PlcBlock plcBlock = plcSoftware.BlockGroup.Blocks.Find(blockName);
            try
            {
                plcBlock.Export(new FileInfo(appBaseDir + "\\ExportedBlocks\\" + plcBlock.Name + ".xml"), ExportOptions.WithDefaults);
            }
            catch (Exception e)
            {
                Log("ERROR Exporting Source Block \n" + e.Message);
                return;
            }

            if (!(plcBlock == null))
                Log("Exported software block: " + plcBlock.Name);
        }

        public List<string> UpdateSourceBlocksList()
        {
            List<string> Blocks = new List<string>();
            //check if Tia Project is attached
            if ((project == null))
            {
                Log("Can't refresh blocks: No Tia Project Attached");
                return Blocks;
            }

            //Get all blocks from the Plc Software            
            string BlockType = "";
            foreach (PlcBlock block in GetAllPlcSoftwareBlocks(project) ?? Enumerable.Empty<object>())
            {
                BlockType = block.GetType().Name.ToString();
                Blocks.Add("[" + BlockType + "] " + block.Name);
            }
            Blocks.Sort();

            if (Blocks.Count > 0)
            {
                Log("Software Blocks List Refreshed: Found " + Blocks.Count + " blocks");
                return Blocks;
            }
            else
            {
                Log("Can't refresh blocks: No Software Blocks found");
                var emptyList = new List<string>{"List Empty"};
                return emptyList;
            }
        }

        public void ImportPlcBlock(string fileName)
        {
            try
            {
                PlcSoftware plcSoftware = GetPlcSoftware(project);
                {
                    PlcBlockGroup blockGroup = plcSoftware.BlockGroup;
                    IList<PlcBlock> blocks = blockGroup.Blocks.Import(new
                         FileInfo(fileName), ImportOptions.Override);
                }
                Log("Plc Source Block : " + fileName + " imported successfully");
            }
            catch (Exception e)
            {
                Log("ERROR Importing Plc Block \n" + e.Message);
            }

        }

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
            if(!HwDb.Identifier[HwIoC.DevicesList[0].identifier].deviceType.Equals("Plc", StringComparison.OrdinalIgnoreCase))
            {
                Log("IoController : " + HwIoC.DevicesList[0].name + " is not of \"Plc\" type." + "\n" +
                                "Line: " + HwIoC.DevicesList[0].srcRow.ToString() + " File: " + HwIoC.DevicesList[0].srcFileName + "\n" +
                                "First device in Csv file must be a Plc");
                return;
            }

            project.ShowHwEditor(Siemens.Engineering.HW.View.Network); //show the network editor

            if (CreateNewIoControllers == true)
            {
                Create_IoControllers(project);
            }                
            else
            {
                if (Attach_IoControllers(project) == false)
                    return;
            }
                
            Create_IoDevices(HwIoD.DevicesList);

            foreach (var a in project.UngroupedDevicesGroup.Devices)
            {
                SetAttribute(a.DeviceItems, "Author", "bdragoi");
                SetAttribute(a.DeviceItems, "Comment", "Tia Portal Openness");
            }
        }

        private bool Attach_IoControllers(Project project)
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

                ManageIoSystems(project, netInterface, ioC);

            }
            return true;

        }

        private void Create_IoControllers(Project project)
        {
            ioControllers = new List<Tuple<Device, DeviceItem>>();
            ioSystems = new Dictionary<string, Tuple<Subnet, IoSystem>>();
            NetworkInterface netInterface = null;

            //create the PLC & HMI devices in the Tia Project
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

                    for (int i = 1; i <= 20; i++) //plug PlcCard
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
                subnet = project.Subnets.Find(c.subnetName);
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

        private void Create_IoDevices(IList<Tuple<HwIoD._Device, IList<HwIoD._Submodule>>> _devicesList)
        {
            ioDevices = new List<Device>();

            foreach (var d in _devicesList)
            {
                var _device = project.UngroupedDevicesGroup.Devices.CreateWithItem(HwDb.Identifier[d.Item1.identifier].identifier, d.Item1.name, d.Item1.name);

                ioDevices.Add(_device);

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

                Fill_IoDevices(_device, d.Item1, d.Item2);

                Log("IoDevice Creation Ok: IoDevice " + _device.Name + " (" + HwDb.Identifier[d.Item1.identifier].comment + " has been created");
            }
        }

        private void Fill_IoDevices(Device _device, HwIoD._Device _mainDeviceData, IList<HwIoD._Submodule> _Submodules)
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

                    SetCustomParameters(T_submodule, HwDb.Identifier[s.identifier].customParameters, s.customParameters, _mainDeviceData.IP);

                    foreach (DeviceItem x in T_submodule.DeviceItems)
                    {
                        if (!x.Name.Equals(s.name)) continue;
                        foreach (Address y in x.Addresses)
                        {
                            bool T_isInput = y.IoType.ToString() == ("Input");
                            bool T_isOutput = y.IoType.ToString() == ("Output");
                            if ((y.IoType.ToString() == ("Input")) && s.I_address != "" && IsAddressReadWrite(y))
                            {
                                try
                                {
                                    Int32.TryParse(s.I_address, out int T_iByte);
                                    y.StartAddress = T_iByte;
                                }
                                catch (Exception e)
                                {
                                    Log("ERROR: write address failed at IoDevice: " + _mainDeviceData.name + "Submodule: " + x.Name + "\n" + 
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
                                    Log("ERROR: write address failed at IoDevice: " + _mainDeviceData.name + "Submodule: " + x.Name + "\n" +
                                        e.Message);
                                }
                            }

                        }
                    }
                    break;
                }

            }
        }

        private void ManageIoSystems(Project project, NetworkInterface netInterface, HwIoC._Controller c)
        {
            //associate or create subnet
            subnet = project.Subnets.Find(c.subnetName);
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
            ioSystem = controller.IoSystem;

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

        private struct DeviceCustomParam
        {
            public string Attribute;
            public ulong Value;
            public int ChannelId;

            public DeviceCustomParam(string _Attribute, ulong _Value, int _ChannelId)
            {
                Attribute = _Attribute;
                Value = _Value;
                ChannelId = _ChannelId;
            }
        }

        private void SetCustomParameters(DeviceItem device, string customParamsGlobal, string customParamsSpecific, string IpAddress = "")
        {
            if (customParamsGlobal.Equals(string.Empty) && customParamsSpecific.Equals(string.Empty))
                return; //skip if no params

            IList<DeviceCustomParam> customParams = new List<DeviceCustomParam>();

            string[] rawGlobalParams = customParamsGlobal.Split(',');
            List<string> globalParams = DispatchCustomParameters(rawGlobalParams);

            string[] rawSpecificParams = customParamsSpecific.Split(',');
            List<string> specificParams = DispatchCustomParameters(rawSpecificParams);

            //add global params not overrided to specificParams list
            bool specifiParamExists;

            foreach (string gParam in globalParams)
            {
                specifiParamExists = false;

                foreach (string sParam in specificParams)
                {
                    //check if a specific parameter exists, then override the global parameter
                    if (sParam.Split('=')[0] == gParam.Split('=')[0])
                    {
                        specifiParamExists = true;
                        break;
                    }
                }

                //add global param to list
                if (!specifiParamExists)
                {
                    specificParams.Add(gParam);
                }
            }

            //process params and fill final list
            foreach (string param in specificParams)
            {
                if (!param.Contains('='))
                    continue; //skip if no equal sign

                string[] splitParam = param.Split('=');
                string _Attribute = splitParam[0];
                int _ChannelId = 0;
                ulong _Value = 0;

                //check if param name contains dot (reference to subdevice/channel)
                if (splitParam[0].Contains("."))
                {
                    string[] splitAttribute = splitParam[0].Split('.');
                    _Attribute = splitAttribute[0];

                    int.TryParse(splitAttribute[1].Split('(', ')')[1], out _ChannelId);
                }

                //check if param value is part of an IP Address
                if (splitParam[1].Contains("IP["))
                {
                    string[] splitIp = IpAddress.Split('.');
                    int ipField = int.TryParse(splitParam[1].Split('[', ']')[1], out int t) ? t: 3;

                    ulong.TryParse(splitIp[ipField], out _Value);
                }
                else
                {
                    ulong.TryParse(splitParam[1], out _Value);
                }
                
                DeviceCustomParam tmpCustomParam = new DeviceCustomParam(_Attribute, _Value, _ChannelId);
                customParams.Add(tmpCustomParam);
            }

            foreach (DeviceCustomParam param in customParams)
            {
                switch (param.Attribute)
                {
                    //pass plugged FS_DATA Module
                    case "Failsafe_FDestinationAddress":
                    case "Failsafe_FMonitoringtime":
                    case "Failsafe_FParameterSignatureIndividualParameters":
                    {
                        try
                        {
                            device.DeviceItems[0].SetAttribute(param.Attribute, param.Value);
                        }
                        catch (Exception e)
                        {
                            Log("SetCustomParameters Error, Attribute: " + param.Attribute + " Value: " + param.Value.ToString() + " Device: " + device.Name + "\n" +
                                e.Message);
                        }
                            
                        break;
                    }

                    //pass plugged Siemens F-DI Module
                    case "PotentialGroup":
                    {
                        try
                        {
                            device.SetAttribute(param.Attribute, param.Value);
                        }
                        catch (Exception e)
                        {
                            Log("SetCustomParameters Error, Attribute: " + param.Attribute + " Value: " + param.Value.ToString() + " Device: " + device.Name + "\n" +
                                e.Message);
                        }

                        break;
                    }

                    ////pass plugged Siemens F-DI Module
                    case "Failsafe_SensorEvaluation":
                    case "Failsafe_DiscrepancyTime":
                    {
                        try
                        {
                            device.DeviceItems[0].Channels[param.ChannelId].SetAttribute(param.Attribute, param.Value);
                        }
                        catch (Exception e)
                        {
                            Log("SetCustomParameters Error, Attribute: " + param.Attribute + " Value: " + param.Value.ToString() + " Device: " + device.Name + "\n" +
                                e.Message);
                        }
                        break;
                    }
                    default:
                        Log($"SetCustomParameters Error, Attribute: {param.Attribute} Value: {param.Value} Device: {device.Name} \n" +
                            "has not been found in CustomParametersConfig.csv");

                        break;
                }

            }

        }

        private List<string> DispatchCustomParameters(string[] ParamList)
        {
            List<string> dispatchedParams = new List<string>();

            for (int i = 0; i < ParamList.Length; i++)
            {
                if (ParamList[i].Contains("("))
                {
                    string[] splitParam = ParamList[i].Split('(', ')');
                    string ID = splitParam[1];

                    if (ID.Contains("-"))
                    {
                        string[] splitID = ID.Split('-');
                        int lowerBound = int.TryParse(splitID[0], out int n) ? n : 0;
                        int upperBound = int.TryParse(splitID[1], out n) ? n : 0;

                        for (int j = lowerBound; j <= upperBound; j++)
                        {
                            dispatchedParams.Add(splitParam[0] + "(" + j.ToString() + ")" + splitParam[2]);
                        }
                    }
                    else
                    {
                        dispatchedParams.Add(ParamList[i]);
                    }

                }
                else
                {
                    dispatchedParams.Add(ParamList[i]);
                }

            }
            return dispatchedParams;
        }


        #region Auxiliary Functions
        private void SaveProject()
        {
            if (project != null)
            {
                project.Save();
                Log("Project Save Ok: " + project.Name + " has been saved");
            }
        }

        private DeviceItem FindRail(DeviceItemComposition devices)
        {
            foreach (var item in devices)
            {
                if (item.Name.IndexOf("Rack") >=0 || item.Name.IndexOf("Rail") >=0 ) return item;
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

        private PlcSoftware GetPlcSoftware(Project _project)
        {
            PlcSoftware plcSoftware = null;
            foreach (Device device in _project.Devices)
            {
                DeviceItemComposition deviceItemComposition = device.DeviceItems;
                foreach (DeviceItem _deviceItem in deviceItemComposition)
                {
                    SoftwareContainer softwareContainer = _deviceItem.GetService<SoftwareContainer>();
                    if (softwareContainer != null)
                    {
                        Software softwareBase = softwareContainer.Software;
                        plcSoftware = softwareBase as PlcSoftware;
                        if (plcSoftware != null)
                        {
                            break;
                        }
                    }
                }
                break;
            }
            return plcSoftware;
        }

        private List<PlcBlock> GetAllPlcSoftwareBlocks(Project _project)
        {
            PlcSoftware plcSoftware = GetPlcSoftware(project);
            if (plcSoftware == null)
                return null;

            List<PlcBlock> plcSoftwareBlocksList = new List<PlcBlock>();

            foreach (PlcBlock plcBlock in plcSoftware.BlockGroup.Blocks ?? Enumerable.Empty<object>())
            {
                plcSoftwareBlocksList.Add(plcBlock);
            }

            return plcSoftwareBlocksList;
        }

        public struct TiaProcessInfo
        {
            public string ProcessID;
            public string ProcessPath;
            public string ProjectPath;
            public string ProjectName;

            public TiaProcessInfo(string _ProcessID, string _ProcessPath, string _ProjectPath, string _ProjectName)
            {
                ProcessID = _ProcessID;
                ProcessPath = _ProcessPath;
                ProjectPath = _ProjectPath; 
                ProjectName = _ProjectName;
            }
        }

        public IList<TiaProcessInfo> GetOpenTiaInstances()
        {
            TiaProcessInfo processInfo = new TiaProcessInfo();
            IList <TiaProcessInfo> processInfoList = new List<TiaProcessInfo>();
            foreach (TiaPortalProcess tiaPortalProcess in TiaPortal.GetProcesses())
            {
                try
                {
                    processInfo.ProcessID = tiaPortalProcess.Id.ToString();
                    processInfo.ProcessPath = tiaPortalProcess.Path.ToString();
                    processInfo.ProjectPath = tiaPortalProcess.ProjectPath != null ? tiaPortalProcess.ProjectPath.ToString() : "No Project";
                    processInfo.ProjectName = new DirectoryInfo(processInfo.ProjectPath).Name.ToString();

                    processInfoList.Add(processInfo);
                }
                catch (Exception e)
                {
                    Log("Error getting Tia Portal Process Information \n" + e.Message);
                }
            }
            return processInfoList;
        }

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

        #endregion Auxiliary Functions




    }
}

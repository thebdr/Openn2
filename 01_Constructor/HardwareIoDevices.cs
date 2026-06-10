using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using static Openn._10_StandardFunctions.LogsManager;
using Openn._10_StandardFunctions;
using System.Runtime.Remoting.Messaging;
using Openn;

namespace Openn._01_Constructor
{
    class HardwareIoDevices
    {
        public struct _Device 
        { 
            public string name;
            public string identifier;
            public string IP;
            public string subnet;
            public string customParameters;
            public string srcFileName;
            public int srcRow;
            public _Device (string _name, string _identifier, string _IP, string _subnet, string _customParameters, string _srcFileName, int _srcRow) 
            { 
                name = _name;
                identifier = _identifier;
                IP = _IP;
                subnet = _subnet;
                customParameters = _customParameters;
                srcFileName = _srcFileName;
                srcRow = _srcRow;
            }
        }

        public struct _Submodule
        {
            public string name;
            public string identifier;
            public string position;
            public string I_address;
            public string Q_address;
            public string customParameters;

            public _Submodule(string _name, string _identifier, string _position, string _I_address, string _Q_address, string _customParameters)
            {
                name = _name;                
                identifier = _identifier;
                position = _position;
                I_address = _I_address;
                Q_address = _Q_address;
                customParameters = _customParameters;
            }
        }

        public static IList<Tuple<_Device, IList<_Submodule>>> DevicesList;
        
        public static void ReadDevicesList(string folder)
        {
            DevicesList = new List<Tuple<_Device, IList<_Submodule>>>();
            int nLineCounter = 0;

            string filename = folder + "\\IoDevicesList.csv";
            if (!File.Exists(filename)) //show error message if file does not exist
            {
                Log("Csv File Read ERROR " + filename + " \n file not found: " + filename);
                return;
            }

            using (StreamReader reader = new StreamReader(filename))
            {
                try //read .csv file ('#' skips line)
                {
                    var entries = 0;

                    //csv parameters
                    int MainModuleLength = 5;
                    int SubModuleLength = 4;

                    while (!reader.EndOfStream)
                    {
                        var line = reader.ReadLine();
                        nLineCounter++;
                        if (line[0] == '#') continue;
                        if (line[0] == '@') break;

                        var values = line.Split(';');

                        var tmpDevice = new _Device(values[0], values[1], values[2], values[3], values[4], filename, nLineCounter); //first 4 columns are the device params

                        IList<_Submodule> tmpSubmodules = new List<_Submodule>();
                        string[] addresses_I_Q = new string[] { "", ""};
                        int j = 1;
                        for (int i = MainModuleLength; i < values.Length; i += SubModuleLength)
                        {
                            if (values[i].Equals(string.Empty)) continue;

                            //get I/O addresses
                            string addr = values[i + 2];
                            if (addr.Contains("&"))
                                addresses_I_Q = addr.Split('&');
                            else
                                addresses_I_Q = new string[] { addr, addr };
                                
                            var submod = new _Submodule(values[i], values[i + 1], j.ToString(), addresses_I_Q[0], addresses_I_Q[1], values[i + 3]); //following sets of 4 columns are the submodules
                            tmpSubmodules.Add(submod);

                            j++;
                        }

                        DevicesList.Add(new Tuple<_Device, IList<_Submodule>>(tmpDevice, tmpSubmodules));

                        entries++;
                    }
                    Log("Csv File Read Ok: " + entries.ToString() + " entries have been read from " + filename);
                }
                catch (Exception e)
                {
                    Log("Csv File Read ERROR " + filename + " \n" + e.Message);
                }
                reader.Dispose();
            }
        }

    }
}

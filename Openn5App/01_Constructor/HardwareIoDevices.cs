using System;
using System.Collections.Generic;

namespace Openn._01_Constructor
{
    /// <summary>
    /// PROFINET I/O devices and their plugged modules.
    /// Filled by HardwareConfigLoader from Stations.csv + Modules.csv.
    /// </summary>
    internal class HardwareIoDevices
    {
        public struct _Device
        {
            public string name;
            public string identifier;
            public string IP;
            public string pnNumber; //explicit PROFINET device number; empty = derive from last IP octet
            public string subnet;
            public string customParameters;
            public string srcFileName;
            public int srcRow;
            public _Device(string _name, string _identifier, string _IP, string _pnNumber, string _subnet, string _customParameters, string _srcFileName, int _srcRow)
            {
                name = _name;
                identifier = _identifier;
                IP = _IP;
                pnNumber = _pnNumber;
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

        public static IList<Tuple<_Device, IList<_Submodule>>> DevicesList = new List<Tuple<_Device, IList<_Submodule>>>();
    }
}

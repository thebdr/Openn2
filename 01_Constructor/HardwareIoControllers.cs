using System.Collections.Generic;

namespace Openn._01_Constructor
{
    /// <summary>
    /// I/O controllers (Plc, PlcCardCm) of the hardware configuration.
    /// Filled by HardwareConfigLoader from Stations.csv; the entry with the
    /// "Plc" role is always first (TiaPortalOpenness relies on that).
    /// </summary>
    internal class HardwareIoControllers
    {
        public struct _Controller
        {
            public string name;
            public string identifier;
            public string IP;
            public string subnetName;
            public string customParameters;
            public string srcFileName;
            public int srcRow;
            public _Controller(string _name, string _identifier, string _IP, string _subnetName, string _customParameters, string _srcFileName, int _srcRow)
            {
                name = _name;
                identifier = _identifier;
                IP = _IP;
                subnetName = _subnetName;
                customParameters = _customParameters;
                srcFileName = _srcFileName;
                srcRow = _srcRow;
            }
        }

        public static IList<_Controller> DevicesList = new List<_Controller>();
    }
}

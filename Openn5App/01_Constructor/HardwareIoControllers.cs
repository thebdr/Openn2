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
            public string connector; //X1/X01... interface designation; empty = default pick
            public string group;     //device-group path "folder/sub/..."; empty = ungrouped root
            public List<TopologyLink> topology; //Stations.csv column 10 port links (HardwareTopology.Parse); the loader fills it, the constructor starts it empty
            public string customParameters;
            public string srcFileName;
            public int srcRow;
            public _Controller(string _name, string _identifier, string _IP, string _subnetName, string _connector, string _group, string _customParameters, string _srcFileName, int _srcRow)
            {
                name = _name;
                identifier = _identifier;
                IP = _IP;
                subnetName = _subnetName;
                connector = _connector;
                group = _group;
                customParameters = _customParameters;
                topology = new List<TopologyLink>();
                srcFileName = _srcFileName;
                srcRow = _srcRow;
            }
        }

        public static IList<_Controller> DevicesList = new List<_Controller>();
    }
}

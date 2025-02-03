using System;
using System.Collections.Generic;
using System.IO;
using static Openn._10_StandardFunctions.LogsManager;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Openn._01_Constructor
{
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

        public static IList<_Controller> DevicesList;

        public static void ReadDevicesList(string folder)
        {
            DevicesList = new List<_Controller>();
            int nLineCounter = 0;

            string filename = folder + "\\IoControllersList.csv";
            if (!File.Exists(filename)) //show error message if file does not exist
            {
                Log("Csv File Read ERROR " + filename + "\n file not found: " + filename);
                return;
            }

            using (StreamReader reader = new StreamReader(filename))
            {
                try //read .csv file ('#' skips line)
                {
                    var entries = 0;
                    while (!reader.EndOfStream)
                    {
                        var line = reader.ReadLine();
                        nLineCounter++;
                        if (line[0] == '#') continue;
                        if (line[0] == '@') break;

                        var values = line.Split(';');

                        var tmpController = new _Controller(values[0], values[1], values[2], values[3], values[4], filename, nLineCounter); //first 3 columns are the device params

                        DevicesList.Add(tmpController);

                        entries++;
                    }
                    Log("Csv File Read Ok: " + entries.ToString() + " entries have been read from " + filename);
                }
                catch (Exception e)
                {
                    Log("Csv File Read ERROR " + filename + "\n" + e.Message);
                }
                reader.Dispose();
            }
        }

    }
}

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using listbox = System.Windows.Controls.ListBox;
using static Openn._10_StandardFunctions.LogsManager;
using System.Runtime.Remoting.Messaging;

namespace Openn._01_Constructor
{
    class HardwareDeviceTypesDatabase
    {
        public struct DeviceInfo
        {
            public string deviceType;
            public string identifier;
            public string comment;
            public string customParameters;
            public string srcFileName;
            public int srcRow;
            public DeviceInfo(string _type, string _identifier, string _comment, string _customParameters, string _srcFileName, int _srcRow)
            {
                deviceType = _type;
                identifier = _identifier;
                comment = _comment;
                customParameters = _customParameters;
                srcFileName = _srcFileName;
                srcRow = _srcRow;
            }
        }

        public static Dictionary<string, DeviceInfo> Identifier;

        public static void ReadHardwareList(string folder)
        {
            Identifier = new Dictionary<string, DeviceInfo>();
            int nLineCounter = 0; 
            
            string filename = folder + "\\DeviceTypesDatabase.csv";
            if (!File.Exists(filename)) //show error message if file does not exist
            {
                Log("Csv File Read ERROR  \n file not found: " + filename);
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

                        var info = new DeviceInfo(values[1], values[2], values[3], values[4], filename, nLineCounter);
                        Identifier.Add(values[0], info);

                        entries++;
                    }
                    Log("Csv File Read Ok: " + entries.ToString() + " entries have been read from " + filename);
                }
                catch (Exception e)
                {
                    Log("Csv File Read ERROR \n" + e.Message);
                }
            reader.Dispose();
            }
        }

    }
}

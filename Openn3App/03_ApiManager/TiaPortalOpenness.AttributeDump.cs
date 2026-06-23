using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Attribute discovery: dumps the complete attribute tree of project devices
    /// into a text file, as a search/diff aid for finding the Openness attribute
    /// names behind TIA GUI parameters (the GUI shows localized display names,
    /// the API expects internal names - there is no API to map one to the other).
    ///
    /// Workflow: set a parameter manually in the TIA GUI to a distinctive value,
    /// dump, search the file for that value - or dump twice around a single GUI
    /// change and diff the two files. Node paths are printed in the custom
    /// parameter syntax (Item(i)/Ch(i)); to use a found attribute in the csv,
    /// strip the plugged module's own path prefix and append Name=Value.
    /// </summary>
    public partial class TiaPortalOpenness
    {
        /// <summary>Counters for the summary log line.</summary>
        private sealed class DumpStats
        {
            public int Devices;
            public int Nodes;
            public int Attributes;
            public int PrmRecords;
        }

        /// <summary>
        /// Dumps all devices whose name matches the filter (regex, case-insensitive,
        /// empty = every device) into a timestamped file under appBaseDir\AttributeDumps.
        /// Cancellable between devices and between top-level modules; a cancelled
        /// dump leaves a partial file marked as such.
        /// </summary>
        public void DumpDeviceAttributes(string deviceNameFilter)
        {
            if (project == null)
            {
                Log("ERROR \n TIA PROJECT not attached.");
                return;
            }

            Regex filter = null;
            if (!string.IsNullOrWhiteSpace(deviceNameFilter))
            {
                try
                {
                    filter = new Regex(deviceNameFilter, RegexOptions.IgnoreCase);
                }
                catch (ArgumentException e)
                {
                    Log("Attribute dump: invalid device name filter \"" + deviceNameFilter + "\" \n" + e.Message);
                    return;
                }
            }

            IList<Device> devices = CollectAllDevices();
            if (filter != null)
                devices = devices.Where(d => filter.IsMatch(d.Name)).ToList();

            if (devices.Count == 0)
            {
                Log("Attribute dump: no device in the project" + (filter == null ? "" : " matches \"" + deviceNameFilter + "\""));
                return;
            }

            string dumpFolder = Path.Combine(appBaseDir, "AttributeDumps");
            Directory.CreateDirectory(dumpFolder);
            string dumpPath = Path.Combine(dumpFolder, "AttributeDump_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".txt");

            var stats = new DumpStats();
            bool cancelled = false;

            using (var writer = new StreamWriter(dumpPath, false, Encoding.UTF8))
            {
                writer.WriteLine("# Openn2 attribute dump - " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));
                writer.WriteLine("# Project: " + project.Name);
                writer.WriteLine("# Device filter: " + (filter == null ? "(all devices)" : deviceNameFilter));
                writer.WriteLine("#");
                writer.WriteLine("# Node paths use the custom parameter syntax: Item(i) = DeviceItems[i],");
                writer.WriteLine("# Ch(i) = Channels[i], Addr(i) = Addresses[i] (I/O address objects).");
                writer.WriteLine("# Csv custom parameters resolve these paths relative to:");
                writer.WriteLine("#   - module rows (Modules.csv): the plugged module - strip the module node's own prefix,");
                writer.WriteLine("#   - station rows (Stations.csv): the device root - paths exactly as printed here.");
                writer.WriteLine("# Attribute format: Name = Value  [AccessMode, ValueType]");
                writer.WriteLine("# PrmData(n)=<hex> lines are pasteable csv entries (raw GSD parameter record,");
                writer.WriteLine("# written byte-exact via GsdDeviceItem.SetPrmData). GSD module parameters (the GUI");
                writer.WriteLine("# 'Module parameters' page) live bit-packed in these records; the byte/bit layout");
                writer.WriteLine("# is defined in the device's GSDML file (<ParameterRecordDataItem>).");
                writer.WriteLine("#");
                writer.WriteLine("# '::' sections (Node/IoConnector/IoController/NetworkPort/Gsd) are service");
                writer.WriteLine("# objects, NOT addressable via csv paths.");

                foreach (Device device in devices)
                {
                    if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                    {
                        cancelled = true;
                        break;
                    }

                    try
                    {
                        cancelled = !DumpDevice(writer, device, stats);
                    }
                    catch (Exception e)
                    {
                        Log("Attribute dump error at device " + device.Name + " (device skipped) \n" + e.Message);
                        writer.WriteLine();
                        writer.WriteLine("# ERROR dumping device \"" + device.Name + "\": " + e.Message);
                        continue;
                    }

                    if (cancelled) break;
                    stats.Devices++;
                }

                if (cancelled)
                {
                    writer.WriteLine();
                    writer.WriteLine("# CANCELLED - dump is incomplete");
                }
            }

            Log((cancelled ? "Attribute dump CANCELLED - partial file: " : "Attribute dump written: ") + dumpPath + "\n" +
                stats.Devices + " device(s), " + stats.Nodes + " node(s), " + stats.Attributes + " attribute(s), " +
                stats.PrmRecords + " GSD PrmData record(s)");
        }

        /// <summary>
        /// All devices of the project: project level, ungrouped group and user
        /// groups (recursively), deduplicated by name (the project-level and
        /// ungrouped compositions can overlap).
        /// </summary>
        private IList<Device> CollectAllDevices()
        {
            var devices = new List<Device>();
            var seenNames = new HashSet<string>();

            foreach (Device device in project.Devices)
                if (seenNames.Add(device.Name)) devices.Add(device);
            foreach (Device device in project.UngroupedDevicesGroup.Devices)
                if (seenNames.Add(device.Name)) devices.Add(device);
            CollectGroupDevices(project.DeviceGroups, devices, seenNames);

            return devices;
        }

        private static void CollectGroupDevices(DeviceUserGroupComposition groups, List<Device> devices, HashSet<string> seenNames)
        {
            foreach (DeviceUserGroup group in groups)
            {
                foreach (Device device in group.Devices)
                    if (seenNames.Add(device.Name)) devices.Add(device);
                CollectGroupDevices(group.Groups, devices, seenNames);
            }
        }

        /// <summary>
        /// One device: its own attributes, then the full device item tree.
        /// Returns false when cancelled between top-level items.
        /// </summary>
        private static bool DumpDevice(StreamWriter writer, Device device, DumpStats stats)
        {
            writer.WriteLine();
            writer.WriteLine("======================================================================");
            writer.WriteLine("DEVICE \"" + device.Name + "\"");
            writer.WriteLine("======================================================================");
            writer.WriteLine();
            writer.WriteLine("<device root>");
            DumpAttributes(writer, device, stats);
            DumpGsdInfo(writer, device);

            int index = 0;
            foreach (DeviceItem item in device.DeviceItems)
            {
                //cooperative cancel between top-level items (typically rack/head/modules)
                if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                    return false;

                DumpDeviceItemTree(writer, item, "Item(" + index + ")", stats);
                index++;
            }
            return true;
        }

        /// <summary>
        /// One device item node: its attributes, channels, I/O addresses, network
        /// interface nodes/connectors, port options and GSD PrmData records, then
        /// all child items, depth first.
        /// </summary>
        private static void DumpDeviceItemTree(StreamWriter writer, DeviceItem item, string path, DumpStats stats)
        {
            writer.WriteLine();
            writer.WriteLine(path + "  \"" + item.Name + "\"");
            DumpAttributes(writer, item, stats);
            DumpChannels(writer, item, path, stats);
            DumpAddresses(writer, item, path, stats);
            DumpNetworkInterface(writer, item, path, stats);
            DumpNetworkPort(writer, item, path, stats);
            DumpGsdPrmData(writer, item, path, stats);

            int index = 0;
            foreach (DeviceItem child in item.DeviceItems)
            {
                DumpDeviceItemTree(writer, child, path + ".Item(" + index + ")", stats);
                index++;
            }
        }

        /// <summary>I/O address objects of the item (this is where StartAddress/Length/IoType live).</summary>
        private static void DumpAddresses(StreamWriter writer, DeviceItem item, string path, DumpStats stats)
        {
            System.Collections.IEnumerable addresses;
            try { addresses = item.Addresses; } catch { return; }
            if (addresses == null) return;

            int index = 0;
            foreach (IEngineeringObject address in addresses)
            {
                writer.WriteLine();
                writer.WriteLine(path + ".Addr(" + index + ")");
                DumpAttributes(writer, address, stats);
                index++;
            }
        }

        /// <summary>
        /// NetworkInterface service: nodes (IP address, subnet mask, PROFINET device
        /// name) and IO connectors/controllers (PnDeviceNumber, ...).
        /// </summary>
        private static void DumpNetworkInterface(StreamWriter writer, DeviceItem item, string path, DumpStats stats)
        {
            NetworkInterface netInterface;
            try { netInterface = item.GetService<NetworkInterface>(); } catch { return; }
            if (netInterface == null) return;

            DumpServiceObjects(writer, SafeEnumerable(() => netInterface.Nodes), path + "::Node", stats);
            DumpServiceObjects(writer, SafeEnumerable(() => netInterface.IoConnectors), path + "::IoConnector", stats);
            DumpServiceObjects(writer, SafeEnumerable(() => netInterface.IoControllers), path + "::IoController", stats);
        }

        /// <summary>NetworkPort service of port items (port options, interconnections).</summary>
        private static void DumpNetworkPort(StreamWriter writer, DeviceItem item, string path, DumpStats stats)
        {
            NetworkPort port;
            try { port = item.GetService<NetworkPort>(); } catch { return; }
            if (port == null) return;

            writer.WriteLine();
            writer.WriteLine(path + "::NetworkPort");
            DumpAttributes(writer, port, stats);
        }

        /// <summary>
        /// GSD identity + raw PROFINET parameter data records of GSD-based items.
        /// The records hold the GUI "Module parameters" page bit-packed; Openness
        /// exposes them only as bytes (GetPrmData/SetPrmData). There is no record
        /// enumeration API, so record numbers 0-255 are probed (trial and error).
        /// </summary>
        private static void DumpGsdPrmData(StreamWriter writer, DeviceItem item, string path, DumpStats stats)
        {
            GsdDeviceItem gsd;
            try { gsd = item.GetService<GsdDeviceItem>(); } catch { return; }
            if (gsd == null) return;

            writer.WriteLine();
            writer.WriteLine(path + "::Gsd");
            try
            {
                writer.WriteLine("    GsdName = " + gsd.GsdName + "  | GsdType = " + gsd.GsdType + "  | GsdId = " + gsd.GsdId +
                    (gsd.IsProfinet ? "  | PROFINET" : "") + (gsd.IsProfibus ? "  | PROFIBUS" : ""));
            }
            catch { /* identity not available on this item */ }
            DumpAttributes(writer, gsd, stats);

            for (int record = 0; record <= 255; record++)
            {
                if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                    return; //the outer device loop logs the cancellation

                byte[] data = TryReadPrmRecord(gsd, record);
                if (data == null || data.Length == 0) continue;

                writer.WriteLine("    PrmData(" + record + ")=" + BitConverter.ToString(data).Replace("-", " ") + "  [" + data.Length + " byte(s)]");
                stats.PrmRecords++;
            }
        }

        /// <summary>
        /// Reads one PrmData record without knowing its length: tries a big read
        /// first; if the API rejects over-long reads, grows from 1 byte and binary
        /// searches the exact record length. Returns null when the record does not
        /// exist (or nothing is readable).
        /// </summary>
        private static byte[] TryReadPrmRecord(GsdDeviceItem gsd, int record)
        {
            try { return gsd.GetPrmData(record, 0, 4096); } catch { }

            int good;
            try
            {
                gsd.GetPrmData(record, 0, 1);
                good = 1;
            }
            catch
            {
                return null; //record does not exist
            }

            int bad = -1;
            for (int length = 2; length <= 4096; length *= 2)
            {
                try { gsd.GetPrmData(record, 0, length); good = length; }
                catch { bad = length; break; }
            }
            if (bad < 0) bad = 8192;

            while (bad - good > 1)
            {
                int middle = (good + bad) / 2;
                try { gsd.GetPrmData(record, 0, middle); good = middle; }
                catch { bad = middle; }
            }

            try { return gsd.GetPrmData(record, 0, good); } catch { return null; }
        }

        /// <summary>Dumps each object of a service composition under an indexed '::' label.</summary>
        private static void DumpServiceObjects(StreamWriter writer, System.Collections.IEnumerable objects, string labelPrefix, DumpStats stats)
        {
            if (objects == null) return;

            int index = 0;
            foreach (IEngineeringObject engineeringObject in objects)
            {
                writer.WriteLine();
                writer.WriteLine(labelPrefix + "(" + index + ")");
                DumpAttributes(writer, engineeringObject, stats);
                index++;
            }
        }

        /// <summary>Evaluates a composition getter, returning null when it throws (not exposed).</summary>
        private static System.Collections.IEnumerable SafeEnumerable(Func<System.Collections.IEnumerable> getter)
        {
            try { return getter(); } catch { return null; }
        }

        /// <summary>GSD identity of a whole device (GSD devices only).</summary>
        private static void DumpGsdInfo(StreamWriter writer, Device device)
        {
            try
            {
                GsdDevice gsd = device.GetService<GsdDevice>();
                if (gsd == null) return;
                writer.WriteLine("    GSD: " + gsd.GsdName + "  | " + gsd.GsdType + "  | " + gsd.GsdId);
            }
            catch { /* not a GSD device */ }
        }

        private static void DumpChannels(StreamWriter writer, DeviceItem item, string path, DumpStats stats)
        {
            System.Collections.IEnumerable channels;
            try
            {
                channels = item.Channels;
            }
            catch
            {
                return; //item exposes no channel composition
            }
            if (channels == null) return;

            int index = 0;
            foreach (IEngineeringObject channel in channels)
            {
                writer.WriteLine();
                writer.WriteLine(path + ".Ch(" + index + ")");
                DumpAttributes(writer, channel, stats);
                index++;
            }
        }

        /// <summary>
        /// Every attribute the node reports via GetAttributeInfos, with its current
        /// value (or &lt;unreadable&gt; for write-only/inaccessible attributes).
        /// </summary>
        private static void DumpAttributes(StreamWriter writer, IEngineeringObject node, DumpStats stats)
        {
            stats.Nodes++;
            foreach (EngineeringAttributeInfo info in node.GetAttributeInfos())
            {
                string value;
                string valueType = null;
                try
                {
                    object raw = node.GetAttribute(info.Name);
                    value = FormatValue(raw);
                    if (raw != null) valueType = raw.GetType().Name;
                }
                catch
                {
                    value = "<unreadable>";
                }

                writer.WriteLine("    " + info.Name + " = " + value +
                    "  [" + info.AccessMode + (valueType == null ? "" : ", " + valueType) + "]");
                stats.Attributes++;
            }
        }

        /// <summary>Single-line, length-limited rendering of an attribute value.</summary>
        private static string FormatValue(object value)
        {
            if (value == null) return "<null>";

            var enumerable = value as System.Collections.IEnumerable;
            if (enumerable != null && !(value is string))
            {
                var parts = new List<string>();
                foreach (object element in enumerable)
                {
                    if (parts.Count >= 32)
                    {
                        parts.Add("...");
                        break;
                    }
                    parts.Add(element == null ? "<null>" : element.ToString());
                }
                return "[" + string.Join(", ", parts) + "]";
            }

            string text = value.ToString().Replace("\r", "").Replace("\n", "\\n");
            if (text.Length > 300) text = text.Substring(0, 300) + "...";
            return text;
        }
    }
}

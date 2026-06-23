using System;
using System.Collections.Generic;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Openn._01_Constructor;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Writes the custom parameters of a plugged module - or of a whole station -
    /// into the TIA object model.
    ///
    /// The parameters come pre-parsed from CustomParameterParser (model defaults
    /// merged with per-row overrides). Where a value is written depends on its path:
    ///   - explicit path (Item(i).Ch(i)/Addr(i).Name=Value): resolved literally from
    ///     the root (module row: the plugged module; station row: the device root -
    ///     matching the paths the attribute dump prints),
    ///   - channel-only path (Ch(i).Name=Value): the sub item owning that channel is searched,
    ///   - no path (Name=Value): the first object in the tree exposing a
    ///     writable attribute of that name is used (GetAttributeInfos discovery),
    ///     so new device families need no code changes,
    ///   - PrmData(n)=hex: raw GSD parameter record n written byte-exact via
    ///     GsdDeviceItem.SetPrmData (GSD module parameters are not attributes).
    /// Values are converted to the type the attribute actually has - TIA attributes
    /// are typed and a fixed-type write would fail for string/bool/enum attributes.
    ///
    /// Stateless; like all Openness access it must run on the TiaWorker thread.
    /// </summary>
    internal static class CustomParameterApplier
    {
        /// <summary>Applies the parameters of one plugged module (paths relative to the module).</summary>
        public static void Apply(DeviceItem module, string globalParameters, string specificParameters, string ipAddress, string context)
        {
            ApplyAll(module, globalParameters, specificParameters, ipAddress, context, "module");
        }

        /// <summary>
        /// Applies the parameters of a station row (paths relative to the created
        /// device - for sub-objects auto-created with the station, deep addresses
        /// and PrmData records). Call AFTER the modules are plugged so the item
        /// indices match an attribute dump of a complete station.
        /// </summary>
        public static void Apply(Device station, string globalParameters, string specificParameters, string ipAddress, string context)
        {
            ApplyAll(station, globalParameters, specificParameters, ipAddress, context, "station");
        }

        /// <summary>
        /// Parses, merges and applies all parameters of one root object. Problems are
        /// logged per parameter (with the given station/module context); one bad
        /// parameter does not stop the others.
        /// </summary>
        private static void ApplyAll(IEngineeringObject root, string globalParameters, string specificParameters, string ipAddress, string context, string rootKind)
        {
            var parseErrors = new List<string>();
            IList<CustomParameter> parameters = CustomParameterParser.Parse(globalParameters, specificParameters, ipAddress, parseErrors);
            foreach (string parseError in parseErrors)
                Log("Custom parameter error (" + context + "): " + parseError);

            if (parameters.Count == 0)
                return;

            if (root == null)
            {
                Log("Custom parameter error (" + context + "): " + rootKind + " not found, " + parameters.Count + " parameter(s) skipped");
                return;
            }

            foreach (CustomParameter parameter in parameters)
            {
                try
                {
                    ApplyParameter(root, parameter, context);
                }
                catch (Exception e)
                {
                    Log("Custom parameter error (" + context + "): " + parameter + "\n" + e.Message);
                }
            }
        }

        /// <summary>Resolves the target object for one parameter and writes the value.</summary>
        private static void ApplyParameter(IEngineeringObject root, CustomParameter parameter, string context)
        {
            if (parameter.IsPrmData)
            {
                ApplyPrmData(root, parameter, context);
                return;
            }

            IEngineeringObject target;
            if (parameter.Path.Count == 0)
            {
                target = FindAttributeOwner(root, parameter.Name);
                if (target == null)
                {
                    Log("Custom parameter error (" + context + "): no object of " + Describe(root) +
                        " has a writable attribute \"" + parameter.Name + "\"");
                    return;
                }
            }
            else if (parameter.Path[0].Kind == CustomParameterStepKind.Channel)
            {
                //channel without an explicit Item(..): find the sub item owning that channel
                target = FindChannelOwner(root, parameter.Path[0].Index, parameter.Name);
                if (target == null)
                {
                    Log("Custom parameter error (" + context + "): no channel " + parameter.Path[0].Index +
                        " with a writable attribute \"" + parameter.Name + "\" found on " + Describe(root));
                    return;
                }
            }
            else
            {
                target = ResolvePath(root, parameter.Path);
                if (target == null)
                {
                    Log("Custom parameter error (" + context + "): path of " + parameter + " does not exist on " + Describe(root));
                    return;
                }
            }

            target.SetAttribute(parameter.Name, ConvertToAttributeType(target, parameter.Name, parameter.Value));
        }

        /// <summary>
        /// Writes a raw GSD parameter record (byte-exact) onto the GsdDeviceItem
        /// service of the path target. The hex value comes normalized from the parser.
        /// </summary>
        private static void ApplyPrmData(IEngineeringObject root, CustomParameter parameter, string context)
        {
            IEngineeringObject target = parameter.Path.Count == 0 ? root : ResolvePath(root, parameter.Path);
            if (target == null)
            {
                Log("Custom parameter error (" + context + "): path of " + parameter + " does not exist on " + Describe(root));
                return;
            }

            DeviceItem item = target as DeviceItem;
            if (item == null)
            {
                Log("Custom parameter error (" + context + "): " + parameter.Name + " needs an Item(..) path to a GSD module (target of " +
                    parameter + " is not a device item)");
                return;
            }

            GsdDeviceItem gsd = item.GetService<GsdDeviceItem>();
            if (gsd == null)
            {
                Log("Custom parameter error (" + context + "): " + Describe(item) + " is not a GSD device item - " + parameter.Name + " skipped");
                return;
            }

            gsd.SetPrmData(parameter.PrmDataRecord, 0, HexToBytes(parameter.Value));
        }

        /// <summary>Walks an explicit Item(i)/Ch(i)/Addr(i) path down from the root.</summary>
        private static IEngineeringObject ResolvePath(IEngineeringObject root, IList<CustomParameterPathStep> path)
        {
            IEngineeringObject current = root;
            foreach (CustomParameterPathStep step in path)
            {
                switch (step.Kind)
                {
                    case CustomParameterStepKind.Item:
                        DeviceItemComposition children = ChildItemsOf(current);
                        if (children == null || step.Index >= children.Count) return null;
                        current = children[step.Index];
                        break;

                    case CustomParameterStepKind.Channel:
                        DeviceItem channelOwner = current as DeviceItem;
                        if (channelOwner == null) return null;
                        current = TryGetChannel(channelOwner, step.Index);
                        if (current == null) return null;
                        break;

                    case CustomParameterStepKind.Address:
                        DeviceItem addressOwner = current as DeviceItem;
                        if (addressOwner == null) return null;
                        current = TryGetAddress(addressOwner, step.Index);
                        if (current == null) return null;
                        break;

                    default:
                        return null;
                }
            }
            return current;
        }

        /// <summary>First object in the tree that exposes the attribute as writable (root included).</summary>
        private static IEngineeringObject FindAttributeOwner(IEngineeringObject root, string attributeName)
        {
            if (HasWritableAttribute(root, attributeName))
                return root;
            foreach (DeviceItem item in EnumerateAllItems(root))
            {
                if (HasWritableAttribute(item, attributeName))
                    return item;
            }
            return null;
        }

        /// <summary>First channel with the given index (anywhere in the tree) exposing the attribute.</summary>
        private static IEngineeringObject FindChannelOwner(IEngineeringObject root, int channelIndex, string attributeName)
        {
            foreach (DeviceItem item in EnumerateAllItems(root))
            {
                IEngineeringObject channel = TryGetChannel(item, channelIndex);
                if (channel != null && HasWritableAttribute(channel, attributeName))
                    return channel;
            }
            return null;
        }

        /// <summary>All device items below the root (module: itself + sub items; station: every item).</summary>
        private static IEnumerable<DeviceItem> EnumerateAllItems(IEngineeringObject root)
        {
            DeviceItem rootItem = root as DeviceItem;
            if (rootItem != null)
            {
                foreach (DeviceItem item in EnumerateModuleItems(rootItem))
                    yield return item;
                yield break;
            }

            Device device = root as Device;
            if (device == null) yield break;
            foreach (DeviceItem topItem in device.DeviceItems)
            {
                foreach (DeviceItem item in EnumerateModuleItems(topItem))
                    yield return item;
            }
        }

        /// <summary>The item itself and all its sub items, depth first.</summary>
        private static IEnumerable<DeviceItem> EnumerateModuleItems(DeviceItem root)
        {
            yield return root;
            foreach (DeviceItem child in root.DeviceItems)
            {
                foreach (DeviceItem descendant in EnumerateModuleItems(child))
                    yield return descendant;
            }
        }

        /// <summary>Child item composition of a Device or DeviceItem; null for other objects.</summary>
        private static DeviceItemComposition ChildItemsOf(IEngineeringObject node)
        {
            DeviceItem item = node as DeviceItem;
            if (item != null) return item.DeviceItems;
            Device device = node as Device;
            return device == null ? null : device.DeviceItems;
        }

        private static IEngineeringObject TryGetChannel(DeviceItem item, int index)
        {
            try
            {
                var channels = item.Channels;
                if (channels == null || index < 0 || index >= channels.Count) return null;
                return channels[index];
            }
            catch
            {
                return null; //item exposes no channel composition
            }
        }

        private static IEngineeringObject TryGetAddress(DeviceItem item, int index)
        {
            try
            {
                var addresses = item.Addresses;
                if (addresses == null || index < 0 || index >= addresses.Count) return null;
                return addresses[index];
            }
            catch
            {
                return null; //item exposes no address composition
            }
        }

        private static bool HasWritableAttribute(IEngineeringObject node, string attributeName)
        {
            foreach (var info in node.GetAttributeInfos())
            {
                if (info.Name == attributeName)
                    return info.AccessMode != EngineeringAttributeAccessMode.Read;
            }
            return false;
        }

        /// <summary>"module X" / "station Y" for error messages.</summary>
        private static string Describe(IEngineeringObject node)
        {
            DeviceItem item = node as DeviceItem;
            if (item != null) return "module " + item.Name;
            Device device = node as Device;
            if (device != null) return "station " + device.Name;
            return node.ToString();
        }

        private static byte[] HexToBytes(string hex)
        {
            var bytes = new byte[hex.Length / 2];
            for (int i = 0; i < bytes.Length; i++)
                bytes[i] = Convert.ToByte(hex.Substring(i * 2, 2), 16);
            return bytes;
        }

        /// <summary>
        /// Converts the value text to the type the attribute actually has (read from
        /// its current value); falls back to ulong-or-string for write-only attributes.
        /// </summary>
        private static object ConvertToAttributeType(IEngineeringObject target, string attributeName, string valueText)
        {
            Type attributeType = null;
            try
            {
                object currentValue = target.GetAttribute(attributeName);
                attributeType = currentValue == null ? null : currentValue.GetType();
            }
            catch
            {
                //write-only or inaccessible attribute: use the fallback below
            }

            if (attributeType == null)
            {
                ulong numeric;
                return ulong.TryParse(valueText, out numeric) ? (object)numeric : valueText;
            }
            if (attributeType == typeof(string)) return valueText;
            if (attributeType.IsEnum) return Enum.Parse(attributeType, valueText, true);
            if (attributeType == typeof(bool))
            {
                if (valueText == "1") return true;
                if (valueText == "0") return false;
                return bool.Parse(valueText);
            }
            return Convert.ChangeType(valueText, attributeType, System.Globalization.CultureInfo.InvariantCulture);
        }
    }
}

using System;
using System.Collections.Generic;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Openn._01_Constructor;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Writes the custom parameters of a plugged module into the TIA object model.
    ///
    /// The parameters come pre-parsed from CustomParameterParser (model defaults
    /// merged with per-row overrides). Where a value is written depends on its path:
    ///   - explicit path (Item(i).Ch(i).Name=Value): resolved literally from the module,
    ///   - channel-only path (Ch(i).Name=Value): the sub item owning that channel is searched,
    ///   - no path (Name=Value): the first object in the module tree exposing a
    ///     writable attribute of that name is used (GetAttributeInfos discovery),
    ///     so new device families need no code changes.
    /// Values are converted to the type the attribute actually has - TIA attributes
    /// are typed and a fixed-type write would fail for string/bool/enum attributes.
    ///
    /// Stateless; like all Openness access it must run on the TiaWorker thread.
    /// </summary>
    internal static class CustomParameterApplier
    {
        /// <summary>
        /// Parses, merges and applies all parameters of one module. Problems are
        /// logged per parameter (with the given station/module context); one bad
        /// parameter does not stop the others.
        /// </summary>
        public static void Apply(DeviceItem module, string globalParameters, string specificParameters, string ipAddress, string context)
        {
            var parseErrors = new List<string>();
            IList<CustomParameter> parameters = CustomParameterParser.Parse(globalParameters, specificParameters, ipAddress, parseErrors);
            foreach (string parseError in parseErrors)
                Log("Custom parameter error (" + context + "): " + parseError);

            if (parameters.Count == 0)
                return;

            if (module == null)
            {
                Log("Custom parameter error (" + context + "): module not found, " + parameters.Count + " parameter(s) skipped");
                return;
            }

            foreach (CustomParameter parameter in parameters)
            {
                try
                {
                    ApplyParameter(module, parameter, context);
                }
                catch (Exception e)
                {
                    Log("Custom parameter error (" + context + "): " + parameter + "\n" + e.Message);
                }
            }
        }

        /// <summary>Resolves the target object for one parameter and writes the value.</summary>
        private static void ApplyParameter(DeviceItem module, CustomParameter parameter, string context)
        {
            IEngineeringObject target;
            if (parameter.Path.Count == 0)
            {
                target = FindAttributeOwner(module, parameter.Name);
                if (target == null)
                {
                    Log("Custom parameter error (" + context + "): no object of module " + module.Name +
                        " has a writable attribute \"" + parameter.Name + "\"");
                    return;
                }
            }
            else if (parameter.Path[0].IsChannel)
            {
                //channel without an explicit Item(..): find the sub item owning that channel
                target = FindChannelOwner(module, parameter.Path[0].Index, parameter.Name);
                if (target == null)
                {
                    Log("Custom parameter error (" + context + "): no channel " + parameter.Path[0].Index +
                        " with a writable attribute \"" + parameter.Name + "\" found on module " + module.Name);
                    return;
                }
            }
            else
            {
                target = ResolvePath(module, parameter.Path);
                if (target == null)
                {
                    Log("Custom parameter error (" + context + "): path of " + parameter + " does not exist on module " + module.Name);
                    return;
                }
            }

            target.SetAttribute(parameter.Name, ConvertToAttributeType(target, parameter.Name, parameter.Value));
        }

        /// <summary>Walks an explicit Item(i)/Ch(i) path down from the module.</summary>
        private static IEngineeringObject ResolvePath(DeviceItem module, IList<CustomParameterPathStep> path)
        {
            IEngineeringObject current = module;
            foreach (CustomParameterPathStep step in path)
            {
                DeviceItem item = current as DeviceItem;
                if (item == null) return null; //only DeviceItems have sub items/channels
                current = step.IsChannel ? (IEngineeringObject)item.Channels[step.Index] : item.DeviceItems[step.Index];
            }
            return current;
        }

        /// <summary>First object in the module tree that exposes the attribute as writable.</summary>
        private static IEngineeringObject FindAttributeOwner(DeviceItem module, string attributeName)
        {
            foreach (DeviceItem item in EnumerateModuleItems(module))
            {
                if (HasWritableAttribute(item, attributeName))
                    return item;
            }
            return null;
        }

        /// <summary>First channel with the given index (anywhere in the module tree) exposing the attribute.</summary>
        private static IEngineeringObject FindChannelOwner(DeviceItem module, int channelIndex, string attributeName)
        {
            foreach (DeviceItem item in EnumerateModuleItems(module))
            {
                IEngineeringObject channel = TryGetChannel(item, channelIndex);
                if (channel != null && HasWritableAttribute(channel, attributeName))
                    return channel;
            }
            return null;
        }

        /// <summary>The module itself and all its sub items, depth first.</summary>
        private static IEnumerable<DeviceItem> EnumerateModuleItems(DeviceItem root)
        {
            yield return root;
            foreach (DeviceItem child in root.DeviceItems)
            {
                foreach (DeviceItem descendant in EnumerateModuleItems(child))
                    yield return descendant;
            }
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

        private static bool HasWritableAttribute(IEngineeringObject node, string attributeName)
        {
            foreach (var info in node.GetAttributeInfos())
            {
                if (info.Name == attributeName)
                    return info.AccessMode != EngineeringAttributeAccessMode.Read;
            }
            return false;
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

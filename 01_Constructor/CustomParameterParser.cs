using System;
using System.Collections.Generic;
using System.Linq;

namespace Openn._01_Constructor
{
    /// <summary>One step in a parameter target path: Item(n) = child DeviceItem n, Ch(n) = channel n.</summary>
    public struct CustomParameterPathStep
    {
        public bool IsChannel;
        public int Index;

        public CustomParameterPathStep(bool isChannel, int index)
        {
            IsChannel = isChannel;
            Index = index;
        }

        public override string ToString() => (IsChannel ? "Ch(" : "Item(") + Index + ")";
    }

    /// <summary>
    /// One parsed custom parameter: where to write (Path; empty = discover the owner
    /// by searching the module's object tree), which attribute (Name), and the value
    /// text (converted to the attribute's actual type at apply time).
    /// </summary>
    public sealed class CustomParameter
    {
        public List<CustomParameterPathStep> Path { get; } = new List<CustomParameterPathStep>();
        public string Name;
        public string Value;

        /// <summary>Normalized "path.Name" identity used for override matching.</summary>
        public string Key => string.Join(".", Path.Select(s => s.ToString()).Concat(new[] { Name }));

        public override string ToString() => Key + "=" + Value;
    }

    /// <summary>
    /// Parser for the Custom Parameters csv cells.
    /// Entries are separated by '|' (',' is rejected - it collides with Excel's csv delimiter).
    /// Entry grammar:  [Item(i).][Ch(i).]Name=Value
    /// One (from-to) range per entry expands to one entry per index, e.g. "Ch(0-7)".
    /// "IP[i]" inside the value is replaced with octet i (0..3) of the station IP.
    /// </summary>
    public static class CustomParameterParser
    {
        public const char Separator = '|';

        /// <summary>
        /// Parses and merges the model-wide defaults with the per-row parameters;
        /// a row parameter overrides the default with the same target (Key).
        /// Problems are appended to <paramref name="errors"/>.
        /// </summary>
        public static IList<CustomParameter> Parse(string globalParameters, string specificParameters, string ipAddress, IList<string> errors)
        {
            List<CustomParameter> specific = ParseList(specificParameters, ipAddress, errors);
            List<CustomParameter> global = ParseList(globalParameters, ipAddress, errors);

            var merged = new List<CustomParameter>(specific);
            foreach (CustomParameter candidate in global)
            {
                if (!specific.Any(p => p.Key.Equals(candidate.Key, StringComparison.OrdinalIgnoreCase)))
                    merged.Add(candidate);
            }
            return merged;
        }

        private static List<CustomParameter> ParseList(string text, string ipAddress, IList<string> errors)
        {
            var parameters = new List<CustomParameter>();
            if (string.IsNullOrWhiteSpace(text)) return parameters;

            if (text.IndexOf(',') >= 0)
            {
                errors.Add("invalid parameter list \"" + text + "\": ',' is not a valid separator - use '|'");
                return parameters;
            }

            foreach (string rawEntry in text.Split(Separator))
            {
                string entry = rawEntry.Trim();
                if (entry.Length == 0) continue;

                foreach (string expanded in ExpandRange(entry, errors))
                {
                    CustomParameter parameter = ParseEntry(expanded, ipAddress, errors);
                    if (parameter != null) parameters.Add(parameter);
                }
            }
            return parameters;
        }

        /// <summary>Expands the one allowed "(from-to)" range left of '=' into per-index entries.</summary>
        private static List<string> ExpandRange(string entry, IList<string> errors)
        {
            var expanded = new List<string>();
            int equalsIndex = entry.IndexOf('=');
            string left = equalsIndex >= 0 ? entry.Substring(0, equalsIndex) : entry;

            int rangeOpen = -1;
            string rangeContent = null;
            for (int open = left.IndexOf('('); open >= 0; open = left.IndexOf('(', open + 1))
            {
                int close = left.IndexOf(')', open + 1);
                if (close < 0) break; //malformed: ParseEntry reports it

                string content = left.Substring(open + 1, close - open - 1);
                if (!content.Contains("-")) continue;

                if (rangeContent != null)
                {
                    errors.Add("invalid parameter \"" + entry + "\": only one (from-to) range is allowed");
                    return expanded;
                }
                rangeOpen = open;
                rangeContent = content;
            }

            if (rangeContent == null)
            {
                expanded.Add(entry);
                return expanded;
            }

            string[] bounds = rangeContent.Split('-');
            int from, to;
            if (bounds.Length != 2 || !int.TryParse(bounds[0], out from) || !int.TryParse(bounds[1], out to) || from < 0 || to < from)
            {
                errors.Add("invalid parameter \"" + entry + "\": bad range \"(" + rangeContent + ")\" (expected (from-to) with from <= to)");
                return expanded;
            }
            if (to - from > 1000)
            {
                errors.Add("invalid parameter \"" + entry + "\": range \"(" + rangeContent + ")\" is too large");
                return expanded;
            }

            string prefix = entry.Substring(0, rangeOpen + 1);
            string suffix = entry.Substring(rangeOpen + 1 + rangeContent.Length); //starts at the closing ')'
            for (int i = from; i <= to; i++)
                expanded.Add(prefix + i + suffix);
            return expanded;
        }

        private static CustomParameter ParseEntry(string entry, string ipAddress, IList<string> errors)
        {
            int equalsIndex = entry.IndexOf('=');
            if (equalsIndex <= 0)
            {
                errors.Add("invalid parameter \"" + entry + "\" (expected Name=Value)");
                return null;
            }

            string value = SubstituteIp(entry.Substring(equalsIndex + 1).Trim(), ipAddress, entry, errors);
            if (value == null) return null;

            var parameter = new CustomParameter { Value = value };

            foreach (string rawToken in entry.Substring(0, equalsIndex).Split('.'))
            {
                string token = rawToken.Trim();

                bool isChannel;
                int index;
                if (TryParseStep(token, out isChannel, out index))
                {
                    if (parameter.Name != null)
                    {
                        errors.Add("invalid parameter \"" + entry + "\": path steps must come before the attribute name");
                        return null;
                    }
                    if (parameter.Path.Any(s => s.IsChannel))
                    {
                        errors.Add("invalid parameter \"" + entry + "\": Ch(..) must be the last path step");
                        return null;
                    }
                    parameter.Path.Add(new CustomParameterPathStep(isChannel, index));
                }
                else
                {
                    if (token.Length == 0 || token.IndexOfAny(new[] { '(', ')' }) >= 0)
                    {
                        errors.Add("invalid parameter \"" + entry + "\": malformed path step or attribute name \"" + token + "\" (expected Item(i), Ch(i) or a name)");
                        return null;
                    }
                    if (parameter.Name != null)
                    {
                        errors.Add("invalid parameter \"" + entry + "\": more than one attribute name");
                        return null;
                    }
                    parameter.Name = token;
                }
            }

            if (parameter.Name == null)
            {
                errors.Add("invalid parameter \"" + entry + "\": no attribute name");
                return null;
            }
            return parameter;
        }

        private static bool TryParseStep(string token, out bool isChannel, out int index)
        {
            isChannel = false;
            index = -1;

            int open = token.IndexOf('(');
            if (open <= 0 || !token.EndsWith(")", StringComparison.Ordinal)) return false;

            string kind = token.Substring(0, open);
            if (kind.Equals("Ch", StringComparison.OrdinalIgnoreCase)) isChannel = true;
            else if (!kind.Equals("Item", StringComparison.OrdinalIgnoreCase)) return false;

            string content = token.Substring(open + 1, token.Length - open - 2);
            return int.TryParse(content, out index) && index >= 0;
        }

        private static string SubstituteIp(string value, string ipAddress, string entry, IList<string> errors)
        {
            int start;
            while ((start = value.IndexOf("IP[", StringComparison.OrdinalIgnoreCase)) >= 0)
            {
                int close = value.IndexOf(']', start);
                int octetIndex;
                if (close < 0 || !int.TryParse(value.Substring(start + 3, close - start - 3), out octetIndex) || octetIndex < 0 || octetIndex > 3)
                {
                    errors.Add("invalid parameter \"" + entry + "\": bad IP placeholder (expected IP[0]..IP[3])");
                    return null;
                }

                string[] octets = (ipAddress ?? string.Empty).Split('.');
                if (octets.Length != 4)
                {
                    errors.Add("invalid parameter \"" + entry + "\": IP[..] used but the station has no valid IP address");
                    return null;
                }

                value = value.Substring(0, start) + octets[octetIndex] + value.Substring(close + 1);
            }
            return value;
        }
    }
}

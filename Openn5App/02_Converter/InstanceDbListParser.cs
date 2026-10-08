using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

namespace Openn._02_Converter
{
    /// <summary>One instance DB to create: maps onto PlcBlockComposition.CreateInstanceDB.</summary>
    public sealed class InstanceDbSpec
    {
        public string Name;          //instance DB name
        public string InstanceOf;    //name of the FB this is an instance of
        public int? Number;          //explicit DB number; null = auto-number
        public string Folder = "";   //target block-group path ("A/B"); "" = root
        public int LineNumber;       //source csv line, for error messages
    }

    /// <summary>
    /// Parser for the instance-DB list csv. Same row-marker conventions as the block
    /// generator (BlockXmlGenerator) but with NAMED columns so column order is free
    /// and a database/PowerQuery export can produce it directly:
    ///   $;separator=";"        directive (optional; default ',')
    ///   #;...                  comment (skipped)
    ///   %;Name;InstanceOf;...  key row (exactly one) - names the columns
    ///   @;value;value;...      one instance DB per row, aligned with the key row
    ///   &amp;END                  stop processing
    /// Recognized field names (case-insensitive): Name; InstanceOf / FB / InstanceOfFB;
    /// Number; Folder / Group. Empty or '#'-prefixed headers mark ignored columns.
    /// Cell 0 is the row marker; cells 1+ align key row to data rows. Validation is
    /// all-or-nothing with file+line errors.
    /// </summary>
    public static class InstanceDbListParser
    {
        public static IList<InstanceDbSpec> Parse(string csvPath, IList<string> errors)
        {
            var specs = new List<InstanceDbSpec>();
            if (!File.Exists(csvPath))
            {
                errors.Add("Instance DB csv not found: " + csvPath);
                return specs;
            }

            string[] lines = File.ReadAllLines(csvPath);
            char separator = ',';
            List<string> keys = null;
            var seenNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            for (int i = 0; i < lines.Length; i++)
            {
                string line = lines[i].Trim();
                if (line.Length == 0) continue;

                if (line.StartsWith("$", StringComparison.Ordinal))
                {
                    ParseSeparatorDirective(line, csvPath, i + 1, ref separator, errors);
                    continue;
                }
                if (line.StartsWith("#", StringComparison.Ordinal)) continue;
                if (IsEndMarker(line)) break;

                List<string> cells = TruncateAtEndMarker(SplitCsvLine(line, separator).Select(c => c.Trim()).ToList());
                if (cells.Count == 0) continue;

                if (cells[0] == "%")
                {
                    if (keys != null) { errors.Add(Where(csvPath, i + 1) + "second % key row (only one is allowed)"); continue; }
                    keys = cells;
                }
                else if (cells[0] == "@")
                {
                    if (keys == null) { errors.Add(Where(csvPath, i + 1) + "data row before the % key row"); continue; }
                    if (cells.Skip(1).All(c => c.Length == 0)) continue;
                    ParseDataRow(cells, keys, csvPath, i + 1, specs, seenNames, errors);
                }
                //unmarked rows are ignored
            }

            if (keys == null) errors.Add(csvPath + ": no % key row found");
            else if (specs.Count == 0) errors.Add(csvPath + ": no @ data rows below the % key row");

            return specs;
        }

        private static void ParseDataRow(List<string> cells, List<string> keys, string csvPath, int lineNumber,
            List<InstanceDbSpec> specs, HashSet<string> seenNames, IList<string> errors)
        {
            var spec = new InstanceDbSpec { LineNumber = lineNumber };
            string numberText = null;

            for (int c = 1; c < keys.Count; c++)
            {
                string key = keys[c];
                if (key.Length == 0 || key.StartsWith("#", StringComparison.Ordinal)) continue;
                string value = c < cells.Count ? cells[c] : "";

                switch (key.ToLowerInvariant())
                {
                    case "name": spec.Name = value; break;
                    case "instanceof":
                    case "instanceoffb":
                    case "fb": spec.InstanceOf = value; break;
                    case "number": numberText = value; break;
                    case "folder":
                    case "group": spec.Folder = value; break;
                    default:
                        errors.Add(Where(csvPath, lineNumber) + "unknown column \"" + key + "\" (known: Name, InstanceOf/FB, Number, Folder)");
                        return;
                }
            }

            if (string.IsNullOrEmpty(spec.Name)) { errors.Add(Where(csvPath, lineNumber) + "missing Name"); return; }
            if (string.IsNullOrEmpty(spec.InstanceOf)) { errors.Add(Where(csvPath, lineNumber) + "missing InstanceOf (the FB name) for \"" + spec.Name + "\""); return; }

            if (!string.IsNullOrEmpty(numberText))
            {
                int number;
                if (!int.TryParse(numberText, out number) || number <= 0)
                {
                    errors.Add(Where(csvPath, lineNumber) + "Number must be a positive integer or empty (auto), found \"" + numberText + "\"");
                    return;
                }
                spec.Number = number;
            }

            if (!seenNames.Add(spec.Name))
                errors.Add(Where(csvPath, lineNumber) + "duplicate instance DB name \"" + spec.Name + "\"");

            specs.Add(spec);
        }

        #region csv plumbing (mirrors BlockXmlGenerator conventions)

        private static void ParseSeparatorDirective(string line, string csvPath, int lineNumber, ref char separator, IList<string> errors)
        {
            string rest = line.Substring(1);
            string directive;
            if (rest.Length > 0 && !char.IsLetterOrDigit(rest[0]))
            {
                char rowDelimiter = rest[0];
                string remainder = rest.Substring(1);
                var quoted = System.Text.RegularExpressions.Regex.Match(remainder, "^\\s*(\\w+)\\s*=\\s*(\"(?:[^\"]|\"\")*\")");
                directive = quoted.Success ? quoted.Groups[1].Value + "=" + quoted.Groups[2].Value : SplitCsvLine(remainder, rowDelimiter)[0].Trim();
            }
            else directive = rest.Trim();

            int eq = directive.IndexOf('=');
            if (eq <= 0) { errors.Add(Where(csvPath, lineNumber) + "malformed directive \"" + line + "\""); return; }
            string key = directive.Substring(0, eq).Trim().ToLowerInvariant();
            string value = Unquote(directive.Substring(eq + 1).Trim());

            if (key == "separator")
            {
                if (value.Equals("tab", StringComparison.OrdinalIgnoreCase)) separator = '\t';
                else if (value.Length == 1) separator = value[0];
                else errors.Add(Where(csvPath, lineNumber) + "separator must be a single character (or \"tab\"); quote it when it equals the row delimiter: separator=\";\"");
            }
            else errors.Add(Where(csvPath, lineNumber) + "unknown directive \"" + key + "\" (only separator is supported here)");
        }

        private static List<string> SplitCsvLine(string line, char separator)
        {
            var cells = new List<string>();
            var cell = new StringBuilder();
            bool quoted = false;
            for (int i = 0; i < line.Length; i++)
            {
                char ch = line[i];
                if (quoted)
                {
                    if (ch == '"')
                    {
                        if (i + 1 < line.Length && line[i + 1] == '"') { cell.Append('"'); i++; }
                        else quoted = false;
                    }
                    else cell.Append(ch);
                }
                else if (ch == '"' && cell.Length == 0) quoted = true;
                else if (ch == separator) { cells.Add(cell.ToString()); cell.Clear(); }
                else cell.Append(ch);
            }
            cells.Add(cell.ToString());
            return cells;
        }

        private static bool IsEndMarker(string line)
        {
            if (!line.StartsWith("&END", StringComparison.OrdinalIgnoreCase)) return false;
            return line.Length == 4 || !char.IsLetterOrDigit(line[4]);
        }

        private static List<string> TruncateAtEndMarker(List<string> cells)
        {
            int index = cells.FindIndex(c => c.Equals("&END", StringComparison.OrdinalIgnoreCase));
            return index < 0 ? cells : cells.Take(index).ToList();
        }

        private static string Unquote(string value) =>
            value.Length >= 2 && value[0] == '"' && value[value.Length - 1] == '"'
                ? value.Substring(1, value.Length - 2).Replace("\"\"", "\"")
                : value;

        private static string Where(string file, int lineNumber) => Path.GetFileName(file) + " line " + lineNumber + ": ";

        #endregion csv plumbing
    }
}

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace Openn._10_StandardFunctions
{
    public sealed class CsvRow
    {
        public CsvRow(int lineNumber, string[] values)
        {
            LineNumber = lineNumber;
            Values = values;
        }

        public int LineNumber { get; }
        public string[] Values { get; }

        /// <summary>Trimmed cell value; missing columns read as empty string.</summary>
        public string Get(int index) =>
            index < Values.Length ? Values[index].Trim() : string.Empty;
    }

    /// <summary>
    /// Shared reader for the HardwareConfig csv files.
    /// Conventions: UTF-8 (BOM tolerated); ';' delimiter unless specified;
    /// '#!format=N' declares the file format version (defaults to 1);
    /// '#' starts a comment line; a line starting with '@' stops reading;
    /// blank lines are skipped; fields may be quoted with '"' ("" escapes a quote).
    /// </summary>
    public sealed class CsvTable
    {
        public string FilePath { get; private set; }
        public int FormatVersion { get; private set; } = 1;
        public IList<CsvRow> Rows { get; } = new List<CsvRow>();
        public IList<string> Errors { get; } = new List<string>();

        public static CsvTable Read(string filePath, char delimiter = ';')
        {
            var table = new CsvTable { FilePath = filePath };

            if (!File.Exists(filePath))
            {
                table.Errors.Add("File not found: " + filePath);
                return table;
            }

            try
            {
                int lineNumber = 0;
                foreach (string rawLine in File.ReadLines(filePath, Encoding.UTF8))
                {
                    lineNumber++;
                    string line = rawLine.Trim();
                    if (line.Length == 0) continue;

                    if (line.StartsWith("#!", StringComparison.Ordinal))
                    {
                        string[] directive = line.Substring(2).Split('=');
                        if (directive.Length == 2 &&
                            directive[0].Trim().Equals("format", StringComparison.OrdinalIgnoreCase) &&
                            int.TryParse(directive[1].Trim(), out int version))
                        {
                            table.FormatVersion = version;
                        }
                        continue;
                    }
                    if (line[0] == '#') continue;
                    if (line[0] == '@') break;

                    table.Rows.Add(new CsvRow(lineNumber, SplitLine(line, delimiter)));
                }
            }
            catch (Exception e)
            {
                table.Errors.Add("Error reading " + filePath + ": " + e.Message);
            }

            return table;
        }

        /// <summary>Splits one csv line, honoring '"' quoting with '""' escapes.</summary>
        public static string[] SplitLine(string line, char delimiter)
        {
            var fields = new List<string>();
            var current = new StringBuilder();
            bool inQuotes = false;

            for (int i = 0; i < line.Length; i++)
            {
                char c = line[i];
                if (inQuotes)
                {
                    if (c == '"')
                    {
                        if (i + 1 < line.Length && line[i + 1] == '"') { current.Append('"'); i++; }
                        else inQuotes = false;
                    }
                    else current.Append(c);
                }
                else if (c == '"' && current.Length == 0)
                {
                    inQuotes = true;
                }
                else if (c == delimiter)
                {
                    fields.Add(current.ToString());
                    current.Length = 0;
                }
                else current.Append(c);
            }
            fields.Add(current.ToString());
            return fields.ToArray();
        }
    }
}

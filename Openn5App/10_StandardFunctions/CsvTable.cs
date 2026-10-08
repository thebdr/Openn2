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
    /// Conventions: UTF-8 (BOM tolerated); ',' delimiter unless specified;
    /// '#!' lines form the OpennN header ('#!openn' ... '#!end', see Openn._00_Contract.OpennHeader)
    /// or the legacy '#!format=N' tag (format defaults to 1);
    /// '#' starts a comment line; a line starting with '@' stops reading;
    /// blank lines are skipped; fields may be quoted with '"' ("" escapes a quote).
    /// </summary>
    public sealed class CsvTable
    {
        public string FilePath { get; private set; }
        /// <summary>The legacy "#!format=N" tag (1 when absent). Contract v1 files carry Header instead.</summary>
        public int FormatVersion { get; private set; } = 1;
        /// <summary>The "#!openn" header block; Status Missing / Legacy when the file has none.</summary>
        public Openn._00_Contract.OpennHeader Header { get; private set; } = new Openn._00_Contract.OpennHeader();
        public IList<CsvRow> Rows { get; } = new List<CsvRow>();
        public IList<string> Errors { get; } = new List<string>();

        public static CsvTable Read(string filePath, char delimiter = ',')
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
                var directives = new List<string>();
                foreach (string rawLine in ReadAllLines(filePath))
                {
                    lineNumber++;
                    string line = rawLine.Trim();
                    if (line.Length == 0) continue;

                    if (line.StartsWith("#!", StringComparison.Ordinal))
                    {
                        // "#!openn" header lines and the legacy "#!format=N" tag. Excel pads these
                        // lines with delimiters ("#!format=2,,,,,") when it saves the file -
                        // NormalizeCsvLine undoes the padding (and Excel's quoting).
                        directives.Add(Openn._00_Contract.OpennHeader.NormalizeCsvLine(line));
                        continue;
                    }
                    if (line[0] == '#') continue;
                    if (line[0] == '@') break;

                    table.Rows.Add(new CsvRow(lineNumber, SplitLine(line, delimiter)));
                }
                table.Header = Openn._00_Contract.OpennHeader.FromDirectiveLines(directives);
                if (table.Header.LegacyFormat.HasValue) table.FormatVersion = table.Header.LegacyFormat.Value;
            }
            catch (Exception e)
            {
                table.Errors.Add("Error reading " + filePath + ": " + e.Message);
            }

            return table;
        }

        /// <summary>
        /// Reads every line, then closes the file before parsing. The handle is opened
        /// FileShare.ReadWrite and released immediately, so reading a config file here
        /// never locks it against the codependent Pipeline5 (which regenerates these csv
        /// files) or against Excel. (File.ReadLines keeps a StreamReader open for the whole
        /// enumeration and shares only FileShare.Read, briefly blocking a concurrent writer.)
        /// </summary>
        private static List<string> ReadAllLines(string filePath)
        {
            var lines = new List<string>();
            using (var stream = new FileStream(filePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true))
            {
                string line;
                while ((line = reader.ReadLine()) != null)
                    lines.Add(line);
            }
            return lines;
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

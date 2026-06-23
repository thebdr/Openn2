using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._02_Converter
{
    /// <summary>
    /// Csv-driven PLC block XML generator - the C# port of the original Excel/VBA
    /// "PlcBlock" workbook motor.
    ///
    /// Template files are TIA Openness block exports with comment markers:
    ///   &lt;!--Begin Template--&gt; ... &lt;!--End Template--&gt;
    ///       the replicated region; everything outside it is the document envelope,
    ///       copied once (head/tail) with the &lt;Engineering version&gt; stamped from
    ///       the RUNNING Openness version - templates cannot go version-stale.
    ///   &lt;!--Begin Template Network Type #NN ...--&gt; ... &lt;!--End ... #NN ...--&gt;
    ///       per-row section variants inside the region; the csv TemplateType
    ///       column selects the variant. No variant markers = single section #1.
    ///
    /// MARKER-LESS templates (plain TIA exports) are auto-templated: every
    /// SW.Blocks.CompileUnit (LAD/FBD network) becomes Network Type #1..#N in
    /// document order; an export without networks (instance/global DB) uses its
    /// single top-level SW.Blocks.* object as the section. Literal ID="hex"
    /// attributes inside any section are renumbered per generated instance, so a
    /// raw export only needs !!key$$ placeholders for the values - no manual
    /// !!Iterator$$ editing.
    ///
    /// Multi-network variants can be authored entirely in TIA via DELIMITER
    /// NETWORKS: an empty network titled "Template #NN" opens variant NN, one
    /// titled "Template End" closes it; the networks in between form the section.
    /// Delimiter networks are dropped from the output; networks before the first
    /// delimiter stay fixed in the envelope.
    ///
    /// Template blocks are version-named "TEMPLATE--v1.0--Block Name" (in TIA and
    /// as files). Generated blocks never carry the marker: the prefix is stripped
    /// from the block name, or the caller-supplied block name replaces it.
    ///
    /// Placeholders inside sections (!!key$$ syntax, as in the hand-built templates):
    ///   !!COLUMN_n$$ (any !!name$$)  value of the csv cell mapped by the key row,
    ///                                xml-escaped
    ///   !!Iterator$$                 next SimaticML object ID - hex, document-global,
    ///                                seeded above the highest literal ID found in the
    ///                                envelope (so generated IDs never collide)
    ///   !!ITERATOR_STRINGS$$         next value of the row's value list. The list starts
    ///                                at the column whose KEY ROW cell is !!ITERATOR_STRINGS$$
    ///                                (everything right of that marker is values, not
    ///                                headers). Occurrences beyond the row's last cell are
    ///                                filled empty - by design, the Network Type sections
    ///                                are capacity-sized (e.g. "#03 (51-250)") and a row
    ///                                fills only as many slots as it has values.
    ///
    /// Csv format - every row is typed by its FIRST cell:
    ///   $      directive row:  $;template=path\to\X_Template.xml   (required; relative to the csv;
    ///                              ?CsvName? = csv file name without extension, so
    ///                              template=.\TEMPLATE-?CsvName? pairs csv and template
    ///                              by name; ".xml" is appended when no extension given)
    ///                          $;separator=";"                     (cell separator; default ',';
    ///                                                               must come before the key row)
    ///          The char right after '$' delimits that row itself, so the separator
    ///          directive works regardless of the active separator. Quote the value
    ///          when it equals the row's own delimiter (Excel pads rows with trailing
    ///          separators, which would otherwise swallow it).
    ///   #      comment row - skipped
    ///   %      the KEY ROW (exactly one), aligned column-for-column with data rows
    ///   @      data row: @ ; TemplateType ; value ; value ; ...    one generated section per row
    ///   &amp;END   stop processing, everything below is ignored
    ///   (unmarked rows are ignored; a count is logged)
    ///
    /// &amp;END also works as a COLUMN terminator: in a % or @ row, a cell that is
    /// exactly &amp;END truncates the row there (everything right of it is ignored).
    ///
    /// Key row alignment: cell 0 = marker column, cell 1 = TemplateType label,
    /// cells 2+ = the !!key$$ each column maps to. A key cell that is empty or
    /// starts with '#' marks an ignored column (helper formulas etc.). The
    /// !!ITERATOR_STRINGS$$ key cell marks where the per-row value lists start -
    /// nothing right of it is a header.
    ///
    /// All problems are reported with file + line and nothing is written on error
    /// (all-or-nothing, HardwareConfigLoader style).
    /// </summary>
    public static class BlockXmlGenerator
    {
        private const string IteratorKey = "!!Iterator$$";
        private const string IteratorStringsKey = "!!ITERATOR_STRINGS$$";

        /// <summary>
        /// Generates one block XML file from the csv. Returns the output path,
        /// or null when generation failed (every problem logged).
        /// The generated block's name: <paramref name="blockNameOverride"/> when
        /// given, otherwise the template's block name with the versioned template
        /// prefix (TEMPLATE--v1.0--) stripped.
        /// </summary>
        public static string Generate(string csvPath, string portalVersionTag, string outputFolder, string blockNameOverride)
        {
            var errors = new List<string>();

            CsvData csv = ParseCsv(csvPath, errors);
            Template template = csv == null ? null : ParseTemplate(csv.TemplatePath, errors);
            if (Fail(errors)) return null;

            //assemble the document: envelope head + one substituted section per row + tail
            var output = new List<string>();
            string overrideName = string.IsNullOrWhiteSpace(blockNameOverride) ? null : blockNameOverride.Trim();
            bool blockNameHandled = false;
            foreach (string headLine in template.Head)
            {
                string line = StampEngineeringVersion(headLine, portalVersionTag);
                if (!blockNameHandled && line.Contains("<Name>"))
                {
                    //the first <Name> element of the envelope is the block's own name
                    if (overrideName != null)
                        line = Regex.Replace(line, "<Name>.*?</Name>", "<Name>" + XmlEscape(overrideName) + "</Name>");
                    else
                        line = StripTemplatePrefix(line);
                    blockNameHandled = true;
                }
                else
                {
                    line = StripTemplatePrefix(line);
                }
                output.Add(line);
            }

            long idCounter = template.IdSeed;
            foreach (CsvRow row in csv.Rows)
            {
                List<string> section;
                if (!template.Sections.TryGetValue(row.TypeNumber, out section))
                {
                    errors.Add(Where(csvPath, row.LineNumber) + "TemplateType " + row.TypeNumber +
                        " has no <!--Begin Template Network Type #" + row.TypeNumber.ToString("00") + "--> section in " +
                        Path.GetFileName(csv.TemplatePath) + " (available: " +
                        string.Join(", ", template.Sections.Keys.OrderBy(k => k)) + ")");
                    continue;
                }

                //!!ITERATOR_STRINGS$$ consumes the row's value list, which starts at the
                //key row's marker column; slots beyond the last cell fill empty
                //(capacity-sized sections)
                if (csv.IteratorStringsStart < 0 && section.Any(l => l.Contains(IteratorStringsKey)))
                {
                    errors.Add(Where(csvPath, row.LineNumber) + "the template section uses " + IteratorStringsKey +
                        " but the key row has no " + IteratorStringsKey + " cell marking where the value list starts");
                    continue;
                }
                int stringsIndex = csv.IteratorStringsStart;
                int stringsConsumed = 0, stringsNonEmpty = 0;
                foreach (string sectionLine in section)
                {
                    //literal ID="hex" attributes in the section (raw exports / auto
                    //templates) get fresh document-global IDs per generated instance;
                    //hand-built templates use ID="!!Iterator$$" which this pattern
                    //does not match - both routes end up collision-free
                    string line = StripTemplatePrefix(ObjectIdAttribute.Replace(sectionLine, m => "ID=\"" + (idCounter++).ToString("X") + "\""));

                    //cells 0/1 = row marker/TemplateType; keys that are empty or start
                    //with '#' mark ignored columns (helper formulas etc.)
                    for (int i = 2; i < csv.Keys.Count; i++)
                    {
                        if (csv.Keys[i].Length == 0 || csv.Keys[i].StartsWith("#", StringComparison.Ordinal)) continue;
                        string value = i < row.Cells.Count ? row.Cells[i] : string.Empty;
                        line = line.Replace(csv.Keys[i], XmlEscape(value));
                    }
                    line = ReplaceEachOccurrence(line, IteratorKey, () => (idCounter++).ToString("X"));
                    line = ReplaceEachOccurrence(line, IteratorStringsKey, () =>
                    {
                        string value = stringsIndex < row.Cells.Count ? row.Cells[stringsIndex] : string.Empty;
                        stringsIndex++;
                        stringsConsumed++;
                        if (value.Length > 0) stringsNonEmpty++;
                        return XmlEscape(value);
                    });
                    output.Add(line);
                }

                if (stringsConsumed > 0 && stringsNonEmpty == 0)
                    Log("Block generation warning " + Where(csvPath, row.LineNumber) + "all " + stringsConsumed +
                        " ITERATOR_STRINGS slot(s) were empty - the row has no values right of the " +
                        IteratorStringsKey + " column");
            }
            foreach (string line in template.Tail)
                output.Add(StripTemplatePrefix(StampEngineeringVersion(line, portalVersionTag)));

            if (Fail(errors)) return null;

            ValidateOutput(output, errors);
            if (Fail(errors)) return null;

            Directory.CreateDirectory(outputFolder);
            string outputPath = Path.Combine(outputFolder,
                Path.GetFileNameWithoutExtension(csvPath) + "_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".xml");
            File.WriteAllLines(outputPath, output, Encoding.UTF8);

            Log("Generated " + csv.Rows.Count + " block section(s) (" + portalVersionTag + ", IDs from 0x" +
                template.IdSeed.ToString("X") + ") from " + Path.GetFileName(csvPath) + "\n" + outputPath);
            return outputPath;
        }

        #region Csv parsing

        private sealed class CsvRow
        {
            public int LineNumber;
            public int TypeNumber;
            public List<string> Cells;
        }

        private sealed class CsvData
        {
            public string TemplatePath;
            public List<string> Keys;   //index 0 = the TemplateType column (label ignored)
            public List<CsvRow> Rows = new List<CsvRow>();

            /// <summary>
            /// 0-based cell index where the ITERATOR_STRINGS value list starts = the
            /// position of the !!ITERATOR_STRINGS$$ marker in the key row; -1 = no marker.
            /// </summary>
            public int IteratorStringsStart = -1;
        }

        private static CsvData ParseCsv(string csvPath, List<string> errors)
        {
            if (!File.Exists(csvPath))
            {
                errors.Add("Generation csv not found: " + csvPath);
                return null;
            }

            var csv = new CsvData();
            string[] lines = File.ReadAllLines(csvPath);
            char separator = ',';
            int ignoredUnmarked = 0;

            for (int i = 0; i < lines.Length; i++)
            {
                string line = lines[i].Trim();
                if (line.Length == 0) continue;

                //row type = first cell ($ rows are self-delimiting, see ParseDirective)
                if (line.StartsWith("$", StringComparison.Ordinal))
                {
                    ParseDirective(line, csvPath, i + 1, csv, ref separator, errors);
                    continue;
                }
                if (line.StartsWith("#", StringComparison.Ordinal)) continue;
                if (IsEndMarker(line)) break;

                List<string> cells = TruncateAtEndMarker(SplitCsvLine(line, separator).Select(c => c.Trim()).ToList());

                if (cells.Count == 0) continue;

                if (cells[0] == "@") //data row
                {
                    if (csv.Keys == null)
                    {
                        errors.Add(Where(csvPath, i + 1) + "data row before the % key row");
                        continue;
                    }
                    if (cells.Skip(1).All(c => c.Length == 0)) continue;
                    if (cells.Count < 2 || cells[1].Length == 0)
                    {
                        errors.Add(Where(csvPath, i + 1) + "data row has no TemplateType (expected @" + separator + "TemplateType" + separator + "...)");
                        continue;
                    }

                    int typeNumber;
                    if (!int.TryParse(cells[1], out typeNumber))
                    {
                        errors.Add(Where(csvPath, i + 1) + "TemplateType \"" + cells[1] + "\" is not a number");
                        continue;
                    }
                    csv.Rows.Add(new CsvRow { LineNumber = i + 1, TypeNumber = typeNumber, Cells = cells });
                }
                else if (cells[0] == "%") //key row
                {
                    if (csv.Keys != null)
                    {
                        errors.Add(Where(csvPath, i + 1) + "second % key row (only one is allowed)");
                        continue;
                    }
                    //aligns column-for-column with data rows (cell 0 = marker column,
                    //cell 1 = TemplateType label, 2+ = !!key$$ map). The
                    //!!ITERATOR_STRINGS$$ cell marks where row value lists start -
                    //everything right of it is data, not headers.
                    int marker = cells.FindIndex(c => c.Equals(IteratorStringsKey, StringComparison.OrdinalIgnoreCase));
                    if (marker >= 0)
                    {
                        csv.IteratorStringsStart = marker;
                        cells = cells.Take(marker).ToList();
                    }
                    csv.Keys = cells;
                }
                else
                {
                    ignoredUnmarked++; //unmarked rows (e.g. the Excel title row) do not generate
                }
            }

            if (ignoredUnmarked > 0)
                Log("Block generation: " + ignoredUnmarked + " unmarked row(s) ignored (only @ rows generate)");

            if (csv.TemplatePath == null)
                errors.Add(csvPath + ": missing template directive ($" + separator + "template=<path>)");
            if (csv.Keys == null)
                errors.Add(csvPath + ": no % key row found");
            else if (csv.Rows.Count == 0)
                errors.Add(csvPath + ": no @ data rows below the % key row");

            return csv;
        }

        /// <summary>&amp;END row marker: stops file processing ("&amp;END", "&amp;END;;;" ...).</summary>
        private static bool IsEndMarker(string line)
        {
            if (!line.StartsWith("&END", StringComparison.OrdinalIgnoreCase)) return false;
            return line.Length == 4 || !char.IsLetterOrDigit(line[4]);
        }

        /// <summary>&amp;END cell = column terminator: the row ends there, the rest is ignored.</summary>
        private static List<string> TruncateAtEndMarker(List<string> cells)
        {
            int index = cells.FindIndex(c => c.Equals("&END", StringComparison.OrdinalIgnoreCase));
            return index < 0 ? cells : cells.Take(index).ToList();
        }

        /// <summary>
        /// Parses a '$' directive row. The character right after '$' is taken as that
        /// row's own delimiter, so the directive parses before any separator is known;
        /// the remainder is split with it (quote-aware), which makes Excel's trailing
        /// empty cells harmless. Quote the value when it equals the row's delimiter:
        ///   $;separator=";"      (also survives Excel re-quoting the whole cell)
        /// </summary>
        private static void ParseDirective(string line, string csvPath, int lineNumber, CsvData csv, ref char separator, List<string> errors)
        {
            string rest = line.Substring(1);
            string directive;
            if (rest.Length > 0 && !char.IsLetterOrDigit(rest[0]))
            {
                char rowDelimiter = rest[0];
                string remainder = rest.Substring(1);

                //a quoted VALUE protects the row delimiter even when the cell itself
                //is not quoted (hand-edited files: separator=";"). Without this, the
                //delimiter inside the quotes would split the cell.
                Match quotedValue = Regex.Match(remainder, "^\\s*(\\w+)\\s*=\\s*(\"(?:[^\"]|\"\")*\")");
                if (quotedValue.Success)
                {
                    directive = quotedValue.Groups[1].Value + "=" + quotedValue.Groups[2].Value;
                }
                else
                {
                    List<string> cells = SplitCsvLine(remainder, rowDelimiter);
                    directive = cells[0].Trim(); //Excel's padded empty cells fall away
                }
            }
            else
            {
                directive = rest.Trim();
            }

            int equalsIndex = directive.IndexOf('=');
            if (equalsIndex <= 0)
            {
                errors.Add(Where(csvPath, lineNumber) + "malformed directive \"" + line + "\" (expected $" + separator + "key=value)");
                return;
            }
            string key = directive.Substring(0, equalsIndex).Trim().ToLowerInvariant();
            string value = Unquote(directive.Substring(equalsIndex + 1).Trim());

            switch (key)
            {
                case "template":
                    //?CsvName? = the csv file name without extension, so one identical
                    //directive row works in every csv: template=.\TEMPLATE-?CsvName?
                    string csvName = Path.GetFileNameWithoutExtension(csvPath);
                    string path = Regex.Replace(value, Regex.Escape("?CsvName?"), m => csvName, RegexOptions.IgnoreCase);

                    if (string.IsNullOrEmpty(Path.GetExtension(path)))
                        path += ".xml"; //template files are always .xml in this ecosystem

                    //"\folder\file" (single leading slash, no drive) counts as csv-relative;
                    //only drive-letter and UNC paths are taken absolute
                    bool drivelessRoot = (path.StartsWith("\\") && !path.StartsWith("\\\\")) || (path.StartsWith("/") && !path.StartsWith("//"));
                    if (!Path.IsPathRooted(path) || drivelessRoot)
                        path = Path.GetFullPath(Path.Combine(Path.GetDirectoryName(csvPath), path.TrimStart('\\', '/')));
                    csv.TemplatePath = path;
                    break;

                case "separator":
                    if (csv.Keys != null)
                    {
                        errors.Add(Where(csvPath, lineNumber) + "separator directive must come before the key row");
                        return;
                    }
                    if (value.Equals("tab", StringComparison.OrdinalIgnoreCase)) separator = '\t';
                    else if (value.Length == 1) separator = value[0];
                    else if (value.Length == 0)
                    {
                        errors.Add(Where(csvPath, lineNumber) + "separator value is empty - when it equals the directive row's own delimiter, quote it: separator=\";\"");
                        return;
                    }
                    else
                    {
                        errors.Add(Where(csvPath, lineNumber) + "separator must be a single character (or \"tab\"), found \"" + value + "\"");
                        return;
                    }
                    break;

                default:
                    errors.Add(Where(csvPath, lineNumber) + "unknown directive \"" + key + "\" (known: template, separator)");
                    break;
            }
        }

        /// <summary>Separator split honoring Excel-style double-quote cells.</summary>
        private static List<string> SplitCsvLine(string line, char separator)
        {
            var cells = new List<string>();
            var cell = new StringBuilder();
            bool quoted = false;

            for (int i = 0; i < line.Length; i++)
            {
                char c = line[i];
                if (quoted)
                {
                    if (c == '"')
                    {
                        if (i + 1 < line.Length && line[i + 1] == '"') { cell.Append('"'); i++; }
                        else quoted = false;
                    }
                    else cell.Append(c);
                }
                else if (c == '"' && cell.Length == 0) quoted = true;
                else if (c == separator) { cells.Add(cell.ToString()); cell.Clear(); }
                else cell.Append(c);
            }
            cells.Add(cell.ToString());
            return cells;
        }

        #endregion Csv parsing

        #region Template parsing

        private sealed class Template
        {
            public List<string> Head = new List<string>();
            public List<string> Tail = new List<string>();
            public Dictionary<int, List<string>> Sections = new Dictionary<int, List<string>>();
            public long IdSeed;
        }

        private static readonly Regex BeginSectionMarker = new Regex(@"<!--\s*Begin Template Network Type #(\d+)", RegexOptions.IgnoreCase);
        private static readonly Regex EndSectionMarker = new Regex(@"<!--\s*End Template Network Type #(\d+)", RegexOptions.IgnoreCase);
        private static readonly Regex ObjectIdAttribute = new Regex(@"\bID=""([0-9A-Fa-f]+)""");

        private static Template ParseTemplate(string templatePath, List<string> errors)
        {
            if (!File.Exists(templatePath))
            {
                errors.Add("Template not found: " + templatePath);
                return null;
            }

            string[] lines = File.ReadAllLines(templatePath);
            int containerBegin = -1, containerEnd = -1;
            for (int i = 0; i < lines.Length; i++)
            {
                if (lines[i].IndexOf("<!--Begin Template-->", StringComparison.OrdinalIgnoreCase) >= 0) containerBegin = i;
                else if (lines[i].IndexOf("<!--End Template-->", StringComparison.OrdinalIgnoreCase) >= 0 && containerEnd < 0) containerEnd = i;
            }
            if (containerBegin < 0 && containerEnd < 0)
                return AutoTemplate(lines, templatePath, errors); //plain TIA export, no hand-marking
            if (containerBegin < 0 || containerEnd < 0 || containerEnd < containerBegin)
            {
                errors.Add(templatePath + ": <!--Begin Template--> / <!--End Template--> markers incomplete or out of order");
                return null;
            }

            var template = new Template();
            template.Head.AddRange(lines.Take(containerBegin));
            template.Tail.AddRange(lines.Skip(containerEnd + 1));

            //sections inside the container; without variant markers the whole container is section 1
            int currentSection = -1;
            List<string> currentLines = null;
            for (int i = containerBegin + 1; i < containerEnd; i++)
            {
                Match begin = BeginSectionMarker.Match(lines[i]);
                Match end = EndSectionMarker.Match(lines[i]);
                if (begin.Success)
                {
                    if (currentSection >= 0)
                        errors.Add(Where(templatePath, i + 1) + "nested Begin Template Network Type marker");
                    currentSection = int.Parse(begin.Groups[1].Value);
                    currentLines = new List<string>();
                }
                else if (end.Success)
                {
                    if (currentSection < 0)
                        errors.Add(Where(templatePath, i + 1) + "End Template Network Type marker without Begin");
                    else
                    {
                        template.Sections[currentSection] = currentLines;
                        currentSection = -1;
                    }
                }
                else if (currentSection >= 0)
                {
                    currentLines.Add(lines[i]);
                }
            }
            if (currentSection >= 0)
                errors.Add(templatePath + ": Begin Template Network Type #" + currentSection + " is never closed");

            if (template.Sections.Count == 0)
                template.Sections[1] = lines.Skip(containerBegin + 1).Take(containerEnd - containerBegin - 1).ToList();

            SeedIdCounter(template);
            return template;
        }

        /// <summary>
        /// Marker-less template = a plain TIA block export. The replicated unit is
        /// detected automatically: every SW.Blocks.CompileUnit (LAD/FBD network)
        /// becomes Network Type #1..#N in document order - or, when the export has
        /// no networks (instance/global DB), the single top-level SW.Blocks.* object
        /// is the section. Multi-network blocks where some networks must stay fixed
        /// need explicit markers (that is deliberate manual territory).
        /// </summary>
        private static Template AutoTemplate(string[] lines, string templatePath, List<string> errors)
        {
            List<Tuple<int, int>> ranges = FindElementRanges(lines, "SW.Blocks.CompileUnit");
            string unit = "network (SW.Blocks.CompileUnit)";

            //delimiter networks (authored in TIA, no XML editing): an empty network
            //titled "Template #NN" begins variant NN, one titled "Template End"
            //closes it - the delimiters themselves are dropped from the output
            if (ranges.Count > 0 && ranges.Any(r => DelimiterBeginTitle.IsMatch(GetNetworkTitle(lines, r))))
                return DelimiterTemplate(lines, ranges, templatePath, errors);

            if (ranges.Count == 0)
            {
                ranges = FindTopLevelBlockRanges(lines);
                unit = "block object";
                if (ranges.Count == 0)
                {
                    errors.Add(templatePath + ": no template markers and no SW.Blocks object found - not a block export?");
                    return null;
                }
                if (ranges.Count > 1)
                {
                    errors.Add(templatePath + ": no template markers and " + ranges.Count + " top-level block objects - add <!--Begin/End Template--> markers manually");
                    return null;
                }
            }

            //content between the replicated units would be silently lost - refuse
            for (int k = 1; k < ranges.Count; k++)
            {
                for (int i = ranges[k - 1].Item2 + 1; i < ranges[k].Item1; i++)
                {
                    if (lines[i].Trim().Length > 0)
                    {
                        errors.Add(Where(templatePath, i + 1) + "unexpected content between networks - add explicit <!--Begin/End Template--> markers");
                        return null;
                    }
                }
            }

            var template = new Template();
            template.Head.AddRange(lines.Take(ranges[0].Item1));
            template.Tail.AddRange(lines.Skip(ranges[ranges.Count - 1].Item2 + 1));
            for (int k = 0; k < ranges.Count; k++)
                template.Sections[k + 1] = lines.Skip(ranges[k].Item1).Take(ranges[k].Item2 - ranges[k].Item1 + 1).ToList();

            SeedIdCounter(template);
            Log("Block generation: auto-template " + Path.GetFileName(templatePath) + " - " + ranges.Count + " " + unit +
                (ranges.Count == 1 ? "" : "s") + " -> Network Type #1" + (ranges.Count == 1 ? "" : "..#" + ranges.Count) +
                " (object IDs are renumbered per generated section)");
            return template;
        }

        private static readonly Regex DelimiterBeginTitle = new Regex(@"^\s*template\s*#\s*(\d+)\s*$", RegexOptions.IgnoreCase);
        private static readonly Regex DelimiterEndTitle = new Regex(@"^\s*template\s*end\s*$", RegexOptions.IgnoreCase);

        /// <summary>
        /// Template structured with delimiter networks authored directly in TIA:
        /// "Template #NN" titled (empty) network opens variant NN, "Template End"
        /// closes it; the networks BETWEEN them form the section (several networks
        /// per variant are fine). Networks before the first delimiter stay fixed in
        /// the envelope head, unenclosed networks after the sections go to the tail.
        /// </summary>
        private static Template DelimiterTemplate(string[] lines, List<Tuple<int, int>> ranges, string templatePath, List<string> errors)
        {
            var template = new Template();
            int firstDelimiter = ranges.FindIndex(r => DelimiterBeginTitle.IsMatch(GetNetworkTitle(lines, r)));

            //everything before the first delimiter network (fixed networks included)
            template.Head.AddRange(lines.Take(ranges[firstDelimiter].Item1));

            var tailRanges = new List<Tuple<int, int>>();
            int currentSection = -1;
            List<string> currentLines = null;

            for (int k = firstDelimiter; k < ranges.Count; k++)
            {
                string title = GetNetworkTitle(lines, ranges[k]);
                Match begin = DelimiterBeginTitle.Match(title);

                if (begin.Success)
                {
                    int number = int.Parse(begin.Groups[1].Value);
                    if (currentSection >= 0)
                    {
                        errors.Add(Where(templatePath, ranges[k].Item1 + 1) + "network \"" + title + "\" opens Template #" + number +
                            " while Template #" + currentSection + " is still open (add a \"Template End\" network)");
                        return null;
                    }
                    if (template.Sections.ContainsKey(number))
                    {
                        errors.Add(Where(templatePath, ranges[k].Item1 + 1) + "duplicate Template #" + number + " delimiter network");
                        return null;
                    }
                    currentSection = number;
                    currentLines = new List<string>();
                }
                else if (DelimiterEndTitle.IsMatch(title))
                {
                    if (currentSection < 0)
                    {
                        errors.Add(Where(templatePath, ranges[k].Item1 + 1) + "\"Template End\" network without an open Template #NN");
                        return null;
                    }
                    template.Sections[currentSection] = currentLines;
                    currentSection = -1;
                }
                else if (currentSection >= 0)
                {
                    currentLines.AddRange(lines.Skip(ranges[k].Item1).Take(ranges[k].Item2 - ranges[k].Item1 + 1));
                }
                else
                {
                    tailRanges.Add(ranges[k]); //fixed network after/between template groups
                }
            }
            if (currentSection >= 0)
            {
                errors.Add(templatePath + ": Template #" + currentSection + " is never closed (add a \"Template End\" network)");
                return null;
            }

            foreach (Tuple<int, int> range in tailRanges)
                template.Tail.AddRange(lines.Skip(range.Item1).Take(range.Item2 - range.Item1 + 1));
            template.Tail.AddRange(lines.Skip(ranges[ranges.Count - 1].Item2 + 1));

            SeedIdCounter(template);
            Log("Block generation: delimiter networks in " + Path.GetFileName(templatePath) + " - section(s) #" +
                string.Join(", #", template.Sections.Keys.OrderBy(n => n)) +
                (tailRanges.Count > 0 ? " + " + tailRanges.Count + " fixed network(s) kept" : "") +
                " (delimiter networks dropped, object IDs renumbered per generated section)");
            return template;
        }

        /// <summary>
        /// The network's Title text (first culture). Empty when the network has no
        /// title - delimiter detection keys off this.
        /// </summary>
        private static string GetNetworkTitle(string[] lines, Tuple<int, int> range)
        {
            bool inTitle = false;
            for (int i = range.Item1; i <= range.Item2; i++)
            {
                if (lines[i].Contains("CompositionName=\"Title\"")) inTitle = true;
                if (!inTitle) continue;

                Match text = Regex.Match(lines[i], "<Text>([^<]*)</Text>");
                if (text.Success) return text.Groups[1].Value;
                if (lines[i].Contains("<Text />")) return string.Empty;
            }
            return string.Empty;
        }

        /// <summary>Line ranges (start, end - inclusive) of the given element, non-nested.</summary>
        private static List<Tuple<int, int>> FindElementRanges(string[] lines, string elementName)
        {
            var ranges = new List<Tuple<int, int>>();
            string openTag = "<" + elementName + " ";
            string closeTag = "</" + elementName + ">";

            int start = -1;
            for (int i = 0; i < lines.Length; i++)
            {
                if (start < 0 && (lines[i].Contains(openTag) || lines[i].Contains("<" + elementName + ">")))
                    start = i;
                else if (start >= 0 && lines[i].Contains(closeTag))
                {
                    ranges.Add(Tuple.Create(start, i));
                    start = -1;
                }
            }
            return ranges;
        }

        private static readonly Regex TopLevelBlockOpen = new Regex(@"<(SW\.Blocks\.\w+) ID=""");

        /// <summary>Line ranges of top-level SW.Blocks.* objects (they never nest).</summary>
        private static List<Tuple<int, int>> FindTopLevelBlockRanges(string[] lines)
        {
            var ranges = new List<Tuple<int, int>>();
            int start = -1;
            string closeTag = null;

            for (int i = 0; i < lines.Length; i++)
            {
                if (start < 0)
                {
                    Match open = TopLevelBlockOpen.Match(lines[i]);
                    if (open.Success)
                    {
                        start = i;
                        closeTag = "</" + open.Groups[1].Value + ">";
                    }
                }
                else if (lines[i].Contains(closeTag))
                {
                    ranges.Add(Tuple.Create(start, i));
                    start = -1;
                }
            }
            return ranges;
        }

        /// <summary>
        /// Seeds the ID counter above every literal ID in the envelope (head + tail),
        /// so generated object IDs can never collide with fixed ones.
        /// </summary>
        private static void SeedIdCounter(Template template)
        {
            foreach (string line in template.Head.Concat(template.Tail))
            {
                foreach (Match match in ObjectIdAttribute.Matches(line))
                {
                    long id = Convert.ToInt64(match.Groups[1].Value, 16);
                    if (id >= template.IdSeed) template.IdSeed = id + 1;
                }
            }
        }

        #endregion Template parsing

        #region Output validation

        /// <summary>
        /// All-or-nothing gate before writing: no placeholder may survive and the
        /// document must be well-formed XML (catches broken templates/values long
        /// before the much less helpful Openness import errors).
        /// </summary>
        private static void ValidateOutput(List<string> output, List<string> errors)
        {
            var leftoverPattern = new Regex(@"!![^!\r\n$]{0,60}\$\$");
            var reported = new HashSet<string>();
            for (int i = 0; i < output.Count; i++)
            {
                foreach (Match match in leftoverPattern.Matches(output[i]))
                {
                    if (reported.Add(match.Value))
                        errors.Add("unsubstituted placeholder " + match.Value + " in generated output (line " + (i + 1) +
                            "): no csv column is mapped to it - check the key row");
                }
            }
            if (errors.Count > 0) return;

            try
            {
                new XmlDocument().LoadXml(string.Join("\r\n", output));
            }
            catch (XmlException e)
            {
                errors.Add("generated document is not well-formed XML at line " + e.LineNumber + ", position " + e.LinePosition +
                    ": " + e.Message + "\nOffending line: " + (e.LineNumber >= 1 && e.LineNumber <= output.Count ? output[e.LineNumber - 1].Trim() : "?"));
            }
        }

        #endregion Output validation

        #region Helpers

        private static string StampEngineeringVersion(string line, string portalVersionTag)
        {
            return Regex.Replace(line, "<Engineering version=\"[^\"]*\"", "<Engineering version=\"" + portalVersionTag + "\"");
        }

        /// <summary>
        /// Drops the versioned template prefix from Name elements:
        /// "TEMPLATE--v1.0--Block Name" and "TEMPLATE-Block Name" both become
        /// "Block Name" - generated blocks never carry the template marker.
        /// </summary>
        private static readonly Regex TemplatePrefixInName = new Regex(@"(<Name>)\s*(?:TEMPLATE--[^<]*?--|TEMPLATE-+)\s*", RegexOptions.IgnoreCase);

        private static string StripTemplatePrefix(string line) =>
            line.Contains("<Name>") ? TemplatePrefixInName.Replace(line, "$1") : line;

        /// <summary>Replaces every occurrence of the token, each with a freshly generated value.</summary>
        private static string ReplaceEachOccurrence(string line, string token, Func<string> nextValue)
        {
            int index;
            while ((index = line.IndexOf(token, StringComparison.Ordinal)) >= 0)
                line = line.Substring(0, index) + nextValue() + line.Substring(index + token.Length);
            return line;
        }

        private static string XmlEscape(string value)
        {
            return value
                .Replace("&", "&amp;")
                .Replace("<", "&lt;")
                .Replace(">", "&gt;")
                .Replace("\"", "&quot;")
                .Replace("'", "&apos;");
        }

        private static string Where(string file, int lineNumber) =>
            Path.GetFileName(file) + " line " + lineNumber + ": ";

        /// <summary>Strips one pair of surrounding double quotes and unescapes "" inside.</summary>
        private static string Unquote(string value)
        {
            if (value.Length >= 2 && value[0] == '"' && value[value.Length - 1] == '"')
                return value.Substring(1, value.Length - 2).Replace("\"\"", "\"");
            return value;
        }

        private static bool Fail(List<string> errors)
        {
            if (errors.Count == 0) return false;
            foreach (string error in errors)
                Log("Block generation error: " + error);
            Log("Block generation FAILED - nothing was written (" + errors.Count + " error(s))");
            return true;
        }

        #endregion Helpers
    }
}

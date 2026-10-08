using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace Openn._00_Contract
{
    public enum HeaderStatus
    {
        /// <summary>No "#!" directive at all.</summary>
        Missing,
        /// <summary>Only the legacy "#!format=N" tag (pre-contract Pipeline output).</summary>
        Legacy,
        /// <summary>A "#!openn" block that is incomplete or wrong (see Problems).</summary>
        Invalid,
        /// <summary>A complete, valid header.</summary>
        Ok
    }

    /// <summary>The comment syntax a header is wrapped in, decided by the file type.</summary>
    public enum HeaderSyntax
    {
        /// <summary>Lines as they are ('#' is the csv comment char); Excel padding tolerated.</summary>
        Csv,
        /// <summary>Inside the first XML comment after the declaration.</summary>
        Xml,
        /// <summary>Each line prefixed with "//" (SCL / STL / DB sources).</summary>
        Source,
        /// <summary>Binary or foreign file: the header lives in a "&lt;file&gt;.openn" sidecar.</summary>
        Sidecar
    }

    /// <summary>
    /// The OpennN file header - the block of "#!" directive lines every managed file opens with:
    ///
    ///   #!openn
    ///   #! kind: hw/stations
    ///   #! schema: 2
    ///   #! producer: Pipeline5 0.9.0
    ///   #! generated: 2026-10-07T18:00:00Z
    ///   #! project: Acme Line 3
    ///   #! plc: n0001-mc1-cc1-k65501
    ///   #! target: Program blocks/00_Safety
    ///   #!end
    ///
    /// wrapped in the file type's comment syntax (HeaderSyntax). Keys are case-insensitive;
    /// "kind", "schema", "producer" and "generated" are required; "plc" and "target", when
    /// present, must agree with the file's location in the workspace (WorkspaceCatalog checks).
    /// The header is the first thing in the file (after an XML declaration / BOM); plain
    /// "#" comment lines may sit between its lines. Contract: Shared\PL5_OP5_contract.md.
    /// </summary>
    public sealed class OpennHeader
    {
        public const string Marker = "#!";
        public const string OpenDirective = "openn";
        public const string EndDirective = "end";
        public const string LegacyFormatDirective = "format";
        public const string SidecarExtension = ".openn";
        /// <summary>Leading lines inspected for a header before giving up.</summary>
        public const int MaxLeadingLines = 200;

        /// <summary>The contract version this build implements (the workspace config's "contract" must not be newer).</summary>
        public const int CurrentContract = 1;

        /// <summary>Required in every file header.</summary>
        public static readonly string[] RequiredKeys = { "kind", "schema", "producer", "generated" };
        /// <summary>Required in the workspace config (.openn\workspace.openn.config) - a header without a kind.</summary>
        public static readonly string[] WorkspaceRequiredKeys = { "contract", "producer", "generated" };
        public static readonly string[] KnownKeys =
        {
            "kind", "schema", "producer", "generated", "run", "project", "plc", "target", "name", "source", "id", "depends", "comment",
            "contract", "plcs", "templates" //workspace config keys
        };

        private static readonly Regex KeyPattern = new Regex("^[a-z0-9][a-z0-9-]*$", RegexOptions.Compiled);

        private readonly Dictionary<string, string> values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        public HeaderStatus Status { get; private set; } = HeaderStatus.Missing;
        /// <summary>Hard problems - any of them makes the header Invalid.</summary>
        public IList<string> Problems { get; } = new List<string>();
        /// <summary>Soft remarks (unknown keys, ignored directives) - the header stays Ok.</summary>
        public IList<string> Remarks { get; } = new List<string>();
        /// <summary>The N of a legacy "#!format=N" tag when the file carries one.</summary>
        public int? LegacyFormat { get; private set; }
        /// <summary>Keys in file order.</summary>
        public IList<string> Keys { get; } = new List<string>();

        public string Get(string key) { string v; return values.TryGetValue(key, out v) ? v : null; }
        public bool Has(string key) => values.ContainsKey(key);
        public void Set(string key, string value)
        {
            if (!values.ContainsKey(key)) Keys.Add(key.ToLowerInvariant());
            values[key] = value ?? string.Empty;
        }

        public string KindId => Get("kind");
        public InputKindInfo KindInfo => InputKindInfo.ById(KindId);
        public int? Schema { get { int s; return int.TryParse(Get("schema"), NumberStyles.Integer, CultureInfo.InvariantCulture, out s) ? s : (int?)null; } }
        public string Producer => Get("producer");
        /// <summary>The producer's run id; a file whose run differs from the workspace's run is a leftover (stale).</summary>
        public string Run => Get("run");
        /// <summary>Workspace config only: the contract version the producer wrote against.</summary>
        public int? Contract { get { int c; return int.TryParse(Get("contract"), NumberStyles.Integer, CultureInfo.InvariantCulture, out c) ? c : (int?)null; } }
        public DateTime? Generated
        {
            get
            {
                DateTime d;
                return DateTime.TryParse(Get("generated"), CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out d) ? d : (DateTime?)null;
            }
        }
        public string Project => Get("project");
        public string Plc => Get("plc");
        public string Target => Get("target");
        public string Name => Get("name");
        public string Id => Get("id");
        public string[] Depends => (Get("depends") ?? string.Empty)
            .Split(new[] { ',', ';' }, StringSplitOptions.RemoveEmptyEntries).Select(s => s.Trim()).Where(s => s.Length > 0).ToArray();

        #region Building (writers: exports, tests, Pipeline reference)

        /// <summary>A valid header for a kind, stamped with producer and generation time (UTC, ISO 8601).</summary>
        public static OpennHeader Create(InputKindInfo kind, string producer, DateTime generatedUtc)
        {
            if (kind == null) throw new ArgumentNullException(nameof(kind));
            var h = new OpennHeader();
            h.Set("kind", kind.Id);
            h.Set("schema", kind.SupportedSchema.ToString(CultureInfo.InvariantCulture));
            h.Set("producer", producer ?? string.Empty);
            h.Set("generated", generatedUtc.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture));
            h.Validate(true, RequiredKeys);
            return h;
        }

        /// <summary>The header block in the given comment syntax, CRLF lines, trailing newline.</summary>
        public string Render(HeaderSyntax syntax)
        {
            var lines = new List<string> { Marker + OpenDirective };
            foreach (string key in Keys)
            {
                string value = (Get(key) ?? string.Empty).Replace("\r", " ").Replace("\n", " ").Trim();
                if (syntax == HeaderSyntax.Xml) value = value.Replace("--", "- -"); //"--" is illegal inside an XML comment
                lines.Add(Marker + " " + key + ": " + value);
            }
            lines.Add(Marker + EndDirective);

            var sb = new StringBuilder();
            if (syntax == HeaderSyntax.Xml) sb.Append("<!--\r\n");
            foreach (string line in lines)
            {
                if (syntax == HeaderSyntax.Source) sb.Append("//");
                sb.Append(line).Append("\r\n");
            }
            if (syntax == HeaderSyntax.Xml) sb.Append("-->\r\n");
            return sb.ToString();
        }

        #endregion Building

        #region Parsing

        /// <summary>
        /// Builds the header from directive lines (each starting with "#!", comment prefixes and
        /// Excel padding already removed), then validates it. Lines outside the #!openn block
        /// are the legacy format tag or ignored with a remark.
        /// </summary>
        public static OpennHeader FromDirectiveLines(IEnumerable<string> directiveLines) =>
            FromDirectiveLines(directiveLines, RequiredKeys);

        /// <summary>Same, with the set of required keys (RequiredKeys for files, WorkspaceRequiredKeys for the workspace config).</summary>
        public static OpennHeader FromDirectiveLines(IEnumerable<string> directiveLines, string[] requiredKeys)
        {
            var h = new OpennHeader();
            bool open = false, closed = false;

            foreach (string raw in directiveLines ?? Enumerable.Empty<string>())
            {
                string line = (raw ?? string.Empty).Trim();
                if (!line.StartsWith(Marker, StringComparison.Ordinal)) continue;
                string body = line.Substring(Marker.Length).Trim();

                if (!open)
                {
                    if (body.Equals(OpenDirective, StringComparison.OrdinalIgnoreCase))
                    {
                        if (closed) h.Problems.Add("second #!" + OpenDirective + " block");
                        open = true;
                        continue;
                    }
                    int eq = body.IndexOf('=');
                    int legacy;
                    if (eq > 0 && body.Substring(0, eq).Trim().Equals(LegacyFormatDirective, StringComparison.OrdinalIgnoreCase) &&
                        int.TryParse(body.Substring(eq + 1).Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out legacy))
                    {
                        h.LegacyFormat = legacy;
                        continue;
                    }
                    h.Remarks.Add("directive outside the header ignored: " + line);
                    continue;
                }

                if (body.Equals(EndDirective, StringComparison.OrdinalIgnoreCase))
                {
                    open = false;
                    closed = true;
                    continue;
                }

                int colon = body.IndexOf(':');
                if (colon <= 0)
                {
                    h.Problems.Add("header line is not 'key: value': " + line);
                    continue;
                }
                string key = body.Substring(0, colon).Trim().ToLowerInvariant();
                string value = body.Substring(colon + 1).Trim();
                if (!KeyPattern.IsMatch(key))
                {
                    h.Problems.Add("invalid header key '" + key + "' (lower-case letters, digits and '-')");
                    continue;
                }
                if (h.Has(key))
                {
                    h.Problems.Add("duplicate header key: " + key);
                    continue;
                }
                h.Set(key, value);
                if (!KnownKeys.Contains(key)) h.Remarks.Add("unknown header key: " + key);
            }

            if (open) h.Problems.Add("#!" + OpenDirective + " block not closed with #!" + EndDirective);
            if (!open && !closed)
            {
                h.Status = h.LegacyFormat.HasValue ? HeaderStatus.Legacy : HeaderStatus.Missing;
                return h;
            }
            h.Validate(false, requiredKeys);
            return h;
        }

        private void Validate(bool throwOnProblem, string[] requiredKeys)
        {
            foreach (string key in requiredKeys ?? RequiredKeys)
                if (string.IsNullOrEmpty(Get(key))) Problems.Add("missing required header key: " + key);

            if (Has("contract"))
            {
                if (Contract == null) Problems.Add("contract is not an integer: " + Get("contract"));
                else if (Contract.Value > CurrentContract)
                    Problems.Add("contract " + Contract + " is newer than the supported contract " + CurrentContract + " - update Openn5");
            }
            if (Has("kind") && KindInfo == null)
                Problems.Add("unknown kind: " + KindId + " (known: " + string.Join(", ", InputKindInfo.All.Select(k => k.Id)) + ")");
            if (Has("schema"))
            {
                if (Schema == null) Problems.Add("schema is not an integer: " + Get("schema"));
                else if (KindInfo != null && Schema.Value > KindInfo.SupportedSchema)
                    Problems.Add("schema " + Schema + " of " + KindInfo.Id + " is newer than the supported schema " + KindInfo.SupportedSchema + " - update Openn5");
            }
            if (Has("generated") && Generated == null)
                Problems.Add("generated is not an ISO 8601 date-time: " + Get("generated"));

            Status = Problems.Count == 0 ? HeaderStatus.Ok : HeaderStatus.Invalid;
            if (throwOnProblem && Status != HeaderStatus.Ok)
                throw new InvalidOperationException("invalid header: " + string.Join("; ", Problems));
        }

        /// <summary>The comment syntax used for a file, from its extension.</summary>
        public static HeaderSyntax SyntaxFor(string path)
        {
            switch ((Path.GetExtension(path) ?? string.Empty).ToLowerInvariant())
            {
                case ".csv": case ".txt": case ".md": case ".config": case ".openn":
                    return HeaderSyntax.Csv;
                case ".xml": case ".aml": case ".xsd":
                    return HeaderSyntax.Xml;
                case ".scl": case ".awl": case ".db": case ".udt": case ".st": case ".src":
                    return HeaderSyntax.Source;
                default:
                    return HeaderSyntax.Sidecar;
            }
        }

        /// <summary>
        /// Reads the header of a file: in-file for text formats, else (or additionally) from the
        /// "&lt;file&gt;.openn" sidecar. An in-file header wins over a sidecar. Never throws: an
        /// unreadable file yields an Invalid header naming the error.
        /// </summary>
        public static OpennHeader Read(string path)
        {
            try
            {
                HeaderSyntax syntax = SyntaxFor(path);
                List<string> inFile = syntax == HeaderSyntax.Sidecar ? new List<string>() : ReadDirectiveLines(path, syntax).ToList();
                string sidecar = path + SidecarExtension;
                bool hasSidecar = File.Exists(sidecar);

                if (inFile.Count > 0 || !hasSidecar)
                {
                    OpennHeader h = FromDirectiveLines(inFile);
                    if (hasSidecar) h.Remarks.Add("sidecar " + Path.GetFileName(sidecar) + " ignored - the in-file header wins");
                    return h;
                }
                OpennHeader side = FromDirectiveLines(ReadDirectiveLines(sidecar, HeaderSyntax.Csv));
                side.Remarks.Add("header read from sidecar " + Path.GetFileName(sidecar));
                return side;
            }
            catch (Exception e)
            {
                var h = new OpennHeader();
                h.Problems.Add("cannot read header: " + e.Message);
                h.Status = HeaderStatus.Invalid;
                return h;
            }
        }

        /// <summary>
        /// The "#!" directive lines at the top of a file, comment prefix and Excel padding
        /// removed, in file order. Stops at the first line that is neither blank, a comment
        /// nor a directive (csv data, source code, the XML root element).
        /// </summary>
        public static IEnumerable<string> ReadDirectiveLines(string path, HeaderSyntax syntax)
        {
            if (syntax == HeaderSyntax.Xml) return XmlLeadingCommentDirectives(path);

            var result = new List<string>();
            foreach (string raw in LeadingLines(path, MaxLeadingLines))
            {
                string line;
                if (syntax == HeaderSyntax.Source)
                {
                    string t = raw.Trim();
                    if (t.Length == 0) continue;
                    if (!t.StartsWith("//", StringComparison.Ordinal)) break;
                    line = t.Substring(2).Trim();
                    if (line.StartsWith(Marker, StringComparison.Ordinal)) result.Add(line);
                    continue; //a plain // comment line
                }

                line = NormalizeCsvLine(raw);
                if (line.Length == 0) continue;
                if (line.StartsWith(Marker, StringComparison.Ordinal)) { result.Add(line); continue; }
                if (line[0] == '#') continue; //plain comment line between header lines
                break;
            }
            return result;
        }

        /// <summary>
        /// Undoes what Excel does to a csv comment line when it saves the file: strips the
        /// delimiter padding (",,,,"), and the quoting of a line that contained the delimiter
        /// ("..." with "" escapes). Values therefore should not END with a delimiter.
        /// </summary>
        public static string NormalizeCsvLine(string rawLine)
        {
            string line = (rawLine ?? string.Empty).TrimEnd('\r', '\n').Trim();
            if (line.Length == 0) return line;
            if (line[0] == '"')
            {
                int close = line.IndexOf('"', 1);
                while (close >= 0 && close + 1 < line.Length && line[close + 1] == '"') close = line.IndexOf('"', close + 2);
                if (close > 0) line = line.Substring(1, close - 1).Replace("\"\"", "\"");
            }
            return line.TrimEnd(',', ';', '\t', ' ');
        }

        private static IEnumerable<string> LeadingLines(string path, int max)
        {
            var lines = new List<string>();
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true))
            {
                string line;
                while (lines.Count < max && (line = reader.ReadLine()) != null)
                    lines.Add(line);
            }
            return lines;
        }

        /// <summary>
        /// The directive lines inside the first XML comment that precedes the root element
        /// (declaration and processing instructions may come before it). Only the leading
        /// 32 KB are inspected.
        /// </summary>
        private static IEnumerable<string> XmlLeadingCommentDirectives(string path)
        {
            string head;
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true))
            {
                var buffer = new char[32 * 1024];
                int read = reader.Read(buffer, 0, buffer.Length);
                head = new string(buffer, 0, Math.Max(read, 0));
            }

            int pos = 0;
            while (true)
            {
                while (pos < head.Length && char.IsWhiteSpace(head[pos])) pos++;
                if (pos >= head.Length || head[pos] != '<') return Enumerable.Empty<string>();

                if (string.CompareOrdinal(head, pos, "<?", 0, 2) == 0)
                {
                    int end = head.IndexOf("?>", pos, StringComparison.Ordinal);
                    if (end < 0) return Enumerable.Empty<string>();
                    pos = end + 2;
                    continue;
                }
                if (string.CompareOrdinal(head, pos, "<!--", 0, 4) == 0)
                {
                    int end = head.IndexOf("-->", pos + 4, StringComparison.Ordinal);
                    if (end < 0) return Enumerable.Empty<string>();
                    string comment = head.Substring(pos + 4, end - pos - 4);
                    return comment.Split('\n').Select(l => l.Trim()).Where(l => l.StartsWith(Marker, StringComparison.Ordinal)).ToList();
                }
                return Enumerable.Empty<string>(); //root element or DOCTYPE: no header comment
            }
        }

        #endregion Parsing

        public override string ToString() =>
            Status + (KindId != null ? " " + KindId : string.Empty) + (LegacyFormat.HasValue ? " (format=" + LegacyFormat + ")" : string.Empty);
    }
}

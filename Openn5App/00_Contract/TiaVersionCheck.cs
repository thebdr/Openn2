using System.Globalization;
using System.Text.RegularExpressions;

namespace Openn._00_Contract
{
    public enum TiaVersionVerdict
    {
        /// <summary>The workspace targets the attached Portal's version.</summary>
        Match,
        /// <summary>The workspace targets an older Portal: TIA upgrades the documents on import - a warning.</summary>
        OlderWorkspace,
        /// <summary>The workspace targets a newer Portal: this TIA cannot read its documents - the import is refused.</summary>
        NewerWorkspace,
        /// <summary>The workspace's tia key is not a version - the import is refused.</summary>
        Unreadable
    }

    /// <summary>
    /// The workspace's TIA Portal version (the workspace config's "tia", contract §3.4) against the Portal Openn5 is
    /// attached to (contract §7): equal = fine, workspace older = a warning (TIA upgrades older SimaticML on import),
    /// workspace newer or unreadable = the import is refused before the first item. A workspace without the key was
    /// generated before Pipeline5 made the version a project setting (C-049) - every document of it was stamped V18.
    /// Siemens-free: the Portal's major version comes in as a number.
    /// </summary>
    public sealed class TiaVersionCheck
    {
        /// <summary>What a workspace without the tia key targets: Pipeline5 stamped V18 before C-049.</summary>
        public const int PreSettingMajor = 18;

        private static readonly Regex Spelling = new Regex(@"^\s*[Vv]?\s*(\d+)\s*$");

        public int? WorkspaceMajor { get; private set; }
        /// <summary>True when the workspace had no tia key and PreSettingMajor was assumed.</summary>
        public bool Assumed { get; private set; }
        public int PortalMajor { get; private set; }
        public TiaVersionVerdict Verdict { get; private set; }
        public string Message { get; private set; }
        /// <summary>The import must not start.</summary>
        public bool Blocks => Verdict == TiaVersionVerdict.NewerWorkspace || Verdict == TiaVersionVerdict.Unreadable;

        /// <summary>"V20" / "20" / "v20" -> 20; null when the text is not a version.</summary>
        public static int? ParseMajor(string text)
        {
            if (string.IsNullOrWhiteSpace(text)) return null;
            Match m = Spelling.Match(text);
            int major;
            return m.Success && int.TryParse(m.Groups[1].Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out major) ? major : (int?)null;
        }

        /// <summary>The verdict for a workspace config (null = no config: the pre-contract case, V18 assumed).</summary>
        public static TiaVersionCheck Compare(OpennHeader workspaceConfig, int portalMajor)
        {
            var check = new TiaVersionCheck { PortalMajor = portalMajor };
            string raw = workspaceConfig == null ? null : workspaceConfig.Tia;
            if (string.IsNullOrWhiteSpace(raw))
            {
                check.WorkspaceMajor = PreSettingMajor;
                check.Assumed = true;
            }
            else
            {
                check.WorkspaceMajor = ParseMajor(raw);
                if (check.WorkspaceMajor == null)
                {
                    check.Verdict = TiaVersionVerdict.Unreadable;
                    check.Message = "TIA version: the workspace config's tia '" + raw.Trim() + "' is not a version - import refused";
                    return check;
                }
            }

            int workspace = check.WorkspaceMajor.Value;
            string source = "workspace V" + workspace + (check.Assumed ? " (no tia key - generated before C-049, stamped V18)" : string.Empty) +
                            ", attached Portal V" + portalMajor;
            if (workspace == portalMajor)
            {
                check.Verdict = TiaVersionVerdict.Match;
                check.Message = "TIA version: " + source;
            }
            else if (workspace < portalMajor)
            {
                check.Verdict = TiaVersionVerdict.OlderWorkspace;
                check.Message = "WARNING TIA version: " + source + " - the documents are upgraded on import; regenerate with tia_version V" +
                                portalMajor + " in Pipeline5 to match";
            }
            else
            {
                check.Verdict = TiaVersionVerdict.NewerWorkspace;
                check.Message = "TIA version: " + source + " - TIA V" + portalMajor + " cannot read V" + workspace +
                                " documents: import refused (attach a V" + workspace + " Portal, or set tia_version V" + portalMajor +
                                " in Pipeline5 and regenerate)";
            }
            return check;
        }
    }
}

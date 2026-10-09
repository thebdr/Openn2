using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

namespace Openn._00_Contract
{
    /// <summary>
    /// Openn5's per-workspace import settings: the files whose Import box the user unticked in the Workspace tab.
    /// Kept in &lt;workspace&gt;\.openn\import.openn5.config so a tick survives a rescan, a restart and the next PL5
    /// generation (PL5 writes only workspace.openn.config in .openn and never sweeps). Siemens-free.
    ///
    /// Format: UTF-8 text, '#' comment lines, then one "disabled: &lt;relative path&gt;" line per unticked file
    /// (the catalog's '/'-separated RelativePath, compared case-insensitively). Lines that are not understood are
    /// reported as problems, not fatal. The file is removed when nothing is unticked.
    /// </summary>
    public sealed class WorkspaceImportSettings
    {
        public const string FileName = WorkspaceLayout.ImportSettingsFile;
        private const string DisabledKey = "disabled";

        private readonly HashSet<string> disabled = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        public string Root { get; }
        public string Path => System.IO.Path.Combine(Root, WorkspaceLayout.ConfigFolder, FileName);
        /// <summary>The unticked files (relative paths), sorted.</summary>
        public IEnumerable<string> Disabled => disabled.OrderBy(p => p, StringComparer.OrdinalIgnoreCase);
        public int Count => disabled.Count;
        /// <summary>Read problems (unreadable file, lines not understood) - the rest still loads.</summary>
        public IList<string> Problems { get; } = new List<string>();

        private WorkspaceImportSettings(string root)
        {
            Root = root;
        }

        /// <summary>Loads the workspace's settings; a missing file = nothing unticked.</summary>
        public static WorkspaceImportSettings Load(string root)
        {
            var settings = new WorkspaceImportSettings(System.IO.Path.GetFullPath(root).TrimEnd('\\', '/'));
            if (!File.Exists(settings.Path)) return settings;

            string[] lines;
            try
            {
                lines = File.ReadAllLines(settings.Path, Encoding.UTF8);
            }
            catch (Exception e)
            {
                settings.Problems.Add("cannot read: " + e.Message);
                return settings;
            }

            for (int i = 0; i < lines.Length; i++)
            {
                string line = lines[i].Trim();
                if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal)) continue;

                int colon = line.IndexOf(':');
                string key = colon > 0 ? line.Substring(0, colon).Trim() : line;
                string value = colon > 0 ? line.Substring(colon + 1).Trim() : string.Empty;
                if (key.Equals(DisabledKey, StringComparison.OrdinalIgnoreCase) && value.Length > 0)
                    settings.disabled.Add(Normalize(value));
                else
                    settings.Problems.Add("line " + (i + 1) + " not understood: " + line);
            }
            return settings;
        }

        public bool IsDisabled(string relativePath) => disabled.Contains(Normalize(relativePath));

        /// <summary>Ticks (isDisabled = false) or unticks a file; returns true when that changed the set.</summary>
        public bool SetDisabled(string relativePath, bool isDisabled)
        {
            string key = Normalize(relativePath);
            if (key.Length == 0) return false;
            return isDisabled ? disabled.Add(key) : disabled.Remove(key);
        }

        /// <summary>
        /// Writes the file (creating the .openn folder when needed), or deletes it when nothing is unticked.
        /// I/O errors propagate: the caller decides how to report them.
        /// </summary>
        public void Save()
        {
            string path = Path;
            if (disabled.Count == 0)
            {
                if (File.Exists(path)) File.Delete(path);
                return;
            }

            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path));
            var lines = new List<string>
            {
                "# Openn5 import settings for this workspace - written by Openn5 (Workspace tab), read at every scan.",
                "# One line per file whose Import box is unticked: listed, never imported, until ticked again.",
                "# Paths are relative to the workspace root, '/' separated, as the Workspace tab shows them.",
            };
            lines.AddRange(Disabled.Select(p => DisabledKey + ": " + p));
            File.WriteAllLines(path, lines, new UTF8Encoding(false));
        }

        private static string Normalize(string relativePath) =>
            (relativePath ?? string.Empty).Replace('\\', '/').Trim().TrimStart('/');
    }
}

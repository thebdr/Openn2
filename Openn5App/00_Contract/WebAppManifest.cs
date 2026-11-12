using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using Openn._10_StandardFunctions;

namespace Openn._00_Contract
{
    /// <summary>One resource a web application manifest lists: a file beside the manifest, uploaded as it is.</summary>
    public sealed class WebAppResource
    {
        /// <summary>The resource name on the CPU = the path relative to the app folder, '/' separated.</summary>
        public string Name { get; set; }
        public string MediaType { get; set; }
        public long Size { get; set; }
        /// <summary>Lower-case hex SHA-256 of the file's bytes.</summary>
        public string Sha256 { get; set; }
        /// <summary>The Web API visibility ("public" = served without a login, "protected").</summary>
        public string Visibility { get; set; }
        public bool IsDefaultPage { get; set; }
        public int LineNumber { get; set; }
    }

    /// <summary>
    /// The manifest of one CPU web application (kind web/app, contract v1 §2): &lt;PLC&gt;\Web applications\&lt;app&gt;\
    /// webapp.manifest.csv - the #!openn header, then one row per resource (name, media_type, size, sha256, visibility,
    /// default_page). The resources themselves stay header-free (they are served to browsers byte for byte); the
    /// manifest's size + sha256 bind them to the generation that wrote it. Siemens-free: the catalog verifies it
    /// without TIA, the Web API deployer (M4) uploads from it.
    /// </summary>
    public sealed class WebAppManifest
    {
        public const string FileName = "webapp.manifest.csv";
        public static readonly string[] Columns = { "name", "media_type", "size", "sha256", "visibility", "default_page" };
        private static readonly string[] Visibilities = { "public", "protected" };

        public string Path { get; private set; }
        /// <summary>The app folder (the manifest's folder); its name is the application name.</summary>
        public string Folder { get; private set; }
        public string AppName { get; private set; }
        public OpennHeader Header { get; private set; } = new OpennHeader();
        public IList<WebAppResource> Resources { get; } = new List<WebAppResource>();
        /// <summary>Problems in the manifest itself (columns, cells, the default page) - each one makes it unusable.</summary>
        public IList<string> Errors { get; } = new List<string>();
        public WebAppResource DefaultPage => Resources.FirstOrDefault(r => r.IsDefaultPage);

        public static WebAppManifest Read(string path)
        {
            var manifest = new WebAppManifest { Path = path, Folder = System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(path)) };
            manifest.AppName = System.IO.Path.GetFileName(manifest.Folder);
            CsvTable table = CsvTable.Read(path);
            manifest.Header = table.Header;
            foreach (string error in table.Errors) manifest.Errors.Add(error);
            if (table.Errors.Count > 0) return manifest;

            if (!string.IsNullOrEmpty(table.Header.Name) && !table.Header.Name.Equals(manifest.AppName, StringComparison.Ordinal))
                manifest.Errors.Add("header name '" + table.Header.Name + "' but the app folder is '" + manifest.AppName + "'");
            if (table.Rows.Count == 0)
            {
                manifest.Errors.Add("no column header row (" + string.Join(",", Columns) + ")");
                return manifest;
            }

            string[] header = table.Rows[0].Values.Select(v => v.Trim().ToLowerInvariant()).ToArray();
            var index = new Dictionary<string, int>();
            foreach (string column in Columns)
            {
                int i = Array.IndexOf(header, column);
                if (i < 0) manifest.Errors.Add("the column header row lacks '" + column + "'");
                else index[column] = i;
            }
            if (manifest.Errors.Count > 0) return manifest;

            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (CsvRow row in table.Rows.Skip(1))
            {
                string where = "line " + row.LineNumber + ": ";
                var resource = new WebAppResource
                {
                    Name = row.Get(index["name"]).Replace('\\', '/'),
                    MediaType = row.Get(index["media_type"]),
                    Sha256 = row.Get(index["sha256"]).ToLowerInvariant(),
                    Visibility = row.Get(index["visibility"]).ToLowerInvariant(),
                    LineNumber = row.LineNumber
                };
                string defaultPage = row.Get(index["default_page"]).ToLowerInvariant();
                resource.IsDefaultPage = defaultPage == "yes" || defaultPage == "true" || defaultPage == "1";

                long size;
                if (resource.Name.Length == 0) manifest.Errors.Add(where + "empty resource name");
                else if (resource.Name.StartsWith("/", StringComparison.Ordinal) || resource.Name.Split('/').Any(p => p == ".." || p == "." || p.Length == 0))
                    manifest.Errors.Add(where + "resource name '" + resource.Name + "' must be a plain path inside the app folder");
                else if (resource.Name.Equals(FileName, StringComparison.OrdinalIgnoreCase))
                    manifest.Errors.Add(where + "the manifest cannot list itself");
                else if (!names.Add(resource.Name)) manifest.Errors.Add(where + "resource '" + resource.Name + "' listed twice");
                if (resource.MediaType.Length == 0) manifest.Errors.Add(where + "empty media_type");
                if (!long.TryParse(row.Get(index["size"]), NumberStyles.None, CultureInfo.InvariantCulture, out size))
                    manifest.Errors.Add(where + "size '" + row.Get(index["size"]) + "' is not a byte count");
                resource.Size = size;
                if (resource.Sha256.Length != 64 || !resource.Sha256.All(Uri.IsHexDigit))
                    manifest.Errors.Add(where + "sha256 '" + resource.Sha256 + "' is not 64 hex digits");
                if (!Visibilities.Contains(resource.Visibility))
                    manifest.Errors.Add(where + "visibility '" + resource.Visibility + "' (expected " + string.Join(" or ", Visibilities) + ")");
                manifest.Resources.Add(resource);
            }

            if (manifest.Resources.Count == 0) manifest.Errors.Add("lists no resource");
            int defaults = manifest.Resources.Count(r => r.IsDefaultPage);
            if (defaults != 1 && manifest.Resources.Count > 0)
                manifest.Errors.Add(defaults == 0 ? "no resource is marked default_page" : defaults + " resources are marked default_page (one expected)");
            return manifest;
        }

        /// <summary>The full path of a listed resource.</summary>
        public string ResourcePath(WebAppResource resource) =>
            System.IO.Path.Combine(Folder, resource.Name.Replace('/', System.IO.Path.DirectorySeparatorChar));

        /// <summary>
        /// Every way the files on disk differ from the manifest: a listed resource missing, of another size or
        /// another SHA-256 (changed after the generation). Empty = the folder is exactly what the manifest says.
        /// </summary>
        public IList<string> VerifyResources()
        {
            var problems = new List<string>();
            foreach (WebAppResource resource in Resources)
            {
                string file = ResourcePath(resource);
                if (!File.Exists(file)) { problems.Add("resource '" + resource.Name + "' is missing"); continue; }
                long length = new FileInfo(file).Length;
                if (length != resource.Size) { problems.Add("resource '" + resource.Name + "' is " + length + " bytes, the manifest says " + resource.Size); continue; }
                if (!Sha256Of(file).Equals(resource.Sha256, StringComparison.OrdinalIgnoreCase))
                    problems.Add("resource '" + resource.Name + "' changed since the generation (SHA-256 differs from the manifest)");
            }
            return problems;
        }

        /// <summary>The files in the app folder the manifest does not list (relative, '/' separated) - never uploaded.</summary>
        public IList<string> UnlistedFiles()
        {
            var listed = new HashSet<string>(Resources.Select(r => r.Name), StringComparer.OrdinalIgnoreCase) { FileName };
            if (!Directory.Exists(Folder)) return new List<string>();
            return Directory.GetFiles(Folder, "*", SearchOption.AllDirectories)
                .Select(f => f.Substring(Folder.Length).TrimStart('\\', '/').Replace('\\', '/'))
                .Where(rel => !listed.Contains(rel))
                .OrderBy(rel => rel, StringComparer.OrdinalIgnoreCase)
                .ToList();
        }

        public static string Sha256Of(string path)
        {
            using (var sha = SHA256.Create())
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
                return string.Concat(sha.ComputeHash(stream).Select(b => b.ToString("x2", CultureInfo.InvariantCulture)));
        }
    }
}

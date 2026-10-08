using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// One installed TIA Portal Openness public API that the user can select.
    /// This type must not reference any Siemens.Engineering type: it runs before
    /// the Siemens assemblies are resolved.
    /// </summary>
    public sealed class OpennessInstallation
    {
        public OpennessInstallation(Version portalVersion, Version apiVersion, string engineeringDllPath)
        {
            PortalVersion = portalVersion;
            ApiVersion = apiVersion;
            EngineeringDllPath = engineeringDllPath;
        }

        /// <summary>TIA Portal version, e.g. 18.0</summary>
        public Version PortalVersion { get; }

        /// <summary>Openness public API version, e.g. 18.0</summary>
        public Version ApiVersion { get; }

        /// <summary>Full path of Siemens.Engineering.dll for this version</summary>
        public string EngineeringDllPath { get; }

        /// <summary>Folder that holds Siemens.Engineering.dll and its sibling assemblies (Hmi, ...)</summary>
        public string ApiDirectory => Path.GetDirectoryName(EngineeringDllPath);

        /// <summary>Project file extension used by this portal version, e.g. ".ap18"</summary>
        public string ProjectFileExtension =>
            ".ap" + (PortalVersion.Minor == 0 ? PortalVersion.Major.ToString() : PortalVersion.Major + "_" + PortalVersion.Minor);

        public string DisplayName =>
            "TIA Portal V" + (PortalVersion.Minor == 0 ? PortalVersion.Major.ToString() : PortalVersion.ToString(2)) +
            " (Openness API " + ApiVersion.ToString(2) + ")";

        public override string ToString() => DisplayName;
    }

    /// <summary>
    /// Discovers the TIA Portal Openness versions installed on this machine and resolves
    /// Siemens.Engineering assembly loads to the version selected by the user.
    /// Select() must be called before the first call into any Siemens.Engineering type;
    /// once the CLR has loaded the assemblies the selection cannot change (restart required).
    /// </summary>
    public static class OpennessSetup
    {
        // V18..V20: the app is built against the V18 API; V21+ introduced breaking
        // changes in Openness and needs a build of its own before it can be allowed here.
        public const int MinimumPortalMajorVersion = 18;
        public const int MaximumPortalMajorVersion = 20;

        private const string OpennessRegistryKey = @"SOFTWARE\Siemens\Automation\Openness";
        private const string DefaultInstallRoot = @"C:\Program Files\Siemens\Automation";

        private static bool resolverRegistered;

        public static OpennessInstallation SelectedInstallation { get; private set; }

        /// <summary>
        /// All usable installations (portal major version within the supported
        /// V18..V20 range), ordered from oldest to newest. Merges the registry entries
        /// (authoritative, per the Openness manual) with a scan of the default install folder.
        /// </summary>
        public static IReadOnlyList<OpennessInstallation> DiscoverInstallations()
        {
            var byPortalVersion = new Dictionary<Version, OpennessInstallation>();

            foreach (var installation in ReadInstallationsFromRegistry().Concat(ScanDefaultInstallFolder()))
            {
                if (installation.PortalVersion.Major < MinimumPortalMajorVersion) continue;
                if (installation.PortalVersion.Major > MaximumPortalMajorVersion) continue;
                if (!File.Exists(installation.EngineeringDllPath)) continue;
                if (!byPortalVersion.ContainsKey(installation.PortalVersion))
                    byPortalVersion.Add(installation.PortalVersion, installation);
            }

            return byPortalVersion.Values.OrderBy(i => i.PortalVersion).ToList();
        }

        /// <summary>
        /// Makes <paramref name="installation"/> the version the AssemblyResolve hook loads.
        /// </summary>
        public static void Select(OpennessInstallation installation)
        {
            if (installation == null) throw new ArgumentNullException(nameof(installation));

            SelectedInstallation = installation;

            if (!resolverRegistered)
            {
                AppDomain.CurrentDomain.AssemblyResolve += OnAssemblyResolve;
                resolverRegistered = true;
            }
        }

        private static Assembly OnAssemblyResolve(object sender, ResolveEventArgs args)
        {
            var installation = SelectedInstallation;
            if (installation == null) return null;

            var requested = new AssemblyName(args.Name);
            if (!requested.Name.StartsWith("Siemens.Engineering", StringComparison.OrdinalIgnoreCase))
                return null;

            string candidate = Path.Combine(installation.ApiDirectory, requested.Name + ".dll");
            return File.Exists(candidate) ? Assembly.LoadFrom(candidate) : null;
        }

        /// <summary>
        /// Registry layout (see the Openness manual and Siemens FAQ 109815895):
        /// HKLM\SOFTWARE\Siemens\Automation\Openness\{portalVersion}\PublicAPI\{apiVersion}
        /// with the string value "Siemens.Engineering" holding the dll path.
        /// </summary>
        private static IEnumerable<OpennessInstallation> ReadInstallationsFromRegistry()
        {
            var installations = new List<OpennessInstallation>();
            try
            {
                using (var hklm = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
                using (var opennessKey = hklm.OpenSubKey(OpennessRegistryKey))
                {
                    if (opennessKey == null) return installations;

                    foreach (string portalVersionName in opennessKey.GetSubKeyNames())
                    {
                        if (!TryParseVersion(portalVersionName, out Version portalVersion)) continue;

                        using (var publicApiKey = opennessKey.OpenSubKey(portalVersionName + @"\PublicAPI"))
                        {
                            if (publicApiKey == null) continue;

                            // a portal can expose several API versions; each is a valid entry
                            foreach (string apiVersionName in publicApiKey.GetSubKeyNames())
                            {
                                if (!TryParseVersion(apiVersionName, out Version apiVersion)) continue;

                                using (var apiKey = publicApiKey.OpenSubKey(apiVersionName))
                                {
                                    if (apiKey?.GetValue("Siemens.Engineering") is string dllPath && dllPath.Length > 0)
                                        installations.Add(new OpennessInstallation(portalVersion, apiVersion, dllPath));
                                }
                            }
                        }
                    }
                }
            }
            catch
            {
                // no registry access: fall back to the folder scan
            }

            // when a portal exposes several API versions keep only the newest one
            return installations
                .GroupBy(i => i.PortalVersion)
                .Select(g => g.OrderByDescending(i => i.ApiVersion).First());
        }

        /// <summary>
        /// Fallback when the registry is not readable: probes
        /// C:\Program Files\Siemens\Automation\Portal Vxx\PublicAPI\Vxx\Siemens.Engineering.dll
        /// </summary>
        private static IEnumerable<OpennessInstallation> ScanDefaultInstallFolder()
        {
            var installations = new List<OpennessInstallation>();
            try
            {
                var automationDir = new DirectoryInfo(DefaultInstallRoot);
                if (!automationDir.Exists) return installations;

                foreach (var portalDir in automationDir.GetDirectories("Portal V*"))
                {
                    if (!TryParseVersion(portalDir.Name.Substring("Portal V".Length), out Version portalVersion)) continue;

                    var publicApiDir = new DirectoryInfo(Path.Combine(portalDir.FullName, "PublicAPI"));
                    if (!publicApiDir.Exists) continue;

                    var apiEntries = new List<OpennessInstallation>();
                    foreach (var apiDir in publicApiDir.GetDirectories("V*"))
                    {
                        if (!TryParseVersion(apiDir.Name.Substring(1).Replace("_", "."), out Version apiVersion)) continue;

                        string dllPath = Path.Combine(apiDir.FullName, "Siemens.Engineering.dll");
                        if (File.Exists(dllPath))
                            apiEntries.Add(new OpennessInstallation(portalVersion, apiVersion, dllPath));
                    }

                    if (apiEntries.Count > 0)
                        installations.Add(apiEntries.OrderByDescending(i => i.ApiVersion).First());
                }
            }
            catch
            {
                // probing only: any IO failure simply yields no entries
            }
            return installations;
        }

        private static bool TryParseVersion(string text, out Version version)
        {
            if (!text.Contains(".")) text += ".0";
            return Version.TryParse(text, out version);
        }
    }
}

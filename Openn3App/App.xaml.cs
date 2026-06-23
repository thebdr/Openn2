using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.RegularExpressions;
using System.Windows;

using Openn._03_ApiManager;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn
{

    public partial class App : Application
    {
        public bool isApplicationActive;

        /// <summary>
        /// Selects the TIA Portal Openness version before any window is created:
        /// the AssemblyResolve hook must be in place before the first
        /// Siemens.Engineering type is touched (which happens as soon as the
        /// main window calls into TiaPortalOpenness).
        ///
        /// Selection order (smooth start):
        ///   1. --tiaversion=NN command line (in-app version switch restarts with this),
        ///   2. running TIA Portal instances, when they are all ONE version,
        ///   3. single installed version,
        ///   4. the version dialog.
        /// </summary>
        public void App_Startup(object sender, StartupEventArgs e)
        {
            // keep the app alive between the version dialog closing and the main window opening
            ShutdownMode = ShutdownMode.OnExplicitShutdown;

            var installations = OpennessSetup.DiscoverInstallations();
            if (installations.Count == 0)
            {
                MessageBox.Show(
                    "No supported TIA Portal Openness installation (V" + OpennessSetup.MinimumPortalMajorVersion +
                    " - V" + OpennessSetup.MaximumPortalMajorVersion + ") was found on this machine.\n\n" +
                    "Install TIA Portal V" + OpennessSetup.MinimumPortalMajorVersion + " - V" + OpennessSetup.MaximumPortalMajorVersion +
                    " including the Openness API, then start Openn2 again.",
                    "Openn2 - TIA Portal Openness not found", MessageBoxButton.OK, MessageBoxImage.Error);
                Shutdown(1);
                return;
            }

            OpennessInstallation selected = FromCommandLine(installations, e.Args);
            if (selected != null)
            {
                Log("TIA version from restart request: " + selected.DisplayName);
            }
            else
            {
                selected = FromRunningPortals(installations);
                if (selected != null)
                    Log("Auto-selected " + selected.DisplayName + " (matches the running TIA Portal instance(s))");
            }

            if (selected == null)
            {
                selected = installations.Count == 1
                    ? installations[0]
                    : OpennessVersionDialog.ShowSelection(installations);
            }

            if (selected == null) // user cancelled the version dialog
            {
                Shutdown(0);
                return;
            }

            OpennessSetup.Select(selected);

            var mainWindow = new MainWindow();
            MainWindow = mainWindow;
            ShutdownMode = ShutdownMode.OnMainWindowClose;
            mainWindow.Show();
        }

        /// <summary>--tiaversion=NN argument (written by the in-app version switch).</summary>
        private static OpennessInstallation FromCommandLine(IReadOnlyList<OpennessInstallation> installations, string[] args)
        {
            foreach (string arg in args)
            {
                int major;
                if (arg.StartsWith("--tiaversion=", StringComparison.OrdinalIgnoreCase) &&
                    int.TryParse(arg.Substring("--tiaversion=".Length), out major))
                {
                    return installations.FirstOrDefault(i => i.PortalVersion.Major == major);
                }
            }
            return null;
        }

        /// <summary>
        /// The version of the running TIA Portal processes, when they all agree.
        /// Detected from the process paths (...\Portal V18\...) - no Siemens type
        /// is touched, which matters because nothing may load before Select().
        /// Inaccessible processes (elevation) are ignored; any ambiguity returns
        /// null and the dialog decides.
        /// </summary>
        private static OpennessInstallation FromRunningPortals(IReadOnlyList<OpennessInstallation> installations)
        {
            var majors = new HashSet<int>();
            foreach (Process process in Process.GetProcessesByName("Siemens.Automation.Portal"))
            {
                try
                {
                    Match match = Regex.Match(process.MainModule.FileName, @"Portal V(\d+)", RegexOptions.IgnoreCase);
                    if (match.Success) majors.Add(int.Parse(match.Groups[1].Value));
                }
                catch
                {
                    //process not accessible (different elevation/bitness): ignore
                }
            }

            if (majors.Count != 1) return null;
            return installations.FirstOrDefault(i => i.PortalVersion.Major == majors.First());
        }

        public void App_Activated(object sender, EventArgs e)
        {
            // Application activated (focused)
            this.isApplicationActive = true;
        }

        public void App_Deactivated(object sender, EventArgs e)
        {
            // Application deactivated (unfocused)
            this.isApplicationActive = false;
        }
    }
}

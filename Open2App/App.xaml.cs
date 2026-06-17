using System;
using System.Windows;

using Openn._03_ApiManager;

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

            OpennessInstallation selected = installations.Count == 1
                ? installations[0]
                : OpennessVersionDialog.ShowSelection(installations);

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

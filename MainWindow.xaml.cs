using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;

using Openn._03_ApiManager;
using Openn._01_Constructor;
using static Openn._10_StandardFunctions.LogsManager;
using static Openn._10_StandardFunctions.StandardFunctions;
using static Openn._03_ApiManager.TiaPortalOpenness;

namespace Openn
{
    public partial class MainWindow : Window
    {
        public IList<TiaProcessInfo> processInfoList = new List<TiaProcessInfo>();

        private readonly TiaPortalOpenness tia = new TiaPortalOpenness(); //instance of API Manager class

        //all backend work (TIA Openness calls, csv loading) runs sequentially on the
        //TiaWorker thread; the UI thread reads control values before queuing and
        //updates controls after awaiting, so the window never freezes.
        private bool backendBusy;
        private int runningOperations;

        public MainWindow()
        {
            InitializeComponent();
            AttachLogView(lbLogView);

            Title += " - " + OpennessSetup.SelectedInstallation.DisplayName;
            Log("Using " + OpennessSetup.SelectedInstallation.DisplayName + ": " + OpennessSetup.SelectedInstallation.EngineeringDllPath);

            InitializeGraphicComponents();
            LoadHardwareConfiguration();
        }

        private void InitializeGraphicComponents()
        {
            string appBaseDir = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);
            tbHardwareCsvPath.Text = appBaseDir + "\\HardwareConfig";
            tbProjectPath.Text = appBaseDir + "\\TiaProjects\\openness_project";
            tbSourceBlockPath.Text = appBaseDir + "\\EditedBlocks";
            rbUseInstance.IsChecked = true;
            rbUseExistingIoControllers.IsChecked = true;
        }

        private async void LoadHardwareConfiguration()
        {
            string folder = tbHardwareCsvPath.Text;
            await RunBackend(() => TiaWorker.Run(() => HardwareConfigLoader.LoadAll(folder)));
            await RefreshOpenInstancesDropdown(quietWhenBusy: true);
        }

        /// <summary>
        /// Runs one backend operation while keeping the UI responsive: shows the
        /// spinner, rejects overlapping operations (the worker queue is serial, so
        /// a second click would otherwise just pile up), and logs uncaught errors.
        /// </summary>
        private async Task RunBackend(Func<Task> operation, bool quietWhenBusy = false)
        {
            if (backendBusy)
            {
                if (!quietWhenBusy)
                    Log("Skipped: another operation is still running");
                return;
            }

            backendBusy = true;
            ShowRunningIcon("start");
            try
            {
                await operation();
            }
            catch (Exception e)
            {
                Log("ERROR (background operation) \n" + e.Message);
            }
            finally
            {
                backendBusy = false;
                ShowRunningIcon("stop");
            }
        }

        #region Buttons & Controls

        private async void btnAttachProject_Click(object sender, RoutedEventArgs e)
        {
            string path = "Invalid Path";
            if (rbUsePath.IsChecked == true)
            {
                path = tbProjectPath.Text;
            }
            else if (rbUseInstance.IsChecked == true)
            {
                if (cbOpenTiaInstances.SelectedIndex < 0)
                {
                    Log("Can't attach: no open Tia Portal instance selected");
                    return;
                }
                path = processInfoList[cbOpenTiaInstances.SelectedIndex].ProjectPath;
            }

            await RunBackend(async () =>
            {
                tbAttachedProject.Text = await TiaWorker.Run(() => tia.AttachToProject(path));
            });
        }

        private void btnBrowseProjects_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFolderDialog(tbProjectPath.Text);
            if (!(_path == null))
                tbProjectPath.Text = _path.FullName;
        }

        private async void btnDetachProject_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(async () =>
            {
                tbAttachedProject.Text = await TiaWorker.Run(() => tia.DetachProject());
            });
        }

        private void btnExportSource_Click(object sender, RoutedEventArgs e)
        {
            if (backendBusy)
            {
                Log("Skipped: another operation is still running");
                return;
            }

            //the window queues its reads/exports on the TiaWorker itself
            var searchWindow = new BlockSearchWindow(
                () => tia.GetAllBlocks(),
                blockName => tia.ExportBlock(blockName))
            {
                Owner = this,
            };
            searchWindow.ShowDialog();
        }

        private async void btnImportSource_Click(object sender, RoutedEventArgs e)
        {
            string fileName = tbSourceBlockPath.Text;
            await RunBackend(() => TiaWorker.Run(() => tia.ImportPlcBlock(fileName)));
        }

        private void btnBrowseBlocks_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFileDialog(startPath: tbSourceBlockPath.Text, filter: "File (.xml)|*.xml");
            if (!(_path == null))
                tbSourceBlockPath.Text = _path.FullName;
        }

        private void btnImportHardwareCsv_Click(object sender, RoutedEventArgs e)
        {
            LoadHardwareConfiguration();
        }

        private void btnBrowseHwConfigCsv_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFolderDialog(tbHardwareCsvPath.Text);
            if (!(_path == null))
                tbHardwareCsvPath.Text = _path.FullName;
        }

        private void btnEditHardwareConfig_Click(object sender, RoutedEventArgs e)
        {
            //the editor saves + reloads through the TiaWorker itself
            var editor = new HardwareConfigEditorWindow(tbHardwareCsvPath.Text) { Owner = this };
            editor.ShowDialog();
        }

        private async void btnGenerateHardware_Click(object sender, RoutedEventArgs e)
        {
            if ((HardwareDeviceTypesDatabase.Identifier == null) || (HardwareDeviceTypesDatabase.Identifier.Count() < 1))
            {
                Log("Can't generate hardware configuration: Hardware Configuration not loaded.");
                return;
            }

            bool? createNewIoControllers = rbCreateNewIoControllers.IsChecked;
            await RunBackend(() => TiaWorker.Run(() => tia.CreateDevices(createNewIoControllers)));
        }

        private async void btnClearLogs_Click(object sender, RoutedEventArgs e)
        {
            lbLogView.Items.Clear();
            await RefreshOpenInstancesDropdown(quietWhenBusy: true);
        }

        private async void Window_Activated(object sender, System.EventArgs e)
        {
            await RefreshOpenInstancesDropdown(quietWhenBusy: true);
        }

        #endregion Buttons & Controls

        private async Task RefreshOpenInstancesDropdown(bool quietWhenBusy)
        {
            await RunBackend(async () =>
            {
                try
                {
                    processInfoList = await TiaWorker.Run(() => tia.GetOpenTiaInstances());
                }
                catch (Exception ex)
                {
                    // typically: Siemens.Engineering.dll of the selected version could not be
                    // loaded, or the user is not a member of the "Siemens TIA Openness" group
                    Log("ERROR querying open Tia Portal instances \n" + ex.Message);
                    return;
                }

                cbOpenTiaInstances.Items.Clear();
                foreach (var processInfo in processInfoList)
                {
                    cbOpenTiaInstances.Items.Add("[" + processInfo.ProcessID + "] " + processInfo.ProjectName);
                }
                cbOpenTiaInstances.SelectedIndex = 0;
            }, quietWhenBusy);
        }

        private void ShowRunningIcon(string Start_Stop)
        {
            if (Start_Stop.Contains("start"))
                runningOperations++;
            else
                runningOperations = Math.Max(0, runningOperations - 1);

            icoRunning.Visibility = runningOperations > 0 ? Visibility.Visible : Visibility.Hidden;
        }

    }

}

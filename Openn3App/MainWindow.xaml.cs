using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;

using Openn._03_ApiManager;
using Openn._01_Constructor;
using Openn._10_StandardFunctions;
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
            //defaults point at the Shared handoff tree this app exchanges with Pipeline3
            //(see AppPaths). The TIA project is Openn2-internal so it stays under the exe.
            tbHardwareCsvPath.Text = AppPaths.HardwareConfigDir;          // Stations.csv + Modules.csv
            tbProjectPath.Text = AppPaths.AppBaseDir + "\\TiaProjects\\openness_project";
            tbSourceBlockPath.Text = AppPaths.ImportReadyBlocksDir;       // single block import (browse start)
            tbBlockGenCsvPath.Text = AppPaths.BlocksCreationDir;          // block-generation csv
            tbInstanceDbCsvPath.Text = AppPaths.BlocksCreationDir;        // InstanceDBs.csv
            tbImportQueuePath.Text = AppPaths.ImportReadyBlocksDir;       // batch import intake
            rbUseInstance.IsChecked = true;
            rbUseExistingIoControllers.IsChecked = true;
            lblSharedRoot.Content = "Shared handoff tree: " + AppPaths.SharedRoot;
        }

        private async void LoadHardwareConfiguration()
        {
            string folder = tbHardwareCsvPath.Text;
            await RunBackend(() => TiaWorker.Run(() => HardwareConfigLoader.LoadAll(folder)));
            await RefreshOpenInstancesDropdown(quietWhenBusy: true);
            await TryAutoAttachAsync(); //one-shot: single instance + single project
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

        /// <summary>Toggle: attaches when detached, detaches when attached.</summary>
        private async void btnAttachProject_Click(object sender, RoutedEventArgs e)
        {
            if (IsProjectAttached)
            {
                await RunBackend(async () =>
                {
                    tbAttachedProject.Text = await TiaWorker.Run(() => tia.DetachProject());
                });
                UpdateAttachButton();
                return;
            }

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
            UpdateAttachButton();
        }

        private bool IsProjectAttached => !string.IsNullOrEmpty(tbAttachedProject.Text);

        private void UpdateAttachButton()
        {
            if (IsProjectAttached)
            {
                btnAttachProject.Content = "Detach Project";
                btnAttachProject.Background = System.Windows.Media.Brushes.SteelBlue;
                btnAttachProject.Foreground = System.Windows.Media.Brushes.White;
            }
            else
            {
                btnAttachProject.Content = "Attach Project";
                btnAttachProject.ClearValue(System.Windows.Controls.Control.BackgroundProperty);
                btnAttachProject.ClearValue(System.Windows.Controls.Control.ForegroundProperty);
            }
        }

        /// <summary>
        /// One-shot at startup: exactly one running TIA instance with exactly one
        /// open project - attach to it without any clicks.
        /// </summary>
        private bool autoAttachAttempted;

        private async Task TryAutoAttachAsync()
        {
            if (autoAttachAttempted || IsProjectAttached) return;
            autoAttachAttempted = true;

            if (processInfoList.Count != 1) return;
            string projectPath = processInfoList[0].ProjectPath;
            if (string.IsNullOrEmpty(projectPath) || projectPath == "No Project") return;

            Log("Auto-attach: one running TIA Portal instance with one open project");
            await RunBackend(async () =>
            {
                tbAttachedProject.Text = await TiaWorker.Run(() => tia.AttachToProject(projectPath));
            });
            UpdateAttachButton();
        }

        private void btnBrowseProjects_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFolderDialog(tbProjectPath.Text);
            if (!(_path == null))
                tbProjectPath.Text = _path.FullName;
        }

        /// <summary>
        /// Reopens the startup version selection. The Openness version is fixed per
        /// process (AssemblyResolve hook), so choosing a different one restarts the
        /// app with the choice passed on the command line.
        /// </summary>
        private void btnTiaVersion_Click(object sender, RoutedEventArgs e)
        {
            var installations = OpennessSetup.DiscoverInstallations();
            OpennessInstallation selection = OpennessVersionDialog.ShowSelection(installations);
            if (selection == null) return;

            if (selection.PortalVersion.Major == OpennessSetup.SelectedInstallation.PortalVersion.Major)
            {
                Log("TIA version unchanged: " + selection.DisplayName);
                return;
            }

            MessageBoxResult answer = MessageBox.Show(
                "The Openness version is fixed for the lifetime of the process.\n\nRestart Openn2 with " + selection.DisplayName + "?",
                "Openn2 - Change TIA Version", MessageBoxButton.YesNo, MessageBoxImage.Question);
            if (answer != MessageBoxResult.Yes) return;

            Process.Start(Process.GetCurrentProcess().MainModule.FileName, "--tiaversion=" + selection.PortalVersion.Major);
            Application.Current.Shutdown();
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
                (blockName, format) => tia.ExportBlock(blockName, format))
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

        private void btnBrowseBlockGenCsv_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFileDialog(startPath: tbBlockGenCsvPath.Text, filter: "File (.csv)|*.csv");
            if (!(_path == null))
                tbBlockGenCsvPath.Text = _path.FullName;
        }

        private void btnBrowseInstanceDbCsv_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFileDialog(startPath: tbInstanceDbCsvPath.Text, filter: "File (.csv)|*.csv");
            if (!(_path == null))
                tbInstanceDbCsvPath.Text = _path.FullName;
        }

        private async void btnCreateInstanceDbs_Click(object sender, RoutedEventArgs e)
        {
            string csvPath = tbInstanceDbCsvPath.Text;
            await RunBackend(() => TiaWorker.Run(() => tia.CreateInstanceDbs(csvPath)));
        }

        private void btnBrowseImportQueue_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFolderDialog(tbImportQueuePath.Text);
            if (!(_path == null))
                tbImportQueuePath.Text = _path.FullName;
        }

        private async void btnRunImportQueue_Click(object sender, RoutedEventArgs e)
        {
            string queueFolder = tbImportQueuePath.Text;
            await RunBackend(() => TiaWorker.Run(() => tia.RunImportQueue(queueFolder)));
        }

        // ----- Project tab: whole-project import / export (the Pipeline3 round-trip) -----

        private async void btnImportFullProject_Click(object sender, RoutedEventArgs e)
        {
            bool createNew = cbImportCreateNewControllers.IsChecked == true;
            await RunBackend(() => TiaWorker.Run(() => tia.ImportFullProject(createNew)));
        }

        private async void btnImportHardware_Click(object sender, RoutedEventArgs e)
        {
            bool createNew = cbImportCreateNewControllers.IsChecked == true;
            await RunBackend(() => TiaWorker.Run(() => tia.ImportHardware(createNew)));
        }

        private async void btnImportUdts_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ImportUserDataTypes()));
        }

        private async void btnImportIoTags_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ImportIoTags()));
        }

        private async void btnImportDataBlocks_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ImportDataBlocks()));
        }

        private async void btnImportInstanceDbsProj_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ImportInstanceDbs()));
        }

        private async void btnImportSoftwareBlocks_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ImportSoftwareBlocks()));
        }

        private async void btnExportFullProject_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ExportFullProject()));
        }

        private async void btnExportSoftwareBlocks_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ExportSoftwareBlocks()));
        }

        private async void btnExportDataBlocks_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ExportDataBlocks()));
        }

        private async void btnExportUdts_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ExportUserDataTypes()));
        }

        private async void btnExportTagTables_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ExportTagTables()));
        }

        private async void btnExportHardwareCax_Click(object sender, RoutedEventArgs e)
        {
            await RunBackend(() => TiaWorker.Run(() => tia.ExportHardwareCax()));
        }

        private async void btnGenerateBlocks_Click(object sender, RoutedEventArgs e)
        {
            string csvPath = tbBlockGenCsvPath.Text;
            string blockName = tbBlockGenName.Text; //empty = template name without TEMPLATE--vX.Y-- prefix
            //the generated document is stamped with the RUNNING Openness version
            string versionTag = "V" + OpennessSetup.SelectedInstallation.PortalVersion.Major;
            string outputFolder = Path.Combine(
                Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName), "GeneratedBlocks");

            string outputPath = null;
            await RunBackend(() => TiaWorker.Run(() =>
            {
                outputPath = Openn._02_Converter.BlockXmlGenerator.Generate(csvPath, versionTag, outputFolder, blockName);
            }));

            //convenience: point the import box at the fresh file
            if (outputPath != null)
                tbSourceBlockPath.Text = outputPath;
        }

        private async void btnDumpAttributes_Click(object sender, RoutedEventArgs e)
        {
            string deviceNameFilter = tbDumpDeviceFilter.Text;
            await RunBackend(() => TiaWorker.Run(() => tia.DumpDeviceAttributes(deviceNameFilter)));
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

        private void btnCancelOperation_Click(object sender, RoutedEventArgs e)
        {
            //cooperative: the operation stops at its next between-calls checkpoint
            TiaWorker.CancelCurrentOperation();
            Log("Cancel requested - the operation stops after the current TIA call completes");
        }

        #region Log copy

        private void lbLogView_KeyDown(object sender, System.Windows.Input.KeyEventArgs e)
        {
            if (e.Key == System.Windows.Input.Key.C && System.Windows.Input.Keyboard.Modifiers == System.Windows.Input.ModifierKeys.Control)
            {
                CopyLogLines(selectedOnly: true);
                e.Handled = true;
            }
        }

        private void miCopyLogSelected_Click(object sender, RoutedEventArgs e) => CopyLogLines(selectedOnly: true);

        private void miCopyLogAll_Click(object sender, RoutedEventArgs e) => CopyLogLines(selectedOnly: false);

        private void CopyLogLines(bool selectedOnly)
        {
            System.Collections.IEnumerable source =
                selectedOnly && lbLogView.SelectedItems.Count > 0 ? lbLogView.SelectedItems : (System.Collections.IEnumerable)lbLogView.Items;

            var text = new System.Text.StringBuilder();
            foreach (object item in source)
                text.AppendLine(TextOf(item));

            if (text.Length == 0) return;
            try
            {
                Clipboard.SetText(text.ToString());
            }
            catch (Exception ex)
            {
                Log("Could not copy to clipboard \n" + ex.Message); //clipboard can be locked by another process
            }
        }

        #endregion Log copy

        #region Log filter & file log

        private void tbLogFilter_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
        {
            string pattern = tbLogFilter.Text;
            if (string.IsNullOrWhiteSpace(pattern))
            {
                tbLogFilter.ClearValue(System.Windows.Controls.Control.BackgroundProperty);
                SetFilter(null);
                return;
            }

            try
            {
                var regex = new System.Text.RegularExpressions.Regex(pattern, System.Text.RegularExpressions.RegexOptions.IgnoreCase);
                tbLogFilter.ClearValue(System.Windows.Controls.Control.BackgroundProperty);
                SetFilter(line => regex.IsMatch(line));
            }
            catch (ArgumentException)
            {
                //invalid regex: mark the box, show everything
                tbLogFilter.Background = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0xFF, 0xDC, 0xDC));
                SetFilter(null);
            }
        }

        private void cbLogToFile_Checked(object sender, RoutedEventArgs e)
        {
            string folder = Path.Combine(Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName), "Logs");
            try
            {
                Log("Logging to file: " + StartFileLog(folder));
            }
            catch (Exception ex)
            {
                Log("ERROR starting file log \n" + ex.Message);
                cbLogToFile.IsChecked = false;
            }
        }

        private void cbLogToFile_Unchecked(object sender, RoutedEventArgs e)
        {
            string path = LogFilePath;
            StopFileLog();
            Log("File logging stopped" + (path == null ? "" : " (" + path + ")"));
        }

        #endregion Log filter & file log

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

            Visibility visibility = runningOperations > 0 ? Visibility.Visible : Visibility.Hidden;
            icoRunning.Visibility = visibility;
            btnCancelOperation.Visibility = visibility;
        }

    }

}

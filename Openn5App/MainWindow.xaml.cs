using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;

using Openn._00_Contract;
using Openn._03_ApiManager;
using Openn._01_Constructor;
using Openn._10_StandardFunctions;
using static Openn._10_StandardFunctions.LogsManager;
using static Openn._10_StandardFunctions.StandardFunctions;
using static Openn._03_ApiManager.TiaPortalOpenness;

namespace Openn
{
    /// <summary>
    /// Main window: a collapsible "TIA project" connection row (rarely used, so collapsed by default; its header
    /// keeps the Attach/Detach toggle and the attached-project status visible), the Workspace tab (the primary
    /// surface - the handoff workspace as a catalog, import and export driven by it; MainWindow.Workspace.cs),
    /// the Files tab (single-file tools: one block, one csv, one hardware folder, the attribute dump) and the log.
    /// </summary>
    public partial class MainWindow : Window
    {
        public IList<TiaProcessInfo> processInfoList = new List<TiaProcessInfo>();

        private readonly TiaPortalOpenness tia = new TiaPortalOpenness(); //instance of API Manager class

        //all backend work (TIA Openness calls, csv loading) runs sequentially on the
        //TiaWorker thread; the UI thread reads control values before queuing and
        //updates controls after awaiting, so the window never freezes.
        private bool backendBusy;
        private int runningOperations;

        //the I/O controller mode has one radio pair per tab (Workspace, Files); they mirror each other
        private bool syncingControllerMode;

        public MainWindow()
        {
            InitializeComponent();
            AttachLogView(lbLogView);

            Title += " - " + OpennessSetup.SelectedInstallation.DisplayName;
            Log("Using " + OpennessSetup.SelectedInstallation.DisplayName + ": " + OpennessSetup.SelectedInstallation.EngineeringDllPath);

            InitializeGraphicComponents();
            InitializeWorkspaceTab();
            Loaded += (s, e) => SetDefaultLogHeight(6);
            Closed += (s, e) => logWindow?.Close(); //the pop-out log lives and dies with the main window
            RunStartupSequence();
        }

        /// <summary>
        /// Starts the log area at <paramref name="rows"/> lines of text: the real height of a rendered log line
        /// (the first item's container once it exists, else the font metrics) times the rows, plus the toolbar,
        /// the list chrome and the horizontal scrollbar when it is showing. Set once at Loaded; the splitter
        /// owns the height afterwards.
        /// </summary>
        private void SetDefaultLogHeight(int rows)
        {
            double line = 0;
            if (lbLogView.Items.Count > 0)
            {
                var first = lbLogView.ItemContainerGenerator.ContainerFromIndex(0) as FrameworkElement;
                if (first != null && first.ActualHeight > 0) line = first.ActualHeight;
            }
            if (line <= 0)
                line = Math.Ceiling(lbLogView.FontSize * lbLogView.FontFamily.LineSpacing) + 4; //item padding + border of the default template

            double scrollbar = 0;
            var scroller = FindDescendant<System.Windows.Controls.ScrollViewer>(lbLogView);
            if (scroller != null && scroller.ComputedHorizontalScrollBarVisibility == Visibility.Visible)
                scrollbar = SystemParameters.HorizontalScrollBarHeight;

            double toolbar = dpLogToolbar.ActualHeight + dpLogToolbar.Margin.Top + dpLogToolbar.Margin.Bottom;
            double chrome = lbLogView.BorderThickness.Top + lbLogView.BorderThickness.Bottom + lbLogView.Margin.Top + lbLogView.Margin.Bottom + 2;
            rowLog.Height = new GridLength(Math.Max(rowLog.MinHeight, toolbar + chrome + scrollbar + rows * line));
        }

        private static T FindDescendant<T>(DependencyObject root) where T : DependencyObject
        {
            if (root == null) return null;
            int count = System.Windows.Media.VisualTreeHelper.GetChildrenCount(root);
            for (int i = 0; i < count; i++)
            {
                DependencyObject child = System.Windows.Media.VisualTreeHelper.GetChild(root, i);
                var typed = child as T;
                if (typed != null) return typed;
                T nested = FindDescendant<T>(child);
                if (nested != null) return nested;
            }
            return null;
        }

        private void InitializeGraphicComponents()
        {
            //the Files tab starts at the default workspace; after the first scan its hardware folder follows the
            //scanned workspace (MainWindow.Workspace.cs). The TIA project default is Openn5-internal (under the exe).
            tbHardwareCsvPath.Text = Path.Combine(AppPaths.BuilderDataDir, WorkspaceLayout.HardwareFolder);
            tbProjectPath.Text = AppPaths.AppBaseDir + "\\TiaProjects\\openness_project";
            rbUseInstance.IsChecked = true;
            rbUseExistingIoControllers.IsChecked = true; //mirrored onto the Workspace tab's pair (ControllerMode_Checked)
            bool wirePorts = false;
            try { wirePorts = Properties.Settings.Default.WireProfinetPorts; }
            catch (Exception e) { Log("Could not read the user settings \n" + e.Message); }
            cbWirePorts.IsChecked = wirePorts; //mirrored onto the Workspace tab's box (WirePorts_Changed)

            bool expanded = false;
            try { expanded = Properties.Settings.Default.ProjectPanelExpanded; }
            catch (Exception e) { Log("Could not read the user settings \n" + e.Message); }
            expProject.IsExpanded = expanded;
            UpdateAttachButton();
        }

        /// <summary>
        /// Startup: the Workspace tab is the primary surface, so its catalog is listed first (no TIA needed; it
        /// also points the Files tab at the workspace's hardware folder), then that hardware config is loaded,
        /// the running instances are listed and the one-shot auto-attach runs.
        /// </summary>
        private async void RunStartupSequence()
        {
            await RescanWorkspaceAsync(quietWhenBusy: true);
            await LoadHardwareConfigurationAsync();
        }

        private async Task LoadHardwareConfigurationAsync()
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

        #region TIA project row

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
                    Log("Can't attach: no open Tia Portal instance selected (expand the TIA project row to pick one, or attach by path)");
                    expProject.IsExpanded = true;
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

        /// <summary>The Attach/Detach toggle and the status text in the (collapsed) row's header.</summary>
        private void UpdateAttachButton()
        {
            if (IsProjectAttached)
            {
                btnAttachProject.Content = "Detach Project";
                btnAttachProject.Background = System.Windows.Media.Brushes.SteelBlue;
                btnAttachProject.Foreground = System.Windows.Media.Brushes.White;
                tbProjectStatus.Text = "TIA project: " + tbAttachedProject.Text;
            }
            else
            {
                btnAttachProject.Content = "Attach Project";
                btnAttachProject.ClearValue(System.Windows.Controls.Control.BackgroundProperty);
                btnAttachProject.ClearValue(System.Windows.Controls.Control.ForegroundProperty);
                tbProjectStatus.Text = cbOpenTiaInstances.Items.Count > 0
                    ? "TIA project: not attached  -  Attach takes the selected open instance (" + cbOpenTiaInstances.Items.Count + " found); expand to choose or to attach by path"
                    : "TIA project: not attached  -  no open TIA instance found; expand to attach by path";
            }
        }

        /// <summary>The row remembers whether the user keeps it open.</summary>
        private void expProject_Toggled(object sender, RoutedEventArgs e)
        {
            if (!IsLoaded) return;
            try
            {
                if (Properties.Settings.Default.ProjectPanelExpanded == expProject.IsExpanded) return;
                Properties.Settings.Default.ProjectPanelExpanded = expProject.IsExpanded;
                Properties.Settings.Default.Save();
            }
            catch (Exception ex)
            {
                Log("Could not save the user settings \n" + ex.Message);
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
                "The Openness version is fixed for the lifetime of the process.\n\nRestart Openn5 with " + selection.DisplayName + "?",
                "Openn5 - Change TIA Version", MessageBoxButton.YesNo, MessageBoxImage.Question);
            if (answer != MessageBoxResult.Yes) return;

            Process.Start(Process.GetCurrentProcess().MainModule.FileName, "--tiaversion=" + selection.PortalVersion.Major);
            TeardownTia(); //Application.Shutdown does not raise Window.Closing: release the attachment here
            Application.Current.Shutdown();
        }

        /// <summary>Exit: stop the file log, close the pop-out log, release the TIA attachment (TiaPortalOpenness.Shutdown) so no XML stays locked.</summary>
        private void Window_Closing(object sender, System.ComponentModel.CancelEventArgs e)
        {
            StopFileLog();
            logWindow?.Close();
            TeardownTia();
        }

        /// <summary>
        /// Releases the TIA Openness connection on exit so the runtime frees every block/tag/UDT XML it still holds
        /// open (see TiaPortalOpenness.Shutdown). Runs on the TiaWorker thread - the only thread allowed to touch
        /// Siemens objects - with a bounded wait, so a stuck Openness call cannot hang the close (the worker is a
        /// background thread and dies with the process anyway).
        /// </summary>
        private void TeardownTia()
        {
            try
            {
                TiaWorker.CancelCurrentOperation();
                TiaWorker.Run(() => tia.Shutdown()).Wait(TimeSpan.FromSeconds(10));
            }
            catch { /* never block the exit on the teardown */ }
        }

        private async void Window_Activated(object sender, System.EventArgs e)
        {
            await RefreshOpenInstancesDropdown(quietWhenBusy: true);
        }

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
                UpdateAttachButton();
            }, quietWhenBusy);
        }

        #endregion TIA project row

        #region I/O controller mode (one choice, two tabs)

        /// <summary>Keeps the Workspace tab's and the Files tab's radio pairs equal; the hardware generation reads either.</summary>
        private void ControllerMode_Checked(object sender, RoutedEventArgs e)
        {
            if (syncingControllerMode) return;
            if (rbWsCreateNewControllers == null || rbCreateNewIoControllers == null) return; //still constructing
            syncingControllerMode = true;
            try
            {
                bool createNew = ReferenceEquals(sender, rbWsCreateNewControllers) || ReferenceEquals(sender, rbCreateNewIoControllers);
                rbWsCreateNewControllers.IsChecked = createNew;
                rbWsUseExistingControllers.IsChecked = !createNew;
                rbCreateNewIoControllers.IsChecked = createNew;
                rbUseExistingIoControllers.IsChecked = !createNew;
            }
            finally
            {
                syncingControllerMode = false;
            }
        }

        /// <summary>True = "Create new I/O controllers" (either pair, they are kept equal).</summary>
        private bool CreateNewControllersSelected => rbWsCreateNewControllers.IsChecked == true;

        /// <summary>"Wire PROFINET ports": one choice, a box on each tab (mirrored), remembered in Properties.Settings.WireProfinetPorts.</summary>
        private bool WirePortsSelected => cbWsWirePorts.IsChecked == true;

        private bool syncingWirePorts;

        private void WirePorts_Changed(object sender, RoutedEventArgs e)
        {
            if (syncingWirePorts) return;
            if (cbWsWirePorts == null || cbWirePorts == null) return; //still constructing
            syncingWirePorts = true;
            try
            {
                bool on = (sender as System.Windows.Controls.CheckBox)?.IsChecked == true;
                cbWsWirePorts.IsChecked = on;
                cbWirePorts.IsChecked = on;
                if (!IsLoaded) return;
                if (Properties.Settings.Default.WireProfinetPorts == on) return;
                Properties.Settings.Default.WireProfinetPorts = on;
                Properties.Settings.Default.Save();
            }
            catch (Exception ex)
            {
                Log("Could not save the user settings \n" + ex.Message);
            }
            finally
            {
                syncingWirePorts = false;
            }
        }

        #endregion I/O controller mode

        #region Workspace tab: export

        /// <summary>The export root of the current workspace: its sibling ExportedData folder.</summary>
        private string CurrentExportRoot() => AppPaths.ExportRootFor(tbWorkspaceRoot.Text);

        private async void btnExportFullProject_Click(object sender, RoutedEventArgs e)
        {
            string root = CurrentExportRoot();
            await RunBackend(() => TiaWorker.Run(() => tia.ExportFullProject(root)));
        }

        private async void btnExportSoftwareBlocks_Click(object sender, RoutedEventArgs e)
        {
            string root = CurrentExportRoot();
            await RunBackend(() => TiaWorker.Run(() => tia.ExportSoftwareBlocks(root)));
        }

        private async void btnExportDataBlocks_Click(object sender, RoutedEventArgs e)
        {
            string root = CurrentExportRoot();
            await RunBackend(() => TiaWorker.Run(() => tia.ExportDataBlocks(root)));
        }

        private async void btnExportUdts_Click(object sender, RoutedEventArgs e)
        {
            string root = CurrentExportRoot();
            await RunBackend(() => TiaWorker.Run(() => tia.ExportUserDataTypes(root)));
        }

        private async void btnExportTagTables_Click(object sender, RoutedEventArgs e)
        {
            string root = CurrentExportRoot();
            await RunBackend(() => TiaWorker.Run(() => tia.ExportTagTables(root)));
        }

        private async void btnExportHardwareCax_Click(object sender, RoutedEventArgs e)
        {
            string root = CurrentExportRoot();
            await RunBackend(() => TiaWorker.Run(() => tia.ExportHardwareCax(root)));
        }

        #endregion Workspace tab: export

        #region Files tab: program blocks

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
            if (string.IsNullOrWhiteSpace(fileName)) { Log("Pick a block XML to import first (Browse..)"); return; }
            await RunBackend(() => TiaWorker.Run(() => tia.ImportPlcBlock(fileName)));
        }

        /// <summary>File dialogs of the Files tab start at the box's own path, else at the workspace root.</summary>
        private string StartPathFor(string boxText) =>
            string.IsNullOrWhiteSpace(boxText) ? tbWorkspaceRoot.Text : boxText;

        private void btnBrowseBlocks_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFileDialog(startPath: StartPathFor(tbSourceBlockPath.Text), filter: "Importable (*.xml;*.csv;*.db;*.scl;*.awl)|*.xml;*.csv;*.db;*.scl;*.awl|All files (*.*)|*.*");
            if (!(_path == null))
                tbSourceBlockPath.Text = _path.FullName;
        }

        private void btnBrowseBlockGenCsv_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFileDialog(startPath: StartPathFor(tbBlockGenCsvPath.Text), filter: "Block generation csv (.csv)|*.csv");
            if (!(_path == null))
                tbBlockGenCsvPath.Text = _path.FullName;
        }

        private void btnBrowseInstanceDbCsv_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFileDialog(startPath: StartPathFor(tbInstanceDbCsvPath.Text), filter: "Instance DB csv (.csv)|*.csv");
            if (!(_path == null))
                tbInstanceDbCsvPath.Text = _path.FullName;
        }

        private async void btnCreateInstanceDbs_Click(object sender, RoutedEventArgs e)
        {
            string csvPath = tbInstanceDbCsvPath.Text;
            if (string.IsNullOrWhiteSpace(csvPath)) { Log("Pick an instance-DB csv first (Browse..)"); return; }
            await RunBackend(() => TiaWorker.Run(() => tia.CreateInstanceDbs(csvPath)));
        }

        private async void btnGenerateBlocks_Click(object sender, RoutedEventArgs e)
        {
            string csvPath = tbBlockGenCsvPath.Text;
            if (string.IsNullOrWhiteSpace(csvPath)) { Log("Pick a block-generation csv first (Browse..)"); return; }
            string blockName = tbBlockGenName.Text; //empty = template name without TEMPLATE--vX.Y-- prefix
            //the generated document is stamped with the RUNNING Openness version
            string versionTag = "V" + OpennessSetup.SelectedInstallation.PortalVersion.Major;
            string outputFolder = AppPaths.GeneratedBlocksDir;

            string outputPath = null;
            await RunBackend(() => TiaWorker.Run(() =>
            {
                outputPath = Openn._02_Converter.BlockXmlGenerator.Generate(csvPath, versionTag, outputFolder, blockName);
            }));

            //convenience: point the import box at the fresh file
            if (outputPath != null)
                tbSourceBlockPath.Text = outputPath;
        }

        #endregion Files tab: program blocks

        #region Files tab: hardware + discovery

        private async void btnImportHardwareCsv_Click(object sender, RoutedEventArgs e)
        {
            await LoadHardwareConfigurationAsync();
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

            bool? createNewIoControllers = CreateNewControllersSelected;
            bool wirePorts = WirePortsSelected;
            await RunBackend(() => TiaWorker.Run(() => tia.CreateDevices(createNewIoControllers, wirePorts)));
        }

        private async void btnDumpAttributes_Click(object sender, RoutedEventArgs e)
        {
            string deviceNameFilter = tbDumpDeviceFilter.Text;
            await RunBackend(() => TiaWorker.Run(() => tia.DumpDeviceAttributes(deviceNameFilter)));
        }

        /// <summary>
        /// "Re-arrange devices..": the mouse-drag layout of the last generation's stations (ArrangeDevicesWindow). Without
        /// a generation in this session the loaded configuration's IO devices stand in - with a warning, since stations
        /// already in the project were never on the default row.
        /// </summary>
        private void btnArrangeDevices_Click(object sender, RoutedEventArgs e)
        {
            IList<string> stations = tia.LastCreatedStations.ToList();
            string source = "the last hardware generation run";
            if (stations.Count == 0)
            {
                var loaded = Openn._01_Constructor.HardwareIoDevices.DevicesList;
                stations = loaded != null ? loaded.Select(d => d.Item1.name).ToList() : new List<string>();
                source = "the loaded configuration - no generation ran in this session, so stations that already existed are NOT on the default row";
            }
            var window = new ArrangeDevicesWindow(stations, source, () => tia.AttachedProcessId) { Owner = this };
            window.Show();
        }

        #endregion Files tab: hardware + discovery

        #region Log toolbar

        private LogWindow logWindow; //the pop-out log (LogWindow.cs): one at a time, null while closed

        /// <summary>Opens the log in its own window, or brings the open one to the front.</summary>
        private void btnLogPopout_Click(object sender, RoutedEventArgs e)
        {
            if (logWindow == null)
            {
                logWindow = new LogWindow(this);
                logWindow.Closed += (s, args) => logWindow = null;
                logWindow.Show();
                return;
            }
            if (logWindow.WindowState == WindowState.Minimized)
                logWindow.WindowState = WindowState.Normal;
            logWindow.Activate();
        }

        private async void btnClearLogs_Click(object sender, RoutedEventArgs e)
        {
            ClearLog();
            await RefreshOpenInstancesDropdown(quietWhenBusy: true);
        }

        private void btnCancelOperation_Click(object sender, RoutedEventArgs e)
        {
            //cooperative: the operation stops at its next between-calls checkpoint
            TiaWorker.CancelCurrentOperation();
            Log("Cancel requested - the operation stops after the current TIA call completes");
        }

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

        private void CopyLogLines(bool selectedOnly) => CopyLines(lbLogView, selectedOnly);

        private void tbLogFilter_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
        {
            //regex, case-insensitive; an invalid pattern marks the box and shows everything (LogsManager.FilterFor)
            bool invalidPattern;
            SetFilter(lbLogView, FilterFor(tbLogFilter.Text, out invalidPattern));
            if (invalidPattern)
                tbLogFilter.Background = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0xFF, 0xDC, 0xDC));
            else
                tbLogFilter.ClearValue(System.Windows.Controls.Control.BackgroundProperty);
        }

        private void cbLogToFile_Checked(object sender, RoutedEventArgs e)
        {
            string folder = Path.Combine(AppPaths.AppBaseDir, "Logs");
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

        #endregion Log toolbar
    }
}

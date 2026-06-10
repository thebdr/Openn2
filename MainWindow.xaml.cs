using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Windows;

using Openn._03_ApiManager;
using Openn._01_Constructor;
using static Openn._10_StandardFunctions.LogsManager;
using static Openn._10_StandardFunctions.StandardFunctions;
using static Openn._03_ApiManager.TiaPortalOpenness;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using System.ComponentModel;
using System.Threading;

namespace Openn
{
    public partial class MainWindow : Window
    {
        public IList<TiaProcessInfo> processInfoList = new List<TiaProcessInfo>();
        private BackgroundWorker backgroundWorker1 = new BackgroundWorker();


        public MainWindow()
        {
            InitializeComponent();
            AttachLogView(lbLogView);

            Title += " - " + OpennessSetup.SelectedInstallation.DisplayName;
            Log("Using " + OpennessSetup.SelectedInstallation.DisplayName + ": " + OpennessSetup.SelectedInstallation.EngineeringDllPath);

            //backgroundWorker1.DoWork += BackgroundWorker1_DoWork;

            InitializeGraphicComponents();
            InitializeAdditionalStuff();
        }

        public delegate void testDelegate();

        private void BackgroundWorker1_DoWork(object sender, DoWorkEventArgs e)
        {
            ShowRunningIcon("start");
        }


        private void InitializeGraphicComponents()
        {
            string appBaseDir = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);
            tbHardwareCsvPath.Text = appBaseDir + "\\HardwareConfig";
            tbProjectPath.Text = appBaseDir + "\\TiaProjects\\openness_project";
            tbSourceBlockPath.Text = appBaseDir + "\\EditedBlocks";
            rbUseInstance.IsChecked = true;
            rbUseExistingIoControllers.IsChecked = true;
            ShowRunningIcon("stop");
        }

        private void InitializeAdditionalStuff()
        {
            ShowRunningIcon("start");
            HardwareDeviceTypesDatabase.ReadHardwareList(tbHardwareCsvPath.Text);
            HardwareIoControllers.ReadDevicesList(tbHardwareCsvPath.Text);
            HardwareIoDevices.ReadDevicesList(tbHardwareCsvPath.Text);
            ShowRunningIcon("stop");
        }

        private TiaPortalOpenness tia = new TiaPortalOpenness(); //instance of API Manager class 

        #region Buttons & Controls

        private async void btnAttachProject_Click(object sender, RoutedEventArgs e)
        {
            ShowRunningIcon("start");
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
                    ShowRunningIcon("stop");
                    return;
                }
                path = processInfoList[cbOpenTiaInstances.SelectedIndex].ProjectPath;
            }

            tbAttachedProject.Text = await tia.AttachToProject(path);
            UpdateBlocksDropdown();
            ShowRunningIcon("stop");
        }

        private void btnBrowseProjects_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFolderDialog(tbProjectPath.Text);
            if (!(_path == null))
                tbProjectPath.Text = _path.FullName;
        }

        private void btnDetachProject_Click(object sender, RoutedEventArgs e)
        {
            tbAttachedProject.Text = tia.DetachProject();
        }

        private void btnExportSource_Click(object sender, RoutedEventArgs e)
        {
            backgroundWorker1.RunWorkerAsync();

            //split Type & Name
            string[] BlockInfo = new string[] { "", "" };
            BlockInfo = cbSourceBlocksList.SelectedItem.ToString().Split(']');
            BlockInfo[0] = BlockInfo[0].Remove(BlockInfo[0].Length - 1);
            BlockInfo[1] = BlockInfo[1].Remove(0, 1);

            tia.ExportBlock(BlockInfo[1]);

            ShowRunningIcon("stop");
        }

        private void btnRefreshBlocks_Click(object sender, RoutedEventArgs e)
        {
            ShowRunningIcon("start");

            UpdateBlocksDropdown();

            ShowRunningIcon("stop");
        }

        private void btnImportSource_Click(object sender, RoutedEventArgs e)
        {
            ShowRunningIcon("start");

            tia.ImportPlcBlock(tbSourceBlockPath.Text);

            ShowRunningIcon("stop");
        }

        private void btnBrowseBlocks_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFileDialog(startPath: tbSourceBlockPath.Text, filter: "File (.xml)|*.xml");
            if (!(_path == null))
                tbSourceBlockPath.Text = _path.FullName;
        }

        private void btnImportHardwareCsv_Click(object sender, RoutedEventArgs e)
        {
            ShowRunningIcon("start");

            HardwareDeviceTypesDatabase.ReadHardwareList(tbHardwareCsvPath.Text);
            HardwareIoControllers.ReadDevicesList(tbHardwareCsvPath.Text);
            HardwareIoDevices.ReadDevicesList(tbHardwareCsvPath.Text);

            ShowRunningIcon("stop");
        }

        private void btnBrowseHwConfigCsv_Click(object sender, RoutedEventArgs e)
        {
            var _path = GetFolderDialog(tbHardwareCsvPath.Text);
            if (!(_path == null))
                tbHardwareCsvPath.Text = _path.FullName;
        }

        private void btnGenerateHardware_Click(object sender, RoutedEventArgs e)
        {
            ShowRunningIcon("start");

            if ((HardwareDeviceTypesDatabase.Identifier == null) || (HardwareDeviceTypesDatabase.Identifier.Count() < 1))
            {
                Log("Can't generate hardware configuration: Hardware Configuration not loaded.");
                return;
            }
            tia.CreateDevices(rbCreateNewIoControllers.IsChecked);
            
            ShowRunningIcon("stop");
        }

        private void btnClearLogs_Click(object sender, RoutedEventArgs e)
        {
            ShowRunningIcon("start");
            lbLogView.Items.Clear();
            UpdateOpenInstancesDropdown();
        }

        private void Window_Activated(object sender, System.EventArgs e)
        {
            UpdateOpenInstancesDropdown();
        }

        #endregion Buttons & Controls

        private void UpdateBlocksDropdown()
        {
            ShowRunningIcon("start");

            cbSourceBlocksList.Items.Clear();
            foreach (string BlockName in tia.UpdateSourceBlocksList())
            {
                cbSourceBlocksList.Items.Add(BlockName);
            }
            cbSourceBlocksList.SelectedIndex = 0;

            ShowRunningIcon("stop");
        }

        public void UpdateOpenInstancesDropdown()
        {
            try
            {
                processInfoList = tia.GetOpenTiaInstances();
            }
            catch (System.Exception e)
            {
                // typically: Siemens.Engineering.dll of the selected version could not be
                // loaded, or the user is not a member of the "Siemens TIA Openness" group
                Log("ERROR querying open Tia Portal instances \n" + e.Message);
                return;
            }

            cbOpenTiaInstances.Items.Clear();
            foreach (var processInfo in processInfoList)
            {
                cbOpenTiaInstances.Items.Add("[" + processInfo.ProcessID + "] " + processInfo.ProjectName);
            }
            cbOpenTiaInstances.SelectedIndex = 0;
        }

        private void ShowRunningIcon(string Start_Stop)
        {
            return;

            if (Start_Stop.Contains("start"))
                this.Dispatcher.Invoke(()=> icoRunning.Visibility = Visibility.Visible);
            else if (Start_Stop.Contains("stop"))
                this.Dispatcher.Invoke(() => icoRunning.Visibility = Visibility.Visible);
            else
                this.Dispatcher.Invoke(() => icoRunning.Visibility = Visibility.Visible);

        }

    }

}

       
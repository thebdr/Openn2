using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;

using Openn._01_Constructor;
using Openn._03_ApiManager;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn
{
    /// <summary>
    /// Object explorer / editor for the hardware configuration csv files.
    ///
    /// Left: tree of stations and their modules, filtered as you type by a
    /// case-insensitive regex (a station matches by its own fields or stays
    /// visible with only its matching modules). Right: edit panel for the
    /// selected object - changes apply to the in-memory document immediately.
    /// Toolbar: add/duplicate/delete station and module (Del key works too).
    /// "Save + Reload" writes Stations.csv/Modules.csv back (format 2) and
    /// re-runs the validating HardwareConfigLoader on the worker thread, so
    /// the main window's configuration stays in sync and all validation
    /// problems land in the main log.
    ///
    /// The editor deliberately tolerates invalid values (the document is not
    /// validated while editing) - that is what makes it usable for FIXING a
    /// configuration the loader rejected.
    /// </summary>
    public class HardwareConfigEditorWindow : Window
    {
        private HardwareConfigDocument document;
        private bool dirty;
        private bool populatingFields; //true while the edit panel is being filled from the model

        private readonly TextBox searchBox;
        private readonly TreeView tree;
        private readonly TextBlock statusText;

        //station edit panel
        private readonly GroupBox stationPanel;
        private readonly ComboBox stationRoleBox;
        private readonly TextBox stationNameBox;
        private readonly ComboBox stationModelBox;
        private readonly TextBlock stationModelInfo;
        private readonly TextBox stationIpBox;
        private readonly TextBox stationPnBox;
        private readonly TextBox stationSubnetBox;
        private readonly TextBox stationParamsBox;

        //module edit panel
        private readonly GroupBox modulePanel;
        private readonly TextBox moduleSlotBox;
        private readonly TextBox moduleNameBox;
        private readonly ComboBox moduleModelBox;
        private readonly TextBlock moduleModelInfo;
        private readonly TextBox moduleIBox;
        private readonly TextBox moduleQBox;
        private readonly TextBox moduleParamsBox;

        private readonly HashSet<StationModel> expandedStations = new HashSet<StationModel>();

        public HardwareConfigEditorWindow(string configFolder)
        {
            document = HardwareConfigDocument.Load(configFolder);

            Title = "Openn2 - Hardware Configuration Editor - " + configFolder;
            Width = 980;
            Height = 640;
            MinWidth = 700;
            MinHeight = 400;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;

            //--- top: search ---
            var searchLabel = new TextBlock
            {
                Text = "Search (regex, case-insensitive, matches role/name/model/IP/subnet/addresses/parameters):",
                FontSize = 11,
                Margin = new Thickness(0, 0, 0, 2),
            };
            searchBox = new TextBox { FontSize = 13, Margin = new Thickness(0, 0, 0, 6) };
            searchBox.TextChanged += (s, e) => RebuildTree();

            //--- left: tree ---
            tree = new TreeView();
            tree.SelectedItemChanged += (s, e) => PopulateEditPanel();
            tree.KeyDown += (s, e) => { if (e.Key == Key.Delete) DeleteSelected(); };

            //--- right: edit panels ---
            stationRoleBox = new ComboBox { ItemsSource = new[] { "Plc", "PlcCardCm", "IoDevice" } };
            stationNameBox = new TextBox();
            stationModelBox = new ComboBox { IsEditable = true };
            stationModelInfo = new TextBlock { FontSize = 10, Foreground = SystemColors.GrayTextBrush, TextWrapping = TextWrapping.Wrap };
            stationIpBox = new TextBox();
            stationPnBox = new TextBox();
            stationSubnetBox = new TextBox();
            stationParamsBox = new TextBox { TextWrapping = TextWrapping.Wrap, AcceptsReturn = false, MinHeight = 40 };

            stationPanel = new GroupBox
            {
                Header = "Station",
                Content = BuildFieldGrid(new[]
                {
                    Tuple.Create("Role:", (FrameworkElement)stationRoleBox),
                    Tuple.Create("Name:", (FrameworkElement)stationNameBox),
                    Tuple.Create("Model Id:", (FrameworkElement)stationModelBox),
                    Tuple.Create("", (FrameworkElement)stationModelInfo),
                    Tuple.Create("IP Address:", (FrameworkElement)stationIpBox),
                    Tuple.Create("PN Number:", (FrameworkElement)stationPnBox),
                    Tuple.Create("Subnet:", (FrameworkElement)stationSubnetBox),
                    Tuple.Create("Custom Parameters:", (FrameworkElement)stationParamsBox),
                }),
                Visibility = Visibility.Collapsed,
            };

            moduleSlotBox = new TextBox();
            moduleNameBox = new TextBox();
            moduleModelBox = new ComboBox { IsEditable = true };
            moduleModelInfo = new TextBlock { FontSize = 10, Foreground = SystemColors.GrayTextBrush, TextWrapping = TextWrapping.Wrap };
            moduleIBox = new TextBox();
            moduleQBox = new TextBox();
            moduleParamsBox = new TextBox { TextWrapping = TextWrapping.Wrap, AcceptsReturn = false, MinHeight = 40 };

            modulePanel = new GroupBox
            {
                Header = "Module",
                Content = BuildFieldGrid(new[]
                {
                    Tuple.Create("Slot (plug order):", (FrameworkElement)moduleSlotBox),
                    Tuple.Create("Name:", (FrameworkElement)moduleNameBox),
                    Tuple.Create("Model Id:", (FrameworkElement)moduleModelBox),
                    Tuple.Create("", (FrameworkElement)moduleModelInfo),
                    Tuple.Create("I Start Address:", (FrameworkElement)moduleIBox),
                    Tuple.Create("Q Start Address:", (FrameworkElement)moduleQBox),
                    Tuple.Create("Custom Parameters:", (FrameworkElement)moduleParamsBox),
                }),
                Visibility = Visibility.Collapsed,
            };

            var modelIds = document.Models.Keys.OrderBy(k => k, StringComparer.OrdinalIgnoreCase).ToList();
            stationModelBox.ItemsSource = modelIds;
            moduleModelBox.ItemsSource = modelIds;

            WireStationFields();
            WireModuleFields();

            var editColumn = new ScrollViewer
            {
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Content = new StackPanel { Children = { stationPanel, modulePanel } },
            };

            //--- bottom: actions + status ---
            statusText = new TextBlock { VerticalAlignment = VerticalAlignment.Center, TextTrimming = TextTrimming.CharacterEllipsis };

            var bottomRow = new DockPanel { Margin = new Thickness(0, 8, 0, 0) };
            Button MakeButton(string caption, RoutedEventHandler onClick, double width)
            {
                var button = new Button { Content = caption, Width = width, Margin = new Thickness(8, 0, 0, 0) };
                button.Click += onClick;
                DockPanel.SetDock(button, Dock.Right);
                return button;
            }
            //added right-docked: last added ends up leftmost of the right group
            bottomRow.Children.Add(MakeButton("Save + Reload", async (s, e) => await SaveAsync(), 100));
            bottomRow.Children.Add(MakeButton("Discard / Re-read", (s, e) => ReloadFromDisk(), 110));
            bottomRow.Children.Add(MakeButton("Delete", (s, e) => DeleteSelected(), 70));
            bottomRow.Children.Add(MakeButton("Duplicate", (s, e) => DuplicateSelected(), 80));
            bottomRow.Children.Add(MakeButton("Add Module", (s, e) => AddModule(), 90));
            bottomRow.Children.Add(MakeButton("Add Station", (s, e) => AddStation(), 90));
            bottomRow.Children.Add(statusText);

            //--- layout ---
            var mainGrid = new Grid();
            mainGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1.2, GridUnitType.Star) });
            mainGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            Grid.SetColumn(tree, 0);
            Grid.SetColumn(editColumn, 1);
            editColumn.Margin = new Thickness(8, 0, 0, 0);
            mainGrid.Children.Add(tree);
            mainGrid.Children.Add(editColumn);

            var layout = new DockPanel { Margin = new Thickness(10) };
            DockPanel.SetDock(searchLabel, Dock.Top);
            DockPanel.SetDock(searchBox, Dock.Top);
            DockPanel.SetDock(bottomRow, Dock.Bottom);
            layout.Children.Add(searchLabel);
            layout.Children.Add(searchBox);
            layout.Children.Add(bottomRow);
            layout.Children.Add(mainGrid);
            Content = layout;

            Closing += OnWindowClosing;

            RebuildTree();
            ShowLoadStatus();
        }

        #region Search / filter

        /// <summary>One station visible in the filtered tree, with the modules to show under it.</summary>
        public sealed class SearchResult
        {
            public StationModel Station;
            public IList<ModuleModel> VisibleModules;
        }

        /// <summary>
        /// Case-insensitive regex filter: a station that matches by its own fields is
        /// shown with all modules; otherwise it is shown only when modules match (with
        /// just those). Returns null when the pattern is invalid.
        /// </summary>
        public static IList<SearchResult> Filter(IEnumerable<StationModel> stations, string pattern, out string patternError)
        {
            patternError = null;

            Regex regex = null;
            if (!string.IsNullOrWhiteSpace(pattern))
            {
                try
                {
                    regex = new Regex(pattern, RegexOptions.IgnoreCase);
                }
                catch (ArgumentException e)
                {
                    patternError = e.Message;
                    return null;
                }
            }

            var results = new List<SearchResult>();
            foreach (StationModel station in stations)
            {
                if (regex == null || regex.IsMatch(station.SearchText))
                {
                    results.Add(new SearchResult { Station = station, VisibleModules = station.Modules });
                    continue;
                }

                var matchingModules = station.Modules.Where(m => regex.IsMatch(m.SearchText)).ToList();
                if (matchingModules.Count > 0)
                    results.Add(new SearchResult { Station = station, VisibleModules = matchingModules });
            }
            return results;
        }

        #endregion Search / filter

        #region Tree

        private void RebuildTree(object selectAfter = null)
        {
            object previousSelection = selectAfter ?? SelectedObject();
            bool filtering = !string.IsNullOrWhiteSpace(searchBox.Text);

            string patternError;
            IList<SearchResult> results = Filter(document.Stations, searchBox.Text, out patternError);
            if (results == null)
            {
                statusText.Text = "Invalid regex: " + patternError; //keep the current tree while typing
                return;
            }

            tree.Items.Clear();
            TreeViewItem itemToSelect = null;

            foreach (SearchResult result in results)
            {
                var stationItem = new TreeViewItem
                {
                    Header = result.Station.DisplayText + (result.Station.Modules.Count > 0 ? "   [" + result.Station.Modules.Count + " module(s)]" : ""),
                    Tag = result.Station,
                    IsExpanded = filtering || expandedStations.Contains(result.Station),
                };
                StationModel station = result.Station;
                stationItem.Expanded += (s, e) => { if (e.Source == stationItem) expandedStations.Add(station); };
                stationItem.Collapsed += (s, e) => { if (e.Source == stationItem) expandedStations.Remove(station); };

                foreach (ModuleModel module in result.VisibleModules)
                {
                    var moduleItem = new TreeViewItem { Header = module.DisplayText, Tag = module };
                    if (ReferenceEquals(module, previousSelection)) itemToSelect = moduleItem;
                    stationItem.Items.Add(moduleItem);
                }

                if (ReferenceEquals(result.Station, previousSelection)) itemToSelect = stationItem;
                tree.Items.Add(stationItem);
            }

            if (itemToSelect != null)
            {
                var parent = itemToSelect.Parent as TreeViewItem;
                if (parent != null) parent.IsExpanded = true;
                itemToSelect.IsSelected = true;
                itemToSelect.BringIntoView();
            }

            UpdateStatusCounts(results.Count);
        }

        private object SelectedObject()
        {
            var item = tree.SelectedItem as TreeViewItem;
            return item == null ? null : item.Tag;
        }

        private StationModel SelectedStation()
        {
            object selected = SelectedObject();
            if (selected is StationModel station) return station;
            if (selected is ModuleModel module) return document.Stations.FirstOrDefault(s => s.Modules.Contains(module));
            return null;
        }

        /// <summary>Refreshes the header of the selected node after a field edit.</summary>
        private void RefreshSelectedHeader()
        {
            var item = tree.SelectedItem as TreeViewItem;
            if (item == null) return;
            if (item.Tag is StationModel station)
                item.Header = station.DisplayText + (station.Modules.Count > 0 ? "   [" + station.Modules.Count + " module(s)]" : "");
            else if (item.Tag is ModuleModel module)
                item.Header = module.DisplayText;
        }

        #endregion Tree

        #region Edit panels

        /// <summary>Two-column label+input grid used by both edit panels.</summary>
        private static Grid BuildFieldGrid(IList<Tuple<string, FrameworkElement>> fields)
        {
            var grid = new Grid { Margin = new Thickness(6) };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto, MinWidth = 130 });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            for (int i = 0; i < fields.Count; i++)
            {
                grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

                var label = new TextBlock { Text = fields[i].Item1, Margin = new Thickness(0, 6, 8, 0), VerticalAlignment = VerticalAlignment.Center };
                Grid.SetRow(label, i);
                Grid.SetColumn(label, 0);
                grid.Children.Add(label);

                fields[i].Item2.Margin = new Thickness(0, 4, 0, 0);
                Grid.SetRow(fields[i].Item2, i);
                Grid.SetColumn(fields[i].Item2, 1);
                grid.Children.Add(fields[i].Item2);
            }
            return grid;
        }

        /// <summary>Edits apply to the model immediately (classic object-explorer behavior).</summary>
        private void WireStationFields()
        {
            void Apply(Action<StationModel> change)
            {
                if (populatingFields) return;
                if (!(SelectedObject() is StationModel station)) return;
                change(station);
                RefreshSelectedHeader();
                MarkDirty();
            }

            stationRoleBox.SelectionChanged += (s, e) => Apply(st => st.Role = stationRoleBox.SelectedItem as string ?? st.Role);
            stationNameBox.TextChanged += (s, e) => Apply(st => st.Name = stationNameBox.Text);
            WireEditableCombo(stationModelBox, () => Apply(st => { st.ModelId = stationModelBox.Text; ShowModelInfo(stationModelBox.Text, stationModelInfo); }));
            stationIpBox.TextChanged += (s, e) => Apply(st => st.IpAddress = stationIpBox.Text);
            stationPnBox.TextChanged += (s, e) => Apply(st => st.PnNumber = stationPnBox.Text);
            stationSubnetBox.TextChanged += (s, e) => Apply(st => st.Subnet = stationSubnetBox.Text);
            stationParamsBox.TextChanged += (s, e) => Apply(st => st.CustomParameters = stationParamsBox.Text);
        }

        private void WireModuleFields()
        {
            void Apply(Action<ModuleModel> change)
            {
                if (populatingFields) return;
                if (!(SelectedObject() is ModuleModel module)) return;
                change(module);
                RefreshSelectedHeader();
                MarkDirty();
            }

            moduleSlotBox.TextChanged += (s, e) => Apply(m => m.Slot = moduleSlotBox.Text);
            moduleNameBox.TextChanged += (s, e) => Apply(m => m.Name = moduleNameBox.Text);
            WireEditableCombo(moduleModelBox, () => Apply(m => { m.ModelId = moduleModelBox.Text; ShowModelInfo(moduleModelBox.Text, moduleModelInfo); }));
            moduleIBox.TextChanged += (s, e) => Apply(m => m.IAddress = moduleIBox.Text);
            moduleQBox.TextChanged += (s, e) => Apply(m => m.QAddress = moduleQBox.Text);
            moduleParamsBox.TextChanged += (s, e) => Apply(m => m.CustomParameters = moduleParamsBox.Text);
        }

        /// <summary>An editable ComboBox reports typing and selection through the inner TextBox.</summary>
        private static void WireEditableCombo(ComboBox comboBox, Action onTextChanged)
        {
            comboBox.AddHandler(System.Windows.Controls.Primitives.TextBoxBase.TextChangedEvent,
                new TextChangedEventHandler((s, e) => onTextChanged()));
        }

        private void PopulateEditPanel()
        {
            populatingFields = true;
            try
            {
                object selected = SelectedObject();
                if (selected is StationModel station)
                {
                    stationPanel.Visibility = Visibility.Visible;
                    modulePanel.Visibility = Visibility.Collapsed;

                    stationRoleBox.SelectedItem = new[] { "Plc", "PlcCardCm", "IoDevice" }.FirstOrDefault(r => r.Equals(station.Role, StringComparison.OrdinalIgnoreCase)) ?? station.Role;
                    stationNameBox.Text = station.Name;
                    stationModelBox.Text = station.ModelId;
                    stationIpBox.Text = station.IpAddress;
                    stationPnBox.Text = station.PnNumber;
                    stationSubnetBox.Text = station.Subnet;
                    stationParamsBox.Text = station.CustomParameters;
                    ShowModelInfo(station.ModelId, stationModelInfo);
                }
                else if (selected is ModuleModel module)
                {
                    stationPanel.Visibility = Visibility.Collapsed;
                    modulePanel.Visibility = Visibility.Visible;

                    moduleSlotBox.Text = module.Slot;
                    moduleNameBox.Text = module.Name;
                    moduleModelBox.Text = module.ModelId;
                    moduleIBox.Text = module.IAddress;
                    moduleQBox.Text = module.QAddress;
                    moduleParamsBox.Text = module.CustomParameters;
                    ShowModelInfo(module.ModelId, moduleModelInfo);
                }
                else
                {
                    stationPanel.Visibility = Visibility.Collapsed;
                    modulePanel.Visibility = Visibility.Collapsed;
                }
            }
            finally
            {
                populatingFields = false;
            }
        }

        private void ShowModelInfo(string modelId, TextBlock target)
        {
            ModelInfo info;
            target.Text = document.Models.TryGetValue(modelId ?? "", out info)
                ? info.DeviceType + " - " + info.Comment
                : "(model id not found in " + HardwareDeviceTypesDatabase.FileName + ")";
        }

        #endregion Edit panels

        #region Actions

        private void AddStation()
        {
            var station = new StationModel
            {
                Role = "IoDevice",
                Name = HardwareConfigDocument.MakeUniqueName("new_station", document.Stations.Select(s => s.Name)),
            };
            document.Stations.Add(station);
            MarkDirty();
            RebuildTree(station);
        }

        private void AddModule()
        {
            StationModel station = SelectedStation();
            if (station == null)
            {
                statusText.Text = "Select a station (or one of its modules) first";
                return;
            }

            var module = new ModuleModel
            {
                Slot = HardwareConfigDocument.NextFreeSlot(station),
                Name = HardwareConfigDocument.MakeUniqueName("new_module", station.Modules.Select(m => m.Name)),
            };
            station.Modules.Add(module);
            expandedStations.Add(station);
            MarkDirty();
            RebuildTree(module);
        }

        private void DuplicateSelected()
        {
            object selected = SelectedObject();
            if (selected is StationModel station)
            {
                StationModel copy = station.Clone();
                copy.Name = HardwareConfigDocument.MakeUniqueName(station.Name, document.Stations.Select(s => s.Name));
                document.Stations.Insert(document.Stations.IndexOf(station) + 1, copy);
                MarkDirty();
                RebuildTree(copy);
            }
            else if (selected is ModuleModel module)
            {
                StationModel owner = SelectedStation();
                if (owner == null) return;
                ModuleModel copy = module.Clone();
                copy.Slot = HardwareConfigDocument.NextFreeSlot(owner);
                copy.Name = HardwareConfigDocument.MakeUniqueName(module.Name, owner.Modules.Select(m => m.Name));
                owner.Modules.Insert(owner.Modules.IndexOf(module) + 1, copy);
                MarkDirty();
                RebuildTree(copy);
            }
            else
            {
                statusText.Text = "Select a station or module to duplicate";
            }
        }

        private void DeleteSelected()
        {
            object selected = SelectedObject();
            if (selected is StationModel station)
            {
                string question = station.Modules.Count > 0
                    ? "Delete station \"" + station.Name + "\" and its " + station.Modules.Count + " module(s)?"
                    : "Delete station \"" + station.Name + "\"?";
                if (MessageBox.Show(this, question, "Delete", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes) return;

                document.Stations.Remove(station);
                MarkDirty();
                RebuildTree();
            }
            else if (selected is ModuleModel module)
            {
                StationModel owner = SelectedStation();
                if (owner == null) return;
                if (MessageBox.Show(this, "Delete module \"" + module.Name + "\"?", "Delete", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes) return;

                owner.Modules.Remove(module);
                MarkDirty();
                RebuildTree(owner);
            }
        }

        private async Task SaveAsync()
        {
            try
            {
                document.Save();
            }
            catch (Exception e)
            {
                statusText.Text = "Save FAILED: " + e.Message;
                return;
            }

            dirty = false;
            statusText.Text = "Saved - validating...";

            //re-run the validating loader so the app state matches the files
            string folder = document.Folder;
            bool loadedOk = await TiaWorker.Run(() => HardwareConfigLoader.LoadAll(folder));
            statusText.Text = loadedOk
                ? "Saved - configuration valid and loaded"
                : "Saved - validation found problems, see the main log";
        }

        private void ReloadFromDisk()
        {
            if (dirty &&
                MessageBox.Show(this, "Discard unsaved changes and re-read the csv files?", "Discard changes",
                    MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes)
                return;

            document = HardwareConfigDocument.Load(document.Folder);
            dirty = false;
            expandedStations.Clear();
            RebuildTree();
            ShowLoadStatus();
        }

        private void OnWindowClosing(object sender, System.ComponentModel.CancelEventArgs e)
        {
            if (!dirty) return;
            if (MessageBox.Show(this, "Close without saving? Unsaved changes will be lost.", "Unsaved changes",
                    MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
                e.Cancel = true;
        }

        #endregion Actions

        #region Status

        private void MarkDirty()
        {
            dirty = true;
            UpdateStatusCounts(tree.Items.Count);
        }

        private void UpdateStatusCounts(int visibleStations)
        {
            string text = document.Stations.Count + " station(s), " + document.ModuleCount + " module(s)";
            if (visibleStations != document.Stations.Count)
                text += " - showing " + visibleStations;
            if (dirty)
                text += "  [modified - not saved]";
            statusText.Text = text;
        }

        private void ShowLoadStatus()
        {
            if (document.LoadWarnings.Count == 0) return;
            foreach (string warning in document.LoadWarnings)
                Log("Hardware editor: " + warning);
            statusText.Text += "  (" + document.LoadWarnings.Count + " load warning(s), see main log)";
        }

        #endregion Status
    }
}

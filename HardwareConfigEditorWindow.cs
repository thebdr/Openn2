using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

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
    /// selected object - changes apply to the in-memory document immediately,
    /// and modified objects are highlighted bold blue until saved (a station
    /// also turns blue while it contains modified modules).
    ///
    /// Selection: single click selects and edits; Ctrl+Click builds a
    /// multi-selection (highlighted background) that Duplicate/Delete - via
    /// the buttons, the right-click context menu or the Del key - operate on.
    ///
    /// "Save + Reload" writes Stations.csv/Modules.csv back (format 2) and
    /// re-runs the validating HardwareConfigLoader on the worker thread, so
    /// the main window's configuration stays in sync and all validation
    /// problems land in the main log. The editor deliberately tolerates
    /// invalid values while editing - that is what makes it usable for
    /// FIXING a configuration the loader rejected.
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
        private readonly TextBox stationGroupBox;
        private readonly ComboBox stationModelBox;
        private readonly TextBlock stationModelInfo;
        private readonly TextBox stationModelDefaults;
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
        private readonly TextBox moduleModelDefaults;
        private readonly TextBox moduleIBox;
        private readonly TextBox moduleQBox;
        private readonly TextBox moduleParamsBox;

        private readonly HashSet<StationModel> expandedStations = new HashSet<StationModel>();

        /// <summary>Objects changed since the last save; rendered bold blue.</summary>
        private readonly HashSet<object> modifiedObjects = new HashSet<object>();

        /// <summary>Ctrl+Click multi-selection (model objects); empty = use the tree's single selection.</summary>
        private readonly HashSet<object> multiSelection = new HashSet<object>();

        private static readonly Brush ModifiedBrush = Brushes.RoyalBlue;
        private static readonly Brush MultiSelectBrush = new SolidColorBrush(Color.FromArgb(70, 0, 120, 215));

        public HardwareConfigEditorWindow(string configFolder)
        {
            document = HardwareConfigDocument.Load(configFolder);

            Title = "Openn2 - Hardware Configuration Editor - " + configFolder;
            Width = 1020;
            Height = 680;
            MinWidth = 720;
            MinHeight = 420;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;

            //--- top: search ---
            var searchLabel = new TextBlock
            {
                Text = "Search (regex, case-insensitive, matches role/name/group/model/IP/subnet/addresses/parameters). Ctrl+Click = multi-select.",
                FontSize = 11,
                Margin = new Thickness(0, 0, 0, 2),
            };
            searchBox = new TextBox { FontSize = 13, Margin = new Thickness(0, 0, 0, 6) };
            searchBox.TextChanged += (s, e) => RebuildTree();

            //--- left: tree ---
            tree = new TreeView();
            tree.SelectedItemChanged += (s, e) => PopulateEditPanel();
            tree.KeyDown += (s, e) => { if (e.Key == Key.Delete) DeleteSelected(); };
            tree.PreviewMouseLeftButtonDown += OnTreeLeftButtonDown;
            tree.PreviewMouseRightButtonDown += OnTreeRightButtonDown;
            tree.ContextMenu = BuildContextMenu();

            //--- right: edit panels ---
            stationRoleBox = new ComboBox { ItemsSource = new[] { "Plc", "PlcCardCm", "IoDevice" } };
            stationNameBox = new TextBox();
            stationGroupBox = new TextBox { ToolTip = "Organizational path, e.g. line1/cell3/safety - informational for now" };
            stationModelBox = new ComboBox { IsEditable = true };
            stationModelInfo = new TextBlock { FontSize = 10, Foreground = SystemColors.GrayTextBrush, TextWrapping = TextWrapping.Wrap };
            stationModelDefaults = MakeReadOnlyBox("Model-wide default parameters from DeviceTypesDatabase.csv; row parameters override them per target");
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
                    Tuple.Create("Group (folder/sub/..):", (FrameworkElement)stationGroupBox),
                    Tuple.Create("Model Id:", (FrameworkElement)stationModelBox),
                    Tuple.Create("", (FrameworkElement)stationModelInfo),
                    Tuple.Create("Model defaults (read-only):", (FrameworkElement)stationModelDefaults),
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
            moduleModelDefaults = MakeReadOnlyBox("Model-wide default parameters from DeviceTypesDatabase.csv; row parameters override them per target");
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
                    Tuple.Create("Model defaults (read-only):", (FrameworkElement)moduleModelDefaults),
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

        private static TextBox MakeReadOnlyBox(string toolTip) => new TextBox
        {
            IsReadOnly = true,
            Background = SystemColors.ControlLightLightBrush,
            Foreground = SystemColors.GrayTextBrush,
            TextWrapping = TextWrapping.Wrap,
            ToolTip = toolTip,
        };

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
                TreeViewItem stationItem = CreateItem(result.Station);
                stationItem.IsExpanded = filtering || expandedStations.Contains(result.Station);
                StationModel station = result.Station;
                stationItem.Expanded += (s, e) => { if (e.Source == stationItem) expandedStations.Add(station); };
                stationItem.Collapsed += (s, e) => { if (e.Source == stationItem) expandedStations.Remove(station); };

                foreach (ModuleModel module in result.VisibleModules)
                {
                    TreeViewItem moduleItem = CreateItem(module);
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

        private TreeViewItem CreateItem(object model)
        {
            var item = new TreeViewItem { Tag = model, Header = new TextBlock() };
            UpdateItemHeader(item);
            return item;
        }

        /// <summary>
        /// Renders text + state of one node: bold blue = modified since last save,
        /// plain blue station = contains modified modules, highlighted = multi-selected.
        /// </summary>
        private void UpdateItemHeader(TreeViewItem item)
        {
            string text = "";
            bool containsModified = false;
            if (item.Tag is StationModel station)
            {
                text = station.DisplayText + (station.Modules.Count > 0 ? "   [" + station.Modules.Count + " module(s)]" : "");
                containsModified = station.Modules.Any(m => modifiedObjects.Contains(m));
            }
            else if (item.Tag is ModuleModel module)
            {
                text = module.DisplayText;
            }

            bool isModified = modifiedObjects.Contains(item.Tag);
            var header = (TextBlock)item.Header;
            header.Text = text;
            header.FontWeight = isModified ? FontWeights.Bold : FontWeights.Normal;
            header.Foreground = (isModified || containsModified) ? ModifiedBrush : SystemColors.ControlTextBrush;
            header.Background = multiSelection.Contains(item.Tag) ? MultiSelectBrush : Brushes.Transparent;
        }

        private void RestyleAllItems()
        {
            foreach (TreeViewItem stationItem in tree.Items)
            {
                UpdateItemHeader(stationItem);
                foreach (TreeViewItem moduleItem in stationItem.Items)
                    UpdateItemHeader(moduleItem);
            }
        }

        /// <summary>Restyles the selected node and its parent (a module edit recolors the station too).</summary>
        private void RefreshSelectedItemStyle()
        {
            var item = tree.SelectedItem as TreeViewItem;
            if (item == null) return;
            UpdateItemHeader(item);
            if (ItemsControl.ItemsControlFromItemContainer(item) is TreeViewItem parent)
                UpdateItemHeader(parent);
        }

        private object SelectedObject()
        {
            var item = tree.SelectedItem as TreeViewItem;
            return item == null ? null : item.Tag;
        }

        /// <summary>The multi-selection when active, otherwise the tree's single selection.</summary>
        private IList<object> SelectedObjects()
        {
            if (multiSelection.Count > 0) return multiSelection.ToList();
            object single = SelectedObject();
            return single == null ? new List<object>() : new List<object> { single };
        }

        private StationModel SelectedStation()
        {
            object selected = SelectedObject();
            if (selected is StationModel station) return station;
            if (selected is ModuleModel module) return OwnerOf(module);
            return null;
        }

        private StationModel OwnerOf(ModuleModel module) =>
            document.Stations.FirstOrDefault(s => s.Modules.Contains(module));

        #endregion Tree

        #region Multi-selection and context menu

        private static TreeViewItem ItemFromEventSource(object source)
        {
            var current = source as DependencyObject;
            while (current != null && !(current is TreeViewItem))
                current = VisualTreeHelper.GetParent(current);
            return current as TreeViewItem;
        }

        private void OnTreeLeftButtonDown(object sender, MouseButtonEventArgs e)
        {
            if ((Keyboard.Modifiers & ModifierKeys.Control) == 0)
            {
                //plain click: drop the multi-selection, normal tree selection proceeds
                if (multiSelection.Count > 0)
                {
                    multiSelection.Clear();
                    RestyleAllItems();
                    UpdateStatusCounts(tree.Items.Count);
                }
                return;
            }

            TreeViewItem item = ItemFromEventSource(e.OriginalSource);
            if (item == null) return;

            if (!multiSelection.Remove(item.Tag))
                multiSelection.Add(item.Tag);
            UpdateItemHeader(item);
            UpdateStatusCounts(tree.Items.Count);
            e.Handled = true; //keep the native selection (and the edit panel) where it is
        }

        private void OnTreeRightButtonDown(object sender, MouseButtonEventArgs e)
        {
            //right-click selects the item under the cursor unless it is part of the multi-selection
            TreeViewItem item = ItemFromEventSource(e.OriginalSource);
            if (item == null) return;
            if (!multiSelection.Contains(item.Tag))
            {
                if (multiSelection.Count > 0)
                {
                    multiSelection.Clear();
                    RestyleAllItems();
                }
                item.IsSelected = true;
            }
        }

        private ContextMenu BuildContextMenu()
        {
            var menu = new ContextMenu();
            MenuItem MakeItem(string caption, Action action)
            {
                var menuItem = new MenuItem { Header = caption };
                menuItem.Click += (s, e) => action();
                return menuItem;
            }
            menu.Items.Add(MakeItem("Add Station", AddStation));
            menu.Items.Add(MakeItem("Add Module", AddModule));
            menu.Items.Add(new Separator());
            menu.Items.Add(MakeItem("Duplicate", DuplicateSelected));
            menu.Items.Add(MakeItem("Delete", DeleteSelected));
            return menu;
        }

        #endregion Multi-selection and context menu

        #region Edit panels

        /// <summary>Two-column label+input grid used by both edit panels.</summary>
        private static Grid BuildFieldGrid(IList<Tuple<string, FrameworkElement>> fields)
        {
            var grid = new Grid { Margin = new Thickness(6) };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto, MinWidth = 150 });
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
                MarkModified(station);
                RefreshSelectedItemStyle();
            }

            stationRoleBox.SelectionChanged += (s, e) => Apply(st => st.Role = stationRoleBox.SelectedItem as string ?? st.Role);
            stationNameBox.TextChanged += (s, e) => Apply(st => st.Name = stationNameBox.Text);
            stationGroupBox.TextChanged += (s, e) => Apply(st => st.Group = stationGroupBox.Text);
            WireEditableCombo(stationModelBox, () => Apply(st => { st.ModelId = stationModelBox.Text; ShowModelDetails(stationModelBox.Text, stationModelInfo, stationModelDefaults); }));
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
                MarkModified(module);
                RefreshSelectedItemStyle();
            }

            moduleSlotBox.TextChanged += (s, e) => Apply(m => m.Slot = moduleSlotBox.Text);
            moduleNameBox.TextChanged += (s, e) => Apply(m => m.Name = moduleNameBox.Text);
            WireEditableCombo(moduleModelBox, () => Apply(m => { m.ModelId = moduleModelBox.Text; ShowModelDetails(moduleModelBox.Text, moduleModelInfo, moduleModelDefaults); }));
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
                    stationGroupBox.Text = station.Group;
                    stationModelBox.Text = station.ModelId;
                    stationIpBox.Text = station.IpAddress;
                    stationPnBox.Text = station.PnNumber;
                    stationSubnetBox.Text = station.Subnet;
                    stationParamsBox.Text = station.CustomParameters;
                    ShowModelDetails(station.ModelId, stationModelInfo, stationModelDefaults);
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
                    ShowModelDetails(module.ModelId, moduleModelInfo, moduleModelDefaults);
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

        /// <summary>Info line (type - comment) and read-only model default parameters.</summary>
        private void ShowModelDetails(string modelId, TextBlock infoLine, TextBox defaultsBox)
        {
            ModelInfo info;
            if (document.Models.TryGetValue(modelId ?? "", out info))
            {
                infoLine.Text = info.DeviceType + " - " + info.Comment;
                defaultsBox.Text = info.DefaultParameters.Length > 0 ? info.DefaultParameters : "(none)";
            }
            else
            {
                infoLine.Text = "(model id not found in " + HardwareDeviceTypesDatabase.FileName + ")";
                defaultsBox.Text = "";
            }
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
            MarkModified(station);
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
            MarkModified(module);
            RebuildTree(module);
        }

        private void DuplicateSelected()
        {
            IList<object> selected = SelectedObjects();
            if (selected.Count == 0)
            {
                statusText.Text = "Select station(s) or module(s) to duplicate";
                return;
            }

            var selectedStations = selected.OfType<StationModel>().ToList();
            object lastCopy = null;

            foreach (StationModel station in selectedStations)
            {
                StationModel copy = station.Clone();
                copy.Name = HardwareConfigDocument.MakeUniqueName(station.Name, document.Stations.Select(s => s.Name));
                document.Stations.Insert(document.Stations.IndexOf(station) + 1, copy);
                MarkModified(copy);
                lastCopy = copy;
            }

            //modules whose station is duplicated as a whole are already covered
            foreach (ModuleModel module in selected.OfType<ModuleModel>())
            {
                StationModel owner = OwnerOf(module);
                if (owner == null || selectedStations.Contains(owner)) continue;

                ModuleModel copy = module.Clone();
                copy.Slot = HardwareConfigDocument.NextFreeSlot(owner);
                copy.Name = HardwareConfigDocument.MakeUniqueName(module.Name, owner.Modules.Select(m => m.Name));
                owner.Modules.Insert(owner.Modules.IndexOf(module) + 1, copy);
                MarkModified(copy);
                lastCopy = copy;
            }

            multiSelection.Clear();
            RebuildTree(lastCopy);
        }

        private void DeleteSelected()
        {
            IList<object> selected = SelectedObjects();
            if (selected.Count == 0) return;

            var stations = selected.OfType<StationModel>().ToList();
            var modules = selected.OfType<ModuleModel>()
                .Where(m => { StationModel owner = OwnerOf(m); return owner == null || !stations.Contains(owner); })
                .ToList();

            string question = stations.Count > 0 && modules.Count > 0
                ? "Delete " + stations.Count + " station(s) and " + modules.Count + " module(s)?"
                : stations.Count > 0
                    ? "Delete " + stations.Count + " station(s)" + (stations.Sum(s => s.Modules.Count) > 0 ? " including their " + stations.Sum(s => s.Modules.Count) + " module(s)?" : "?")
                    : "Delete " + modules.Count + " module(s)?";
            if (MessageBox.Show(this, question, "Delete", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes)
                return;

            foreach (ModuleModel module in modules)
            {
                StationModel owner = OwnerOf(module);
                if (owner == null) continue;
                owner.Modules.Remove(module);
                modifiedObjects.Remove(module);
                MarkModified(owner); //composition changed
            }
            foreach (StationModel station in stations)
            {
                document.Stations.Remove(station);
                modifiedObjects.Remove(station);
            }

            dirty = true;
            multiSelection.Clear();
            RebuildTree();
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
            modifiedObjects.Clear();
            RestyleAllItems();
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
            modifiedObjects.Clear();
            multiSelection.Clear();
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

        private void MarkModified(object model)
        {
            modifiedObjects.Add(model);
            dirty = true;
            UpdateStatusCounts(tree.Items.Count);
        }

        private void UpdateStatusCounts(int visibleStations)
        {
            string text = document.Stations.Count + " station(s), " + document.ModuleCount + " module(s)";
            if (visibleStations != document.Stations.Count)
                text += " - showing " + visibleStations;
            if (multiSelection.Count > 0)
                text += " - " + multiSelection.Count + " selected";
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

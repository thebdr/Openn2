using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;
using System.Windows.Media;

using Openn._00_Contract;
using Openn._03_ApiManager;
using Openn._10_StandardFunctions;
using static Openn._10_StandardFunctions.LogsManager;
using static Openn._10_StandardFunctions.StandardFunctions;

namespace Openn
{
    /// <summary>
    /// One catalog item as a row of the Workspace tab's grid: display strings, status colours and the
    /// outcome of the last import run. The grid groups rows by Owner (PLC folder) > Folder (TIA folder) > Group.
    /// </summary>
    public sealed class WorkspaceRow : INotifyPropertyChanged
    {
        public event PropertyChangedEventHandler PropertyChanged;

        public WorkspaceItem Item { get; }

        //grouping keys (+ ranks that put the workspace level first and the TIA folders in tree order)
        public string Owner { get; }
        public int OwnerRank { get; }
        public string Folder { get; }
        public int FolderRank { get; }
        public string Group { get; }

        public string Name { get; }
        public string RelativePath => Item.RelativePath;
        public string KindId { get; }
        public string StatusText => Item.Status.ToString();
        public string Action { get; }
        public string Producer { get; }
        public string Generated { get; }
        public string Run { get; }
        public string NotesText { get; }
        public string ToolTipText { get; }
        public Brush StatusBrush { get; }
        public Brush RowBackground { get; }
        public Brush RowForeground { get; }

        private string result = string.Empty;
        public string Result { get { return result; } private set { result = value; Notify("Result"); } }

        private Brush resultBrush = WorkspaceColors.Text;
        public Brush ResultBrush { get { return resultBrush; } private set { resultBrush = value; Notify("ResultBrush"); } }

        public WorkspaceRow(WorkspaceItem item)
        {
            Item = item;
            Name = Path.GetFileName(item.Path);
            KindId = item.KindInfo != null ? item.KindInfo.Id : (item.Status == ItemStatus.Ignored ? "-" : "?");
            Action = WorkspaceLabels.ActionOf(item);

            OpennHeader h = item.Header;
            bool headered = h != null && (h.Status == HeaderStatus.Ok || h.Status == HeaderStatus.Invalid);
            Producer = headered ? (h.Producer ?? string.Empty) : (h != null && h.Status == HeaderStatus.Legacy ? "(#!format=" + h.LegacyFormat + ")" : string.Empty);
            Generated = headered && h.Generated != null ? h.Generated.Value.ToUniversalTime().ToString("yyyy-MM-dd HH:mm'Z'") : (headered ? (h.Get("generated") ?? string.Empty) : string.Empty);
            Run = headered ? (h.Run ?? string.Empty) : string.Empty;
            NotesText = string.Join("; ", item.Notes);

            bool ignoredNonObject = item.Status == ItemStatus.Ignored && item.Kind == InputKind.Unknown;
            if (ignoredNonObject)
            {
                Owner = "(workspace files)";
                OwnerRank = 9;
                Folder = "(not a TIA object: config, sidecars, temporary files)";
                FolderRank = 9;
                Group = string.Empty;
            }
            else
            {
                bool workspaceLevel = item.Plc == null &&
                    (item.Category == WorkspaceLayout.HardwareFolder || item.Category == WorkspaceLayout.TemplatesFolder || item.Category.Length == 0);
                Owner = item.Plc ?? (workspaceLevel ? "<workspace>" : "<default PLC>");
                OwnerRank = workspaceLevel ? 0 : 1;
                Folder = item.Category.Length > 0 ? item.Category : "(misplaced)";
                FolderRank = WorkspaceLabels.FolderRank(item.Category);
                Group = item.GroupPath.Length > 0 ? item.GroupPath : "(root)";
            }

            StatusBrush = WorkspaceColors.ForStatus(item.Status);
            bool rejected = item.Status != ItemStatus.Ready && item.Status != ItemStatus.Ignored; //everything that is not imported is tinted
            RowBackground = rejected ? WorkspaceColors.RedTint : Brushes.Transparent;
            RowForeground = item.Status == ItemStatus.Ignored ? WorkspaceColors.Grey : WorkspaceColors.Text;
            ToolTipText = WorkspaceLabels.Describe(item, null);
        }

        public void SetResult(WorkspaceImportResult r)
        {
            Result = r.Outcome + ": " + r.Message;
            ResultBrush = WorkspaceColors.ForOutcome(r.Outcome);
        }

        private void Notify(string name)
        {
            PropertyChangedEventHandler handler = PropertyChanged;
            if (handler != null) handler(this, new PropertyChangedEventArgs(name));
        }
    }

    /// <summary>The Workspace tab's colour code: Ready green, Legacy / NeedsHeader amber, Invalid / Stale / Unclassified red, Ignored grey.</summary>
    public static class WorkspaceColors
    {
        public static readonly Brush Green = Frozen(0x1E, 0x6E, 0x1E);
        public static readonly Brush Amber = Frozen(0xB2, 0x6B, 0x00);
        public static readonly Brush Red = Frozen(0xB0, 0x00, 0x00);
        public static readonly Brush Grey = Frozen(0x8A, 0x8A, 0x8A);
        public static readonly Brush Blue = Frozen(0x1F, 0x4E, 0x79);
        public static readonly Brush Text = Frozen(0x20, 0x20, 0x20);
        public static readonly Brush GreenTint = Frozen(0xEE, 0xF7, 0xEE);
        public static readonly Brush AmberTint = Frozen(0xFF, 0xF6, 0xE5);
        public static readonly Brush RedTint = Frozen(0xFF, 0xF1, 0xF1);
        public static readonly Brush GreyTint = Frozen(0xF0, 0xF0, 0xF2);
        public static readonly Brush BlueTint = Frozen(0xEE, 0xF3, 0xFA);

        public static Brush ForStatus(ItemStatus status)
        {
            switch (status)
            {
                case ItemStatus.Ready: return Green;
                case ItemStatus.Legacy:
                case ItemStatus.NeedsHeader: return Amber;
                case ItemStatus.Ignored: return Grey;
                default: return Red; //Invalid, Stale, Unclassified
            }
        }

        public static Brush TintForStatus(ItemStatus status)
        {
            switch (status)
            {
                case ItemStatus.Ready: return GreenTint;
                case ItemStatus.Legacy:
                case ItemStatus.NeedsHeader: return AmberTint;
                case ItemStatus.Ignored: return GreyTint;
                default: return RedTint;
            }
        }

        public static Brush ForOutcome(WorkspaceImportOutcome outcome)
        {
            switch (outcome)
            {
                case WorkspaceImportOutcome.Imported: return Green;
                case WorkspaceImportOutcome.NothingToDo: return Grey;
                case WorkspaceImportOutcome.Skipped: return Amber;
                case WorkspaceImportOutcome.Cancelled: return Grey;
                default: return Red;
            }
        }

        private static Brush Frozen(byte r, byte g, byte b)
        {
            var brush = new SolidColorBrush(Color.FromRgb(r, g, b));
            brush.Freeze();
            return brush;
        }
    }

    /// <summary>Human-readable texts for catalog items (grid cells, tooltips, the detail pane).</summary>
    public static class WorkspaceLabels
    {
        public static string ActionOf(WorkspaceItem item)
        {
            if (item.KindInfo == null) return item.Status == ItemStatus.Ignored ? "-" : "not imported";
            string route = RouteLabel(item.KindInfo.Route);
            return item.Importable || item.KindInfo.Route == ImportRoute.Template || item.KindInfo.Route == ImportRoute.None
                ? route
                : "not imported (" + route + ")";
        }

        public static string RouteLabel(ImportRoute route)
        {
            switch (route)
            {
                case ImportRoute.HardwareGeneration: return "generate hardware (folder)";
                case ImportRoute.Reference: return "reference (hardware)";
                case ImportRoute.ImportTypeXml: return "import UDT";
                case ImportRoute.ImportTagTableXml: return "import tag table";
                case ImportRoute.ImportBlockXml: return "import block";
                case ImportRoute.GenerateThenImport: return "generate + import block";
                case ImportRoute.CreateInstanceDbs: return "create instance DBs";
                case ImportRoute.GenerateFromSource: return "compile source";
                case ImportRoute.Template: return "template (never imported)";
                default: return "listed only";
            }
        }

        public static string RouteDetail(ImportRoute route)
        {
            switch (route)
            {
                case ImportRoute.HardwareGeneration: return "HardwareConfigLoader.LoadAll(folder) + CreateDevices - stations already in TIA are skipped with their modules";
                case ImportRoute.Reference: return "read by the hardware generation of its folder (DeviceTypesDatabase)";
                case ImportRoute.ImportTypeXml: return "TypeGroup.Types.Import (Override), into the type group of the file's folder";
                case ImportRoute.ImportTagTableXml: return "TagTableGroup.TagTables.Import (Override), into the tag group of the file's folder";
                case ImportRoute.ImportBlockXml: return "Blocks.Import (Override), into the block group of the file's folder";
                case ImportRoute.GenerateThenImport: return "BlockXmlGenerator.Generate, then Blocks.Import (Override) into the block group of the file's folder";
                case ImportRoute.CreateInstanceDbs: return "CreateInstanceDB per csv row (Folder column relative to the file's folder); name clashes prompt Retry/Abort/Ignore";
                case ImportRoute.GenerateFromSource: return "ExternalSources.CreateFromFile + GenerateBlocksFromSource - blocks land in the Program blocks root";
                case ImportRoute.Template: return "referenced by block-gen csvs through template=, never imported by itself";
                default: return "documentation - listed, never imported";
            }
        }

        public static string StatusExplanation(ItemStatus status)
        {
            switch (status)
            {
                case ItemStatus.Ready: return "valid #!openn header, placement consistent - importable";
                case ItemStatus.Legacy: return "recognized by legacy markers only (format tag, csv markers, XML root) - NOT imported: the #!openn header is required (legacy acceptance retired 2026-10-09)";
                case ItemStatus.NeedsHeader: return "classified by extension / location only, no header - NOT imported: the #!openn header is required";
                case ItemStatus.Invalid: return "header invalid, or contradicting the file's location - NOT imported";
                case ItemStatus.Stale: return "its run differs from the workspace run - leftover of an older generation - NOT imported";
                case ItemStatus.Unclassified: return "nothing recognizable in header, name, extension or content - NOT imported";
                default: return "listed, never imported (workspace config, sidecar, temporary file, documentation)";
            }
        }

        /// <summary>TIA tree order of the folders, for the grid's group sort.</summary>
        public static int FolderRank(string category)
        {
            if (category == WorkspaceLayout.HardwareFolder) return 0;
            if (category == WorkspaceLayout.TemplatesFolder) return 1;
            if (category == WorkspaceLayout.PlcDataTypes) return 2;
            if (category == WorkspaceLayout.PlcTags) return 3;
            if (category == WorkspaceLayout.ProgramBlocks) return 4;
            return category.Length == 0 ? 9 : 5;
        }

        /// <summary>The full description of an item (tooltip and detail pane); lastResult may be null.</summary>
        public static string Describe(WorkspaceItem item, string lastResult)
        {
            var sb = new StringBuilder();
            sb.AppendLine(item.RelativePath);

            InputKindInfo kind = item.KindInfo;
            sb.AppendLine("Kind:       " + (kind != null ? kind.Id + " - " + kind.Title + "  (" + kind.Description + ")" : "unknown"));
            sb.AppendLine("Status:     " + item.Status + " - " + StatusExplanation(item.Status));
            if (kind != null)
                sb.AppendLine("Route:      " + RouteLabel(kind.Route) + " - " + RouteDetail(kind.Route) + "  [import order " + kind.ImportOrder + "]");
            sb.AppendLine("Placement:  " + item.Placement +
                          (item.LegacyPlacement ? "  (legacy BuilderData folder mapped onto the TIA tree)" : string.Empty) +
                          (item.Misplaced ? "  (no usable TIA target)" : string.Empty));

            OpennHeader h = item.Header;
            if (h == null || h.Status == HeaderStatus.Missing)
                sb.AppendLine("Header:     none");
            else if (h.Status == HeaderStatus.Legacy)
                sb.AppendLine("Header:     legacy #!format=" + h.LegacyFormat + " tag only");
            else
            {
                sb.AppendLine("Header:     " + h.Status);
                foreach (string key in h.Keys)
                    sb.AppendLine("            " + key + ": " + h.Get(key));
            }

            if (item.Notes.Count > 0)
            {
                sb.AppendLine("Notes:");
                foreach (string note in item.Notes) sb.AppendLine("  - " + note);
            }
            if (!string.IsNullOrEmpty(lastResult)) sb.AppendLine("Last run:   " + lastResult);
            sb.Append("Full path:  " + item.Path);
            return sb.ToString();
        }
    }

    /// <summary>
    /// The Workspace tab: the catalog of a handoff workspace (WorkspaceCatalog) as a grouped grid, with the
    /// workspace root picker, the summary strip and the catalog-driven import actions. The import itself
    /// runs on the TiaWorker (TiaPortalOpenness.ImportWorkspaceItems); this file only reads control values
    /// before queuing and renders the results afterwards.
    /// </summary>
    public partial class MainWindow
    {
        private WorkspaceCatalog workspaceCatalog;

        /// <summary>The rows of the last scan (the grid shows a grouped ListCollectionView over this list).</summary>
        private List<WorkspaceRow> workspaceRows = new List<WorkspaceRow>();

        /// <summary>The Hardware tab's csv folder tracks the workspace's hardware folder until the user edits it.</summary>
        private bool hardwarePathFollowsWorkspace = true;
        private bool settingHardwarePath;

        private void InitializeWorkspaceTab()
        {
            string remembered = null;
            try { remembered = Properties.Settings.Default.WorkspaceRoot; }
            catch (Exception e) { Log("Could not read the user settings \n" + e.Message); }
            tbWorkspaceRoot.Text = string.IsNullOrWhiteSpace(remembered) ? AppPaths.BuilderDataDir : remembered;
            rbWsUseExistingControllers.IsChecked = true;

            ShowWorkspaceRows(new List<WorkspaceRow>());
            tbHardwareCsvPath.TextChanged += (s, e) => { if (!settingHardwarePath) hardwarePathFollowsWorkspace = false; };
            UpdateWorkspaceSelectionInfo();
        }

        /// <summary>
        /// Shows the rows grouped Owner > Folder > Group and sorted in TIA tree order. A fresh view per scan:
        /// WPF forbids changing a collection while its view's refresh is deferred, and regrouping row by row
        /// is pointless when the whole catalog changes at once.
        /// </summary>
        private void ShowWorkspaceRows(List<WorkspaceRow> rows)
        {
            workspaceRows = rows;
            var view = new ListCollectionView(rows);
            view.GroupDescriptions.Add(new PropertyGroupDescription("Owner"));
            view.GroupDescriptions.Add(new PropertyGroupDescription("Folder"));
            view.GroupDescriptions.Add(new PropertyGroupDescription("Group"));
            view.SortDescriptions.Add(new SortDescription("OwnerRank", ListSortDirection.Ascending));
            view.SortDescriptions.Add(new SortDescription("Owner", ListSortDirection.Ascending));
            view.SortDescriptions.Add(new SortDescription("FolderRank", ListSortDirection.Ascending));
            view.SortDescriptions.Add(new SortDescription("Folder", ListSortDirection.Ascending));
            view.SortDescriptions.Add(new SortDescription("Group", ListSortDirection.Ascending));
            view.SortDescriptions.Add(new SortDescription("Name", ListSortDirection.Ascending));
            lvWorkspace.ItemsSource = view;
        }

        #region Scan

        /// <summary>Scans the workspace root (Siemens-free, on the worker so it queues behind a running operation) and rebuilds the grid.</summary>
        private async Task RescanWorkspaceAsync(bool quietWhenBusy = false)
        {
            string root = tbWorkspaceRoot.Text.Trim();
            if (root.Length == 0)
            {
                root = AppPaths.BuilderDataDir;
                tbWorkspaceRoot.Text = root;
            }
            RememberWorkspaceRoot(root);
            runExportRoot.Text = AppPaths.ExportRootFor(root);

            WorkspaceCatalog catalog = null;
            await RunBackend(() => TiaWorker.Run(() => { catalog = WorkspaceCatalog.Scan(root); }), quietWhenBusy);
            if (catalog == null) return; //busy, or failed (logged by RunBackend)

            workspaceCatalog = catalog;
            PopulateWorkspaceRows(catalog);
            UpdateWorkspaceSummary(catalog);
            UpdateWorkspaceSelectionInfo();
            FollowWorkspaceHardwareFolder(catalog);

            if (!catalog.Exists)
            {
                Log("Workspace folder not found: " + catalog.Root);
                return;
            }
            Log("Workspace scanned: " + catalog.Root + " - " + Totals(catalog));
        }

        private void PopulateWorkspaceRows(WorkspaceCatalog catalog)
        {
            ShowWorkspaceRows(catalog.Items.Select(item => new WorkspaceRow(item)).ToList());
            tbWorkspaceDetail.Text = !catalog.Exists ? "Folder not found: " + catalog.Root
                : catalog.Items.Count == 0 ? "The workspace is empty."
                : "Select a row to see its header, placement and notes. Hover a row for the same text.";
        }

        private static string Totals(WorkspaceCatalog c)
        {
            int classified = c.Items.Count(i => i.Status != ItemStatus.Ignored && i.Kind != InputKind.Unknown);
            return c.Items.Count + " file(s): " + classified + " classified, " +
                   c.Items.Count(i => i.Status == ItemStatus.Unclassified) + " unclassified, " +
                   c.Items.Count(i => i.Status == ItemStatus.Ignored) + " ignored; " +
                   c.InImportOrder().Count() + " importable; layout " + (c.LegacyLayout ? "legacy BuilderData folders" : "VCI shape") +
                   "; config " + (c.Config == null ? "missing" : c.Config.Status.ToString().ToLowerInvariant());
        }

        /// <summary>The summary strip: layout, workspace config, totals and one chip per kind (WorkspaceCatalog.Summary semantics).</summary>
        private void UpdateWorkspaceSummary(WorkspaceCatalog catalog)
        {
            wpWorkspaceSummary.Children.Clear();
            if (!catalog.Exists)
            {
                AddSummaryChip("folder not found", "The workspace root does not exist: " + catalog.Root, WorkspaceColors.Red, WorkspaceColors.RedTint, true);
                return;
            }

            AddSummaryChip("layout: " + (catalog.LegacyLayout ? "legacy BuilderData folders - not importable" : "VCI shape"),
                catalog.LegacyLayout
                    ? "HardwareConfiguration, SoftwareBlocks\\CreationInfo|ImportReady, PlcTags, UserDataTypes, DataBlocks: the pre-contract layout. Openn5 reads only the VCI shape (<PLC>/Program blocks | PLC tags | PLC data types + Devices & networks + Templates) - regenerate the workspace with Pipeline5 5.0+."
                    : "<PLC>/Program blocks | PLC tags | PLC data types + Devices & networks + Templates at the root",
                catalog.LegacyLayout ? WorkspaceColors.Red : WorkspaceColors.Green,
                catalog.LegacyLayout ? WorkspaceColors.RedTint : WorkspaceColors.GreenTint);

            OpennHeader cfg = catalog.Config;
            if (cfg == null)
                AddSummaryChip("config: missing", WorkspaceLayout.ConfigFolder + "\\" + WorkspaceLayout.ConfigFile + " is absent - no run id, so stale files cannot be detected",
                    WorkspaceColors.Amber, WorkspaceColors.AmberTint);
            else
            {
                string text = "config: " + cfg.Status.ToString().ToLowerInvariant() +
                              (cfg.Contract != null ? ", contract " + cfg.Contract : string.Empty) +
                              (cfg.Project != null ? ", project " + cfg.Project : string.Empty) +
                              (cfg.Run != null ? ", run " + cfg.Run : string.Empty);
                string tip = string.Join("\n", cfg.Keys.Select(k => k + ": " + cfg.Get(k))) +
                             (cfg.Problems.Count > 0 ? "\n\nProblems:\n" + string.Join("\n", cfg.Problems) : string.Empty);
                bool ok = cfg.Status == HeaderStatus.Ok;
                AddSummaryChip(text, tip, ok ? WorkspaceColors.Green : WorkspaceColors.Red, ok ? WorkspaceColors.GreenTint : WorkspaceColors.RedTint);
            }

            AddSummaryChip(Totals(catalog).Split(';')[0] + "; " + catalog.InImportOrder().Count() + " importable",
                "classified = a kind was recognized (header or legacy markers); importable = Ready (valid #!openn header, consistent placement, current run) with an import route",
                WorkspaceColors.Blue, WorkspaceColors.BlueTint, true);

            var classified = catalog.Items.Where(i => i.Status != ItemStatus.Ignored && i.Kind != InputKind.Unknown).ToList();
            foreach (var group in classified.GroupBy(i => i.KindInfo).OrderBy(g => g.Key.ImportOrder))
            {
                int ready = group.Count(i => i.Status == ItemStatus.Ready), legacy = group.Count(i => i.Status == ItemStatus.Legacy),
                    needs = group.Count(i => i.Status == ItemStatus.NeedsHeader), invalid = group.Count(i => i.Status == ItemStatus.Invalid),
                    stale = group.Count(i => i.Status == ItemStatus.Stale);
                ItemStatus worst = invalid + stale > 0 ? ItemStatus.Invalid : legacy + needs > 0 ? ItemStatus.Legacy : ItemStatus.Ready;
                string breakdown = "ready " + ready + ", legacy " + legacy + ", needs-header " + needs + ", invalid " + invalid + ", stale " + stale;
                AddSummaryChip(group.Key.Id + "  " + group.Count(), group.Key.Title + " - " + group.Count() + " file(s): " + breakdown +
                    "\n" + WorkspaceLabels.RouteLabel(group.Key.Route) + " (import order " + group.Key.ImportOrder + ")",
                    WorkspaceColors.ForStatus(worst), WorkspaceColors.TintForStatus(worst));
            }

            int attention = catalog.Items.Count(i => i.Status == ItemStatus.Invalid || i.Status == ItemStatus.Stale || i.Status == ItemStatus.Unclassified);
            if (attention > 0)
                AddSummaryChip("needs attention: " + attention, "Invalid / Stale / Unclassified files - listed red below, never imported; the notes say why",
                    WorkspaceColors.Red, WorkspaceColors.RedTint, true);
            int unheadered = catalog.Items.Count(i => i.Status == ItemStatus.Legacy || i.Status == ItemStatus.NeedsHeader);
            if (unheadered > 0)
                AddSummaryChip("without #!openn header: " + unheadered + " - not imported",
                    "Recognized by legacy markers or extension only. Contract v1 requires the #!openn header (legacy acceptance retired 2026-10-09): regenerate with Pipeline5 5.0+, or add the header by hand",
                    WorkspaceColors.Red, WorkspaceColors.RedTint);
        }

        private void AddSummaryChip(string text, string tooltip, Brush color, Brush tint, bool bold = false)
        {
            var border = new Border
            {
                BorderBrush = color,
                Background = tint,
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(3),
                Padding = new Thickness(6, 1, 6, 1),
                Margin = new Thickness(0, 1, 6, 1),
                ToolTip = tooltip,
                Child = new TextBlock { Text = text, Foreground = color, FontSize = 11, FontWeight = bold ? FontWeights.SemiBold : FontWeights.Normal },
            };
            ToolTipService.SetShowDuration(border, 60000);
            wpWorkspaceSummary.Children.Add(border);
        }

        /// <summary>Points the Files tab's hardware csv folder at the workspace's hardware folder when there is exactly one (until the user edits that box).</summary>
        private void FollowWorkspaceHardwareFolder(WorkspaceCatalog catalog)
        {
            if (!hardwarePathFollowsWorkspace || !catalog.Exists) return;
            List<string> folders = catalog.Items
                .Where(i => (i.Kind == InputKind.HwStations || i.Kind == InputKind.HwModules) && i.Status != ItemStatus.Ignored)
                .Select(i => Path.GetDirectoryName(i.Path))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();
            if (folders.Count != 1 || string.Equals(tbHardwareCsvPath.Text, folders[0], StringComparison.OrdinalIgnoreCase)) return;

            settingHardwarePath = true;
            try { tbHardwareCsvPath.Text = folders[0]; }
            finally { settingHardwarePath = false; }
            Log("Files tab: the hardware csv folder follows the workspace -> " + folders[0]);
        }

        /// <summary>Remembers the root in the user settings; the default root is stored as "" so it keeps following the exe location.</summary>
        private void RememberWorkspaceRoot(string root)
        {
            string value = string.Equals(root, AppPaths.BuilderDataDir, StringComparison.OrdinalIgnoreCase) ? string.Empty : root;
            try
            {
                if (Properties.Settings.Default.WorkspaceRoot == value) return;
                Properties.Settings.Default.WorkspaceRoot = value;
                Properties.Settings.Default.Save();
            }
            catch (Exception e)
            {
                Log("Could not save the workspace root to the user settings \n" + e.Message);
            }
        }

        private void LogWorkspaceCatalog()
        {
            WorkspaceCatalog catalog = workspaceCatalog;
            if (catalog == null)
            {
                Log("No workspace scanned yet");
                return;
            }
            foreach (string line in catalog.Summary()) Log(line);
        }

        #endregion Scan

        #region Import

        private IList<WorkspaceItem> SelectedWorkspaceItems() =>
            lvWorkspace.SelectedItems.OfType<WorkspaceRow>().Select(r => r.Item).ToList();

        /// <summary>Runs the catalog-driven import for the given items (the worker sorts them into import order).</summary>
        private async Task ImportWorkspaceAsync(IList<WorkspaceItem> items, string what)
        {
            WorkspaceCatalog catalog = workspaceCatalog;
            if (catalog == null)
            {
                Log("Scan a workspace first");
                return;
            }
            if (items.Count == 0)
            {
                Log("Workspace import: nothing to import (" + what + ")");
                return;
            }
            if (!IsProjectAttached)
            {
                Log("Can't import: attach a TIA project first");
                return;
            }
            int importable = items.Count(i => i.Importable);
            if (importable == 0)
            {
                Log("Workspace import: none of the " + items.Count + " item(s) (" + what + ") is importable - only Ready rows (valid #!openn header, consistent placement, current run) are imported, see the notes");
                return;
            }

            bool createNew = rbWsCreateNewControllers.IsChecked == true;
            IList<WorkspaceImportResult> results = null;
            await RunBackend(() => TiaWorker.Run(() => { results = tia.ImportWorkspaceItems(catalog, items, createNew); }));
            if (results == null) return;

            var byItem = new Dictionary<WorkspaceItem, WorkspaceImportResult>();
            foreach (WorkspaceImportResult r in results) byItem[r.Item] = r;
            foreach (WorkspaceRow row in workspaceRows)
            {
                WorkspaceImportResult r;
                if (byItem.TryGetValue(row.Item, out r)) row.SetResult(r);
            }
            WorkspaceRow selected = LastSelectedRow();
            if (selected != null) tbWorkspaceDetail.Text = WorkspaceLabels.Describe(selected.Item, selected.Result);
        }

        #endregion Import

        #region Buttons & controls

        private async void btnWsRescan_Click(object sender, RoutedEventArgs e) => await RescanWorkspaceAsync();

        private async void tbWorkspaceRoot_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.Key != Key.Enter) return;
            e.Handled = true;
            await RescanWorkspaceAsync();
        }

        private async void btnWsBrowse_Click(object sender, RoutedEventArgs e)
        {
            string start = Directory.Exists(tbWorkspaceRoot.Text) ? tbWorkspaceRoot.Text : AppPaths.SharedRoot;
            var path = GetFolderDialog(start);
            if (path == null) return;
            tbWorkspaceRoot.Text = path.FullName;
            await RescanWorkspaceAsync();
        }

        private async void btnWsDefault_Click(object sender, RoutedEventArgs e)
        {
            tbWorkspaceRoot.Text = AppPaths.BuilderDataDir;
            await RescanWorkspaceAsync();
        }

        private void btnWsLogCatalog_Click(object sender, RoutedEventArgs e) => LogWorkspaceCatalog();

        private async void btnWsImportSelected_Click(object sender, RoutedEventArgs e) =>
            await ImportWorkspaceAsync(SelectedWorkspaceItems(), "selected rows");

        private async void btnWsImportAll_Click(object sender, RoutedEventArgs e)
        {
            WorkspaceCatalog catalog = workspaceCatalog;
            IList<WorkspaceItem> all = catalog != null ? catalog.InImportOrder().ToList() : new List<WorkspaceItem>();
            await ImportWorkspaceAsync(all, "all importable");
        }

        private void lvWorkspace_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            UpdateWorkspaceSelectionInfo();
            WorkspaceRow row = LastSelectedRow();
            if (row != null) tbWorkspaceDetail.Text = WorkspaceLabels.Describe(row.Item, row.Result);
        }

        private void lvWorkspace_RowDoubleClick(object sender, MouseButtonEventArgs e)
        {
            var row = (sender as ListViewItem)?.Content as WorkspaceRow;
            if (row != null) LogRowDetails(row);
        }

        private void miWsLogDetails_Click(object sender, RoutedEventArgs e)
        {
            foreach (WorkspaceRow row in lvWorkspace.SelectedItems.OfType<WorkspaceRow>().ToList())
                LogRowDetails(row);
        }

        private void miWsOpenFolder_Click(object sender, RoutedEventArgs e)
        {
            WorkspaceRow row = LastSelectedRow();
            if (row == null) return;
            try { Process.Start("explorer.exe", "/select,\"" + row.Item.Path + "\""); }
            catch (Exception ex) { Log("Could not open the folder \n" + ex.Message); }
        }

        private void miWsCopyPath_Click(object sender, RoutedEventArgs e)
        {
            var rows = lvWorkspace.SelectedItems.OfType<WorkspaceRow>().ToList();
            if (rows.Count == 0) return;
            try { Clipboard.SetText(string.Join(Environment.NewLine, rows.Select(r => r.Item.Path))); }
            catch (Exception ex) { Log("Could not copy to clipboard \n" + ex.Message); }
        }

        private WorkspaceRow LastSelectedRow() =>
            lvWorkspace.SelectedItems.Count > 0 ? lvWorkspace.SelectedItems[lvWorkspace.SelectedItems.Count - 1] as WorkspaceRow : null;

        private static void LogRowDetails(WorkspaceRow row)
        {
            foreach (string line in WorkspaceLabels.Describe(row.Item, row.Result).Split('\n'))
                Log("  " + line.TrimEnd('\r'));
        }

        private void UpdateWorkspaceSelectionInfo()
        {
            int selected = lvWorkspace.SelectedItems.Count;
            int importable = lvWorkspace.SelectedItems.OfType<WorkspaceRow>().Count(r => r.Item.Importable);
            tbWsSelection.Text = selected == 0 ? "no row selected" : selected + " selected, " + importable + " importable";
        }

        #endregion Buttons & controls
    }
}

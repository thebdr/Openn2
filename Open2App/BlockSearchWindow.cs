using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;

using Openn._03_ApiManager;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn
{
    /// <summary>
    /// Search-as-you-type browser over all program blocks of the attached project
    /// (subfolders included). The pattern is a case-insensitive regex matched against
    /// the "[Type] Folder/Name" display text. Selected blocks (multi-select) are
    /// exported on the backend worker thread; the window stays usable in between.
    /// Talks to the TIA layer only through the two delegates, so the window itself
    /// is free of Siemens dependencies.
    /// </summary>
    public class BlockSearchWindow : Window
    {
        private readonly Func<IList<PlcBlockInfo>> readBlocks;
        private readonly Action<string> exportBlock;

        private readonly TextBox searchBox;
        private readonly ListBox resultsList;
        private readonly TextBlock statusText;
        private readonly Button refreshButton;
        private readonly Button exportButton;

        private IList<PlcBlockInfo> allBlocks = new List<PlcBlockInfo>();

        public BlockSearchWindow(Func<IList<PlcBlockInfo>> readBlocks, Action<string> exportBlock)
        {
            this.readBlocks = readBlocks;
            this.exportBlock = exportBlock;

            Title = "Openn2 - Search / Export Blocks";
            Width = 640;
            Height = 520;
            MinWidth = 420;
            MinHeight = 300;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;

            var searchLabel = new TextBlock
            {
                Text = "Search (regex, case-insensitive, matches \"[Type] Folder/Name\"):",
                FontSize = 11,
                Margin = new Thickness(0, 0, 0, 2),
            };

            searchBox = new TextBox { FontSize = 13, Margin = new Thickness(0, 0, 0, 6) };
            searchBox.TextChanged += (s, e) => ApplyFilter();

            resultsList = new ListBox { SelectionMode = SelectionMode.Extended };
            resultsList.MouseDoubleClick += async (s, e) => await ExportSelectedAsync();

            statusText = new TextBlock { VerticalAlignment = VerticalAlignment.Center };

            refreshButton = new Button { Content = "Refresh", Width = 80, Margin = new Thickness(8, 0, 0, 0) };
            refreshButton.Click += async (s, e) => await RefreshAsync();

            exportButton = new Button { Content = "Export Selected", Width = 110, Margin = new Thickness(8, 0, 0, 0) };
            exportButton.Click += async (s, e) => await ExportSelectedAsync();

            var bottomRow = new DockPanel { Margin = new Thickness(0, 8, 0, 0) };
            DockPanel.SetDock(exportButton, Dock.Right);
            DockPanel.SetDock(refreshButton, Dock.Right);
            bottomRow.Children.Add(exportButton);
            bottomRow.Children.Add(refreshButton);
            bottomRow.Children.Add(statusText);

            var layout = new DockPanel { Margin = new Thickness(10) };
            DockPanel.SetDock(searchLabel, Dock.Top);
            DockPanel.SetDock(searchBox, Dock.Top);
            DockPanel.SetDock(bottomRow, Dock.Bottom);
            layout.Children.Add(searchLabel);
            layout.Children.Add(searchBox);
            layout.Children.Add(bottomRow);
            layout.Children.Add(resultsList);
            Content = layout;

            Loaded += async (s, e) =>
            {
                searchBox.Focus();
                await RefreshAsync();
            };
        }

        /// <summary>
        /// Case-insensitive regex filter over the block display texts.
        /// Returns null when the pattern is invalid (patternError holds the reason).
        /// </summary>
        public static IList<PlcBlockInfo> Filter(IEnumerable<PlcBlockInfo> blocks, string pattern, out string patternError)
        {
            patternError = null;
            if (string.IsNullOrWhiteSpace(pattern))
                return blocks.ToList();

            Regex regex;
            try
            {
                regex = new Regex(pattern, RegexOptions.IgnoreCase);
            }
            catch (ArgumentException e)
            {
                patternError = e.Message;
                return null;
            }

            return blocks.Where(b => regex.IsMatch(b.DisplayText)).ToList();
        }

        private void ApplyFilter()
        {
            string patternError;
            IList<PlcBlockInfo> matches = Filter(allBlocks, searchBox.Text, out patternError);
            if (matches == null)
            {
                //keep showing the previous matches while an incomplete pattern is being typed
                statusText.Text = "Invalid regex: " + patternError;
                return;
            }

            resultsList.ItemsSource = matches;
            statusText.Text = matches.Count + " / " + allBlocks.Count + " blocks";
        }

        private async Task RefreshAsync()
        {
            SetBusy(true, "Reading blocks from the Tia project...");
            try
            {
                allBlocks = await TiaWorker.Run(readBlocks);
            }
            catch (Exception e)
            {
                Log("ERROR reading blocks \n" + e.Message);
                allBlocks = new List<PlcBlockInfo>();
            }
            SetBusy(false, null);
            ApplyFilter();
        }

        private async Task ExportSelectedAsync()
        {
            var selected = resultsList.SelectedItems.Cast<PlcBlockInfo>().ToList();
            if (selected.Count == 0)
            {
                statusText.Text = "Select one or more blocks to export";
                return;
            }

            SetBusy(true, "Exporting " + selected.Count + " block(s)...");
            try
            {
                await TiaWorker.Run(() =>
                {
                    foreach (PlcBlockInfo block in selected)
                        exportBlock(block.Name);
                });
                SetBusy(false, "Exported " + selected.Count + " block(s) - details in the main log");
            }
            catch (Exception e)
            {
                Log("ERROR exporting blocks \n" + e.Message);
                SetBusy(false, "Export failed - see the main log");
            }
        }

        private void SetBusy(bool busy, string message)
        {
            refreshButton.IsEnabled = !busy;
            exportButton.IsEnabled = !busy;
            resultsList.IsEnabled = !busy;
            if (message != null) statusText.Text = message;
        }
    }
}

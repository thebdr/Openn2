using System;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

using static Openn._10_StandardFunctions.LogsManager;

namespace Openn
{
    /// <summary>
    /// The log in its own window: a second view of the same session log (seeded with the whole history when it
    /// opens, fed live afterwards) with its own regex filter, copy and clear, and a keep-on-top toggle. Meant for
    /// a second monitor, or for reading a long run while the main window's small log area stays small. Not owned
    /// by the main window, so the two order freely (pin it with "Keep on top"); it closes with the main window.
    /// Placement and the keep-on-top state are remembered (Properties.Settings). Siemens-free.
    /// </summary>
    public class LogWindow : Window
    {
        private const double DefaultWidth = 960;
        private const double DefaultHeight = 520;

        private static readonly Brush InvalidPatternBrush = new SolidColorBrush(Color.FromRgb(0xFF, 0xDC, 0xDC));

        private readonly ListView logView;
        private readonly TextBox filterBox;
        private readonly CheckBox topmostBox;

        /// <param name="placeNear">The main window: a first-time popup opens centered on its screen.</param>
        public LogWindow(Window placeNear)
        {
            Title = "Openn5 - Log";
            MinWidth = 480;
            MinHeight = 200;
            Background = new SolidColorBrush(Color.FromRgb(0xF4, 0xF4, 0xF6));

            //toolbar: title, filter (fills the rest), keep-on-top, copy all, clear
            var toolbar = new DockPanel { Margin = new Thickness(6, 2, 6, 2) };

            var title = new Label { Content = "Log", FontWeight = FontWeights.SemiBold, VerticalAlignment = VerticalAlignment.Center };
            DockPanel.SetDock(title, Dock.Left);
            toolbar.Children.Add(title);

            Button clearButton = ToolbarButton("Clear Logs", "Empties the log here and in the main window");
            clearButton.Background = new SolidColorBrush(Color.FromRgb(0xAD, 0xFF, 0xF9));
            clearButton.Click += (s, e) => ClearLog();
            DockPanel.SetDock(clearButton, Dock.Right);
            toolbar.Children.Add(clearButton);

            Button copyButton = ToolbarButton("Copy all", "Copies every log line to the clipboard (the filter does not apply)");
            copyButton.Margin = new Thickness(0, 0, 8, 0);
            copyButton.Click += (s, e) => CopyLines(logView, selectedOnly: false);
            DockPanel.SetDock(copyButton, Dock.Right);
            toolbar.Children.Add(copyButton);

            topmostBox = new CheckBox
            {
                Content = "Keep on top",
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(0, 0, 12, 0),
                ToolTip = "Keep this window above every other window (TIA Portal included)",
            };
            topmostBox.Checked += (s, e) => ApplyTopmost();
            topmostBox.Unchecked += (s, e) => ApplyTopmost();
            DockPanel.SetDock(topmostBox, Dock.Right);
            toolbar.Children.Add(topmostBox);

            filterBox = new TextBox
            {
                Height = 24,
                VerticalContentAlignment = VerticalAlignment.Center,
                Margin = new Thickness(8, 0, 12, 0),
                ToolTip = "Filter shown log lines (regex, case-insensitive). Invalid pattern = show all (box turns red). Esc clears.",
            };
            filterBox.TextChanged += (s, e) => ApplyFilter();
            filterBox.KeyDown += (s, e) =>
            {
                if (e.Key != Key.Escape) return;
                filterBox.Clear();
                e.Handled = true;
            };
            toolbar.Children.Add(filterBox); //the last child fills the remaining width

            //the view: same look and behavior as the main window's log area
            logView = new ListView
            {
                FontSize = 11,
                FontFamily = new FontFamily("Consolas"),
                SelectionMode = SelectionMode.Extended,
                BorderThickness = new Thickness(1),
                BorderBrush = new SolidColorBrush(Color.FromRgb(0x00, 0x15, 0xC7)),
                Margin = new Thickness(4, 0, 4, 4),
            };
            ScrollViewer.SetHorizontalScrollBarVisibility(logView, ScrollBarVisibility.Auto);
            logView.KeyDown += (s, e) =>
            {
                if (e.Key != Key.C || Keyboard.Modifiers != ModifierKeys.Control) return;
                CopyLines(logView, selectedOnly: true);
                e.Handled = true;
            };
            logView.ContextMenu = BuildContextMenu();

            var grid = new Grid { Margin = new Thickness(6) };
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            Grid.SetRow(toolbar, 0);
            Grid.SetRow(logView, 1);
            grid.Children.Add(toolbar);
            grid.Children.Add(logView);
            Content = grid;

            RestorePlacement(placeNear);
            RestoreTopmost();

            Loaded += (s, e) => AttachLogView(logView);
            Closing += (s, e) => SavePlacement();
            Closed += (s, e) => DetachLogView(logView);
        }

        private static Button ToolbarButton(string caption, string toolTip)
        {
            return new Button
            {
                Content = caption,
                ToolTip = toolTip,
                MinWidth = 80,
                MinHeight = 26,
                Padding = new Thickness(10, 2, 10, 2),
            };
        }

        private ContextMenu BuildContextMenu()
        {
            var copySelected = new MenuItem { Header = "Copy selected", InputGestureText = "Ctrl+C" };
            copySelected.Click += (s, e) => CopyLines(logView, selectedOnly: true);
            var copyAll = new MenuItem { Header = "Copy all" };
            copyAll.Click += (s, e) => CopyLines(logView, selectedOnly: false);
            var clear = new MenuItem { Header = "Clear" };
            clear.Click += (s, e) => ClearLog();

            var menu = new ContextMenu();
            menu.Items.Add(copySelected);
            menu.Items.Add(copyAll);
            menu.Items.Add(new Separator());
            menu.Items.Add(clear);
            return menu;
        }

        private void ApplyFilter()
        {
            bool invalidPattern;
            SetFilter(logView, FilterFor(filterBox.Text, out invalidPattern));
            if (invalidPattern)
                filterBox.Background = InvalidPatternBrush;
            else
                filterBox.ClearValue(Control.BackgroundProperty);
        }

        #region Placement + keep-on-top (remembered)

        /// <summary>
        /// The last placement when it still lands on a screen, else the default size centered on the screen
        /// showing <paramref name="placeNear"/>.
        /// </summary>
        private void RestorePlacement(Window placeNear)
        {
            WindowStartupLocation = WindowStartupLocation.Manual;

            string remembered = "";
            try { remembered = Properties.Settings.Default.LogWindowPlacement; }
            catch (Exception ex) { Log("Could not read the user settings \n" + ex.Message); }

            Rect saved;
            if (TryParsePlacement(remembered, out saved) && OnAScreen(saved))
            {
                Left = saved.Left;
                Top = saved.Top;
                Width = saved.Width;
                Height = saved.Height;
                return;
            }

            Width = DefaultWidth;
            Height = DefaultHeight;
            Rect? area = WorkingAreaOf(placeNear);
            if (area == null)
            {
                WindowStartupLocation = WindowStartupLocation.CenterScreen;
                return;
            }
            Width = Math.Min(Width, area.Value.Width);
            Height = Math.Min(Height, area.Value.Height);
            Left = area.Value.Left + (area.Value.Width - Width) / 2;
            Top = area.Value.Top + (area.Value.Height - Height) / 2;
        }

        /// <summary>"left,top,width,height" in WPF units, invariant culture (what SavePlacement writes).</summary>
        private static bool TryParsePlacement(string text, out Rect rect)
        {
            rect = Rect.Empty;
            if (string.IsNullOrWhiteSpace(text)) return false;

            string[] parts = text.Split(',');
            if (parts.Length != 4) return false;
            var values = new double[4];
            for (int i = 0; i < 4; i++)
            {
                if (!double.TryParse(parts[i], NumberStyles.Float, CultureInfo.InvariantCulture, out values[i])) return false;
            }
            if (values[2] < 100 || values[3] < 100) return false;

            rect = new Rect(values[0], values[1], values[2], values[3]);
            return true;
        }

        /// <summary>Part of the title bar must land on the virtual screen, else the window could not be reached (a monitor that is gone).</summary>
        private static bool OnAScreen(Rect bounds)
        {
            var screen = new Rect(SystemParameters.VirtualScreenLeft, SystemParameters.VirtualScreenTop, SystemParameters.VirtualScreenWidth, SystemParameters.VirtualScreenHeight);
            var titleBar = new Rect(bounds.Left, bounds.Top, bounds.Width, Math.Min(bounds.Height, 40));
            return screen.IntersectsWith(titleBar);
        }

        /// <summary>The working area of the screen showing <paramref name="window"/>, in WPF units; null without a window handle.</summary>
        private static Rect? WorkingAreaOf(Window window)
        {
            if (window == null) return null;
            var source = PresentationSource.FromVisual(window);
            if (source == null || source.CompositionTarget == null) return null;

            IntPtr handle = new System.Windows.Interop.WindowInteropHelper(window).Handle;
            System.Drawing.Rectangle area = System.Windows.Forms.Screen.FromHandle(handle).WorkingArea;
            Matrix fromDevice = source.CompositionTarget.TransformFromDevice;
            Point topLeft = fromDevice.Transform(new Point(area.Left, area.Top));
            Point bottomRight = fromDevice.Transform(new Point(area.Right, area.Bottom));
            return new Rect(topLeft, bottomRight);
        }

        private void SavePlacement()
        {
            Rect bounds = WindowState == WindowState.Normal ? new Rect(Left, Top, ActualWidth, ActualHeight) : RestoreBounds;
            if (bounds.IsEmpty || bounds.Width < 100 || bounds.Height < 100 || double.IsNaN(bounds.Left) || double.IsNaN(bounds.Top)) return;

            string text = string.Join(",", new[] { bounds.Left, bounds.Top, bounds.Width, bounds.Height }
                .Select(v => Math.Round(v).ToString(CultureInfo.InvariantCulture)));
            try
            {
                if (Properties.Settings.Default.LogWindowPlacement == text) return;
                Properties.Settings.Default.LogWindowPlacement = text;
                Properties.Settings.Default.Save();
            }
            catch (Exception ex)
            {
                Log("Could not save the user settings \n" + ex.Message);
            }
        }

        private void RestoreTopmost()
        {
            bool topmost = false;
            try { topmost = Properties.Settings.Default.LogWindowTopmost; }
            catch (Exception ex) { Log("Could not read the user settings \n" + ex.Message); }

            topmostBox.IsChecked = topmost;
            Topmost = topmost;
        }

        /// <summary>The checkbox drives Topmost; a change made by the user (window loaded) is remembered.</summary>
        private void ApplyTopmost()
        {
            bool value = topmostBox.IsChecked == true;
            Topmost = value;
            if (!IsLoaded) return;

            try
            {
                if (Properties.Settings.Default.LogWindowTopmost == value) return;
                Properties.Settings.Default.LogWindowTopmost = value;
                Properties.Settings.Default.Save();
            }
            catch (Exception ex)
            {
                Log("Could not save the user settings \n" + ex.Message);
            }
        }

        #endregion Placement + keep-on-top (remembered)
    }
}

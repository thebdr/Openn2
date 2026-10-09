using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;

using Openn._01_Constructor;
using Openn._10_StandardFunctions;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn
{
    /// <summary>
    /// "Re-arrange devices": lays the stations of the last hardware generation out by their Stations.csv Group in
    /// TIA's network (or topology) view with MOUSE DRAGS, because that is the only way to move an object there (no
    /// Openness layout call, editors invisible to UI Automation, keys do nothing - verified 2026-10-09). The user
    /// does the part a program cannot: opens the view, zooms until the whole default row and the rows below it fit
    /// on screen, and calibrates three points with F9 (the first created station, the last one, the spot of the
    /// first station of row 2). From those the window computes every default slot and every target cell
    /// (NetworkViewLayout: one row per group, at most N per row, rows in order of first appearance), brings TIA to
    /// the front and drags in an order where every drop lands on a free spot; F12 stops, and so does a foreground
    /// change (the robot never drags inside another window). Siemens-free: it only needs names and groups in
    /// creation order.
    /// </summary>
    public class ArrangeDevicesWindow : Window
    {
        private const int HotkeyCapture = 0x5001; //F9
        private const int HotkeyStop = 0x5002;    //F12

        private readonly IList<NetworkViewLayout.Station> stations;
        private readonly string stationsSource;
        private readonly Func<int?> tiaProcessId;
        private NetworkViewLayout layout;

        private readonly Point?[] calibration = new Point?[3];
        private readonly TextBlock[] calibrationTexts = new TextBlock[3];
        private readonly TextBlock summaryText;
        private readonly ListBox plan;
        private readonly TextBlock statusText;
        private readonly TextBox maxPerRowBox;
        private readonly TextBox stepDelayBox;
        private readonly TextBox deviceDelayBox;
        private readonly Button startButton;
        private readonly Button stopButton;
        private readonly Button resetButton;

        private int calibrationStep;
        private bool running;
        private bool stopRequested;
        private HwndSource source;

        /// <param name="stationsInCreationOrder">the stations on the default row, in the order they were created, with their Group</param>
        /// <param name="stationsSource">where that order comes from, for the instructions</param>
        /// <param name="tiaProcessId">the attached TIA Portal process, when known</param>
        public ArrangeDevicesWindow(IList<NetworkViewLayout.Station> stationsInCreationOrder, string stationsSource, Func<int?> tiaProcessId)
        {
            stations = stationsInCreationOrder;
            this.stationsSource = stationsSource;
            this.tiaProcessId = tiaProcessId;
            layout = new NetworkViewLayout(stations);

            Title = "Openn5 - Re-arrange devices (network / topology view)";
            Width = 660;
            Height = 720;
            MinWidth = 540;
            MinHeight = 500;
            Topmost = true; //stays readable in front of TIA; it is never the foreground window while the robot drags
            WindowStartupLocation = WindowStartupLocation.CenterOwner;
            Background = new SolidColorBrush(Color.FromRgb(0xF4, 0xF4, 0xF6));

            var root = new Grid { Margin = new Thickness(10) };
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

            // 1. instructions
            string first = stations.Count > 0 ? stations[0].Name : "(none)";
            string last = stations.Count > 0 ? stations[stations.Count - 1].Name : "(none)";
            var instructions = new TextBlock
            {
                TextWrapping = TextWrapping.Wrap,
                FontSize = 12,
                Margin = new Thickness(0, 0, 0, 8),
                Text =
                    "1. In TIA Portal open the network view (or the topology view) of the project, right after the generation - the stations must still sit on their default row.\n" +
                    "2. Zoom OUT until the whole default row AND the empty space for the rows below it are visible without scrolling. Do not scroll or zoom afterwards.\n" +
                    "3. Calibrate: hover the mouse over the CENTER of the first created station, " + first + ", and press F9. Then hover the center of the last one, " + last + ", and press F9. " +
                    "Then hover the point where the FIRST station of row 2 should sit (straight below the first station, one row down) and press F9.\n" +
                    "4. Press Start. Openn5 brings TIA to the front and drags the stations - hands off the mouse and keyboard until it reports done. F12 stops at once; switching to another window stops it too.\n" +
                    "5. Check the result in TIA; stations that landed badly can be dragged by hand.",
            };
            Grid.SetRow(instructions, 0);
            root.Children.Add(instructions);

            // 2. the plan: summary + max per row
            var planHeader = new DockPanel { Margin = new Thickness(0, 0, 0, 4) };
            maxPerRowBox = new TextBox { Text = NetworkViewLayout.DefaultMaxPerRow.ToString(), Width = 40, VerticalContentAlignment = VerticalAlignment.Center };
            maxPerRowBox.TextChanged += (s, e) => RebuildPlan();
            DockPanel.SetDock(maxPerRowBox, Dock.Right);
            planHeader.Children.Add(maxPerRowBox);
            var maxLabel = new TextBlock { Text = "max per row:", Margin = new Thickness(0, 0, 6, 0), VerticalAlignment = VerticalAlignment.Center };
            DockPanel.SetDock(maxLabel, Dock.Right);
            planHeader.Children.Add(maxLabel);
            summaryText = new TextBlock { TextWrapping = TextWrapping.Wrap, VerticalAlignment = VerticalAlignment.Center };
            planHeader.Children.Add(summaryText);
            Grid.SetRow(planHeader, 1);
            root.Children.Add(planHeader);

            plan = new ListBox { FontFamily = new FontFamily("Consolas"), FontSize = 11, Margin = new Thickness(0, 0, 0, 8) };
            Grid.SetRow(plan, 2);
            root.Children.Add(plan);

            // 3. calibration
            var calibrationPanel = new StackPanel { Margin = new Thickness(0, 0, 0, 8) };
            string[] labels =
            {
                "F9 on the center of the first station (" + first + "):",
                "F9 on the center of the last station (" + last + "):",
                "F9 where the first station of row 2 goes:",
            };
            for (int i = 0; i < 3; i++)
            {
                var row = new DockPanel { Margin = new Thickness(0, 1, 0, 1) };
                var label = new TextBlock { Text = labels[i], Width = 350, VerticalAlignment = VerticalAlignment.Center };
                calibrationTexts[i] = new TextBlock { Text = "-", VerticalAlignment = VerticalAlignment.Center, FontFamily = new FontFamily("Consolas") };
                row.Children.Add(label);
                row.Children.Add(calibrationTexts[i]);
                calibrationPanel.Children.Add(row);
            }
            resetButton = new Button { Content = "Reset calibration", HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 4, 0, 0), Padding = new Thickness(10, 2, 10, 2) };
            resetButton.Click += (s, e) => ResetCalibration();
            calibrationPanel.Children.Add(resetButton);
            Grid.SetRow(calibrationPanel, 3);
            root.Children.Add(calibrationPanel);

            // 4. timing
            var timing = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 8) };
            timing.Children.Add(new TextBlock { Text = "Drag step delay (ms):", VerticalAlignment = VerticalAlignment.Center });
            stepDelayBox = new TextBox { Text = "25", Width = 50, Margin = new Thickness(6, 0, 16, 0), VerticalContentAlignment = VerticalAlignment.Center };
            timing.Children.Add(stepDelayBox);
            timing.Children.Add(new TextBlock { Text = "Pause after each station (ms):", VerticalAlignment = VerticalAlignment.Center });
            deviceDelayBox = new TextBox { Text = "500", Width = 60, Margin = new Thickness(6, 0, 0, 0), VerticalContentAlignment = VerticalAlignment.Center };
            timing.Children.Add(deviceDelayBox);
            Grid.SetRow(timing, 4);
            root.Children.Add(timing);

            // 5. actions + status
            var actions = new DockPanel();
            var closeButton = new Button { Content = "Close", MinWidth = 80, Padding = new Thickness(10, 3, 10, 3) };
            closeButton.Click += (s, e) => Close();
            DockPanel.SetDock(closeButton, Dock.Right);
            actions.Children.Add(closeButton);
            stopButton = new Button { Content = "Stop (F12)", MinWidth = 90, Margin = new Thickness(0, 0, 8, 0), Padding = new Thickness(10, 3, 10, 3), IsEnabled = false };
            stopButton.Click += (s, e) => stopRequested = true;
            DockPanel.SetDock(stopButton, Dock.Right);
            actions.Children.Add(stopButton);
            startButton = new Button { Content = "Start", MinWidth = 90, Margin = new Thickness(0, 0, 8, 0), Padding = new Thickness(10, 3, 10, 3), FontWeight = FontWeights.SemiBold, IsEnabled = false };
            startButton.Click += async (s, e) => await RunAsync();
            DockPanel.SetDock(startButton, Dock.Right);
            actions.Children.Add(startButton);
            statusText = new TextBlock { VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap, Text = "Waiting for the calibration (F9 three times)." };
            actions.Children.Add(statusText);
            Grid.SetRow(actions, 5);
            root.Children.Add(actions);

            Content = root;

            RebuildPlan();
            SourceInitialized += (s, e) => RegisterHotkeys();
            Closing += (s, e) => { if (running) stopRequested = true; };
            Closed += (s, e) => UnregisterHotkeys();
        }

        // ============================== the plan ==============================

        /// <summary>Recomputes the rows from the Group column and the "max per row" box; the calibration stays, its validity is rechecked.</summary>
        private void RebuildPlan()
        {
            int maxPerRow;
            if (!int.TryParse(maxPerRowBox.Text, out maxPerRow) || maxPerRow < 1) maxPerRow = NetworkViewLayout.DefaultMaxPerRow;
            layout = new NetworkViewLayout(stations, maxPerRow);

            summaryText.Text = stations.Count + " station(s) in creation order (" + stationsSource + ") - grouped by the Stations.csv Group column into " +
                               layout.RowCount + " row(s), " + layout.Moves + " move(s).";
            plan.Items.Clear();
            foreach (string line in layout.Describe()) plan.Items.Add(line);
            if (stations.Count == 0) plan.Items.Add("(no stations - generate the hardware first)");
            UpdateCalibrationState();
        }

        // ============================== hotkeys ==============================

        private void RegisterHotkeys()
        {
            source = HwndSource.FromHwnd(new WindowInteropHelper(this).Handle);
            if (source == null) return;
            source.AddHook(WndProc);
            bool ok = MouseRobot.RegisterHotkey(source.Handle, HotkeyCapture, MouseRobot.VK_F9) & MouseRobot.RegisterHotkey(source.Handle, HotkeyStop, MouseRobot.VK_F12);
            if (!ok)
                statusText.Text = "F9 / F12 could not be registered as global hotkeys (another program holds them) - close that program and reopen this window.";
        }

        private void UnregisterHotkeys()
        {
            if (source == null) return;
            MouseRobot.UnregisterHotkey(source.Handle, HotkeyCapture);
            MouseRobot.UnregisterHotkey(source.Handle, HotkeyStop);
            source.RemoveHook(WndProc);
            source = null;
        }

        private IntPtr WndProc(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
        {
            if (msg != MouseRobot.WM_HOTKEY) return IntPtr.Zero;
            int id = wParam.ToInt32();
            if (id == HotkeyCapture && !running) Capture();
            else if (id == HotkeyStop && running) stopRequested = true;
            handled = true;
            return IntPtr.Zero;
        }

        // ============================== calibration ==============================

        private void Capture()
        {
            if (calibrationStep >= 3) return;
            Point p = MouseRobot.CursorPosition;
            calibration[calibrationStep] = p;
            calibrationTexts[calibrationStep].Text = ((int)p.X) + ", " + ((int)p.Y);
            calibrationStep++;
            UpdateCalibrationState();
        }

        private void ResetCalibration()
        {
            for (int i = 0; i < 3; i++)
            {
                calibration[i] = null;
                calibrationTexts[i].Text = "-";
            }
            calibrationStep = 0;
            UpdateCalibrationState();
        }

        private void UpdateCalibrationState()
        {
            if (running) return;
            string problem = PlanProblem();
            startButton.IsEnabled = problem == null;
            statusText.Text = problem ?? "Calibrated: pitch " + Pitch().ToString("0") + " px, rows " + RowPitch().ToString("0") + " px apart - press Start.";
        }

        private double Pitch() => stations.Count > 1 ? (calibration[1].Value.X - calibration[0].Value.X) / (stations.Count - 1) : 0;

        private double RowPitch() => calibration[2].Value.Y - calibration[0].Value.Y;

        private Point SlotOf(int index) => new Point(calibration[0].Value.X + index * Pitch(), calibration[0].Value.Y);

        private Point TargetOf(NetworkViewLayout.Cell cell) => new Point(calibration[0].Value.X + cell.Column * Pitch(), calibration[0].Value.Y + cell.Row * RowPitch());

        /// <summary>Why the robot cannot start yet; null when everything is in place.</summary>
        private string PlanProblem()
        {
            if (stations.Count == 0) return "Nothing to arrange: generate the hardware first.";
            if (layout.Moves == 0) return "Nothing to move: every station already sits on its row (one group, within the max per row).";
            if (calibrationStep < 3) return "Waiting for the calibration: F9 three times (" + calibrationStep + " of 3 captured).";
            if (stations.Count > 1 && Pitch() < 8) return "The first and the last station are too close: hover the right stations (first = " + stations[0].Name + ", last = " + stations[stations.Count - 1].Name + ") or zoom in a little.";
            if (RowPitch() < 8) return "Row 2 must be BELOW the default row: hover a point under the first station for the third capture.";
            Rect screen = MouseRobot.VirtualScreen;
            foreach (NetworkViewLayout.Cell cell in layout.Cells)
            {
                if (!screen.Contains(SlotOf(cell.Index)) || !screen.Contains(TargetOf(cell)))
                    return "The plan leaves the screen (" + cell.Name + " -> row " + (cell.Row + 1) + ", column " + (cell.Column + 1) + "): zoom out further or enlarge the TIA window, then calibrate again.";
            }
            return null;
        }

        // ============================== the run ==============================

        private async Task RunAsync()
        {
            if (running) return;
            string problem = PlanProblem();
            if (problem != null)
            {
                statusText.Text = problem;
                return;
            }
            int stepDelay, deviceDelay;
            if (!int.TryParse(stepDelayBox.Text, out stepDelay) || stepDelay < 1) stepDelay = 25;
            if (!int.TryParse(deviceDelayBox.Text, out deviceDelay) || deviceDelay < 0) deviceDelay = 500;

            IntPtr tia = MouseRobot.FindTiaPortalWindow(tiaProcessId());
            if (tia == IntPtr.Zero)
            {
                statusText.Text = "No TIA Portal window found.";
                return;
            }

            running = true;
            stopRequested = false;
            startButton.IsEnabled = false;
            resetButton.IsEnabled = false;
            maxPerRowBox.IsEnabled = false;
            stopButton.IsEnabled = true;
            int moved = 0;
            string outcome;
            try
            {
                MouseRobot.BringToFront(tia);
                await Task.Delay(800);

                foreach (NetworkViewLayout.Cell cell in layout.MovesInSafeOrder())
                {
                    if (stopRequested) { outcome = "stopped by you (F12)"; goto Done; }
                    if (MouseRobot.ForegroundWindow != tia) { outcome = "stopped: TIA Portal lost the foreground (another window came up)"; goto Done; }

                    statusText.Text = "Moving " + cell.Name + " to row " + (cell.Row + 1) + ", column " + (cell.Column + 1) + " (" + (moved + 1) + " of " + layout.Moves + ")";
                    bool completed = await DragAsync(SlotOf(cell.Index), TargetOf(cell), stepDelay);
                    if (!completed) { outcome = "stopped by you (F12) - the last station may have been dropped halfway"; goto Done; }
                    moved++;
                    Log("Re-arrange: " + cell.Name + " -> row " + (cell.Row + 1) + ", column " + (cell.Column + 1) + " (" + cell.Key + ")");
                    await Task.Delay(deviceDelay);
                }
                outcome = "done";
            }
            catch (Exception e)
            {
                outcome = "failed: " + e.Message;
            }
            Done:
            running = false;
            stopButton.IsEnabled = false;
            resetButton.IsEnabled = true;
            maxPerRowBox.IsEnabled = true;
            string summary = "Re-arrange devices " + outcome + ": " + moved + " of " + layout.Moves + " station(s) moved";
            Log(summary + " - check the view in TIA");
            statusText.Text = summary + ". Check TIA; calibrate again before another run (the stations are no longer on the default row).";
            calibrationStep = 3; //keep the numbers visible; Start stays disabled until Reset + a fresh calibration
            startButton.IsEnabled = false;
        }

        /// <summary>One drag: press on the station, wiggle past the drag threshold, glide to the target in steps, release. False when stopped mid-way.</summary>
        private async Task<bool> DragAsync(Point from, Point to, int stepDelay)
        {
            MouseRobot.MoveTo(from);
            await Task.Delay(stepDelay * 4);
            MouseRobot.LeftDown();
            await Task.Delay(stepDelay * 4);
            MouseRobot.MoveTo(new Point(from.X + 6, from.Y + 6)); //past the drag threshold
            await Task.Delay(stepDelay * 2);

            const int steps = 16;
            for (int i = 1; i <= steps; i++)
            {
                if (stopRequested)
                {
                    MouseRobot.LeftUp();
                    return false;
                }
                MouseRobot.MoveTo(new Point(from.X + (to.X - from.X) * i / steps, from.Y + (to.Y - from.Y) * i / steps));
                await Task.Delay(stepDelay);
            }
            MouseRobot.MoveTo(to);
            await Task.Delay(stepDelay * 4);
            MouseRobot.LeftUp();
            await Task.Delay(stepDelay * 4);
            return true;
        }
    }
}

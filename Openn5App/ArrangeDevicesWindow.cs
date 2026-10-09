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
    /// Openness layout call, editors invisible to UI Automation, keys do nothing - verified 2026-10-09). The default
    /// row is usually wider than the screen even at the smallest zoom (65 stations on the FVT), so the robot
    /// scrolls: it READS the horizontal scrollbar from screen pixels (thumb length = canvas width, thumb position =
    /// offset; colours sampled at the calibration), scrolls by dragging the thumb, and moves a far station in hops
    /// of one viewport each (dropped on a parking strip below the planned rows) until the final drag can reach its
    /// cell. The user does the part a program cannot: opens the view, zooms until the planned rows fit vertically
    /// and the first columns fit horizontally, and calibrates six points with F9. F12 stops, and so does a
    /// foreground change (the robot never drags inside another window). Siemens-free: it only needs names and
    /// groups in creation order.
    /// </summary>
    public class ArrangeDevicesWindow : Window
    {
        private const int HotkeyCapture = 0x5001; //F9
        private const int HotkeyStop = 0x5002;    //F12
        private const int CaptureCount = 6;
        private const double EdgeMargin = 70;     //px kept between a grabbed / dropped station and the viewport edges
        private const int MaxHops = 24;

        private readonly IList<NetworkViewLayout.Station> stations;
        private readonly string stationsSource;
        private readonly Func<int?> tiaProcessId;
        private NetworkViewLayout layout;

        private readonly Point?[] calibration = new Point?[CaptureCount];
        private readonly TextBlock[] calibrationTexts = new TextBlock[CaptureCount];
        private readonly TextBlock summaryText;
        private readonly ListBox plan;
        private readonly TextBlock statusText;
        private readonly TextBox maxPerRowBox;
        private readonly TextBox stepDelayBox;
        private readonly TextBox deviceDelayBox;
        private readonly Button startButton;
        private readonly Button stopButton;
        private readonly Button resetButton;

        //the horizontal scrollbar, measured at the fully-left view (captures 4 and 5)
        private System.Drawing.Color thumbColor, troughColor;
        private int barY, troughLeft, troughRight;
        private double thumbFraction0;   //thumb length / trough length when calibrated
        private double viewportCanvas;   //the viewport width in canvas px (from the thumb fraction and the fully-right capture)
        private string scrollbarProblem; //why the scrollbar could not be read at the calibration

        //the model: where every station is now, in canvas px - the first station sits at (0, 0) when scrolled fully left
        private double[] canvasX, canvasY;

        private int calibrationStep;
        private bool running;
        private bool stopRequested;
        private int stepDelay = 25;
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
            Width = 700;
            Height = 780;
            MinWidth = 560;
            MinHeight = 520;
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
            string second = stations.Count > 1 ? stations[1].Name : "(none)";
            string last = stations.Count > 0 ? stations[stations.Count - 1].Name : "(none)";
            var instructions = new TextBlock
            {
                TextWrapping = TextWrapping.Wrap,
                FontSize = 12,
                Margin = new Thickness(0, 0, 0, 8),
                Text =
                    "1. In TIA Portal open the network view (or the topology view) right after the generation - the stations must still sit on their default row. Scroll the view fully LEFT.\n" +
                    "2. Zoom out until the planned rows fit VERTICALLY and the first columns fit horizontally (the row itself may run off the screen - the robot scrolls). Do not zoom afterwards. Keep this window away from the bottom of the TIA canvas: the robot reads the horizontal scrollbar there.\n" +
                    "3. Calibrate with F9 (hover, then press): the center of the first station " + first + "; the center of the second one " + second + "; the spot where the first station of row 2 goes (straight below the first station); " +
                    "the scrollbar's THUMB (the slider at the bottom of the canvas); an empty part of the scrollbar TRACK right of the thumb. Then scroll the view fully RIGHT and F9 on the center of the last station " + last + ".\n" +
                    "4. Press Start. Openn5 brings TIA to the front, scrolls and drags - hands off the mouse and keyboard until it reports done. F12 stops at once; switching to another window stops it too.\n" +
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
                "F9 on the center of the first station (" + first + "), view fully LEFT:",
                "F9 on the center of the second station (" + second + "):",
                "F9 where the first station of row 2 goes:",
                "F9 on the horizontal scrollbar's THUMB:",
                "F9 on an empty part of the scrollbar TRACK (right of the thumb):",
                "Scroll fully RIGHT, then F9 on the center of the last station (" + last + "):",
            };
            for (int i = 0; i < CaptureCount; i++)
            {
                var row = new DockPanel { Margin = new Thickness(0, 1, 0, 1) };
                var label = new TextBlock { Text = labels[i], Width = 420, VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap };
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
            statusText = new TextBlock { VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap, Text = "Waiting for the calibration (F9 six times)." };
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
            if (calibrationStep >= CaptureCount) return;
            Point p = MouseRobot.CursorPosition;
            calibration[calibrationStep] = p;
            calibrationTexts[calibrationStep].Text = ((int)p.X) + ", " + ((int)p.Y);
            calibrationStep++;
            if (calibrationStep == 4) thumbColor = MouseRobot.SampleColor(p);
            if (calibrationStep == 5) MeasureScrollbar();
            UpdateCalibrationState();
        }

        /// <summary>
        /// Captures 4 and 5 done: samples the trough colour, scans the scrollbar row for the thumb (the view is scrolled
        /// fully left, so the thumb's left end is the trough's left end) and for the trough's right end.
        /// </summary>
        private void MeasureScrollbar()
        {
            scrollbarProblem = null;
            Point thumb = calibration[3].Value, trough = calibration[4].Value;
            troughColor = MouseRobot.SampleColor(trough);
            barY = (int)thumb.Y;
            if (MouseRobot.ColorDistance(thumbColor, troughColor) < 40)
            {
                scrollbarProblem = "The thumb and the track have the same colour - hover the slider itself for capture 4 and an empty part of the bar for capture 5 (Reset calibration).";
                return;
            }
            int x = (int)thumb.X;
            int left = x, right = x;
            while (left > 0 && MouseRobot.ColorDistance(MouseRobot.PixelAt(left - 1, barY), thumbColor) < 48) left--;
            while (MouseRobot.ColorDistance(MouseRobot.PixelAt(right + 1, barY), thumbColor) < 48 && right < left + 4000) right++;
            int troughEnd = (int)trough.X;
            while (MouseRobot.ColorDistance(MouseRobot.PixelAt(troughEnd + 1, (int)trough.Y), troughColor) < 48 && troughEnd < x + 6000) troughEnd++;
            if (right - left < 6 || troughEnd <= right)
            {
                scrollbarProblem = "The scrollbar could not be read (thumb " + (right - left + 1) + " px, track end " + troughEnd + ") - is the horizontal scrollbar visible and the view scrolled fully left? Reset calibration and try again.";
                return;
            }
            troughLeft = left;
            troughRight = troughEnd;
            thumbFraction0 = (right - left + 1.0) / (troughRight - troughLeft + 1.0);
        }

        private void ResetCalibration()
        {
            for (int i = 0; i < CaptureCount; i++)
            {
                calibration[i] = null;
                calibrationTexts[i].Text = "-";
            }
            calibrationStep = 0;
            scrollbarProblem = null;
            UpdateCalibrationState();
        }

        private void UpdateCalibrationState()
        {
            if (running) return;
            string problem = PlanProblem();
            startButton.IsEnabled = problem == null;
            statusText.Text = problem ?? "Calibrated: pitch " + Pitch().ToString("0") + " px, rows " + RowPitch().ToString("0") + " px apart, the row is " +
                              (thumbFraction0 > 0 ? (1 / thumbFraction0).ToString("0.0") : "?") + " viewport(s) wide - press Start.";
        }

        private double X0 => calibration[0].Value.X;
        private double Y0 => calibration[0].Value.Y;
        private double Pitch() => calibration[1].Value.X - calibration[0].Value.X;
        private double RowPitch() => calibration[2].Value.Y - calibration[0].Value.Y;
        private double ViewLeft => troughLeft + EdgeMargin;
        private double ViewRight => troughRight - EdgeMargin;
        private double UsableWidth => ViewRight - ViewLeft;
        private double ParkY => layout.RowCount * RowPitch();

        /// <summary>Why the robot cannot start yet; null when everything is in place.</summary>
        private string PlanProblem()
        {
            if (stations.Count == 0) return "Nothing to arrange: generate the hardware first.";
            if (layout.Moves == 0) return "Nothing to move: every station already sits on its row (one group, within the max per row).";
            if (calibrationStep < CaptureCount) return "Waiting for the calibration: F9 " + CaptureCount + " times (" + calibrationStep + " of " + CaptureCount + " captured).";
            if (scrollbarProblem != null) return scrollbarProblem;
            if (Pitch() < 8) return "The first and the second station are too close: hover " + stations[0].Name + " then " + stations[1].Name + ", or zoom in a little.";
            if (RowPitch() < 8) return "Row 2 must be BELOW the default row: hover a point under the first station for the third capture.";
            double oMax0 = X0 + (stations.Count - 1) * Pitch() - calibration[5].Value.X;
            if (oMax0 < 0) return "The last station (capture 6) must be hovered with the view scrolled fully RIGHT; it came out left of where the row ends.";
            Rect screen = MouseRobot.VirtualScreen;
            double widest = Math.Min(layout.MaxPerRow, layout.Cells.Max(c => c.Column) + 1) * Pitch();
            if (X0 + widest > ViewRight) return "The first " + Math.Min(layout.MaxPerRow, layout.Cells.Max(c => c.Column) + 1) + " columns do not fit in the viewport - zoom out, then calibrate again.";
            if (Y0 + ParkY + EdgeMargin > barY) return "The planned rows (plus one parking row below them) do not fit above the scrollbar - zoom out, then calibrate again.";
            if (X0 - EdgeMargin < screen.Left) return "The first station must sit inside the canvas, away from its left edge.";
            return null;
        }

        // ============================== the scrollbar ==============================

        private sealed class ScrollState
        {
            public bool Found;
            public double Offset;   //canvas px scrolled
            public double Max;      //the largest offset
            public int ThumbLeft;
            public int ThumbLength;
        }

        /// <summary>
        /// Reads the horizontal scrollbar: the longest run of thumb-coloured pixels on the bar's row gives the thumb;
        /// its length over the trough is viewport / canvas, its position the offset. A missing thumb (the canvas
        /// fits, or the bar is hidden) reads as offset 0.
        /// </summary>
        private ScrollState ReadScrollbar()
        {
            var state = new ScrollState();
            System.Drawing.Color[] row = MouseRobot.ReadRow(barY, troughLeft, troughRight);
            if (row == null) return state;
            int bestStart = -1, bestLength = 0, runStart = -1;
            for (int i = 0; i <= row.Length; i++)
            {
                bool isThumb = i < row.Length && MouseRobot.ColorDistance(row[i], thumbColor) < 48;
                if (isThumb && runStart < 0) runStart = i;
                if (!isThumb && runStart >= 0)
                {
                    if (i - runStart > bestLength) { bestLength = i - runStart; bestStart = runStart; }
                    runStart = -1;
                }
            }
            if (bestLength < 6) return state;
            state.Found = true;
            state.ThumbLeft = troughLeft + bestStart;
            state.ThumbLength = bestLength;
            double troughLength = troughRight - troughLeft + 1;
            double fraction = bestLength / troughLength;
            if (fraction >= 0.995)
            {
                state.Offset = 0;
                state.Max = 0;
                return state;
            }
            state.Max = viewportCanvas * (1 / fraction - 1);
            state.Offset = Math.Max(0, Math.Min(1, bestStart / (troughLength - bestLength))) * state.Max;
            return state;
        }

        /// <summary>Scrolls to the wanted offset by dragging the thumb, re-reading up to three times; false when the bar cannot be read or the offset stays off.</summary>
        private async Task<bool> ScrollToAsync(double wanted)
        {
            for (int attempt = 0; attempt < 3; attempt++)
            {
                ScrollState state = ReadScrollbar();
                if (!state.Found) return wanted <= 1; //no bar: everything is in view already
                double target = Math.Max(0, Math.Min(state.Max, wanted));
                if (Math.Abs(state.Offset - target) <= Math.Max(6, Pitch() / 3)) return true;
                double troughLength = troughRight - troughLeft + 1;
                double travel = troughLength - state.ThumbLength;
                double targetLeft = troughLeft + (state.Max > 0 ? target / state.Max : 0) * travel;
                var from = new Point(state.ThumbLeft + state.ThumbLength / 2.0, barY);
                var to = new Point(targetLeft + state.ThumbLength / 2.0, barY);
                if (!await DragAsync(from, to, stepDelay, wiggle: false)) return false;
                await Task.Delay(stepDelay * 6);
            }
            ScrollState final = ReadScrollbar();
            return final.Found && Math.Abs(final.Offset - Math.Max(0, Math.Min(final.Max, wanted))) <= Pitch();
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
            int deviceDelay;
            if (!int.TryParse(stepDelayBox.Text, out stepDelay) || stepDelay < 1) stepDelay = 25;
            if (!int.TryParse(deviceDelayBox.Text, out deviceDelay) || deviceDelay < 0) deviceDelay = 500;

            IntPtr tia = MouseRobot.FindTiaPortalWindow(tiaProcessId());
            if (tia == IntPtr.Zero)
            {
                statusText.Text = "No TIA Portal window found.";
                return;
            }

            //the model, from the calibration: the viewport in canvas px follows from the thumb fraction and the fully-right capture
            double oMax0 = X0 + (stations.Count - 1) * Pitch() - calibration[5].Value.X;
            viewportCanvas = thumbFraction0 < 0.995 ? oMax0 * thumbFraction0 / (1 - thumbFraction0) : double.MaxValue / 4;
            canvasX = new double[stations.Count];
            canvasY = new double[stations.Count];
            for (int i = 0; i < stations.Count; i++) canvasX[i] = i * Pitch();

            running = true;
            stopRequested = false;
            startButton.IsEnabled = false;
            resetButton.IsEnabled = false;
            maxPerRowBox.IsEnabled = false;
            stopButton.IsEnabled = true;
            int moved = 0, hops = 0;
            string outcome;
            try
            {
                MouseRobot.BringToFront(tia);
                await Task.Delay(800);

                foreach (NetworkViewLayout.Cell cell in layout.MovesInSafeOrder())
                {
                    if (stopRequested) { outcome = "stopped by you (F12)"; goto Done; }
                    if (MouseRobot.ForegroundWindow != tia) { outcome = "stopped: TIA Portal lost the foreground (another window came up)"; goto Done; }

                    Tuple<int, string> moveResult = await MoveStationAsync(cell, tia, moved + 1);
                    int cellHops = moveResult.Item1;
                    string why = moveResult.Item2;
                    if (cellHops < 0)
                    {
                        outcome = (stopRequested ? "stopped by you (F12)" : "failed at " + cell.Name + ": " + why);
                        goto Done;
                    }
                    hops += cellHops;
                    moved++;
                    Log("Re-arrange: " + cell.Name + " -> row " + (cell.Row + 1) + ", column " + (cell.Column + 1) + " (" + cell.Key + ")" +
                        (cellHops > 0 ? " after " + cellHops + " hop(s)" : string.Empty));
                    await Task.Delay(deviceDelay);
                }
                await ScrollToAsync(0);
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
            string summary = "Re-arrange devices " + outcome + ": " + moved + " of " + layout.Moves + " station(s) moved" + (hops > 0 ? ", " + hops + " hop(s)" : string.Empty);
            Log(summary + " - check the view in TIA");
            statusText.Text = summary + ". Check TIA; calibrate again before another run (the stations are no longer on the default row).";
            calibrationStep = CaptureCount; //keep the numbers visible; Start stays disabled until Reset + a fresh calibration
            startButton.IsEnabled = false;
        }

        /// <summary>
        /// One station to its cell: a direct drag when its current spot and the cell fit in one viewport (scrolled
        /// so that both are inside the margins); otherwise hops - scroll so the station sits at the right margin,
        /// drag it to the left margin on the parking strip, repeat - until the direct drag is possible. Returns the
        /// number of hops and null, or -1 and the reason when a scroll or a drag failed.
        /// </summary>
        private async Task<Tuple<int, string>> MoveStationAsync(NetworkViewLayout.Cell cell, IntPtr tia, int number)
        {
            int i = cell.Index;
            double tx = cell.Column * Pitch(), ty = cell.Row * RowPitch();
            int hops = 0;
            while (true)
            {
                if (stopRequested || MouseRobot.ForegroundWindow != tia) { return Fail("stopped"); }
                double x = canvasX[i], y = canvasY[i];
                double span = Math.Abs(x - tx);
                if (span <= UsableWidth)
                {
                    double wanted = X0 + Math.Min(x, tx) - ViewLeft;
                    if (!await ScrollToAsync(wanted)) { return Fail("could not scroll the view (is the horizontal scrollbar visible?)"); }
                    ScrollState state = ReadScrollbar();
                    double o = state.Found ? state.Offset : 0;
                    var from = new Point(X0 + x - o, Y0 + y);
                    var to = new Point(X0 + tx - o, Y0 + ty);
                    if (from.X < ViewLeft - EdgeMargin / 2 || from.X > ViewRight + EdgeMargin / 2 || to.X < ViewLeft - EdgeMargin / 2 || to.X > ViewRight + EdgeMargin / 2)
                    {
                        return Fail("the station or its cell is outside the viewport after scrolling (offset " + o.ToString("0") + ")");
                    }
                    statusText.Text = "Moving " + cell.Name + " to row " + (cell.Row + 1) + ", column " + (cell.Column + 1) + " (" + number + " of " + layout.Moves + ")";
                    if (!await DragAsync(from, to, stepDelay, wiggle: true)) { return Fail("stopped"); }
                    canvasX[i] = tx;
                    canvasY[i] = ty;
                    return Tuple.Create(hops, (string)null);
                }

                //a hop: the station at the right margin, dropped at the left margin on the parking strip
                if (++hops > MaxHops) { return Fail("too many hops - the scrollbar reading drifts"); }
                double wantedHop = X0 + x - ViewRight;
                if (!await ScrollToAsync(wantedHop)) { return Fail("could not scroll the view (is the horizontal scrollbar visible?)"); }
                ScrollState hopState = ReadScrollbar();
                double oh = hopState.Found ? hopState.Offset : 0;
                var grab = new Point(X0 + x - oh, Y0 + y);
                if (grab.X < ViewLeft - EdgeMargin / 2 || grab.X > ViewRight + EdgeMargin / 2)
                {
                    return Fail("the station is outside the viewport after scrolling (offset " + oh.ToString("0") + ", expected " + wantedHop.ToString("0") + ")");
                }
                var drop = new Point(ViewLeft, Y0 + ParkY);
                statusText.Text = "Hop " + hops + ": " + cell.Name + " one viewport to the left (" + number + " of " + layout.Moves + ")";
                if (!await DragAsync(grab, drop, stepDelay, wiggle: true)) { return Fail("stopped"); }
                canvasX[i] = drop.X - X0 + oh;
                canvasY[i] = ParkY;
                await Task.Delay(stepDelay * 8);
            }
        }

        private static Tuple<int, string> Fail(string why) => Tuple.Create(-1, why);

        /// <summary>One drag: press, (wiggle past the drag threshold,) glide to the target in steps, release. False when stopped mid-way.</summary>
        private async Task<bool> DragAsync(Point from, Point to, int delay, bool wiggle)
        {
            MouseRobot.MoveTo(from);
            await Task.Delay(delay * 4);
            MouseRobot.LeftDown();
            await Task.Delay(delay * 4);
            if (wiggle)
            {
                MouseRobot.MoveTo(new Point(from.X + 6, from.Y + 6)); //past the drag threshold
                await Task.Delay(delay * 2);
            }

            const int steps = 16;
            for (int i = 1; i <= steps; i++)
            {
                if (stopRequested)
                {
                    MouseRobot.LeftUp();
                    return false;
                }
                MouseRobot.MoveTo(new Point(from.X + (to.X - from.X) * i / steps, from.Y + (to.Y - from.Y) * i / steps));
                await Task.Delay(delay);
            }
            MouseRobot.MoveTo(to);
            await Task.Delay(delay * 4);
            MouseRobot.LeftUp();
            await Task.Delay(delay * 4);
            return true;
        }
    }
}

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
    /// Openness layout call, editors invisible to UI Automation, keys do nothing - verified 2026-10-09). The view
    /// never shows the whole picture (65 stations on the FVT), so the robot SCROLLS with the scrollbar arrow
    /// buttons: one click is a fixed step, the robot measures the step itself (it clicks the button a few times and
    /// the user hovers the first station again), and from then on it knows the exact offset by counting clicks -
    /// no pixel reading, no guessing. The user zooms so that at least "max per row + 1" columns fit, calibrates
    /// seven points with F9 and re-hovers the first station twice; the robot keeps a model of every station's
    /// position, brings TIA to the front and drags: a far station travels down in hops of one viewport and left in
    /// hops along its target row's free columns (beyond the planned ones), then one drag puts it in its cell. F12
    /// stops, and so does a foreground change (the robot never drags inside another window). Siemens-free.
    /// </summary>
    public class ArrangeDevicesWindow : Window
    {
        private const int HotkeyCapture = 0x5001; //F9
        private const int HotkeyStop = 0x5002;    //F12
        private const double EdgeMargin = 60;     //px kept between a grabbed / dropped station and the canvas edges
        private const int StepClicksX = 8;        //clicks the robot makes to measure the horizontal step
        private const int StepClicksY = 6;        //clicks the robot makes to measure the vertical step
        private const int MaxHops = 60;

        //calibration steps: seven are hover + F9; 7 and 8 are "hover the first station again" after the robot clicked
        private const int CapFirst = 0, CapSecond = 1, CapRow2 = 2, CapLeft = 3, CapRight = 4, CapUp = 5, CapDown = 6, CapAfterX = 7, CapAfterY = 8, CaptureCount = 9;

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

        //the model: canvas px, the first station at (0, 0) when scrolled to the origin (fully left, fully up)
        private double[] canvasX, canvasY;
        private int clicksX, clicksY;    //the scroll position in arrow clicks from the origin
        private double stepX, stepY;     //canvas px per click

        private int calibrationStep;
        private bool calibrating;        //the robot is clicking for the step measurement
        private bool running;
        private bool stopRequested;
        private int stepDelay = 25;
        private HwndSource source;

        public ArrangeDevicesWindow(IList<NetworkViewLayout.Station> stationsInCreationOrder, string stationsSource, Func<int?> tiaProcessId)
        {
            stations = stationsInCreationOrder;
            this.stationsSource = stationsSource;
            this.tiaProcessId = tiaProcessId;
            layout = new NetworkViewLayout(stations);

            Title = "Openn5 - Re-arrange devices (network / topology view)";
            Width = 720;
            Height = 820;
            MinWidth = 580;
            MinHeight = 560;
            Topmost = true; //stays readable in front of TIA; it is never the foreground window while the robot works
            WindowStartupLocation = WindowStartupLocation.CenterOwner;
            Background = new SolidColorBrush(Color.FromRgb(0xF4, 0xF4, 0xF6));

            var root = new Grid { Margin = new Thickness(10) };
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

            string first = stations.Count > 0 ? stations[0].Name : "(none)";
            string second = stations.Count > 1 ? stations[1].Name : "(none)";
            var instructions = new TextBlock
            {
                TextWrapping = TextWrapping.Wrap,
                FontSize = 12,
                Margin = new Thickness(0, 0, 0, 8),
                Text =
                    "1. In TIA Portal open the network view (or the topology view) right after the generation - the stations must still sit on their default row. Scroll the view fully LEFT and fully UP (the origin).\n" +
                    "2. Zoom so that at least \"max per row + 1\" columns of stations fit the canvas width (" + (NetworkViewLayout.DefaultMaxPerRow + 1) + " by default). Do not zoom afterwards. Keep this window off the TIA canvas and its scrollbars.\n" +
                    "3. Calibrate with F9 (hover, then press): the center of the first station " + first + "; the center of the second one " + second + "; the spot where the first station of row 2 goes (straight below the first station); " +
                    "then the four scrollbar arrow buttons: < and > on the bottom bar, ^ and v on the right bar. The robot then clicks > " + StepClicksX + " times: hover the first station again (it moved left) and press F9; " +
                    "it scrolls back, clicks v " + StepClicksY + " times: hover the first station again and press F9. That measures the scroll step.\n" +
                    "4. Press Start. Openn5 brings TIA to the front, scrolls with the arrow buttons and drags - hands off the mouse and keyboard until it reports done. F12 stops at once; switching to another window stops it too.\n" +
                    "5. Check the result in TIA; stations that landed badly can be dragged by hand.",
            };
            Grid.SetRow(instructions, 0);
            root.Children.Add(instructions);

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

            var calibrationPanel = new StackPanel { Margin = new Thickness(0, 0, 0, 8) };
            string[] labels =
            {
                "F9 on the center of the first station (" + first + "), view at the origin:",
                "F9 on the center of the second station (" + second + "):",
                "F9 where the first station of row 2 goes (below the first):",
                "F9 on the bottom scrollbar's  <  arrow button:",
                "F9 on the bottom scrollbar's  >  arrow button:",
                "F9 on the right scrollbar's  ^  arrow button:",
                "F9 on the right scrollbar's  v  arrow button:",
                "After the robot clicked  >  " + StepClicksX + " times: F9 on the first station again:",
                "After the robot clicked  v  " + StepClicksY + " times: F9 on the first station again:",
            };
            for (int i = 0; i < CaptureCount; i++)
            {
                var row = new DockPanel { Margin = new Thickness(0, 1, 0, 1) };
                var label = new TextBlock { Text = labels[i], Width = 460, VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap };
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

            var timing = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 0, 0, 8) };
            timing.Children.Add(new TextBlock { Text = "Drag step delay (ms):", VerticalAlignment = VerticalAlignment.Center });
            stepDelayBox = new TextBox { Text = "25", Width = 50, Margin = new Thickness(6, 0, 16, 0), VerticalContentAlignment = VerticalAlignment.Center };
            timing.Children.Add(stepDelayBox);
            timing.Children.Add(new TextBlock { Text = "Pause after each station (ms):", VerticalAlignment = VerticalAlignment.Center });
            deviceDelayBox = new TextBox { Text = "400", Width = 60, Margin = new Thickness(6, 0, 0, 0), VerticalContentAlignment = VerticalAlignment.Center };
            timing.Children.Add(deviceDelayBox);
            Grid.SetRow(timing, 4);
            root.Children.Add(timing);

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
            statusText = new TextBlock { VerticalAlignment = VerticalAlignment.Center, TextWrapping = TextWrapping.Wrap, Text = "Waiting for the calibration." };
            actions.Children.Add(statusText);
            Grid.SetRow(actions, 5);
            root.Children.Add(actions);

            Content = root;

            RebuildPlan();
            SourceInitialized += (s, e) => RegisterHotkeys();
            Closing += (s, e) => { if (running || calibrating) stopRequested = true; };
            Closed += (s, e) => UnregisterHotkeys();
        }

        // ============================== the plan ==============================

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
            if (id == HotkeyCapture && !running && !calibrating) Capture();
            else if (id == HotkeyStop && (running || calibrating)) stopRequested = true;
            handled = true;
            return IntPtr.Zero;
        }

        // ============================== calibration ==============================

        private async void Capture()
        {
            if (calibrationStep >= CaptureCount) return;
            Point p = MouseRobot.CursorPosition;
            calibration[calibrationStep] = p;
            calibrationTexts[calibrationStep].Text = ((int)p.X) + ", " + ((int)p.Y);
            calibrationStep++;

            //after the last button the robot clicks > a few times and waits for the re-hover; after that it scrolls back and clicks v
            if (calibrationStep == CapAfterX)
                await MeasureStepAsync(calibration[CapRight].Value, StepClicksX, "Hover the first station again (it moved left) and press F9.");
            else if (calibrationStep == CapAfterY)
            {
                stepX = (calibration[CapFirst].Value.X - calibration[CapAfterX].Value.X) / StepClicksX;
                await ClickAsync(calibration[CapLeft].Value, StepClicksX + 3, "scrolling back to the left");
                await MeasureStepAsync(calibration[CapDown].Value, StepClicksY, "Hover the first station again (it moved up) and press F9.");
            }
            else if (calibrationStep == CaptureCount)
            {
                stepY = (calibration[CapFirst].Value.Y - calibration[CapAfterY].Value.Y) / StepClicksY;
                await ClickAsync(calibration[CapUp].Value, StepClicksY + 3, "scrolling back to the top");
                clicksX = 0;
                clicksY = 0;
            }
            UpdateCalibrationState();
        }

        private async Task MeasureStepAsync(Point button, int clicks, string thenAsk)
        {
            calibrating = true;
            try
            {
                IntPtr tia = MouseRobot.FindTiaPortalWindow(tiaProcessId());
                if (tia != IntPtr.Zero) MouseRobot.BringToFront(tia);
                await Task.Delay(400);
                await ClickAsync(button, clicks, "measuring the scroll step");
            }
            finally
            {
                calibrating = false;
            }
            statusText.Text = thenAsk;
        }

        private async Task ClickAsync(Point button, int clicks, string what)
        {
            statusText.Text = what + " (" + clicks + " click(s))...";
            for (int i = 0; i < clicks; i++)
            {
                if (stopRequested) break;
                MouseRobot.MoveTo(button);
                await Task.Delay(stepDelay);
                MouseRobot.LeftDown();
                await Task.Delay(stepDelay);
                MouseRobot.LeftUp();
                await Task.Delay(stepDelay);
            }
            await Task.Delay(stepDelay * 6); //let TIA repaint
        }

        private void ResetCalibration()
        {
            for (int i = 0; i < CaptureCount; i++)
            {
                calibration[i] = null;
                calibrationTexts[i].Text = "-";
            }
            calibrationStep = 0;
            stepX = stepY = 0;
            UpdateCalibrationState();
        }

        private void UpdateCalibrationState()
        {
            if (running) return;
            string problem = PlanProblem();
            startButton.IsEnabled = problem == null;
            if (problem != null)
            {
                if (calibrationStep == CapAfterX || calibrationStep == CapAfterY) return; //MeasureStepAsync shows the "hover again" text
                statusText.Text = problem;
                return;
            }
            statusText.Text = "Calibrated: pitch " + Pitch().ToString("0") + " px, rows " + RowPitch().ToString("0") + " px apart, scroll step " + stepX.ToString("0.0") + " / " + stepY.ToString("0.0") +
                              " px per click, viewport " + VisibleColumns + " column(s) x " + VisibleRows + " row(s) - press Start.";
        }

        private double X0 => calibration[CapFirst].Value.X;
        private double Y0 => calibration[CapFirst].Value.Y;
        private double Pitch() => calibration[CapSecond].Value.X - calibration[CapFirst].Value.X;
        private double RowPitch() => calibration[CapRow2].Value.Y - calibration[CapFirst].Value.Y;
        private double ViewLeft => calibration[CapLeft].Value.X + EdgeMargin;
        private double ViewRight => calibration[CapRight].Value.X - EdgeMargin;
        private double ViewTop => calibration[CapUp].Value.Y + EdgeMargin;
        private double ViewBottom => calibration[CapDown].Value.Y - EdgeMargin;
        private int VisibleColumns => Pitch() > 0 ? (int)Math.Floor((ViewRight - ViewLeft) / Pitch()) + 1 : 0;
        private int VisibleRows => RowPitch() > 0 ? (int)Math.Floor((ViewBottom - ViewTop) / RowPitch()) + 1 : 0;

        /// <summary>Why the robot cannot start yet; null when everything is in place.</summary>
        private string PlanProblem()
        {
            if (stations.Count == 0) return "Nothing to arrange: generate the hardware first.";
            if (layout.Moves == 0) return "Nothing to move: every station already sits on its row (one group, within the max per row).";
            if (calibrationStep < CaptureCount) return "Waiting for the calibration: " + calibrationStep + " of " + CaptureCount + " captured.";
            if (Pitch() < 8) return "The first and the second station are too close: hover " + stations[0].Name + " then " + stations[1].Name + ".";
            if (RowPitch() < 8) return "Row 2 must be BELOW the default row: hover a point under the first station for the third capture.";
            if (calibration[CapRight].Value.X <= calibration[CapLeft].Value.X + 100 || calibration[CapDown].Value.Y <= calibration[CapUp].Value.Y + 100)
                return "The scrollbar buttons came out in the wrong places: < and > are the ends of the bottom bar, ^ and v the ends of the right bar.";
            if (stepX < 1) return "The horizontal scroll step came out as " + stepX.ToString("0.0") + " px per click: after the robot clicked >, hover the first station at its NEW position (capture 8).";
            if (stepY < 1) return "The vertical scroll step came out as " + stepY.ToString("0.0") + " px per click: after the robot clicked v, hover the first station at its NEW position (capture 9).";
            if (VisibleColumns < layout.MaxPerRow + 1) return "Only " + VisibleColumns + " column(s) fit the canvas - zoom out until at least " + (layout.MaxPerRow + 1) + " fit, scroll to the origin and calibrate again.";
            if (VisibleRows < 2) return "Only " + VisibleRows + " row(s) fit the canvas - zoom out until at least 2 fit, scroll to the origin and calibrate again.";
            if (X0 < ViewLeft || X0 > ViewRight || Y0 < ViewTop || Y0 > ViewBottom) return "The first station must sit inside the canvas, away from its edges.";
            return null;
        }

        // ============================== scrolling by arrow clicks ==============================

        private Point ScreenOf(double canvasX, double canvasY) => new Point(X0 + canvasX - clicksX * stepX, Y0 + canvasY - clicksY * stepY);

        private bool Visible(Point p) => p.X >= ViewLeft - EdgeMargin / 2 && p.X <= ViewRight + EdgeMargin / 2 && p.Y >= ViewTop - EdgeMargin / 2 && p.Y <= ViewBottom + EdgeMargin / 2;

        /// <summary>Scrolls so that the canvas point (ox, oy) lands at the viewport's top-left margin (as far as the clicks allow): counted arrow clicks from the current position.</summary>
        private async Task<bool> ScrollToAsync(double ox, double oy)
        {
            int wantX = Math.Max(0, (int)Math.Round((X0 + ox - ViewLeft) / stepX));
            int wantY = Math.Max(0, (int)Math.Round((Y0 + oy - ViewTop) / stepY));
            if (wantX != clicksX)
            {
                int n = Math.Abs(wantX - clicksX);
                await ClickAsync(wantX > clicksX ? calibration[CapRight].Value : calibration[CapLeft].Value, n, "scrolling");
                clicksX = wantX;
            }
            if (wantY != clicksY)
            {
                int n = Math.Abs(wantY - clicksY);
                await ClickAsync(wantY > clicksY ? calibration[CapDown].Value : calibration[CapUp].Value, n, "scrolling");
                clicksY = wantY;
            }
            return !stopRequested;
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
            if (!int.TryParse(deviceDelayBox.Text, out deviceDelay) || deviceDelay < 0) deviceDelay = 400;

            IntPtr tia = MouseRobot.FindTiaPortalWindow(tiaProcessId());
            if (tia == IntPtr.Zero)
            {
                statusText.Text = "No TIA Portal window found.";
                return;
            }

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
                //the origin: the robot scrolled back after measuring, but make sure (the clicks clamp at the ends)
                await ClickAsync(calibration[CapLeft].Value, 3, "at the origin");
                await ClickAsync(calibration[CapUp].Value, 3, "at the origin");
                clicksX = 0;
                clicksY = 0;

                foreach (NetworkViewLayout.Cell cell in layout.MovesInSafeOrder())
                {
                    if (stopRequested) { outcome = "stopped by you (F12)"; goto Done; }
                    if (MouseRobot.ForegroundWindow != tia) { outcome = "stopped: TIA Portal lost the foreground (another window came up)"; goto Done; }

                    Tuple<int, string> result = await MoveStationAsync(cell, tia, moved + 1);
                    if (result.Item1 < 0)
                    {
                        outcome = stopRequested ? "stopped by you (F12)" : "failed at " + cell.Name + ": " + result.Item2;
                        goto Done;
                    }
                    hops += result.Item1;
                    moved++;
                    Log("Re-arrange: " + cell.Name + " -> row " + (cell.Row + 1) + ", column " + (cell.Column + 1) + " (" + cell.Key + ")" +
                        (result.Item1 > 0 ? " after " + result.Item1 + " hop(s)" : string.Empty));
                    await Task.Delay(deviceDelay);
                }
                await ScrollToAsync(0, 0);
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
        /// One station to its cell. Its lane is its target row (row 2 for a station bound for the first row); the
        /// columns beyond the planned ones (column &gt; max per row) are free on every row, so hops drop there. Journey:
        /// down in hops of one viewport at a free column, then left in hops of one viewport along the lane, then the
        /// one drag into the cell. Returns the hop count and null, or -1 and the reason.
        /// </summary>
        private async Task<Tuple<int, string>> MoveStationAsync(NetworkViewLayout.Cell cell, IntPtr tia, int number)
        {
            int i = cell.Index;
            double pitch = Pitch(), rowPitch = RowPitch();
            double tx = cell.Column * pitch, ty = cell.Row * rowPitch;
            double laneY = (cell.Row == 0 ? 1 : cell.Row) * rowPitch;
            double freeX = layout.MaxPerRow * pitch;              //the first free column of every row
            double spanX = (VisibleColumns - 1) * pitch;           //the farthest a drag can reach
            double spanY = (VisibleRows - 1) * rowPitch;
            int hops = 0;

            while (true)
            {
                if (stopRequested || MouseRobot.ForegroundWindow != tia) return Fail("stopped");
                double x = canvasX[i], y = canvasY[i];

                //the one drag into the cell, when it is within reach
                if (Math.Abs(x - tx) <= spanX && Math.Abs(y - ty) <= spanY)
                {
                    statusText.Text = "Moving " + cell.Name + " to row " + (cell.Row + 1) + ", column " + (cell.Column + 1) + " (" + number + " of " + layout.Moves + ")";
                    if (!await DragOnCanvasAsync(i, Math.Min(x, tx), Math.Min(y, ty), tx, ty)) return Fail(stopRequested ? "stopped" : "the station or its cell is outside the viewport after scrolling");
                    return Tuple.Create(hops, (string)null);
                }
                if (++hops > MaxHops) return Fail("too many hops");

                //down to the lane first (one viewport at most), on a free column
                if (Math.Abs(y - laneY) > 1)
                {
                    double nextY = y + Math.Min(laneY - y, spanY);
                    double parkX = Math.Max(x, freeX);
                    statusText.Text = "Hop " + hops + ": " + cell.Name + " down (" + number + " of " + layout.Moves + ")";
                    if (!await DragOnCanvasAsync(i, Math.Min(x, parkX), y, parkX, nextY)) return Fail(stopRequested ? "stopped" : "a hop left the viewport");
                    continue;
                }

                //left along the lane, one viewport per hop, never onto the planned columns
                double newX = Math.Max(x - spanX, freeX);
                if (newX >= x - 1) return Fail("cannot hop left any further");
                statusText.Text = "Hop " + hops + ": " + cell.Name + " left (" + number + " of " + layout.Moves + ")";
                if (!await DragOnCanvasAsync(i, newX, y, newX, y)) return Fail(stopRequested ? "stopped" : "a hop left the viewport");
            }
        }

        /// <summary>Scrolls so that (ox, oy) is at the viewport's top-left margin, then drags station i from its position to (toX, toY); updates the model.</summary>
        private async Task<bool> DragOnCanvasAsync(int i, double ox, double oy, double toX, double toY)
        {
            if (!await ScrollToAsync(ox, oy)) return false;
            Point from = ScreenOf(canvasX[i], canvasY[i]);
            Point to = ScreenOf(toX, toY);
            if (!Visible(from) || !Visible(to)) return false;
            if (!await DragAsync(from, to, stepDelay)) return false;
            canvasX[i] = toX;
            canvasY[i] = toY;
            await Task.Delay(stepDelay * 6);
            return true;
        }

        private static Tuple<int, string> Fail(string why) => Tuple.Create(-1, why);

        /// <summary>One drag: press, wiggle past the drag threshold, glide to the target in steps, release. False when stopped mid-way.</summary>
        private async Task<bool> DragAsync(Point from, Point to, int delay)
        {
            MouseRobot.MoveTo(from);
            await Task.Delay(delay * 4);
            MouseRobot.LeftDown();
            await Task.Delay(delay * 4);
            MouseRobot.MoveTo(new Point(from.X + 6, from.Y + 6)); //past the drag threshold
            await Task.Delay(delay * 2);

            const int steps = 16;
            for (int s = 1; s <= steps; s++)
            {
                if (stopRequested)
                {
                    MouseRobot.LeftUp();
                    return false;
                }
                MouseRobot.MoveTo(new Point(from.X + (to.X - from.X) * s / steps, from.Y + (to.Y - from.Y) * s / steps));
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

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;
using System.Windows.Shapes;

using Openn._01_Constructor;
using Openn._10_StandardFunctions;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn
{
    /// <summary>
    /// "Re-arrange devices": lays the stations of the last hardware generation out by their Stations.csv Group in
    /// TIA's network (or topology) view with MOUSE DRAGS, because that is the only way to move an object there (no
    /// Openness layout call, editors invisible to UI Automation, keys do nothing - verified 2026-10-09). Two numbers
    /// - X and Y - that the API will not tell us, so a mouse robot learns them the long way round: a guided
    /// calibration (seven hovers with F9, then the robot clicks the scrollbar arrows and the user re-hovers twice,
    /// which measures the scroll step) and a model of every station's canvas position kept by counting arrow
    /// clicks. A far station travels down in hops of one viewport and left along its target row's free columns
    /// (beyond the planned ones), then one drag puts it in its cell. F12 stops, and so does a foreground change.
    /// The window is a step-by-step wizard - colourful on purpose: it underlines what is being worked around, and a
    /// strip under the header keeps the score (what Openness tells us about a device, and the two numbers it does not).
    /// </summary>
    public class ArrangeDevicesWindow : Window
    {
        private const int HotkeyCapture = 0x5001; //F9
        private const int HotkeyStop = 0x5002;    //F12
        private const double EdgeMargin = 60;     //px kept between a grabbed / dropped station and the canvas edges
        private const int StepClicksX = 8;        //clicks the robot makes to measure the horizontal step
        private const int StepClicksY = 6;        //clicks the robot makes to measure the vertical step
        private const int MaxHops = 60;

        //calibration steps: seven are hover + F9; the last two are "hover the first station again" after the robot clicked
        private const int CapFirst = 0, CapSecond = 1, CapRow2 = 2, CapLeft = 3, CapRight = 4, CapUp = 5, CapDown = 6, CapAfterX = 7, CapAfterY = 8, CaptureCount = 9;

        // ---- palette: colourful on purpose
        private static readonly Brush Ink = Frozen(0x2B, 0x2D, 0x42);
        private static readonly Brush Muted = Frozen(0x7B, 0x80, 0x94);
        private static readonly Brush Accent = Frozen(0xFF, 0x7A, 0x00);   //orange: what to hover now
        private static readonly Brush Done = Frozen(0x2E, 0x9E, 0x5B);     //green: captured
        private static readonly Brush Pending = Frozen(0xC9, 0xCD, 0xD6);  //grey: later
        private static readonly Brush Plum = Frozen(0x6C, 0x4A, 0xB6);
        private static readonly Brush Card = Frozen(0xFF, 0xFF, 0xFF);
        private static readonly Brush Paper = Frozen(0xF6, 0xF4, 0xFB);
        private static readonly Brush Station = Frozen(0xB8, 0xC4, 0xD6);
        private static readonly Brush Canvas = Frozen(0xEE, 0xF1, 0xF7);
        private static readonly Brush Red = Frozen(0xC0, 0x39, 0x2B);      //what Openness does not expose
        private static readonly Brush Mint = Frozen(0xDD, 0xF3, 0xE4);
        private static readonly Brush Rose = Frozen(0xFD, 0xE2, 0xE2);

        private readonly IList<NetworkViewLayout.Station> stations;
        private readonly string stationsSource;
        private readonly Func<int?> tiaProcessId;
        private NetworkViewLayout layout;

        private readonly Point?[] calibration = new Point?[CaptureCount];

        //wizard surfaces
        private readonly Ellipse[] stepBadges = new Ellipse[CaptureCount];
        private readonly TextBlock[] stepBadgeTexts = new TextBlock[CaptureCount];
        private readonly TextBlock stepTitle;
        private readonly TextBlock stepInstruction;
        private readonly Border f9Pill;
        private readonly TextBlock f9PillText;
        private readonly ContentControl illustrationHost;
        private readonly TextBlock whimsy;
        private readonly TextBlock numbers;
        private readonly TextBlock planSummary;
        private readonly ListBox planList;
        private readonly TextBox maxPerRowBox;
        private readonly TextBox stepDelayBox;
        private readonly TextBox deviceDelayBox;
        private readonly TextBlock statusText;
        private readonly ProgressBar progress;
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
        private readonly Random dice = new Random();

        private static readonly string[] Whimsies =
        {
            "Two numbers. X and Y. Siemens has them. We don't.",
            "This step exists because a position API doesn't.",
            "Somewhere, an Openness engineer could have typed \"public Point Position\". Five versions later, nobody has.",
            "Openness reports a firmware version to the last digit. Where the device is drawn? Not its department.",
            "A scrollbar button, hovered by hand, because the API has no Scroll() either.",
            "TIA saves every position in the project. Openness opens that project. Draw your own conclusions.",
            "Teaching a robot to hover, so nobody drags 65 boxes by hand ever again.",
            "Eight clicks to learn what a property getter would have told us in a microsecond.",
            "Last one. Then the robot does Siemens' homework.",
        };

        public ArrangeDevicesWindow(IList<NetworkViewLayout.Station> stationsInCreationOrder, string stationsSource, Func<int?> tiaProcessId)
        {
            stations = stationsInCreationOrder;
            this.stationsSource = stationsSource;
            this.tiaProcessId = tiaProcessId;
            layout = new NetworkViewLayout(stations);

            Title = "Openn5 - Re-arrange devices";
            Width = 1040;
            Height = 800;
            MinWidth = 860;
            MinHeight = 600;
            Topmost = true; //stays readable in front of TIA; it is never the foreground window while the robot works
            WindowStartupLocation = WindowStartupLocation.CenterOwner;
            Background = Paper;
            FontFamily = new FontFamily("Segoe UI");

            var root = new Grid();
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

            // ---- header band
            var header = new Border
            {
                Padding = new Thickness(22, 16, 22, 16),
                Background = new LinearGradientBrush(Color.FromRgb(0x6C, 0x4A, 0xB6), Color.FromRgb(0xFF, 0x7A, 0x00), 0),
            };
            var headerStack = new StackPanel();
            headerStack.Children.Add(new TextBlock { Text = "Re-arrange devices", FontSize = 24, FontWeight = FontWeights.Bold, Foreground = Brushes.White });
            headerStack.Children.Add(new TextBlock
            {
                Text = "TIA knows where every station is drawn - it saves it in the project. Openness just won't say: no X, no Y, no Move(). Two numbers, withheld through five API versions. So a mouse robot learns them the long way round, then does the dragging for you.",
                FontSize = 13, Foreground = Brushes.White, Opacity = 0.92, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 0),
            });
            header.Child = headerStack;
            Grid.SetRow(header, 0);
            root.Children.Add(header);

            // ---- the score: what the API tells us about a device, and the two numbers it does not
            var score = new WrapPanel { Margin = new Thickness(22, 12, 22, 0) };
            score.Children.Add(ScoreLabel("Openness tells us"));
            foreach (string known in new[] { "name", "type", "order number", "firmware", "IP address", "modules", "tags" })
                score.Children.Add(Chip("✓ " + known, Mint, Done));
            score.Children.Add(ScoreLabel("but not"));
            foreach (string missing in new[] { "X", "Y", "Move()" })
                score.Children.Add(Chip("✗ " + missing, Rose, Red));
            score.Children.Add(ScoreLabel("- checked in the PublicAPI docs of V15 to V19"));
            Grid.SetRow(score, 1);
            root.Children.Add(score);

            // ---- step strip
            var strip = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(22, 14, 22, 6), HorizontalAlignment = HorizontalAlignment.Left };
            string[] shortLabels = { "1st station", "2nd station", "row 2", "<", ">", "^", "v", "→ again", "↓ again" };
            for (int i = 0; i < CaptureCount; i++)
            {
                var cell = new StackPanel { Width = 92 };
                var grid = new Grid { Width = 32, Height = 32 };
                stepBadges[i] = new Ellipse { Width = 32, Height = 32, Fill = Pending, RenderTransformOrigin = new Point(0.5, 0.5), RenderTransform = new ScaleTransform(1, 1) };
                stepBadgeTexts[i] = new TextBlock { Text = (i + 1).ToString(), Foreground = Brushes.White, FontWeight = FontWeights.Bold, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
                grid.Children.Add(stepBadges[i]);
                grid.Children.Add(stepBadgeTexts[i]);
                cell.Children.Add(grid);
                cell.Children.Add(new TextBlock { Text = shortLabels[i], FontSize = 11, Foreground = Muted, HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 3, 0, 0) });
                strip.Children.Add(cell);
                if (i < CaptureCount - 1)
                    strip.Children.Add(new Rectangle { Width = 14, Height = 2, Fill = Pending, VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(-14, 15, 0, 0) });
            }
            Grid.SetRow(strip, 2);
            root.Children.Add(strip);

            // ---- body: the wizard card + the side panel
            var body = new Grid { Margin = new Thickness(22, 6, 22, 10) };
            body.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(3, GridUnitType.Star) });
            body.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(2, GridUnitType.Star) });

            Border card = MakeCard();
            var cardStack = new StackPanel();
            stepTitle = new TextBlock { FontSize = 20, FontWeight = FontWeights.SemiBold, Foreground = Ink, TextWrapping = TextWrapping.Wrap };
            cardStack.Children.Add(stepTitle);
            illustrationHost = new ContentControl { Margin = new Thickness(0, 12, 0, 12), HorizontalAlignment = HorizontalAlignment.Left };
            cardStack.Children.Add(illustrationHost);
            stepInstruction = new TextBlock { FontSize = 15, Foreground = Ink, TextWrapping = TextWrapping.Wrap, LineHeight = 22 };
            cardStack.Children.Add(stepInstruction);
            f9Pill = new Border
            {
                Background = Accent, CornerRadius = new CornerRadius(16), Padding = new Thickness(16, 6, 16, 6),
                HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(0, 14, 0, 0),
                Effect = new DropShadowEffect { BlurRadius = 10, ShadowDepth = 2, Opacity = 0.25 },
            };
            f9PillText = new TextBlock { Text = "hover its center, then press  F9", Foreground = Brushes.White, FontWeight = FontWeights.Bold, FontSize = 14 };
            f9Pill.Child = f9PillText;
            cardStack.Children.Add(f9Pill);
            whimsy = new TextBlock { FontSize = 12, FontStyle = FontStyles.Italic, Foreground = Muted, Margin = new Thickness(0, 16, 0, 0), TextWrapping = TextWrapping.Wrap };
            cardStack.Children.Add(whimsy);
            card.Child = cardStack;
            Grid.SetColumn(card, 0);
            body.Children.Add(card);

            var side = new StackPanel { Margin = new Thickness(14, 0, 0, 0) };
            Border numbersCard = MakeCard();
            var numbersStack = new StackPanel();
            numbersStack.Children.Add(new TextBlock { Text = "The two numbers (and the few more we need)", FontWeight = FontWeights.SemiBold, Foreground = Plum, FontSize = 13 });
            numbers = new TextBlock { FontFamily = new FontFamily("Consolas"), FontSize = 12, Foreground = Ink, Margin = new Thickness(0, 6, 0, 0), TextWrapping = TextWrapping.Wrap };
            numbersStack.Children.Add(numbers);
            numbersCard.Child = numbersStack;
            side.Children.Add(numbersCard);

            Border planCard = MakeCard();
            planCard.Margin = new Thickness(0, 12, 0, 0);
            var planStack = new StackPanel();
            var planHeader = new DockPanel();
            maxPerRowBox = new TextBox { Text = NetworkViewLayout.DefaultMaxPerRow.ToString(), Width = 40, VerticalContentAlignment = VerticalAlignment.Center };
            maxPerRowBox.TextChanged += (s, e) => RebuildPlan();
            DockPanel.SetDock(maxPerRowBox, Dock.Right);
            planHeader.Children.Add(maxPerRowBox);
            var maxLabel = new TextBlock { Text = "max per row", Foreground = Muted, Margin = new Thickness(0, 0, 6, 0), VerticalAlignment = VerticalAlignment.Center, FontSize = 12 };
            DockPanel.SetDock(maxLabel, Dock.Right);
            planHeader.Children.Add(maxLabel);
            planHeader.Children.Add(new TextBlock { Text = "The plan", FontWeight = FontWeights.SemiBold, Foreground = Plum, FontSize = 13, VerticalAlignment = VerticalAlignment.Center });
            planStack.Children.Add(planHeader);
            planSummary = new TextBlock { FontSize = 12, Foreground = Muted, Margin = new Thickness(0, 4, 0, 4), TextWrapping = TextWrapping.Wrap };
            planStack.Children.Add(planSummary);
            planList = new ListBox { FontFamily = new FontFamily("Consolas"), FontSize = 11, BorderThickness = new Thickness(0), Background = Brushes.Transparent, MaxHeight = 200 };
            ScrollViewer.SetHorizontalScrollBarVisibility(planList, ScrollBarVisibility.Disabled);
            var planItem = new DataTemplate();
            var planText = new FrameworkElementFactory(typeof(TextBlock));
            planText.SetBinding(TextBlock.TextProperty, new System.Windows.Data.Binding("."));
            planText.SetValue(TextBlock.TextWrappingProperty, TextWrapping.Wrap);
            planItem.VisualTree = planText;
            planList.ItemTemplate = planItem;
            planStack.Children.Add(planList);
            var advanced = new Expander { Header = "Timing", FontSize = 12, Foreground = Muted, Margin = new Thickness(0, 8, 0, 0) };
            var timing = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 4, 0, 0) };
            timing.Children.Add(new TextBlock { Text = "step delay (ms)", VerticalAlignment = VerticalAlignment.Center, Foreground = Ink });
            stepDelayBox = new TextBox { Text = "25", Width = 44, Margin = new Thickness(6, 0, 14, 0), VerticalContentAlignment = VerticalAlignment.Center };
            timing.Children.Add(stepDelayBox);
            timing.Children.Add(new TextBlock { Text = "pause per station (ms)", VerticalAlignment = VerticalAlignment.Center, Foreground = Ink });
            deviceDelayBox = new TextBox { Text = "400", Width = 52, Margin = new Thickness(6, 0, 0, 0), VerticalContentAlignment = VerticalAlignment.Center };
            timing.Children.Add(deviceDelayBox);
            advanced.Content = timing;
            planStack.Children.Add(advanced);
            planCard.Child = planStack;
            side.Children.Add(planCard);
            Grid.SetColumn(side, 1);
            body.Children.Add(side);

            Grid.SetRow(body, 3);
            root.Children.Add(body);

            // ---- footer: status, progress, buttons
            var footer = new Border { Padding = new Thickness(22, 10, 22, 14), Background = Card, BorderBrush = Pending, BorderThickness = new Thickness(0, 1, 0, 0) };
            var footerGrid = new Grid();
            footerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            footerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var statusStack = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            statusText = new TextBlock { FontSize = 13, Foreground = Ink, TextWrapping = TextWrapping.Wrap };
            statusStack.Children.Add(statusText);
            progress = new ProgressBar { Height = 8, Margin = new Thickness(0, 6, 16, 0), Minimum = 0, Maximum = 1, Value = 0, Visibility = Visibility.Collapsed, Foreground = Done };
            statusStack.Children.Add(progress);
            Grid.SetColumn(statusStack, 0);
            footerGrid.Children.Add(statusStack);
            var buttons = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
            resetButton = MakeButton("Reset", Muted);
            resetButton.Click += (s, e) => ResetCalibration();
            buttons.Children.Add(resetButton);
            startButton = MakeButton("Start the robot", Accent);
            startButton.FontWeight = FontWeights.Bold;
            startButton.IsEnabled = false;
            startButton.Click += async (s, e) => await RunAsync();
            buttons.Children.Add(startButton);
            stopButton = MakeButton("Stop (F12)", Plum);
            stopButton.IsEnabled = false;
            stopButton.Click += (s, e) => stopRequested = true;
            buttons.Children.Add(stopButton);
            var closeButton = MakeButton("Close", Muted);
            closeButton.Click += (s, e) => Close();
            buttons.Children.Add(closeButton);
            Grid.SetColumn(buttons, 1);
            footerGrid.Children.Add(buttons);
            footer.Child = footerGrid;
            Grid.SetRow(footer, 4);
            root.Children.Add(footer);

            Content = root;

            RebuildPlan();
            ShowStep();
            SourceInitialized += (s, e) => RegisterHotkeys();
            Loaded += (s, e) => Pulse(f9Pill);
            Closing += (s, e) => { if (running || calibrating) stopRequested = true; };
            Closed += (s, e) => UnregisterHotkeys();
        }

        // ============================== look ==============================

        private static Brush Frozen(byte r, byte g, byte b)
        {
            var brush = new SolidColorBrush(Color.FromRgb(r, g, b));
            brush.Freeze();
            return brush;
        }

        private static Border MakeCard() => new Border
        {
            Background = Card, CornerRadius = new CornerRadius(10), Padding = new Thickness(18, 16, 18, 16),
            Effect = new DropShadowEffect { BlurRadius = 14, ShadowDepth = 2, Opacity = 0.12 },
        };

        private static TextBlock ScoreLabel(string text) => new TextBlock
        {
            Text = text, Foreground = Muted, FontSize = 12, FontStyle = FontStyles.Italic, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 8, 4),
        };

        private static Border Chip(string text, Brush background, Brush foreground) => new Border
        {
            Background = background, CornerRadius = new CornerRadius(10), Padding = new Thickness(9, 2, 9, 3), Margin = new Thickness(0, 0, 6, 4),
            Child = new TextBlock { Text = text, Foreground = foreground, FontSize = 12, FontWeight = FontWeights.SemiBold },
        };

        private static Button MakeButton(string caption, Brush background)
        {
            var button = new Button
            {
                Content = caption, Background = background, Foreground = Brushes.White, BorderThickness = new Thickness(0),
                Padding = new Thickness(16, 7, 16, 7), Margin = new Thickness(8, 0, 0, 0), FontSize = 13, Cursor = System.Windows.Input.Cursors.Hand,
            };
            var template = new ControlTemplate(typeof(Button));
            var border = new FrameworkElementFactory(typeof(Border));
            border.SetValue(Border.BackgroundProperty, new TemplateBindingExtension(BackgroundProperty));
            border.SetValue(Border.CornerRadiusProperty, new CornerRadius(8));
            border.SetValue(Border.PaddingProperty, new TemplateBindingExtension(PaddingProperty));
            var presenter = new FrameworkElementFactory(typeof(ContentPresenter));
            presenter.SetValue(HorizontalAlignmentProperty, HorizontalAlignment.Center);
            presenter.SetValue(VerticalAlignmentProperty, VerticalAlignment.Center);
            border.AppendChild(presenter);
            template.VisualTree = border;
            var disabled = new Trigger { Property = IsEnabledProperty, Value = false };
            disabled.Setters.Add(new Setter(OpacityProperty, 0.45));
            template.Triggers.Add(disabled);
            button.Template = template;
            return button;
        }

        private static void Pulse(UIElement element)
        {
            var animation = new DoubleAnimation(1.0, 0.55, TimeSpan.FromMilliseconds(700)) { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever };
            element.BeginAnimation(OpacityProperty, animation);
        }

        // ============================== the wizard ==============================

        private static readonly string[] StepTitles =
        {
            "The first station", "The second station", "Where row 2 begins",
            "The  <  button", "The  >  button", "The  ^  button", "The  v  button",
            "The horizontal step", "The vertical step",
        };

        private string StepInstruction(int step)
        {
            string first = stations.Count > 0 ? stations[0].Name : "(none)";
            string second = stations.Count > 1 ? stations[1].Name : "(none)";
            switch (step)
            {
                case CapFirst: return "Scroll the view fully left and fully up. Zoom until at least " + (layout.MaxPerRow + 1) + " columns fit, then leave the zoom alone.\nHover the center of " + first + ".";
                case CapSecond: return "Hover the center of " + second + ".";
                case CapRow2: return "Hover the spot straight below " + first + ", one row down - where row 2 begins.";
                case CapLeft: return "Hover the  <  button at the left end of the bottom scrollbar.";
                case CapRight: return "Hover the  >  button at the right end of the bottom scrollbar.";
                case CapUp: return "Hover the  ^  button at the top of the right scrollbar.";
                case CapDown: return "Hover the  v  button at the bottom of the right scrollbar. Then the robot clicks.";
                case CapAfterX: return "The robot clicked  >  " + StepClicksX + " times. Hover the center of " + first + " where it is NOW.";
                default: return "The robot clicked  v  " + StepClicksY + " times. Hover the center of " + first + " where it is NOW.";
            }
        }

        /// <summary>The card for the current step: title, drawing, instruction, the F9 pill, a line of whimsy.</summary>
        private void ShowStep()
        {
            int step = Math.Min(calibrationStep, CaptureCount - 1);
            bool complete = calibrationStep >= CaptureCount;
            for (int i = 0; i < CaptureCount; i++)
            {
                bool done = i < calibrationStep;
                bool current = i == calibrationStep && !complete;
                stepBadges[i].Fill = done ? Done : current ? Accent : Pending;
                stepBadgeTexts[i].Text = done ? "✓" : (i + 1).ToString();
                var scale = (ScaleTransform)stepBadges[i].RenderTransform;
                scale.BeginAnimation(ScaleTransform.ScaleXProperty, null);
                scale.BeginAnimation(ScaleTransform.ScaleYProperty, null);
                scale.ScaleX = scale.ScaleY = 1;
                if (current)
                {
                    var pulse = new DoubleAnimation(1.0, 1.18, TimeSpan.FromMilliseconds(600)) { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever };
                    scale.BeginAnimation(ScaleTransform.ScaleXProperty, pulse);
                    scale.BeginAnimation(ScaleTransform.ScaleYProperty, pulse);
                }
            }

            if (running)
            {
                stepTitle.Text = "The robot is at work";
                stepInstruction.Text = "Hands off the mouse and the keyboard. F12 stops it; so does any other window coming to the front.";
                illustrationHost.Content = DrawIllustration(-1);
                f9Pill.Visibility = Visibility.Collapsed;
                whimsy.Text = "Every drag below is one line of API Siemens never wrote.";
                return;
            }
            if (complete)
            {
                stepTitle.Text = "Calibrated. Two numbers Siemens wouldn't tell, learned the hard way.";
                stepInstruction.Text = "Pitch, row pitch, scroll step and viewport are known. Press Start and keep your hands off the mouse until it reports done.";
                illustrationHost.Content = DrawIllustration(-1);
                f9Pill.Visibility = Visibility.Collapsed;
                whimsy.Text = Whimsies[Whimsies.Length - 1];
                return;
            }
            if (calibrating)
            {
                stepTitle.Text = "Clicking...";
                stepInstruction.Text = "The robot is clicking the arrow. Watch the picture slide, then wait for the next instruction.";
                illustrationHost.Content = DrawIllustration(step);
                f9Pill.Visibility = Visibility.Collapsed;
                whimsy.Text = "Counting clicks, because counting pixels was not an option either.";
                return;
            }

            stepTitle.Text = "Step " + (step + 1) + " of " + CaptureCount + " - " + StepTitles[step];
            stepInstruction.Text = StepInstruction(step);
            illustrationHost.Content = DrawIllustration(step);
            f9Pill.Visibility = Visibility.Visible;
            f9PillText.Text = step >= CapAfterX ? "hover its center again, then press  F9" : step >= CapLeft ? "hover the button, then press  F9" : "hover its center, then press  F9";
            whimsy.Text = Whimsies[Math.Min(step, Whimsies.Length - 1)];
        }

        /// <summary>A small drawing of the TIA canvas: the default row, both scrollbars, and the thing to hover in orange.</summary>
        private UIElement DrawIllustration(int step)
        {
            const double w = 380, h = 150, bar = 14;
            var canvas = new System.Windows.Controls.Canvas { Width = w, Height = h };
            canvas.Children.Add(new Rectangle { Width = w - bar, Height = h - bar, Fill = Canvas, Stroke = Pending, StrokeThickness = 1, RadiusX = 3, RadiusY = 3 });

            //the scrollbars with their arrow buttons
            AddRect(canvas, 0, h - bar, w - bar, bar, Paper, Pending);
            AddRect(canvas, w - bar, 0, bar, h - bar, Paper, Pending);
            AddButton(canvas, 1, h - bar + 1, bar - 2, "<", step == CapLeft);
            AddButton(canvas, w - 2 * bar + 1, h - bar + 1, bar - 2, ">", step == CapRight || step == CapAfterX);
            AddButton(canvas, w - bar + 1, 1, bar - 2, "^", step == CapUp);
            AddButton(canvas, w - bar + 1, h - 2 * bar + 1, bar - 2, "v", step == CapDown || step == CapAfterY);

            //the default row, shifted for the two measuring steps
            double shiftX = step == CapAfterX ? -34 : 0, shiftY = step == CapAfterY ? -22 : 0;
            double x0 = 28 + shiftX, y0 = 34 + shiftY;
            for (int i = 0; i < 9; i++)
            {
                bool hot = (step == CapFirst || step == CapAfterX || step == CapAfterY) ? i == 0 : step == CapSecond && i == 1;
                double x = x0 + i * 40;
                if (x < 2 || x > w - bar - 30) continue;
                AddRect(canvas, x, y0, 28, 20, hot ? Accent : Station, hot ? Accent : Pending);
                if (hot) AddCursor(canvas, x + 14, y0 + 10);
            }
            if (step == CapRow2)
            {
                var ghost = new Rectangle { Width = 28, Height = 20, Stroke = Accent, StrokeThickness = 2, StrokeDashArray = new DoubleCollection { 3, 2 }, Fill = Brushes.Transparent };
                System.Windows.Controls.Canvas.SetLeft(ghost, x0);
                System.Windows.Controls.Canvas.SetTop(ghost, y0 + 40);
                canvas.Children.Add(ghost);
                AddCursor(canvas, x0 + 14, y0 + 50);
            }
            if (step == CapAfterX || step == CapAfterY)
            {
                var motion = new TextBlock { Text = step == CapAfterX ? "⟵ ⟵ ⟵  slid left" : "⟰  slid up", Foreground = Plum, FontSize = 11, FontStyle = FontStyles.Italic };
                System.Windows.Controls.Canvas.SetLeft(motion, 200);
                System.Windows.Controls.Canvas.SetTop(motion, 90);
                canvas.Children.Add(motion);
            }
            if (step < 0)
            {
                //the plan: rows of boxes, the robot's work
                for (int r = 0; r < Math.Min(4, Math.Max(1, layout.RowCount)); r++)
                    for (int c = 0; c < Math.Min(layout.MaxPerRow, 7); c++)
                        AddRect(canvas, 28 + c * 40, 34 + r * 28, 28, 20, r == 0 ? Station : Done, Pending);
            }
            return canvas;
        }

        private static void AddRect(System.Windows.Controls.Canvas canvas, double x, double y, double width, double height, Brush fill, Brush stroke)
        {
            var rect = new Rectangle { Width = width, Height = height, Fill = fill, Stroke = stroke, StrokeThickness = 1, RadiusX = 2, RadiusY = 2 };
            System.Windows.Controls.Canvas.SetLeft(rect, x);
            System.Windows.Controls.Canvas.SetTop(rect, y);
            canvas.Children.Add(rect);
        }

        private static void AddButton(System.Windows.Controls.Canvas canvas, double x, double y, double size, string glyph, bool hot)
        {
            var grid = new Grid { Width = size, Height = size };
            grid.Children.Add(new Rectangle { Fill = hot ? Accent : Pending, RadiusX = 2, RadiusY = 2 });
            grid.Children.Add(new TextBlock { Text = glyph, FontSize = 9, FontWeight = FontWeights.Bold, Foreground = hot ? Brushes.White : Muted, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center });
            System.Windows.Controls.Canvas.SetLeft(grid, x);
            System.Windows.Controls.Canvas.SetTop(grid, y);
            canvas.Children.Add(grid);
            if (hot) AddCursor(canvas, x + size / 2, y + size / 2);
        }

        /// <summary>The pointer with its tip exactly on the point to hover; a dot and a pulsing ring mark that point.</summary>
        private static void AddCursor(System.Windows.Controls.Canvas canvas, double x, double y)
        {
            var ring = new Ellipse { Width = 14, Height = 14, Stroke = Accent, StrokeThickness = 2, Fill = Brushes.Transparent, RenderTransformOrigin = new Point(0.5, 0.5), RenderTransform = new ScaleTransform(1, 1) };
            System.Windows.Controls.Canvas.SetLeft(ring, x - 7);
            System.Windows.Controls.Canvas.SetTop(ring, y - 7);
            canvas.Children.Add(ring);
            var grow = new DoubleAnimation(0.6, 2.0, TimeSpan.FromMilliseconds(1100)) { RepeatBehavior = RepeatBehavior.Forever };
            var fade = new DoubleAnimation(1.0, 0.0, TimeSpan.FromMilliseconds(1100)) { RepeatBehavior = RepeatBehavior.Forever };
            ((ScaleTransform)ring.RenderTransform).BeginAnimation(ScaleTransform.ScaleXProperty, grow);
            ((ScaleTransform)ring.RenderTransform).BeginAnimation(ScaleTransform.ScaleYProperty, grow);
            ring.BeginAnimation(OpacityProperty, fade);

            var dot = new Ellipse { Width = 4, Height = 4, Fill = Brushes.White, Stroke = Ink, StrokeThickness = 1 };
            System.Windows.Controls.Canvas.SetLeft(dot, x - 2);
            System.Windows.Controls.Canvas.SetTop(dot, y - 2);
            canvas.Children.Add(dot);

            var pointer = new Polygon
            {
                Points = new PointCollection { new Point(0, 0), new Point(0, 16), new Point(4, 12), new Point(7, 18), new Point(10, 16), new Point(7, 11), new Point(12, 11) },
                Fill = Ink, Stroke = Brushes.White, StrokeThickness = 1,
            };
            System.Windows.Controls.Canvas.SetLeft(pointer, x);
            System.Windows.Controls.Canvas.SetTop(pointer, y);
            canvas.Children.Add(pointer);
        }

        private void RefreshNumbers()
        {
            var lines = new List<string>();
            if (calibrationStep > CapSecond) lines.Add("pitch        " + Pitch().ToString("0") + " px between stations");
            if (calibrationStep > CapRow2) lines.Add("row pitch    " + RowPitch().ToString("0") + " px between rows");
            if (calibrationStep > CapDown) lines.Add("canvas       " + (calibration[CapRight].Value.X - calibration[CapLeft].Value.X).ToString("0") + " x " + (calibration[CapDown].Value.Y - calibration[CapUp].Value.Y).ToString("0") + " px");
            if (stepX > 0) lines.Add("step >       " + stepX.ToString("0.0") + " px per click");
            if (stepY > 0) lines.Add("step v       " + stepY.ToString("0.0") + " px per click");
            if (calibrationStep > CapDown && Pitch() > 0 && RowPitch() > 0) lines.Add("viewport     " + VisibleColumns + " columns x " + VisibleRows + " rows");
            var captured = new List<string>();
            for (int i = 0; i < CaptureCount; i++)
                if (calibration[i].HasValue) captured.Add((i + 1) + ": " + (int)calibration[i].Value.X + "," + (int)calibration[i].Value.Y);
            if (captured.Count > 0) lines.Add("captures     " + string.Join("   ", captured));
            numbers.Text = lines.Count > 0 ? string.Join("\n", lines) : "nothing yet - the first hover is the origin";
        }

        private void RebuildPlan()
        {
            int maxPerRow;
            if (!int.TryParse(maxPerRowBox.Text, out maxPerRow) || maxPerRow < 1) maxPerRow = NetworkViewLayout.DefaultMaxPerRow;
            layout = new NetworkViewLayout(stations, maxPerRow);
            planSummary.Text = stations.Count + " station(s) in creation order (" + stationsSource + ") grouped by the Stations.csv Group column: " + layout.RowCount + " row(s), " + layout.Moves + " move(s).";
            planList.Items.Clear();
            foreach (string line in layout.Describe()) planList.Items.Add(line);
            if (stations.Count == 0) planList.Items.Add("(no stations - generate the hardware first)");
            UpdateState();
        }

        private void UpdateState()
        {
            RefreshNumbers();
            if (running) return;
            string problem = PlanProblem();
            startButton.IsEnabled = problem == null;
            if (problem == null)
                statusText.Text = "Ready: pitch " + Pitch().ToString("0") + " px, rows " + RowPitch().ToString("0") + " px, step " + stepX.ToString("0.0") + " / " + stepY.ToString("0.0") + " px per click, viewport " + VisibleColumns + " x " + VisibleRows + ".";
            else if (!(calibrationStep == CapAfterX || calibrationStep == CapAfterY) || !problem.StartsWith("Waiting"))
                statusText.Text = problem;
            ShowStep();
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
            calibrationStep++;
            statusText.Text = "Got it: " + ((int)p.X) + ", " + ((int)p.Y) + ".";
            UpdateState();

            //after the last button the robot clicks > a few times and waits for the re-hover; after that it scrolls back and clicks v
            if (calibrationStep == CapAfterX)
                await MeasureStepAsync(calibration[CapRight].Value, StepClicksX, "Hover the first station again (it slid left) and press F9.");
            else if (calibrationStep == CapAfterY)
            {
                stepX = (calibration[CapFirst].Value.X - calibration[CapAfterX].Value.X) / StepClicksX;
                await ClickAsync(calibration[CapLeft].Value, StepClicksX + 3, "scrolling back to the left");
                await MeasureStepAsync(calibration[CapDown].Value, StepClicksY, "Hover the first station again (it slid up) and press F9.");
            }
            else if (calibrationStep == CaptureCount)
            {
                stepY = (calibration[CapFirst].Value.Y - calibration[CapAfterY].Value.Y) / StepClicksY;
                await ClickAsync(calibration[CapUp].Value, StepClicksY + 3, "scrolling back to the top");
                clicksX = 0;
                clicksY = 0;
            }
            UpdateState();
        }

        private async Task MeasureStepAsync(Point button, int clicks, string thenAsk)
        {
            calibrating = true;
            ShowStep();
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
            ShowStep();
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
            for (int i = 0; i < CaptureCount; i++) calibration[i] = null;
            calibrationStep = 0;
            stepX = stepY = 0;
            statusText.Text = "Calibration cleared. Scroll the view to the origin and start over.";
            UpdateState();
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
            if (stepX < 1) return "The horizontal scroll step came out as " + stepX.ToString("0.0") + " px per click: after the robot clicked >, hover the first station at its NEW position (step 8).";
            if (stepY < 1) return "The vertical scroll step came out as " + stepY.ToString("0.0") + " px per click: after the robot clicked v, hover the first station at its NEW position (step 9).";
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
            progress.Visibility = Visibility.Visible;
            progress.Maximum = Math.Max(1, layout.Moves);
            progress.Value = 0;
            ShowStep();
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
                    progress.Value = moved;
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
            statusText.Text = summary + ". Check TIA; Reset and calibrate again before another run (the stations are no longer on the default row).";
            calibrationStep = CaptureCount; //keep the numbers visible; Start stays disabled until Reset + a fresh calibration
            startButton.IsEnabled = false;
            ShowStep();
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

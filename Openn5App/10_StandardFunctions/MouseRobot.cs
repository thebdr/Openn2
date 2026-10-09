using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Openn._10_StandardFunctions
{
    /// <summary>
    /// Win32 glue for the "Re-arrange devices" robot (ArrangeDevicesWindow): the cursor position for the
    /// calibration, absolute mouse moves and button events through SendInput for the drags, the foreground
    /// window (the robot refuses to drag inside any window but TIA's), and global hotkeys so the capture / stop
    /// keys work while TIA Portal has the focus. Coordinates are what GetCursorPos reports in this process;
    /// SendInput normalizes them over the same virtual screen, so capture and playback agree whatever the DPI mode.
    /// </summary>
    internal static class MouseRobot
    {
        [StructLayout(LayoutKind.Sequential)]
        private struct POINT { public int X; public int Y; }

        [StructLayout(LayoutKind.Sequential)]
        private struct MOUSEINPUT
        {
            public int dx;
            public int dy;
            public uint mouseData;
            public uint dwFlags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct INPUT
        {
            public uint type;
            public MOUSEINPUT mi;
        }

        private const uint INPUT_MOUSE = 0;
        private const uint MOUSEEVENTF_MOVE = 0x0001;
        private const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
        private const uint MOUSEEVENTF_LEFTUP = 0x0004;
        private const uint MOUSEEVENTF_ABSOLUTE = 0x8000;
        private const uint MOUSEEVENTF_VIRTUALDESK = 0x4000;
        private const int SM_XVIRTUALSCREEN = 76, SM_YVIRTUALSCREEN = 77, SM_CXVIRTUALSCREEN = 78, SM_CYVIRTUALSCREEN = 79;

        public const int WM_HOTKEY = 0x0312;

        [DllImport("user32.dll")] private static extern bool GetCursorPos(out POINT point);
        [DllImport("user32.dll", SetLastError = true)] private static extern uint SendInput(uint count, INPUT[] inputs, int size);
        [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll")] private static extern bool ShowWindow(IntPtr hWnd, int cmd);
        [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr hWnd);
        [DllImport("user32.dll")] private static extern int GetSystemMetrics(int index);
        [DllImport("user32.dll", SetLastError = true)] private static extern bool RegisterHotKey(IntPtr hWnd, int id, uint modifiers, uint vk);
        [DllImport("user32.dll", SetLastError = true)] private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

        /// <summary>Where the mouse is now, in this process's screen coordinates.</summary>
        public static System.Windows.Point CursorPosition
        {
            get
            {
                POINT p;
                GetCursorPos(out p);
                return new System.Windows.Point(p.X, p.Y);
            }
        }

        /// <summary>The virtual screen (all monitors) in the same coordinates.</summary>
        public static System.Windows.Rect VirtualScreen =>
            new System.Windows.Rect(GetSystemMetrics(SM_XVIRTUALSCREEN), GetSystemMetrics(SM_YVIRTUALSCREEN),
                                    GetSystemMetrics(SM_CXVIRTUALSCREEN), GetSystemMetrics(SM_CYVIRTUALSCREEN));

        public static IntPtr ForegroundWindow => GetForegroundWindow();

        /// <summary>Restores a minimized window and brings it to the front; false when Windows refused (focus rules).</summary>
        public static bool BringToFront(IntPtr hWnd)
        {
            if (hWnd == IntPtr.Zero) return false;
            if (IsIconic(hWnd)) ShowWindow(hWnd, 9); //SW_RESTORE
            return SetForegroundWindow(hWnd);
        }

        /// <summary>The main window of the first TIA Portal process that has one (the attached one when its id is known).</summary>
        public static IntPtr FindTiaPortalWindow(int? preferredProcessId)
        {
            try
            {
                if (preferredProcessId.HasValue)
                {
                    Process p = Process.GetProcessById(preferredProcessId.Value);
                    if (p.MainWindowHandle != IntPtr.Zero) return p.MainWindowHandle;
                }
            }
            catch { /* gone */ }
            foreach (Process p in Process.GetProcessesByName("Siemens.Automation.Portal"))
                if (p.MainWindowHandle != IntPtr.Zero) return p.MainWindowHandle;
            return IntPtr.Zero;
        }

        /// <summary>Moves the mouse to an absolute screen position (an input event, so the window under it sees a real move).</summary>
        public static void MoveTo(System.Windows.Point p) => Send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, p);

        public static void LeftDown() => Send(MOUSEEVENTF_LEFTDOWN, CursorPosition);

        public static void LeftUp() => Send(MOUSEEVENTF_LEFTUP, CursorPosition);

        private static void Send(uint flags, System.Windows.Point p)
        {
            System.Windows.Rect screen = VirtualScreen;
            var input = new INPUT
            {
                type = INPUT_MOUSE,
                mi = new MOUSEINPUT
                {
                    dx = (int)Math.Round((p.X - screen.X) * 65535.0 / Math.Max(1, screen.Width - 1)),
                    dy = (int)Math.Round((p.Y - screen.Y) * 65535.0 / Math.Max(1, screen.Height - 1)),
                    dwFlags = flags,
                },
            };
            if ((flags & MOUSEEVENTF_MOVE) == 0)
            {
                //button events at the current position: no coordinates needed
                input.mi.dx = 0;
                input.mi.dy = 0;
            }
            SendInput(1, new[] { input }, Marshal.SizeOf(typeof(INPUT)));
        }

        /// <summary>Registers a global hotkey (no modifiers) on a window; the window's message hook receives WM_HOTKEY with the id.</summary>
        public static bool RegisterHotkey(IntPtr hWnd, int id, uint virtualKey) => RegisterHotKey(hWnd, id, 0, virtualKey);

        public static void UnregisterHotkey(IntPtr hWnd, int id) => UnregisterHotKey(hWnd, id);

        // ============================== screen pixels (the scrollbar reading) ==============================

        /// <summary>The colour at a screen point (the average of the 3x3 pixels around it); black when the screen cannot be read.</summary>
        public static System.Drawing.Color SampleColor(System.Windows.Point p)
        {
            try
            {
                using (var bitmap = new System.Drawing.Bitmap(3, 3))
                {
                    using (var g = System.Drawing.Graphics.FromImage(bitmap))
                        g.CopyFromScreen((int)p.X - 1, (int)p.Y - 1, 0, 0, new System.Drawing.Size(3, 3));
                    int r = 0, gr = 0, b = 0;
                    for (int y = 0; y < 3; y++)
                        for (int x = 0; x < 3; x++)
                        {
                            System.Drawing.Color c = bitmap.GetPixel(x, y);
                            r += c.R; gr += c.G; b += c.B;
                        }
                    return System.Drawing.Color.FromArgb(r / 9, gr / 9, b / 9);
                }
            }
            catch { return System.Drawing.Color.Black; }
        }

        /// <summary>One screen pixel; black when it cannot be read.</summary>
        public static System.Drawing.Color PixelAt(int x, int y)
        {
            try
            {
                using (var bitmap = new System.Drawing.Bitmap(1, 1))
                {
                    using (var g = System.Drawing.Graphics.FromImage(bitmap))
                        g.CopyFromScreen(x, y, 0, 0, new System.Drawing.Size(1, 1));
                    return bitmap.GetPixel(0, 0);
                }
            }
            catch { return System.Drawing.Color.Black; }
        }

        /// <summary>The pixels of one screen row from xFrom to xTo inclusive; null when the screen cannot be read.</summary>
        public static System.Drawing.Color[] ReadRow(int y, int xFrom, int xTo)
        {
            int width = xTo - xFrom + 1;
            if (width < 1) return null;
            try
            {
                using (var bitmap = new System.Drawing.Bitmap(width, 1))
                {
                    using (var g = System.Drawing.Graphics.FromImage(bitmap))
                        g.CopyFromScreen(xFrom, y, 0, 0, new System.Drawing.Size(width, 1));
                    var row = new System.Drawing.Color[width];
                    for (int x = 0; x < width; x++) row[x] = bitmap.GetPixel(x, 0);
                    return row;
                }
            }
            catch { return null; }
        }

        /// <summary>Sum of the channel differences - below ~48 two colours read as the same thing.</summary>
        public static int ColorDistance(System.Drawing.Color a, System.Drawing.Color b) =>
            Math.Abs(a.R - b.R) + Math.Abs(a.G - b.G) + Math.Abs(a.B - b.B);

        public const uint VK_F9 = 0x78;
        public const uint VK_F12 = 0x7B;
    }
}

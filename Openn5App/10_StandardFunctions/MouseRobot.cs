using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Openn._10_StandardFunctions
{
    /// <summary>
    /// Win32 glue for the "Re-arrange devices" robot (ArrangeDevicesWindow): the cursor position for the
    /// calibration, absolute mouse moves and button events through SendInput for the drags, the foreground
    /// window (the robot refuses to drag inside any window but TIA's), global hotkeys (so the capture / stop
    /// keys work while TIA Portal has the focus), the window under a point (a click is refused when another process's
    /// window covers it) and window bounds (the wizard moves off the canvas while the robot works). Coordinates are what GetCursorPos reports in this process;
    /// SendInput normalizes them over the same virtual screen, so capture and playback agree whatever the DPI mode.
    /// </summary>
    internal static class MouseRobot
    {
        [StructLayout(LayoutKind.Sequential)]
        private struct POINT { public int X; public int Y; }

        [StructLayout(LayoutKind.Sequential)]
        private struct RECT { public int Left, Top, Right, Bottom; }

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
        [DllImport("user32.dll")] private static extern IntPtr WindowFromPoint(POINT point);
        [DllImport("user32.dll")] private static extern IntPtr GetAncestor(IntPtr hWnd, uint flags);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int max);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr hWnd, System.Text.StringBuilder text, int max);
        [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
        [DllImport("user32.dll")] private static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [DllImport("user32.dll")] private static extern uint GetDoubleClickTime();

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

        /// <summary>The id of the process that owns a window; 0 for no window.</summary>
        public static int ProcessIdOf(IntPtr hWnd)
        {
            if (hWnd == IntPtr.Zero) return 0;
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            return (int)pid;
        }

        /// <summary>The top-level window under a screen point - what a click there would hit (a topmost window in front of TIA, say).</summary>
        public static IntPtr TopLevelWindowAt(System.Windows.Point p)
        {
            IntPtr hit = WindowFromPoint(new POINT { X = (int)Math.Round(p.X), Y = (int)Math.Round(p.Y) });
            if (hit == IntPtr.Zero) return IntPtr.Zero;
            IntPtr root = GetAncestor(hit, 2); //GA_ROOT
            return root == IntPtr.Zero ? hit : root;
        }

        /// <summary>'title' (process) - for the messages that name the window that got in the way.</summary>
        public static string Describe(IntPtr hWnd)
        {
            if (hWnd == IntPtr.Zero) return "(no window)";
            var title = new System.Text.StringBuilder(256);
            GetWindowText(hWnd, title, title.Capacity);
            var cls = new System.Text.StringBuilder(256);
            GetClassName(hWnd, cls, cls.Capacity);
            string process = "?";
            try { process = Process.GetProcessById(ProcessIdOf(hWnd)).ProcessName; } catch { /* gone */ }
            return "'" + (title.Length > 0 ? title.ToString() : cls.ToString()) + "' (" + process + ")";
        }

        /// <summary>A window's screen rectangle; Rect.Empty for no window.</summary>
        public static System.Windows.Rect WindowBounds(IntPtr hWnd)
        {
            RECT r;
            if (hWnd == IntPtr.Zero || !GetWindowRect(hWnd, out r)) return System.Windows.Rect.Empty;
            return new System.Windows.Rect(r.Left, r.Top, Math.Max(0, r.Right - r.Left), Math.Max(0, r.Bottom - r.Top));
        }

        /// <summary>Moves and sizes a window (screen px) without activating it or changing its z-order.</summary>
        public static void SetWindowBounds(IntPtr hWnd, System.Windows.Rect bounds)
        {
            if (hWnd == IntPtr.Zero || bounds.IsEmpty) return;
            SetWindowPos(hWnd, IntPtr.Zero, (int)bounds.X, (int)bounds.Y, (int)bounds.Width, (int)bounds.Height, 0x0004 | 0x0010); //SWP_NOZORDER | SWP_NOACTIVATE
        }

        /// <summary>The system double-click time in ms: two presses closer than this, at the same spot, make a double-click.</summary>
        public static int DoubleClickTime => (int)GetDoubleClickTime();

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

        public const uint VK_F9 = 0x78;
        public const uint VK_F12 = 0x7B;
    }
}

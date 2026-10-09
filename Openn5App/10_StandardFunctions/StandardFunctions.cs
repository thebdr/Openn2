using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Runtime.Remoting.Messaging;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Controls;
using System.Windows.Forms;
using System.Windows.Navigation;
using System.Windows.Media;
using System.Collections.ObjectModel;
using static System.Windows.Forms.VisualStyles.VisualStyleElement;

namespace Openn._10_StandardFunctions
{
    class StandardFunctions
    {
        public static FileInfo GetFileDialog(string startPath = "C:\\", string filter = "All Files|*.*")
        {
            System.Windows.Forms.OpenFileDialog openDialog = new System.Windows.Forms.OpenFileDialog
            {
                InitialDirectory = startPath,
                Filter = filter,
                FilterIndex = 2,
                RestoreDirectory = true,
                Multiselect = false
            };

            if (openDialog.ShowDialog() == System.Windows.Forms.DialogResult.OK)
            {
                return new FileInfo(openDialog.FileName);
            }
            return null;
        }

        public static FileInfo GetFolderDialog(string startPath = "C:\\", string filter = "All Files|*.*")
        {
            System.Windows.Forms.FolderBrowserDialog openDialog = new System.Windows.Forms.FolderBrowserDialog
            {
                Description = "Choose a folder",
                SelectedPath = startPath, 
            };

            if (openDialog.ShowDialog() == System.Windows.Forms.DialogResult.OK)
            {
                return new FileInfo(openDialog.SelectedPath);
            }
            return null;
        }
    }


    /// <summary>
    /// The session log: one static sink that any number of ListViews display (the main window's log area and
    /// the pop-out <see cref="LogWindow"/>). Every view gets every line, severity-colored, through its own
    /// visibility filter; a view attached later is seeded with the whole session history. <see cref="Log"/> is
    /// thread-safe; everything else runs on the UI thread.
    /// </summary>
    public static class LogsManager
    {
        /// <summary>One attached view and its own visibility filter (null = show all).</summary>
        private sealed class Sink
        {
            public System.Windows.Controls.ListView View;
            public Func<string, bool> Filter;
        }

        //UI-thread state: the attached views and the full session history (a view attached later is seeded from it)
        private static readonly List<Sink> sinks = new List<Sink>();
        private static readonly List<string> history = new List<string>();

        //cross-thread state: the UI dispatcher (bound by the first attach) and the lines logged before any view existed
        private static readonly object pendingLock = new object();
        private static System.Windows.Threading.Dispatcher dispatcher;
        private static readonly List<string> pendingMessages = new List<string>();

        //frozen brushes: created once, usable from any thread
        private static readonly Brush ErrorBrush = Freeze(new SolidColorBrush(Color.FromRgb(0xB0, 0x00, 0x00)));
        private static readonly Brush WarningBrush = Freeze(new SolidColorBrush(Color.FromRgb(0xB2, 0x6B, 0x00)));
        private static readonly Brush SuccessBrush = Freeze(new SolidColorBrush(Color.FromRgb(0x1E, 0x6E, 0x1E)));
        private static readonly Brush DefaultBrush = Freeze(new SolidColorBrush(Color.FromRgb(0x20, 0x20, 0x20)));

        private static Brush Freeze(SolidColorBrush brush)
        {
            brush.Freeze();
            return brush;
        }

        /// <summary>
        /// Adds a ListView to the log. The first view binds the UI dispatcher and receives the messages logged
        /// before the window existed (startup/version selection); any later view (the pop-out window) starts
        /// with the whole session history. UI thread only.
        /// </summary>
        public static void AttachLogView(System.Windows.Controls.ListView view)
        {
            if (view == null || sinks.Any(s => s.View == view)) return;

            var sink = new Sink { View = view };
            sinks.Add(sink);
            foreach (string line in history)
                AddItem(sink, line, scroll: false);
            ScrollToLastVisible(sink);

            List<string> flush = null;
            lock (pendingLock)
            {
                if (dispatcher == null)
                {
                    dispatcher = view.Dispatcher;
                    flush = new List<string>(pendingMessages);
                    pendingMessages.Clear();
                }
            }
            if (flush != null)
            {
                foreach (string line in flush)
                    Append(line);
            }
        }

        /// <summary>
        /// Stops feeding a view (the pop-out window closing). The history and the other views are untouched.
        /// </summary>
        public static void DetachLogView(System.Windows.Controls.ListView view)
        {
            sinks.RemoveAll(s => s.View == view);
        }

        /// <summary>
        /// Thread-safe: messages logged from the backend worker thread are
        /// marshalled to the UI dispatcher.
        /// </summary>
        public static void Log(string Message)
        {
            string line = DateTime.Now.ToString("HH:mm:ss") + " " + Message;

            //file mirror first - works from any thread and survives a UI freeze
            lock (fileLock)
            {
                if (logFile != null) logFile.WriteLine(line);
            }

            System.Windows.Threading.Dispatcher target;
            lock (pendingLock)
            {
                target = dispatcher;
                if (target == null)
                {
                    pendingMessages.Add(line);
                    return;
                }
            }

            if (target.CheckAccess())
                Append(line);
            else
                target.BeginInvoke((Action)(() => Append(line)));
        }

        /// <summary>Empties the history and every attached view. UI thread only.</summary>
        public static void ClearLog()
        {
            history.Clear();
            foreach (Sink sink in sinks)
                sink.View.Items.Clear();
        }

        /// <summary>The raw text of a log entry (for clipboard copy).</summary>
        public static string TextOf(object listViewItem)
        {
            var item = listViewItem as System.Windows.Controls.ListViewItem;
            return item != null ? (string)item.Tag : listViewItem?.ToString();
        }

        /// <summary>
        /// Copies a view's selected lines (every line when nothing is selected or <paramref name="selectedOnly"/>
        /// is false, the filter notwithstanding) to the clipboard. A locked clipboard is logged, not thrown.
        /// UI thread only.
        /// </summary>
        public static void CopyLines(System.Windows.Controls.ListView view, bool selectedOnly)
        {
            System.Collections.IEnumerable source =
                selectedOnly && view.SelectedItems.Count > 0 ? view.SelectedItems : (System.Collections.IEnumerable)view.Items;

            var text = new StringBuilder();
            foreach (object item in source)
                text.AppendLine(TextOf(item));
            if (text.Length == 0) return;

            try
            {
                System.Windows.Clipboard.SetText(text.ToString());
            }
            catch (Exception ex)
            {
                Log("Could not copy to clipboard \n" + ex.Message); //clipboard can be locked by another process
            }
        }

        #region View filter

        /// <summary>
        /// Shows only the entries of one view matching the predicate (null = show all), the existing ones and
        /// everything logged afterwards. Each view has its own filter. UI thread only.
        /// </summary>
        public static void SetFilter(System.Windows.Controls.ListView view, Func<string, bool> filter)
        {
            Sink sink = sinks.FirstOrDefault(s => s.View == view);
            if (sink == null) return;

            sink.Filter = filter;
            foreach (object entry in view.Items)
            {
                var item = entry as System.Windows.Controls.ListViewItem;
                if (item != null)
                    item.Visibility = Passes(sink, (string)item.Tag) ? System.Windows.Visibility.Visible : System.Windows.Visibility.Collapsed;
            }
        }

        /// <summary>
        /// The filter a pattern box asks for: null (show all) for an empty pattern, else a case-insensitive
        /// regex match. An invalid pattern also shows all and reports itself so the box can be marked.
        /// </summary>
        public static Func<string, bool> FilterFor(string pattern, out bool invalidPattern)
        {
            invalidPattern = false;
            if (string.IsNullOrWhiteSpace(pattern)) return null;

            try
            {
                var regex = new System.Text.RegularExpressions.Regex(pattern, System.Text.RegularExpressions.RegexOptions.IgnoreCase);
                return line => regex.IsMatch(line);
            }
            catch (ArgumentException)
            {
                invalidPattern = true;
                return null;
            }
        }

        private static bool Passes(Sink sink, string line)
        {
            Func<string, bool> filter = sink.Filter;
            return filter == null || filter(line);
        }

        #endregion View filter

        #region File log

        private static readonly object fileLock = new object();
        private static StreamWriter logFile;

        /// <summary>Path of the current session log file; null while file logging is off.</summary>
        public static string LogFilePath { get; private set; }

        /// <summary>
        /// Starts mirroring the log to a timestamped file in the given folder,
        /// seeded with the whole session history so the file is complete from
        /// session start. UI thread only; returns the file path.
        /// </summary>
        public static string StartFileLog(string folder)
        {
            lock (fileLock)
            {
                if (logFile != null) return LogFilePath;

                Directory.CreateDirectory(folder);
                LogFilePath = Path.Combine(folder, "Openn5_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".log");
                var writer = new StreamWriter(LogFilePath, false, Encoding.UTF8) { AutoFlush = true };
                try
                {
                    foreach (string line in history)
                        writer.WriteLine(line);
                    logFile = writer; //published only after seeding succeeded - StopFileLog owns the disposal from here
                }
                catch
                {
                    //a WriteLine failure (disk full, I/O error) while seeding must not orphan the open handle: it is not
                    //in logFile yet, so StopFileLog could not reach it and the fresh .log would stay write-locked
                    writer.Dispose();
                    LogFilePath = null;
                    throw;
                }
                return LogFilePath;
            }
        }

        public static void StopFileLog()
        {
            lock (fileLock)
            {
                if (logFile == null) return;
                logFile.Dispose();
                logFile = null;
                LogFilePath = null;
            }
        }

        #endregion File log

        /// <summary>Records the line and shows it in every attached view. UI thread only.</summary>
        private static void Append(string line)
        {
            history.Add(line);
            foreach (Sink sink in sinks)
                AddItem(sink, line, scroll: true);
        }

        /// <summary>
        /// Adds the line to one view as a severity-colored item. The raw text is kept in Tag so copy-to-clipboard
        /// does not depend on the visual tree. Scrolls to the new entry when asked but never selects it
        /// (selection belongs to the user).
        /// </summary>
        private static void AddItem(Sink sink, string line, bool scroll)
        {
            var item = new System.Windows.Controls.ListViewItem
            {
                Content = line,
                Tag = line,
                Foreground = SeverityBrush(line),
            };
            if (!Passes(sink, line))
                item.Visibility = System.Windows.Visibility.Collapsed;

            sink.View.Items.Add(item);
            if (scroll && item.Visibility == System.Windows.Visibility.Visible)
                sink.View.ScrollIntoView(item);
        }

        private static void ScrollToLastVisible(Sink sink)
        {
            for (int i = sink.View.Items.Count - 1; i >= 0; i--)
            {
                var item = sink.View.Items[i] as System.Windows.Controls.ListViewItem;
                if (item != null && item.Visibility == System.Windows.Visibility.Visible)
                {
                    sink.View.ScrollIntoView(item);
                    return;
                }
            }
        }

        private static Brush SeverityBrush(string line)
        {
            if (Contains(line, "ERROR") || Contains(line, "error"))
                return ErrorBrush;
            if (Contains(line, "CANCELLED") || Contains(line, "ABORTED") || Contains(line, "SKIPPED") || Contains(line, "Cancel requested") || Contains(line, "Skipped:"))
                return WarningBrush;
            if (Contains(line, " Ok") || Contains(line, "loaded") || Contains(line, "written") || Contains(line, "Attached to") || Contains(line, "saved"))
                return SuccessBrush;
            return DefaultBrush;
        }

        private static bool Contains(string line, string token) =>
            line.IndexOf(token, StringComparison.Ordinal) >= 0;
    }

}

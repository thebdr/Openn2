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


    public static class LogsManager
    {
        private static System.Windows.Controls.ListView lvLogView;
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
        /// Binds the log output to a ListView and flushes messages logged before
        /// the window existed (e.g. during startup/version selection).
        /// </summary>
        public static void AttachLogView(System.Windows.Controls.ListView logView)
        {
            lock (pendingMessages)
            {
                lvLogView = logView;
                foreach (string message in pendingMessages)
                    Append(message);
                pendingMessages.Clear();
            }
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

            System.Windows.Controls.ListView view;
            lock (pendingMessages)
            {
                view = lvLogView;
                if (view == null)
                {
                    pendingMessages.Add(line);
                    return;
                }
            }

            if (view.Dispatcher.CheckAccess())
                Append(line);
            else
                view.Dispatcher.BeginInvoke((Action)(() => Append(line)));
        }

        /// <summary>The raw text of a log entry (for clipboard copy).</summary>
        public static string TextOf(object listViewItem)
        {
            var item = listViewItem as System.Windows.Controls.ListViewItem;
            return item != null ? (string)item.Tag : listViewItem?.ToString();
        }

        #region View filter

        private static Func<string, bool> visibilityFilter;

        /// <summary>
        /// Shows only entries matching the predicate (null = show all). Applies to
        /// the existing entries and to everything logged afterwards. UI thread only.
        /// </summary>
        public static void SetFilter(Func<string, bool> filter)
        {
            visibilityFilter = filter;
            if (lvLogView == null) return;

            foreach (object entry in lvLogView.Items)
            {
                var item = entry as System.Windows.Controls.ListViewItem;
                if (item != null)
                    item.Visibility = PassesFilter((string)item.Tag) ? System.Windows.Visibility.Visible : System.Windows.Visibility.Collapsed;
            }
        }

        private static bool PassesFilter(string line)
        {
            Func<string, bool> filter = visibilityFilter;
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
        /// seeded with everything already in the view so the file is complete from
        /// session start. UI thread only; returns the file path.
        /// </summary>
        public static string StartFileLog(string folder)
        {
            lock (fileLock)
            {
                if (logFile != null) return LogFilePath;

                Directory.CreateDirectory(folder);
                LogFilePath = Path.Combine(folder, "Openn2_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".log");
                var writer = new StreamWriter(LogFilePath, false, Encoding.UTF8) { AutoFlush = true };

                if (lvLogView != null)
                {
                    foreach (object entry in lvLogView.Items)
                        writer.WriteLine(TextOf(entry));
                }

                logFile = writer;
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

        /// <summary>
        /// Adds the line as a severity-colored item. The raw text is kept in Tag
        /// so copy-to-clipboard does not depend on the visual tree. Scrolls to the
        /// new entry but does not select it (selection belongs to the user).
        /// </summary>
        private static void Append(string line)
        {
            var item = new System.Windows.Controls.ListViewItem
            {
                Content = line,
                Tag = line,
                Foreground = SeverityBrush(line),
            };
            if (!PassesFilter(line))
                item.Visibility = System.Windows.Visibility.Collapsed;

            lvLogView.Items.Add(item);
            if (item.Visibility == System.Windows.Visibility.Visible)
                lvLogView.ScrollIntoView(item);
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

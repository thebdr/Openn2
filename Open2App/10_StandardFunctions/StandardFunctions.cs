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

        private static void Append(string line)
        {
            lvLogView.Items.Add(line);
            lvLogView.ScrollIntoView(lvLogView.Items[lvLogView.Items.Count - 1]);
            lvLogView.SelectedIndex = lvLogView.Items.Count - 1;
        }
    }


    public class MvvmBaseModel : INotifyPropertyChanged
    {
        public event PropertyChangedEventHandler PropertyChanged;

        protected void OnPropertyChanged(string propertyName)
        {
            if (PropertyChanged != null)
                PropertyChanged(this, new PropertyChangedEventArgs(propertyName));
        }
    }

    public class LogViewModel : MvvmBaseModel
    {

        string _Text1;
        Brush _BackgroundColor;

        public string Text1 
        { 
            get  => _Text1;

            set 
            { 
                _Text1 = value;
                OnPropertyChanged("Text1");
            } 
        }

        public Brush BackgroundColor {
            get => _BackgroundColor;  
            set 
            {
                _BackgroundColor = value;
                OnPropertyChanged("BackgroundColor");
            } 
        }

    }


    public static class LogsManager2
    {
        public static ObservableCollection<LogViewModel> LogsList { get; set; } = new ObservableCollection<LogViewModel>();

        public static void Log(string Message)
        {
            LogViewModel line = new LogViewModel();
            line.Text1 = Message;
            line.BackgroundColor = (SolidColorBrush)new BrushConverter().ConvertFromString("#76EB7E");

            LogsList.Add(line);
        }
    }

}

using Siemens.Engineering.HW;
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
        private static System.Windows.Controls.ListView lvLogView = ((MainWindow)System.Windows.Application.Current.MainWindow).lbLogView;
        public static void Log(string Message)
        {
            //lvLogView.Items.Insert(0, DateTime.Now.ToString("HH:mm:ss") + " " + Message);
            lvLogView.Items.Add(DateTime.Now.ToString("HH:mm:ss") + " " + Message);
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

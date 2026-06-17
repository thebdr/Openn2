using System.Collections.Generic;
using System.Linq;
using System.Windows;
using System.Windows.Controls;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Startup dialog that lets the user pick which installed TIA Portal Openness
    /// version the application binds to. Shown before any Siemens assembly is loaded;
    /// the choice is fixed for the lifetime of the process.
    /// </summary>
    public class OpennessVersionDialog : Window
    {
        private readonly ComboBox versionComboBox;

        private OpennessVersionDialog(IReadOnlyList<OpennessInstallation> installations)
        {
            Title = "Openn2 - Select TIA Portal Version";
            SizeToContent = SizeToContent.WidthAndHeight;
            ResizeMode = ResizeMode.NoResize;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;

            versionComboBox = new ComboBox
            {
                ItemsSource = installations,
                SelectedItem = installations.Last(), // newest installed version
                MinWidth = 300,
                Margin = new Thickness(0, 8, 0, 12),
            };

            var okButton = new Button { Content = "OK", IsDefault = true, Width = 80, Margin = new Thickness(0, 0, 8, 0) };
            okButton.Click += (s, e) => { DialogResult = true; };
            var cancelButton = new Button { Content = "Exit", IsCancel = true, Width = 80 };

            var buttonRow = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
            buttonRow.Children.Add(okButton);
            buttonRow.Children.Add(cancelButton);

            var layout = new StackPanel { Margin = new Thickness(12) };
            layout.Children.Add(new TextBlock { Text = "TIA Portal version to work with:" });
            layout.Children.Add(versionComboBox);
            layout.Children.Add(buttonRow);

            Content = layout;
        }

        /// <summary>Returns the chosen installation, or null when the user cancelled.</summary>
        public static OpennessInstallation ShowSelection(IReadOnlyList<OpennessInstallation> installations)
        {
            var dialog = new OpennessVersionDialog(installations);
            return dialog.ShowDialog() == true ? (OpennessInstallation)dialog.versionComboBox.SelectedItem : null;
        }
    }
}

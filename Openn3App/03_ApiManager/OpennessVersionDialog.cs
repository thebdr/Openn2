using System.Collections.Generic;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Startup dialog that lets the user pick which installed TIA Portal Openness
    /// version the application binds to. Shown before any Siemens assembly is loaded;
    /// the choice is fixed for the lifetime of the process.
    /// Keyboard-first: the list is focused on open (newest version preselected),
    /// arrows navigate, Enter confirms, double-click confirms, Esc exits.
    /// </summary>
    public class OpennessVersionDialog : Window
    {
        private const int VisibleItems = 5;

        private readonly ListBox versionListBox;

        private OpennessVersionDialog(IReadOnlyList<OpennessInstallation> installations)
        {
            Title = "Openn2 - Select TIA Portal Version";
            SizeToContent = SizeToContent.WidthAndHeight;
            ResizeMode = ResizeMode.NoResize;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;

            versionListBox = new ListBox
            {
                ItemsSource = installations,
                SelectedItem = installations.Last(), //newest installed version
                MinWidth = 320,
                Margin = new Thickness(0, 8, 0, 12),
            };
            ScrollViewer.SetVerticalScrollBarVisibility(versionListBox, ScrollBarVisibility.Auto);
            versionListBox.Loaded += (s, e) =>
            {
                //fix the height to ~5 rows once the real item height is known, focus
                //the list and make sure the preselected (newest) version is visible
                if (versionListBox.Items.Count > 0)
                {
                    var container = (ListBoxItem)versionListBox.ItemContainerGenerator.ContainerFromIndex(0);
                    if (container != null && container.ActualHeight > 0)
                        versionListBox.Height = container.ActualHeight * VisibleItems + 8; //+border/padding
                }
                versionListBox.ScrollIntoView(versionListBox.SelectedItem);
                versionListBox.Focus();
                if (versionListBox.SelectedItem != null)
                {
                    var selected = (ListBoxItem)versionListBox.ItemContainerGenerator.ContainerFromItem(versionListBox.SelectedItem);
                    if (selected != null) selected.Focus();
                }
            };
            versionListBox.MouseDoubleClick += (s, e) => Confirm();
            versionListBox.KeyDown += (s, e) =>
            {
                if (e.Key == Key.Enter)
                {
                    Confirm();
                    e.Handled = true;
                }
            };

            var okButton = new Button { Content = "OK", IsDefault = true, Width = 80, Margin = new Thickness(0, 0, 8, 0) };
            okButton.Click += (s, e) => Confirm();
            var cancelButton = new Button { Content = "Exit", IsCancel = true, Width = 80 };

            var buttonRow = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
            buttonRow.Children.Add(okButton);
            buttonRow.Children.Add(cancelButton);

            var layout = new StackPanel { Margin = new Thickness(12) };
            layout.Children.Add(new TextBlock { Text = "TIA Portal version to work with (Enter to confirm):" });
            layout.Children.Add(versionListBox);
            layout.Children.Add(buttonRow);

            Content = layout;
        }

        private void Confirm()
        {
            if (versionListBox.SelectedItem != null)
                DialogResult = true;
        }

        /// <summary>Returns the chosen installation, or null when the user cancelled.</summary>
        public static OpennessInstallation ShowSelection(IReadOnlyList<OpennessInstallation> installations)
        {
            var dialog = new OpennessVersionDialog(installations);
            return dialog.ShowDialog() == true ? (OpennessInstallation)dialog.versionListBox.SelectedItem : null;
        }
    }
}

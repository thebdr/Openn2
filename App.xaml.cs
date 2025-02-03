using System;
using System.Collections.Generic;
using System.Configuration;
using System.Data;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;

namespace Openn
{

    public partial class App : Application
    {
        public bool isApplicationActive;
        public void App_Activated(object sender, EventArgs e)
        {
            // Application activated (focused)
            this.isApplicationActive = true;
        }

        public void App_Deactivated(object sender, EventArgs e)
        {
            // Application deactivated (unfocused)
            this.isApplicationActive = false;
        }
    }
}

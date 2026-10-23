"""sycon5 - the SYCON.net GUI driver of Sycon5App (pywinauto / UI Automation + Win32).

Every operation is a proven mechanism from the spike (see Sycon5App/README.md); the saved SYCON_net.xml,
decoded by `readback`, is the verification oracle. Nothing here saves a project unless the caller asks for it.
"""
from .driver import SyconDriver, DriverError  # noqa: F401
from .readback import read_project, Project, Device  # noqa: F401

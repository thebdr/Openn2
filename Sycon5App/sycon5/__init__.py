"""sycon5 - the SYCON.net GUI driver of Sycon5App (pywinauto / UI Automation + Win32).

Every operation is a proven mechanism from the spike (see Sycon5App/README.md); the saved SYCON_net.xml,
decoded by `readback`, is the verification oracle. Nothing here saves a project unless the caller asks for it.
The driver is loaded on first use (PEP 562): `sycon5.gui` / `sycon5.workspace` import without pywinauto - the users'
GUI launched with a Python that is not the repo venv showed nothing (user 2026-10-25: "launch_gui.py opens nothing").
"""
_LAZY = {"SyconDriver": "driver", "DriverError": "driver", "read_project": "readback", "Project": "readback", "Device": "readback"}
__all__ = sorted(_LAZY)


def __getattr__(name):
    if name in _LAZY:
        import importlib
        module = importlib.import_module("." + _LAZY[name], __name__)
        return getattr(module, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))

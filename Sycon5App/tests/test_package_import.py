"""The package imports without the driver's dependencies (user 2026-10-25: "launch_gui.py opens nothing" - the GUI
launched with a Python that had no pywinauto): `sycon5.gui` / `sycon5.workspace` load with pywinauto, comtypes and
pywin32 hidden; `from sycon5 import SyconDriver` still resolves (lazily) with them present."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
HIDE = ("import sys\n"
        "class Hide:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('pywinauto', 'comtypes', 'win32gui', 'win32api', 'win32con', 'win32process', 'olefile'):\n"
        "            raise ImportError('hidden: ' + name)\n"
        "sys.meta_path.insert(0, Hide())\n"
        "sys.path.insert(0, %r)\n" % APP)


def run(code):
    return subprocess.run([sys.executable, "-I", "-c", HIDE + code], capture_output=True, text=True, cwd=HERE)


def test_the_gui_imports_without_the_driver_packages():
    r = run("import sycon5.workspace, sycon5.gui; print('ok', sycon5.gui.RUN_OUTPUT)")
    assert r.returncode == 0 and r.stdout.strip() == "ok run output", r.stdout + r.stderr


def test_the_driver_is_loaded_lazily():
    r = run("import sycon5\n"
            "try:\n    sycon5.SyconDriver\nexcept ImportError as ex:\n    print('lazy:', str(ex).startswith('hidden'))\n"
            "try:\n    sycon5.nothing\nexcept AttributeError:\n    print('attr ok')")
    assert r.returncode == 0 and r.stdout.split() == ["lazy:", "True", "attr", "ok"], r.stdout + r.stderr
    import sycon5
    from sycon5 import SyconDriver, read_project   # the real thing, with the packages present
    assert sycon5.SyconDriver is SyconDriver and callable(read_project) and "SyconDriver" in sycon5.__all__


def test_the_launcher_reexecs_into_the_venv():
    """The launcher started by another interpreter calls the venv's python; here: the venv's own python re-launched under
    SYCON5_NO_REEXEC skips the GUI itself (a window) - only the decision is checked, through a stub child."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("launch_gui", os.path.join(APP, "launch_gui.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.VENV_PYTHON.endswith(os.path.join(".venv", "Scripts", "python.exe"))
    assert mod.same_file(sys.executable, sys.executable) and not mod.same_file(sys.executable, mod.VENV_PYTHON + ".x")

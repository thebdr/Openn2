# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the I/O List Checker (gui_designer.py) - a ONE-FOLDER build.

One-folder (NOT one-file) and NO UPX, on purpose: a one-file self-extractor + UPX packing are
the two biggest false-positive triggers for corporate antivirus. A plain one-folder exe (+ DLLs)
with version metadata is far less likely to be quarantined. The read-only CSV tables load from the
bundle (config._HERE = sys._MEIPASS = the app folder); the WRITABLE default params.yaml is relocated
by config.py to %LOCALAPPDATA%/Pipeline2/, and designer projects live in folders they pick.

On a managed PC the guaranteed fix is still IT allow-listing the exe (by SHA-256/path) or
code-signing it (see build_designer.bat for an optional signtool step).

Build:  pip install pyinstaller
        build_designer.bat            (or:  pyinstaller --noconfirm gui_designer.spec)
Output: dist/IOListChecker/IOListChecker.exe   (ship the whole IOListChecker/ folder, or zip it)
"""
import os

HERE = os.path.abspath(SPECPATH)
_icon = os.path.join(HERE, "assets", "Pipeline2.ico")
_version = os.path.join(HERE, "version_info.txt")

# read-only config the app needs at runtime (resolved via sys._MEIPASS = the app folder)
datas = [(os.path.join(HERE, "config", f), "config") for f in (
    "column_map.csv", "signal_types.csv", "iolist_columns.csv", "permanent_parts.csv", "params.yaml")]
datas += [(os.path.join(HERE, "assets", "Pipeline2.png"), "assets")]

a = Analysis(
    ["gui_designer.py"],
    pathex=[HERE],
    binaries=[],
    datas=datas,
    # these safetydb submodules are imported lazily (from . import X) inside validate(), which
    # PyInstaller's static scan can miss - pin them so Phase 0A + the error registry work frozen.
    hiddenimports=["ruamel.yaml", "safetydb.iolist_checks", "safetydb.error_management"],
    hookspath=[],
    runtime_hooks=[],
    # keep the build slim + guarantee the heavy generation modules never sneak in
    excludes=["block_builders", "block_templates", "softwareblocks", "blockshells",
              "hardware", "interface_tool", "diagnostic_opc", "verify", "editor", "tksheet",
              "numpy", "pandas", "matplotlib", "gui", "run"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,         # one-folder: binaries/datas go in COLLECT, not the exe
    name="IOListChecker",
    console=False,                 # windowed app (no console)
    upx=False,                     # UPX packing is a common AV false-positive trigger
    version=_version if os.path.exists(_version) else None,
    icon=_icon if os.path.exists(_icon) else None,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="IOListChecker")

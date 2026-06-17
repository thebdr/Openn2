"""Project manager for the safety-DB tools (used by gui.py and gui_designer.py).

A *project* is a self-contained folder:

    <project>/
        project.yaml        the run parameters (same schema as config_project/project_params.yaml)
        Input/              optional local copies of the I/O List + C&E workbooks
        Output/             where the validation logs / artifacts are written (the OUTPUT_PATHS tree)

`config_project/project_params.yaml` stays the built-in default project. Relative `io_list`/`ce` paths in a
project.yaml resolve against the project folder (see config.load_params), so a project with
"copy inputs on save" enabled is fully portable - zip it (archive_project) and it is complete.

Pure functions only (no tkinter); the GUIs wire these to a File menu. ruamel round-trip
preserves the project.yaml comments/key order across saves.
"""
from __future__ import annotations
import json
import os
import shutil
import zipfile

from pipeline2.core import config

PROJECT_FILE = "project.yaml"
INPUTS_DIR = "Input"
OUTPUT_DIR = "Output"
_INPUT_KEYS = ("io_list", "ce")           # params keys whose .path is a workbook to copy


# --------------------------------------------------------------------------- #
# ruamel round-trip helpers (shared with the GUIs)                            #
# --------------------------------------------------------------------------- #
def _yaml():
    from ruamel.yaml import YAML
    y = YAML()                 # round-trip mode: preserves comments + key order
    y.preserve_quotes = True
    y.width = 4096
    return y


def load_doc(path: str):
    """Load a project.yaml (or params.yaml) as a comment-preserving document (CommentedMap)."""
    with open(path, encoding="utf-8") as f:
        return _yaml().load(f) or {}


def dump_doc(doc, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        _yaml().dump(doc, f)


# --------------------------------------------------------------------------- #
# project paths                                                               #
# --------------------------------------------------------------------------- #
def project_yaml(folder_or_yaml: str) -> str:
    """The project.yaml path for a folder, or the file itself if one was passed."""
    if os.path.isdir(folder_or_yaml):
        return os.path.join(folder_or_yaml, PROJECT_FILE)
    return folder_or_yaml


def project_dir(project_path: str) -> str:
    return os.path.dirname(os.path.abspath(project_path))


def project_name(project_path: str) -> str:
    return os.path.basename(project_dir(project_path))


def _ensure_layout(folder: str) -> None:
    os.makedirs(folder, exist_ok=True)
    os.makedirs(os.path.join(folder, INPUTS_DIR), exist_ok=True)
    os.makedirs(os.path.join(folder, OUTPUT_DIR), exist_ok=True)


# --------------------------------------------------------------------------- #
# new / open / save                                                           #
# --------------------------------------------------------------------------- #
def default_doc():
    """A fresh project document, seeded from config_project/project_params.yaml (keeping its comments) with
    the input paths blanked and the project knobs defaulted."""
    doc = load_doc(config.PARAMS_FILE)
    for key in _INPUT_KEYS:
        if key in doc and "path" in doc[key]:
            doc[key]["path"] = ""
    doc.setdefault("copy_inputs_on_save", False)
    doc.setdefault("language", "en")
    doc.setdefault("output_dir", "Output")     # a project writes into <project>/Output (relative -> portable)
    return doc


def new_project(folder: str) -> str:
    """Create the project folder layout + a default project.yaml. Returns its path."""
    _ensure_layout(folder)
    path = project_yaml(folder)
    dump_doc(default_doc(), path)
    return path


def open_project(folder_or_yaml: str) -> str:
    """Resolve to an existing project.yaml. Raises FileNotFoundError if absent."""
    path = project_yaml(folder_or_yaml)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return path


def _copy_inputs(doc, folder: str) -> None:
    """Copy each input workbook into <folder>/Input/ and repoint its param to the relative
    'Input/<name>'. Missing/blank/already-local paths are left untouched."""
    inputs = os.path.join(folder, INPUTS_DIR)
    os.makedirs(inputs, exist_ok=True)
    for key in _INPUT_KEYS:
        if key not in doc or "path" not in doc[key]:
            continue
        src = str(doc[key]["path"] or "").strip()
        if not src:
            continue
        abs_src = src if os.path.isabs(src) else os.path.normpath(os.path.join(folder, src))
        if not os.path.isfile(abs_src):
            continue
        name = os.path.basename(abs_src)
        dst = os.path.join(inputs, name)
        if os.path.abspath(abs_src) != os.path.abspath(dst):
            shutil.copy2(abs_src, dst)
        doc[key]["path"] = f"{INPUTS_DIR}/{name}"          # forward slash: portable in YAML


def save_project(doc, project_path: str, copy_inputs: bool = False) -> str:
    """Write `doc` to project_path. With copy_inputs, first copy the I/O List + C&E into
    Input/ and rewrite their paths to be project-relative. Returns the project path."""
    folder = project_dir(project_path)
    _ensure_layout(folder)
    if copy_inputs:
        _copy_inputs(doc, folder)
    dump_doc(doc, project_path)
    return project_path


def save_project_as(doc, new_folder: str, copy_inputs: bool = False) -> str:
    """Save `doc` as a new project in new_folder (creating the layout). Returns the new path."""
    _ensure_layout(new_folder)
    return save_project(doc, project_yaml(new_folder), copy_inputs)


# --------------------------------------------------------------------------- #
# archive                                                                      #
# --------------------------------------------------------------------------- #
def archive_project(project_path: str, base_name: str | None = None,
                    add_datetime: bool = False, now=None) -> str:
    """Zip the whole project folder into '<base_name>[_YYYYMMDD_HHMMSS].zip' beside it.
    `now` (a datetime) is injectable for tests; defaults to datetime.now(). Returns the zip path."""
    folder = project_dir(project_path)
    parent = os.path.dirname(folder)
    base = (base_name or project_name(project_path)).strip() or project_name(project_path)
    if add_datetime:
        if now is None:
            from datetime import datetime
            now = datetime.now()
        base = f"{base}_{now.strftime('%Y%m%d_%H%M%S')}"
    zip_path = os.path.join(parent, base + ".zip")
    root = os.path.basename(folder)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, files in os.walk(folder):
            for fn in files:
                full = os.path.join(dirpath, fn)
                if os.path.abspath(full) == os.path.abspath(zip_path):
                    continue                                # never zip the archive into itself
                arc = os.path.join(root, os.path.relpath(full, folder))
                zf.write(full, arc)
    return zip_path


# --------------------------------------------------------------------------- #
# last-opened-project state (user-writable, survives a frozen .exe)            #
# --------------------------------------------------------------------------- #
def _state_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Pipeline2")


def _state_file() -> str:
    return os.path.join(_state_dir(), "state.json")


def get_last_project() -> str | None:
    try:
        with open(_state_file(), encoding="utf-8") as f:
            return json.load(f).get("last_project") or None
    except (OSError, ValueError):
        return None


def set_last_project(path: str) -> None:
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        with open(_state_file(), "w", encoding="utf-8") as f:
            json.dump({"last_project": os.path.abspath(path)}, f)
    except OSError:
        pass

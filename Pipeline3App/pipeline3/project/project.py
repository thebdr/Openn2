"""Folder-based Project Manager - pure functions, no tkinter (the GUI wires these). Ported from
Pipeline2's project.py and extended for Pipeline3's per-project ISOLATION: a project owns its config
+ treatments, not just its inputs/outputs.

A project is a self-contained folder:

    <project>/
        project.yaml       run params (same schema as config_project/project_params.yaml)
        Input/             local copies of the I/O List + C&E workbooks
        Output/            the generated OUTPUT_PATHS tree (<project>/Output)
        config_project/    the project's OWN copy of the config CSVs (column_map, signal_types, rules…)
        user_input/        the project's OWN treatment registry (error_management.csv)

`config_project/project_params.yaml` stays the built-in default (= no project open). Relative
io_list/ce paths in a project.yaml resolve against the project folder (config.load_params), and the
GUI points the loaders at <project>/config_project + <project>/user_input via config.use_project() -
so a project is fully isolated AND portable (zip the folder and it is complete). ruamel round-trip
keeps project.yaml's comments + key order across saves; workbooks are copied BINARY (never
round-tripped through openpyxl, which would drop formula caches / array formulas / VBA).
"""
from __future__ import annotations
import os
import shutil

from pipeline3.core import config

PROJECT_FILE = "project.yaml"
INPUTS_DIR = "Input"
OUTPUT_DIR = "Output"
CONFIG_DIRNAME = "config_project"      # the project's own copy of the app config CSVs
USER_INPUT_DIRNAME = "user_input"      # the project's own treatment registry
_INPUT_KEYS = ("io_list", "ce")        # params keys whose .path is a workbook to copy into Input/


# ---- ruamel round-trip (comment/key-order preserving) ---------------------- #
def _yaml():
    from ruamel.yaml import YAML
    y = YAML()                         # round-trip mode
    y.preserve_quotes = True
    y.width = 4096                     # don't re-wrap long lines (e.g. single-quoted regexes)
    return y


def load_doc(path: str):
    with open(path, encoding="utf-8") as f:
        return _yaml().load(f) or {}


def dump_doc(doc, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _yaml().dump(doc, f)


# ---- project paths --------------------------------------------------------- #
def project_yaml(folder_or_yaml: str) -> str:
    """The project.yaml path for a folder, or the file itself if one was passed."""
    return os.path.join(folder_or_yaml, PROJECT_FILE) if os.path.isdir(folder_or_yaml) else folder_or_yaml


def project_dir(project_path: str) -> str:
    return os.path.dirname(os.path.abspath(project_path))


def project_name(project_path: str) -> str:
    return os.path.basename(project_dir(project_path))


def config_root(project_path: str) -> str:
    """The project's config_project/ - the loaders' base while this project is active."""
    return os.path.join(project_dir(project_path), CONFIG_DIRNAME)


def user_input_root(project_path: str) -> str:
    """The project's user_input/ - its own treatment registry while active."""
    return os.path.join(project_dir(project_path), USER_INPUT_DIRNAME)


# ---- new / open / save ----------------------------------------------------- #
def _ensure_layout(folder: str) -> None:
    for sub in ("", INPUTS_DIR, OUTPUT_DIR, USER_INPUT_DIRNAME):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)


def _seed_config(folder: str) -> None:
    """Give the project its OWN copy of the app config CSVs (once); existing project config is kept."""
    dst = os.path.join(folder, CONFIG_DIRNAME)
    if not os.path.isdir(dst):
        shutil.copytree(config.CONFIG_PROJECT, dst)


def default_doc():
    """A fresh project.yaml, seeded from config_project/project_params.yaml (comments kept) with the
    input paths blanked + the project knobs defaulted (copy inputs on; output_dir -> <project>/Output)."""
    doc = load_doc(config.PARAMS_FILE)
    for key in _INPUT_KEYS:
        if key in doc and "path" in doc[key]:
            doc[key]["path"] = ""
    doc.setdefault("copy_inputs_on_save", True)
    doc.setdefault("language", "en")
    doc["output_dir"] = "Output"           # relative -> load_params resolves it to <project>/Output
    return doc


def new_project(folder: str, doc=None) -> str:
    """Create the project layout (Input/ Output/ user_input/ + its own config_project/) and write
    project.yaml. Returns its path."""
    _ensure_layout(folder)
    _seed_config(folder)
    path = project_yaml(folder)
    dump_doc(doc if doc is not None else default_doc(), path)
    return path


def open_project(folder_or_yaml: str) -> str:
    """Resolve to an existing project.yaml; raises FileNotFoundError if absent."""
    path = project_yaml(folder_or_yaml)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return path


def _copy_inputs(doc, folder: str) -> None:
    """Copy each input workbook into <folder>/Input/ and repoint its param to 'Input/<name>'.
    Missing / blank / already-local paths are left untouched."""
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
            shutil.copy2(abs_src, dst)                  # binary copy - formula caches/VBA survive
        doc[key]["path"] = f"{INPUTS_DIR}/{name}"       # forward slash: portable in YAML


def save_project(doc, project_path: str, copy_inputs: bool = False) -> str:
    """Write `doc` to project_path. With copy_inputs, first copy the I/O List + C&E into Input/ and
    rewrite their paths project-relative. Returns the project path."""
    folder = project_dir(project_path)
    _ensure_layout(folder)
    if copy_inputs:
        _copy_inputs(doc, folder)
    dump_doc(doc, project_path)
    return project_path

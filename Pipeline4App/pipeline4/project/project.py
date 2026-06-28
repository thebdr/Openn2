"""Folder-based projects for PL4 (GUI M6) - pure functions, no tkinter (the GUI wires these).

A PL4 project is a self-contained ROOT folder:

    <root>/
        config_project/      the project's OWN config (project_params.yaml + the CSVs + user_input/)
        Database/            the SSOT tables (one CSV-with-JSON-cells per table)
        Output/              the BuilderData + ProjectDocumentation tree

`config.use_project(root)` points the loaders, the Database folder, and the Output tree at <root>;
`use_builtin()` reverts to the app's bundled `config_project/` + `Shared/`. A project is identified by
`<root>/config_project/project_params.yaml` (the run params). New-project SCAFFOLDS the layout by copying
the builtin config_project (the operator then re-points the I/O List / C&E doc paths via the Files tab /
externally). Simpler than PL3's project.yaml-at-root model because PL4 keeps project_params.yaml inside
config_project/ and auto-saves its Database — there's no separate save step.
"""
from __future__ import annotations

import os
import shutil

from pipeline4.core import config
from pipeline4.project import state

CONFIG_DIRNAME = "config_project"
_PARAMS_REL = os.path.join(CONFIG_DIRNAME, "project_params.yaml")


def is_project(root: str) -> bool:
    """True when `root` is a PL4 project folder (it carries config_project/project_params.yaml)."""
    return bool(root) and os.path.isfile(os.path.join(root, _PARAMS_REL))


def project_name(root: str) -> str:
    return os.path.basename(os.path.abspath(root)) if root else ""


def open_project(root: str) -> str:
    """Make `root` the active project: validate it, point `config` at it, record it recent/last-opened.
    Returns the absolute root. Raises FileNotFoundError when `root` isn't a project folder."""
    root = os.path.abspath(root)
    if not is_project(root):
        raise FileNotFoundError(os.path.join(root, _PARAMS_REL))
    config.use_project(root)
    state.push_recent(root)
    return root


def close_project() -> None:
    """Revert to the builtin app config + Shared/ (no project open) and forget the auto-reopen target."""
    config.use_builtin()
    state.clear_last_opened()


def new_project(parent: str, name: str) -> str:
    """Scaffold a project at <parent>/<name>/ (its own config_project copied from the builtin + empty
    Database/ and Output/), open it, and return the root. Raises FileExistsError if it already exists."""
    root = os.path.abspath(os.path.join(parent, name))
    if os.path.exists(root):
        raise FileExistsError(root)
    os.makedirs(root)
    shutil.copytree(config.config_project_dir(), os.path.join(root, CONFIG_DIRNAME))
    for sub in ("Database", "Output"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    return open_project(root)


def auto_reopen() -> str | None:
    """Re-point `config` at the last-opened project (launch-time). Returns the root, or None when there's
    no valid last project (then the builtin config stays active). Does NOT re-push recents."""
    root = state.last_opened()
    if root and is_project(root):
        config.use_project(os.path.abspath(root))
        return os.path.abspath(root)
    return None

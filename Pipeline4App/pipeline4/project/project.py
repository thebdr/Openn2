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


class ProjectConfigError(Exception):
    """A project's `config_project/` is INCOMPLETE vs the builtin canonical config set (it is missing files
    the app ships with). This is a DEVELOPMENT-phase code error - e.g. new-project scaffolding drift, or a
    project created before a config file was added - and must surface as a hard FAIL-AND-STOP, never be
    silently defaulted around (a shipped app would otherwise run on wrong/empty config). Carries the list
    of missing relative paths."""

    def __init__(self, root: str, missing: list):
        self.root, self.missing = root, list(missing)
        super().__init__(f"project config incomplete ({project_name(root)}): missing {', '.join(self.missing)}")


def is_project(root: str) -> bool:
    """True when `root` is a PL4 project folder (it carries config_project/project_params.yaml)."""
    return bool(root) and os.path.isfile(os.path.join(root, _PARAMS_REL))


def _config_file_set(config_dir: str) -> set:
    """Every file under a `config_project/` dir, as relative '/'-joined paths."""
    out = set()
    for dirpath, _dirs, files in os.walk(config_dir):
        for name in files:
            out.add(os.path.relpath(os.path.join(dirpath, name), config_dir).replace(os.sep, "/"))
    return out


def config_gaps(root: str) -> list:
    """The canonical config files (present in the BUILTIN config_project) that are MISSING from
    `<root>/config_project`. Empty -> complete. The bundled builtin is the single source of truth - there
    is NO baked manifest. Project-specific extra files are fine; only missing canonical files are gaps."""
    builtin = _config_file_set(config.builtin_config_project_dir())
    have = _config_file_set(os.path.join(root, CONFIG_DIRNAME))
    return sorted(builtin - have)


def assert_config_complete(root: str) -> None:
    """Raise `ProjectConfigError` when `<root>/config_project` is missing any canonical config file - the
    fail-loud guard so a scaffolding/drift bug is caught in development, not shipped."""
    missing = config_gaps(root)
    if missing:
        raise ProjectConfigError(root, missing)


def project_name(root: str) -> str:
    return os.path.basename(os.path.abspath(root)) if root else ""


def open_project(root: str) -> str:
    """Make `root` the active project: validate it, point `config` at it, record it recent/last-opened.
    Returns the absolute root. Raises FileNotFoundError when `root` isn't a project folder."""
    root = os.path.abspath(root)
    if not is_project(root):
        raise FileNotFoundError(os.path.join(root, _PARAMS_REL))
    assert_config_complete(root)            # fail loud + stop if the project's config is incomplete
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
    shutil.copytree(config.builtin_config_project_dir(), os.path.join(root, CONFIG_DIRNAME))
    for sub in ("Database", "Output"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    assert_config_complete(root)            # the scaffold MUST be complete vs the builtin - fail loud if not
    return open_project(root)


def auto_reopen() -> str | None:
    """Re-point `config` at the last-opened project (launch-time). Returns the root, or None when there's
    no valid last project (then the builtin config stays active). Does NOT re-push recents."""
    root = state.last_opened()
    if root and is_project(root) and not config_gaps(root):   # an incomplete project is NOT auto-reopened
        config.use_project(os.path.abspath(root))
        return os.path.abspath(root)
    return None

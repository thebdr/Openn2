"""User-local persisted state for the Project Manager: the user-selectable projects ROOT, the recent
projects, and the last-opened project (for auto-reopen). Stored at %LOCALAPPDATA%/Pipeline5/state.json
(or ~ when LOCALAPPDATA is absent) so a frozen .exe can write it; a missing/corrupt file degrades to a
clean default. Clean-room port of PL3's `project/state.py` - PL4 stores project ROOT FOLDERS (PL4's
`config.use_project` takes the root, not a project.yaml path).
"""
from __future__ import annotations

import json
import os

_RECENT_CAP = 10
# The default starting folder for the Open/New dialogs (override with PIPELINE4_PROJECTS); ~ otherwise.
_DEFAULT_PROJECTS_ROOT = os.environ.get("PIPELINE4_PROJECTS") or os.path.expanduser("~")


def _state_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Pipeline5")


def _state_file() -> str:
    return os.path.join(_state_dir(), "state.json")


def _read() -> dict:
    try:
        with open(_state_file(), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        with open(_state_file(), "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
    except OSError:
        pass


def projects_root() -> str:
    """The persisted projects root (the Open/New dialog's start folder), or the default when unset."""
    return _read().get("projects_root") or _DEFAULT_PROJECTS_ROOT


def set_projects_root(path: str) -> None:
    data = _read()
    data["projects_root"] = os.path.abspath(path)
    _write(data)


def recent_projects() -> list:
    """Most-recent-first project ROOT folders that still exist (vanished ones pruned)."""
    return [p for p in _read().get("recent_projects", []) if p and os.path.isdir(p)]


def push_recent(root: str) -> None:
    """Record `root` as the most-recently-opened project (also the last_opened auto-reopen target)."""
    p = os.path.abspath(root)
    data = _read()
    rest = [x for x in data.get("recent_projects", []) if os.path.abspath(x) != p]
    data["recent_projects"] = [p] + rest[:_RECENT_CAP - 1]
    data["last_opened"] = p
    _write(data)


def last_opened() -> str | None:
    """The last-opened project ROOT (for auto-reopen), or None if unset/gone."""
    p = _read().get("last_opened")
    return p if (p and os.path.isdir(p)) else None


def clear_last_opened() -> None:
    """Forget the auto-reopen target (e.g. on Close Project) without touching recents."""
    data = _read()
    data.pop("last_opened", None)
    _write(data)

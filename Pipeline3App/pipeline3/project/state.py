"""User-local persisted state for the Project Manager: the user-selectable projects ROOT, the recent
projects, and the last-opened project (for auto-reopen). Stored at %LOCALAPPDATA%/Pipeline3/state.json
(or ~ when LOCALAPPDATA is absent) so a frozen .exe can write it; a missing/corrupt file degrades to a
clean default. (Pipeline2 persisted only last_project; Pipeline3 adds the selectable root.)
"""
from __future__ import annotations
import json
import os

from pipeline3.core import config

_RECENT_CAP = 10


def _state_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Pipeline3")


def _state_file() -> str:
    return os.path.join(_state_dir(), "state.json")


def _read() -> dict:
    try:
        with open(_state_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d: dict) -> None:
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        with open(_state_file(), "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except OSError:
        pass


def projects_root() -> str:
    """The persisted projects root, or config.PROJECTS_DIR (PIPELINE3_PROJECTS env / ~ default) when unset."""
    return _read().get("projects_root") or config.PROJECTS_DIR


def set_projects_root(path: str) -> None:
    d = _read()
    d["projects_root"] = os.path.abspath(path)
    _write(d)


def recent_projects() -> list:
    """Most-recent-first existing project.yaml paths (vanished ones pruned)."""
    return [p for p in _read().get("recent_projects", []) if p and os.path.exists(p)]


def push_recent(path: str) -> None:
    """Record `path` as the most-recently-opened project (also the last_opened auto-reopen target)."""
    p = os.path.abspath(path)
    d = _read()
    rest = [x for x in d.get("recent_projects", []) if os.path.abspath(x) != p]
    d["recent_projects"] = [p] + rest[:_RECENT_CAP - 1]
    d["last_opened"] = p
    _write(d)


def last_opened() -> str | None:
    """The last-opened project.yaml (for auto-reopen), or None if unset/gone."""
    p = _read().get("last_opened")
    return p if (p and os.path.exists(p)) else None


def clear_last_opened() -> None:
    """Forget the auto-reopen target (e.g. on Close Project) without touching recents."""
    d = _read()
    d.pop("last_opened", None)
    _write(d)

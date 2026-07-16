"""Phase-bar icon assets: the `assets/icons/phase_icons.yaml` registry -> per-phase `tk.PhotoImage`s.

The registry maps a phase key ("run" or the phase number) to a 72x72 PNG in `assets/icons/` (official
Twemoji art + project-drawn customs - see the NOTICE there). Loading is FAIL-SOFT end to end: a missing
registry, a bad row, or a missing/corrupt PNG downgrades to "that button has no icon" plus a warning
string - the bar must never fail to build over cosmetics.

`load_registry()` + `resolve()` are Tk-free (unit-tested); `load_phase_icons()` is the thin Tk layer.
"""
from __future__ import annotations

import os

# .../pipeline5/workbench/icons.py -> up 3 -> the Pipeline5App root (assets/ lives there, like gui/fonts.py).
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ICONS_DIR = os.path.join(APP_ROOT, "assets", "icons")
REGISTRY_PATH = os.path.join(ICONS_DIR, "phase_icons.yaml")
SUBSAMPLE = 3                      # 72 px assets -> 24 px button icons (integer subsample = crisp)


def load_registry(path: str = REGISTRY_PATH) -> dict:
    """The `phase_icons` mapping with every key normalized to str ("run", "100", ...). An absent or
    unparsable registry returns {} (no icons, not an error)."""
    if not os.path.exists(path):
        return {}
    try:
        from ruamel.yaml import YAML
        with open(path, encoding="utf-8") as handle:
            data = YAML(typ="safe").load(handle) or {}
        mapping = data.get("phase_icons") or {}
        return {str(k): str(v) for k, v in mapping.items() if v}
    except Exception:  # noqa: BLE001 - cosmetics never take the GUI down
        return {}


def resolve(registry: dict, icons_dir: str = ICONS_DIR) -> tuple[dict, list]:
    """(found {key -> absolute png path}, warnings) - a registry row whose file is missing becomes a
    warning line, never a raise."""
    found, warnings = {}, []
    for key, filename in registry.items():
        path = os.path.join(icons_dir, filename)
        if os.path.exists(path):
            found[key] = path
        else:
            warnings.append(f"phase icon missing: {filename} (phase {key}) - button renders without an icon")
    return found, warnings


def load_phase_icons(master) -> tuple[dict, list]:
    """({key -> tk.PhotoImage at SUBSAMPLE}, warnings). The caller must HOLD the returned dict for the
    widgets' lifetime (a garbage-collected PhotoImage blanks its label)."""
    import tkinter as tk
    paths, warnings = resolve(load_registry())
    images = {}
    for key, path in paths.items():
        try:
            images[key] = tk.PhotoImage(master=master, file=path).subsample(SUBSAMPLE)
        except Exception:  # noqa: BLE001 - a corrupt PNG is a warning, not a crash
            warnings.append(f"phase icon unreadable: {os.path.basename(path)} (phase {key})")
    return images, warnings

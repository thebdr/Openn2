"""The 4-tier config resolver - where a config file is looked up, in one place (C-004's PL5 form).

Every config artifact resolves through the SAME walk, most specific first:

    1. <project>/config_project/systems/<sid>/<rel>    the open project's per-system override
    2. <project>/config_project/shared/<rel>           the open project's shared tier
    3. <system.config_root>/<rel>                      the system's BUILTIN config (in-package)
    4. <app>/config_project/shared/<rel>               the app's builtin shared tier

Tiers 1 and 3 exist only while a system is ACTIVE (`config.use_system`); tiers 1-2 only while a
project is open (`config.use_project`). `find()` returns None when nothing matches (the
missing-tolerant loaders return empty); `resolve()` RAISES with the searched tiers - config is
config, never an in-code default (the completeness rule).
"""
from __future__ import annotations

import os

from pipeline5.config import paths


def tiers() -> list:
    """The existing-or-not tier BASES for the current project/system state, most specific first."""
    out = []
    project = paths.active_project()
    system = paths.active_system()          # (id, config_root) or None
    if project and system:
        out.append(os.path.join(project, "config_project", "systems", system[0]))
    if project:
        out.append(os.path.join(project, "config_project", "shared"))
    if system and system[1]:
        out.append(system[1])
    out.append(paths.builtin_shared_config_dir())
    return out


def find(rel: str):
    """The first tier holding `rel`, or None (for the missing-tolerant loaders)."""
    for base in tiers():
        p = os.path.join(base, rel.replace("/", os.sep))
        if os.path.exists(p):
            return p
    return None


def resolve(rel: str) -> str:
    """`find`, but ABSENT is an error naming every searched tier (fail loud, never default)."""
    p = find(rel)
    if p is None:
        raise FileNotFoundError(
            f"config file {rel!r} not found in any tier: " + "; ".join(tiers()))
    return p

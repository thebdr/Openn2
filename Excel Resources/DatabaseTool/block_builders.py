#!/usr/bin/env python3
"""block_builders.py — YOU edit this. One function per Software Block template.

Each builder receives `db` (the CentralDatabase: a list of staged row dicts —
canonical columns + matrix_areas + name_in_db) and returns a list of INSTANCES,
one per @row in the generated SoftwareBlocksBuilder CSV.

An instance is a dict { "<!!key$$ name>": value }:
  * value = str          -> one cell (a scalar placeholder)
  * value = list[str]    -> the horizontal ITERATOR (one such key per instance;
                            the writer pads it to the template's capacity with the
                            pad value and computes #Elements Needed / TemplateType)
  * optional "_pad": str -> override the pad element for this instance (default PAD)

You only gather the data here; softwareblocks.py does the CSV/markers/sizing.
Register every builder in BUILDERS, keyed by the template file stem.
"""
from __future__ import annotations
import re

PAD = "ALWAYS_TRUE"   # default ITERATOR padding element (override per-instance via "_pad")


# --------------------------------------------------------------------------- #
# small helpers you may use (or ignore and write your own)                    #
# --------------------------------------------------------------------------- #
def unique_areas(db: list) -> list:
    """Distinct AREA n across the CentralDatabase (matrix_areas is '|'-joined)."""
    areas = set()
    for r in db:
        for a in str(r.get("matrix_areas", "")).split("|"):
            if a.strip():
                areas.add(a.strip())
    return sorted(areas)


def area_index(area: str) -> str:
    """'AREA 1' -> '1' (trailing digits)."""
    m = re.search(r"(\d+)\s*$", str(area))
    return m.group(1) if m else ""


def names_in_db(db: list, *, script_type=None, area=None, db_name=None) -> list:
    """name_in_db of rows matching the given filters (each filter optional)."""
    out = []
    for r in db:
        if script_type is not None and r.get("script_type") != script_type:
            continue
        if area is not None and area not in str(r.get("matrix_areas", "")).split("|"):
            continue
        n = r.get("name_in_db", "")
        if n:
            out.append(n)
    return out


# --------------------------------------------------------------------------- #
# one builder per template — EDIT THESE                                       #
# --------------------------------------------------------------------------- #
def build_03_zone_cumulative(db: list) -> list:
    """TEMPLATE--v1.0--03_Zone Cumulative.xml
    keys: NetworkComment, nameOfDB, memberOf:02_COM, ITERATOR_STRINGS

    EXAMPLE gathering (adjust to your real rules): for each AREA, one @row per
    memberOf — pushbuttons (E1/2) and feedback (KQ); the ITERATOR is the name_in_db
    of the matching rows in that area."""
    instances = []
    for area in unique_areas(db):
        i = area_index(area)
        for suffix, stype in (("PB", "E1/2"), ("FDB", "KQ")):
            instances.append({
                "NetworkComment":  f"{area} - SYSTEM",
                "nameOfDB":        "02_COM",
                "memberOf:02_COM": f"A{i}_{suffix}",
                "ITERATOR_STRINGS": names_in_db(db, script_type=stype, area=area),
            })
    return instances


def build_05_output_feedback(db: list) -> list:
    """TEMPLATE--v1.1--05_Output Feedback.xml — TODO: gather instances."""
    return []


def build_06_feedback_error(db: list) -> list:
    """TEMPLATE--v1.0--06_Feedback Error.xml — TODO: gather instances."""
    return []


# template file stem -> builder
BUILDERS = {
    "TEMPLATE--v1.0--03_Zone Cumulative": build_03_zone_cumulative,
    "TEMPLATE--v1.1--05_Output Feedback": build_05_output_feedback,
    "TEMPLATE--v1.0--06_Feedback Error":  build_06_feedback_error,
}

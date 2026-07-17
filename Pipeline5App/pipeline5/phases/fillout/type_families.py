"""ph200 / 220 - object families (the §7 INDEX grouping strategy).

Loads the classification tier's `object_families.csv` into `ObjectFamily` records + provides
`family_for(script_type)` (LONGEST-key prefix match, so `DI` wins over `D`). A faithful clean-room
port of PL3's `domain/iolist_diag/families.py` into PL4's SSOT model: the CSV cols are
`family,key,member_types(|-split),anchor,link(lowercased),index_stride,bits,diag_block`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from pipeline5 import config

# --- link kinds (the object-grouping strategy, from object_families.csv 'link') --- #
LINK_CHANNEL = "channel"
LINK_SERIES = "series"
LINK_FLD = "fld"
LINK_PATTERN = "pattern"
LINK_NONE = "none"


@dataclass(frozen=True)
class ObjectFamily:
    family: str                  # human name, e.g. "door"
    key: str                     # leading letter(s) matched against script_type, e.g. "D"
    member_types: tuple          # canonical members, e.g. ("DI","DD","DR","DL","DQ")
    anchor: str                  # the type that consumes the index, e.g. "DI1/2"
    link: str                    # LINK_* grouping strategy
    index_stride: int            # index slots per family member (currently 1)
    bits: int                    # diag bits one object consumes (0 = not diagnosed)
    diag_block: str              # Type-2 destination block stem ("" = node cabinet / Type-1)


def load_object_families() -> list:
    """Load object_families.csv into ObjectFamily records (the 4-tier config resolver)."""
    fams = []
    for r in config.read_config_csv(
        config.resolver.find("classification/object_families.csv")
    ):
        if not (r.get("family") or "").strip():
            continue
        fams.append(ObjectFamily(
            family=(r.get("family") or "").strip(),
            key=(r.get("key") or "").strip(),
            member_types=tuple(t.strip() for t in (r.get("member_types") or "").split("|") if t.strip()),
            anchor=(r.get("anchor") or "").strip(),
            link=(r.get("link") or "").strip().lower(),
            index_stride=int((r.get("index_stride") or "1").strip() or 1),
            bits=int((r.get("bits") or "0").strip() or 0),
            diag_block=(r.get("diag_block") or "").strip(),
        ))
    return fams


def family_for(script_type: str, families: list) -> ObjectFamily | None:
    """Longest-key prefix match (so 'DI' wins over 'D'). Non-families (A/W/PA/PW/IOC) -> None."""
    st = (script_type or "").strip().upper()
    if not st:
        return None
    for fam in sorted(families, key=lambda f: len(f.key), reverse=True):
        if fam.key and st.startswith(fam.key.upper()):
            return fam
    return None

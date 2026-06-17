"""Object-family registry (config_project/input_docs/object_families.csv).

One row per multi-signal object family (spec §7.1): which script_types compose it, the anchor
that consumes the progressive index, how siblings link (channel/series/fld/pattern/none), the
diag-bit demand and the destination diagnosis block. New families later = new rows, no code
change. `family_for` keys a canonical script_type to its family by leading letter(s).
"""
from __future__ import annotations
import os

from pipeline2.core import config
from pipeline2.iolist_diag.models import LinkKind, ObjectFamily

FAMILIES_CSV = "object_families.csv"


def load_families() -> list[ObjectFamily]:
    """Load object_families.csv -> [ObjectFamily]; [] when the file is absent."""
    path = os.path.join(config.INPUT_DOCS_DIR, FAMILIES_CSV)
    if not os.path.exists(path):
        return []
    out: list[ObjectFamily] = []
    for r in config._read_csv(FAMILIES_CSV):
        if not (r.get("family") or "").strip():
            continue
        try:
            link = LinkKind((r.get("link") or "none").strip().lower())
        except ValueError:
            link = LinkKind.NONE
        out.append(ObjectFamily(
            family=r["family"].strip(),
            key=(r.get("key") or "").strip(),
            member_types=tuple(t.strip() for t in (r.get("member_types") or "").split("|") if t.strip()),
            anchor=(r.get("anchor") or "").strip(),
            link=link,
            index_stride=int((r.get("index_stride") or "1").strip() or 1),
            bits=int((r.get("bits") or "0").strip() or 0),
            diag_block=(r.get("diag_block") or "").strip(),
        ))
    return out


def family_for(script_type: str, families: list[ObjectFamily]) -> ObjectFamily | None:
    """The family whose `key` is the leading letter(s) of `script_type` (longest key wins).
    Runs on the CANONICAL script_type (after the old->new map), so A/W/PA/PW/PLC/IOC -> None
    (standalone, no object grouping)."""
    st = (script_type or "").strip().upper()
    if not st:
        return None
    for fam in sorted(families, key=lambda f: len(f.key), reverse=True):
        if fam.key and st.startswith(fam.key.upper()):
            return fam
    return None

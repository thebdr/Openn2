"""Load object_families.csv into ObjectFamily records + family_for(script_type)."""
from __future__ import annotations

from pipeline3.core import config
from pipeline3.domain.iolist_diag.models import ObjectFamily


def load_families() -> list:
    fams = []
    for r in config._read_csv("object_families.csv"):
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

"""Validation-local helpers shared by the five phase-100 builders.

`entry()` is the ONE LogEntry factory every builder uses - it forces a `type` slug (the
code-traceable log-type index) and localizes the message through `tr("v_<type>")`. The rest are
small normalization + fuzzy-match + cross-check-rendering helpers.
"""
from __future__ import annotations
import re

from pipeline3.core.model import LogEntry, InfoBlock, Cmp
from pipeline3.core.i18n import tr


# --- the one entry factory -------------------------------------------------- #
def entry(level: str, phase: int, type_: str, lang: str, *, location: str = "", doc: str = "",
          location2: str = "", doc2: str = "", info: InfoBlock | None = None, cmp: Cmp | None = None,
          **fmt) -> LogEntry:
    """Build a LogEntry. `type_` is the log-type slug → the rendered id `<phase>-<type_>` AND the
    i18n key `v_<type_>` (localized with **fmt). The detail is the localized message; a cross-check's
    `cmp` (a `Cmp`) rides structured on the entry so the renderer aligns it per-phase."""
    return LogEntry(level=level, phase=phase, type=type_, detail=tr(f"v_{type_}", lang, **fmt),
                    location=location, doc=doc, location2=location2, doc2=doc2,
                    cmp=cmp, info=info or InfoBlock())


# --- normalization ---------------------------------------------------------- #
def key(*parts) -> str:
    """FLD identity key (Functional unit + Location + Device): all whitespace removed, upper-cased."""
    return "".join("".join(str(p if p is not None else "").split()) for p in parts).upper()


def addr(value) -> str:
    """Address key: whitespace removed, upper-cased."""
    return "".join(str(value if value is not None else "").split()).upper()


def raw(value) -> str:
    """Raw display text: outer whitespace stripped, inner preserved."""
    return "" if value is None else str(value).strip()


def fld_text(*parts) -> str:
    """Human FLD: the non-empty parts joined by space (for display / InfoBlock)."""
    return " ".join(p for p in (raw(x) for x in parts) if p)


def info_for_row(row: dict) -> InfoBlock:
    """InfoBlock from a staged/dict row (canonical keys)."""
    ti = "-".join(p for p in (raw(row.get("script_type")), raw(row.get("index"))) if p)
    return InfoBlock(bit=raw(row.get("bit")), fld=fld_text(row.get("functional_unit"),
                     row.get("location"), row.get("device")), desc_l1=raw(row.get("desc_l1")),
                     desc_l1b=raw(row.get("desc_l1b")), drawing=raw(row.get("drawing")), type_index=ti)


# --- fuzzy word matching (untyped-row safety, phase 140) -------------------- #
def levenshtein(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


_TOKEN = re.compile(r"[A-Za-z]+")


def first_match(text: str, words, max_dist: int):
    """The first `word` that matches `text` (substring when max_dist==0; else a token within
    Levenshtein `max_dist`), or None."""
    low = (text or "").lower()
    toks = _TOKEN.findall(low)
    for w in words or ():
        wl = str(w).strip().lower()
        if not wl:
            continue
        if wl in low:
            return w
        if max_dist > 0 and any(levenshtein(t, wl) <= max_dist for t in toks):
            return w
    return None


def matches_words(text: str, words, max_dist: int) -> bool:
    return first_match(text, words, max_dist) is not None


# --- cross-check comparison body (phases 130/140) --------------------------- #
def cmp_detail(caller_addr: str, other_addr: str, caller_fld: str, other_fld: str,
               addr_eq: bool, fld_eq: bool) -> Cmp:
    """The STRUCTURED cross-check comparison (IO address + FLD, each with its equality). The renderer
    aligns the four fields per-phase and prints `<addr> op <addr> | <fld> op <fld>` (op `===`/`=/=`)."""
    return Cmp(caller_addr or "(none)", other_addr or "(none)", addr_eq,
               caller_fld or "(none)", other_fld or "(none)", fld_eq)

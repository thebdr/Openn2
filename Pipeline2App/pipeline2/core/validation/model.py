"""Leaf helpers, data classes and constants for validation.

No dependencies on the other validation submodules - everything else builds on this.
"""
from __future__ import annotations
import re

CE_MANDATORY_WORDS = ("emergency", "safety", "relay", "contactor", "enable")

# the stable 5-phase validation interface (string ids drive `validate(phases=...)` + the GUIs):
#   0A I/O List standalone | 0B C&E Matrix standalone (placeholder) | 1 C&E in IOList |
#   2 IOList in C&E | 3 Diagnosis.  Default runs them all.
ALL_PHASES = {"0A", "0B", "1", "2", "3"}

# --- cross-check comparison line (Phase 1/2) --------------------------------- #
# A line reads from the CALLER workbook's perspective: "<caller cell> vs <OtherDoc>", then the
# caller value (left) vs the other document's value (right) for the address and the device.
# The caller flips per phase (Phase 1 caller = C&E, Phase 2 caller = I/O List), so the left
# side flips too - hence `caller_*` / `other_*` rather than a fixed I/O/C&E side.
NONE_VALUE = "(none)"            # an absent side
DOC_IO, DOC_CE = "IOList", "CEMatrix"   # the short "vs <OtherDoc>" labels


class Cmp:
    """A Phase-1/2 cross-check comparison from the caller's perspective: the caller workbook's
    value (left) and the other document's value (right) for the address (ADDR) and the device
    key (FLD), plus the two verdict booleans (drive `===`/`=/=`). Values are raw cell text
    (looked-up side already joined via `_join_set`; absent side -> (none)). `other_doc` is the
    short name of the compared-against document (shown as 'vs <other_doc>')."""
    __slots__ = ("caller_addr", "other_addr", "caller_fld", "other_fld", "addr_eq", "fld_eq", "other_doc")

    def __init__(self, caller_addr, other_addr, caller_fld, other_fld, addr_eq, fld_eq, other_doc):
        self.caller_addr = caller_addr or NONE_VALUE
        self.other_addr = other_addr or NONE_VALUE
        self.caller_fld = caller_fld or NONE_VALUE
        self.other_fld = other_fld or NONE_VALUE
        self.addr_eq = addr_eq
        self.fld_eq = fld_eq
        self.other_doc = other_doc


class LogEntry:
    __slots__ = ("level", "location", "key", "address", "message", "path", "row", "phase",
                 "location2", "path2", "cmp")

    def __init__(self, level, location, key, address, message, path=None, row=None,
                 location2="", path2="", cmp=None):
        self.level = level          # PASS / FAIL / WARN / INFO / PHASE / SKIP
        self.location = location    # "Sheet!Cell"
        self.key = key
        self.address = address
        self.message = message
        self.path = path            # workbook the location refers to (None -> the C&E doc)
        self.row = row or {}        # the I/O (or C&E ref) row, for the per-entry info block
        self.phase = ""             # phase id (0A/0B/1/2/3), set by error_management.assign_phases
        # a SECOND workbook cell for a partial match (the other side: I/O List <-> C&E), so the
        # GUI can offer links to BOTH workbooks. "" when there is only one side.
        self.location2 = location2  # "Sheet!Cell" on the other workbook
        self.path2 = path2          # that workbook's path
        # a Phase-1/2 cross-check comparison (Cmp) -> renders the aligned comparison table; None on
        # every other line (banners, INFO/SKIP, Phase 0A/3), which keep the plain format.
        self.cmp = cmp

    def info(self) -> str:
        """The shared per-entry identifier: bit | desc_l1 desc_l1b | FLD | drawing | st-index."""
        return _row_info(self.row)

    def format(self) -> str:
        if self.level == "PHASE":   # a phase banner separating the validation log
            bar = "=" * 78
            return f"\n{bar}\n{self.message}\n{bar}"
        head = f"[{self.level:4}] {self.location}"
        if self.cmp is not None:    # cross-check line: <loc vs OtherDoc> | addr | fld | caller : msg
            from .render import _cmp_body   # lazy: render builds on model, avoid a cycle at import
            caller = _caller_info(self.row)
            tail = f"{caller} : {self.message}" if caller else self.message
            return f"{head} vs {self.cmp.other_doc} | {_cmp_body(self.cmp)} | {tail}".rstrip()
        info = self.info()
        parts = [head] + ([info] if info else []) + ([self.message] if self.message else [])
        return "  ".join(parts).rstrip()


def _norm(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _key(*parts) -> str:
    """Device key: concatenated, whitespace removed, upper-cased."""
    return "".join(_norm(p) for p in parts).replace(" ", "").upper()


def _addr(value) -> str:
    return _norm(value).replace(" ", "").upper()


def _raw(value) -> str:
    """The cell text as shown in Excel (outer whitespace trimmed, inner preserved) - the raw
    value displayed in the comparison table (vs `_key`/`_addr`, which normalize)."""
    return "" if value is None else str(value).strip()


def _join_set(values) -> str:
    """Render the looked-up side's set of values as one comparison cell (sorted, comma-joined)."""
    items = sorted({v for v in values if v})
    return ", ".join(items)


def _row_info_parts(row):
    """The 6 fields of the per-entry identifier block, in display order: (bit, FLD, desc_l1,
    desc_l1b, drawing, st-index), or None when the row has nothing identifying. FLD =
    functional_unit+location+device (kept next to the address). Lets the renderer column-align the
    plain info-block lines (Phase 0A, SKIP, diagnosis) per phase."""
    if not row:
        return None
    bit = _norm(row.get("bit"))
    desc1 = _norm(row.get("desc_l1"))
    desc2 = _norm(row.get("desc_l1b"))
    fld = "".join(_norm(row.get(c)) for c in ("functional_unit", "location", "device"))
    drawing = _norm(row.get("drawing"))
    st, idx = _norm(row.get("script_type")), _norm(row.get("index"))
    sti = f"{st}-{idx}" if (st or idx) else ""
    if not any((bit, desc1, desc2, fld, drawing, sti)):
        return None
    return (bit, fld, desc1, desc2, drawing, sti)


def _row_info(row) -> str:
    """Per-entry identifier block (every log line carries it): `bit | FLD | desc_l1 | desc_l1b |
    drawing | script_type-index`. '' when the row has nothing identifying (e.g. summary/INFO lines)."""
    parts = _row_info_parts(row)
    return " | ".join(parts) if parts else ""


def _caller_info(row) -> str:
    """The caller block for a cross-check line: `desc  drawing  st-index` - the per-entry
    `info()` MINUS bit and FLD (those now have their own comparison columns)."""
    if not row:
        return ""
    desc = " ".join(p for p in (_norm(row.get("desc_l1")), _norm(row.get("desc_l1b"))) if p)
    drawing = _norm(row.get("drawing"))
    st, idx = _norm(row.get("script_type")), _norm(row.get("index"))
    sti = f"{st}-{idx}" if (st or idx) else ""
    return "  ".join(p for p in (desc, drawing, sti) if p)


def _is_warning(row) -> bool:
    """Alarm vs warning family (I/O List col R 'Type' ending in 'W' = warning)."""
    return str(row.get("type_hw", "")).strip().upper().endswith("W")


def _io_loc(row, col: str) -> str:
    """'Sheet!<col><row>' back into the I/O List for a staged row (just the sheet when the
    source row wasn't recorded)."""
    sheet = row.get("_source_sheet") or "I/O List"
    r = row.get("_source_row")
    return f"{sheet}!{col}{r}" if r else sheet


def _dev_label(row) -> str:
    fld = f"{row.get('functional_unit', '')}{row.get('location', '')}{row.get('device', '')}"
    return fld or "(no device)"


def _row_text(row) -> str:
    """The row's human description (where words like EMERGENCY / SAFETY / RELAY appear)."""
    return " ".join(str(row.get(c, "")) for c in
                    ("desc_l1", "desc_l1b", "desc_l2", "desc_l2b", "mnemonic"))


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _first_match(text: str, words, fuzzy: int):
    """The first `words` entry that appears in `text` - as a substring (handles multi-word
    phrases like 'circuit breaker'), or (when fuzzy > 0) as a whole token within Levenshtein
    distance `fuzzy` ('tolerance up to N chars'). fuzzy == 0 keeps only the substring match.
    Returns the matched word (for the log reason) or None."""
    low = text.lower()
    cand = [w.lower() for w in words if w]
    for w in cand:
        if w in low:
            return w
    if fuzzy and fuzzy > 0:
        for tok in re.findall(r"[a-z]+", low):
            for w in cand:
                if _levenshtein(tok, w) <= fuzzy:
                    return w
    return None


def _matches_words(text: str, words, fuzzy: int) -> bool:
    return _first_match(text, words, fuzzy) is not None


def _banner(log: list, title: str) -> None:
    """Append a phase banner that visually separates the validation log into its phases."""
    log.append(LogEntry("PHASE", "", "", "", title))

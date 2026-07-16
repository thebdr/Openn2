"""ph200 / the DiagnosisBlocks sheet writer (the §9 leg of the integrated fill).

Clean-room port of PL3's `domain/iolist_diag/blocks.py` into PL4's SSOT model. The DiagnosisBlocks
sheet splits into IDENTITY columns (ID_Local / ID_SWP / Functional Unit / Location / FullName /
TemplateType / Notes - APPEND-ONLY, never rewritten on an existing row) and DERIVED columns (Count /
unused_bits / non_unique_bits - recomputed and rewritten every run from the REAL post-fill
(Diag_Cabinet, Diag_Bit) data). Type-1 rows first, then Type-2 (the `allocate` block order).

PL4 ADAPTER: the `blocks` are `diag_alloc.DiagBlock` records (id_local/fu/location/full_name/
template_type); `read_existing(wb)` reads the I/O List's own DiagnosisBlocks sheet to REUSE each
cabinet's stable ID_Local (so a re-fill never renumbers - the same idempotency PL3 has) and to find
each existing cabinet's worksheet row (for the derived edits). The grid/append/header writers feed
`io.xlsx_edit` (new_sheets / append_rows / cell_edits) exactly as the PL3 surgical write does.
"""
from __future__ import annotations
from collections import defaultdict

from openpyxl.utils import get_column_letter

DIAGBLOCKS_SHEET = "DiagnosisBlocks"        # generated sheet (also accept the legacy spelling)
DIAGBLOCKS_LEGACY = "DiagnosticBlocks"

HEADERS = ["ID_Local", "ID_SWP", "Functional Unit", "Location", "FullName",
           "TemplateType", "Notes", "Count", "unused_bits", "non_unique_bits"]

# the DERIVED columns (recomputed every run): normalized header name -> (display header, canonical 1-based col)
_DERIVED = [("count", "Count", 8), ("unused_bits", "unused_bits", 9), ("non_unique_bits", "non_unique_bits", 10)]


def _cabinet_text(block) -> str:
    """The 3-digit cabinet key (== PL3 DiagBlock.cabinet_text) the derived map is keyed by."""
    return f"{block.id_local:03d}"


def _norm_cab(v) -> str:
    """A Diag_Cabinet cell -> the 3-digit key matching the cabinet text (numeric zero-padded; a
    non-numeric text label passes through)."""
    s = str(v).strip() if v is not None else ""
    return f"{int(s):03d}" if s.lstrip("-").isdigit() else s


def _bit_int(v):
    """A Diag_Bit cell -> int, or None when blank / non-numeric / the <input required> sentinel."""
    s = str(v).strip() if v is not None else ""
    return int(s) if s.lstrip("-").isdigit() else None


def _fmt_ranges(ints) -> str:
    """Collapse an iterable of ints into a compact "a, b-c, d" string (sorted, deduped, consecutive runs
    as ranges). Empty -> ""."""
    nums = sorted({int(i) for i in ints})
    if not nums:
        return ""
    out, lo, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
        else:
            out.append(f"{lo}-{prev}" if prev > lo else f"{lo}")
            lo = prev = n
    out.append(f"{lo}-{prev}" if prev > lo else f"{lo}")
    return ", ".join(out)


def analyze(placed: list, min_b: int, max_b: int) -> dict:
    """placed = [(cabinet_str, bit_int_or_None), ...] = the REAL post-fill (Diag_Cabinet, Diag_Bit) of
    every relevant I/O-list row. Returns {cabinet_str: (count, unused_bits, non_unique_bits)}:
      count           = times the cabinet appears (a row with no bit still counts);
      unused_bits     = _fmt_ranges of [min_b..max_b] minus the bits the cabinet uses;
      non_unique_bits = _fmt_ranges of the bits the cabinet assigns more than once."""
    count = defaultdict(int)
    uses = defaultdict(lambda: defaultdict(int))        # cabinet -> {bit: times used}
    for cab, bit in placed:
        count[cab] += 1
        if bit is not None:
            uses[cab][bit] += 1
    full = set(range(min_b, max_b + 1))
    return {cab: (n, _fmt_ranges(full - set(uses[cab])),
                  _fmt_ranges(b for b, t in uses[cab].items() if t > 1))
            for cab, n in count.items()}


def _block_row(b, derived: dict, default: tuple) -> list:
    """One DiagnosisBlocks row (A..J). ID_SWP == ID_Local; FU/Location/FullName are emitted as inline
    strings by the writer (a leading '='/'+' stays TEXT); Count is numeric; unused_bits/non_unique_bits
    are range strings."""
    c, unused, nonuniq = derived.get(_cabinet_text(b), default)
    return [b.id_local, b.id_local, b.fu, b.location, b.full_name,
            b.template_type, "", c, unused, nonuniq]


def diagnosis_blocks_grid(blocks: list, derived: dict, default: tuple) -> list:
    """HEADERS + one row per block - the FRESH sheet (used only when DiagnosisBlocks is ABSENT)."""
    return [list(HEADERS)] + [_block_row(b, derived, default) for b in blocks]


def block_rows(blocks: list, derived: dict, default: tuple) -> list:
    """Just the VALUE rows (no header) for `blocks` - APPENDED for the new cabinets, leaving every
    present row untouched."""
    return [_block_row(b, derived, default) for b in blocks]


def derived_edits(header: dict, rows: dict, derived: dict, default: tuple) -> dict:
    """{cell_ref: value} surgical edits that REFRESH the derived columns on the EXISTING rows: (a) a HEADER
    cell for any of Count/unused_bits/non_unique_bits the sheet lacks (Count at H, the two new columns at
    the canonical I/J so they stay aligned with appended 10-col rows), and (b) each existing cabinet row's
    three derived values (Count numeric; the ranges as text). A present column resolves by header NAME and
    is overwritten in place (re-run safe - no duplicate columns). Identity columns are never touched."""
    edits, col = {}, {}
    for norm, display, canon in _DERIVED:
        idx0 = header.get(norm)
        if idx0 is None:                                # absent -> canonical column + a header cell
            idx0 = canon - 1
            edits[f"{get_column_letter(canon)}1"] = display
        col[norm] = get_column_letter(idx0 + 1)
    for cid, row in rows.items():
        c, unused, nonuniq = derived.get(f"{cid:03d}", default)
        edits[f"{col['count']}{row}"] = c
        edits[f"{col['unused_bits']}{row}"] = unused
        edits[f"{col['non_unique_bits']}{row}"] = nonuniq
    return edits


def read_existing(wb) -> tuple:
    """Read the workbook's existing DiagnosisBlocks sheet (accepts the legacy 'DiagnosticBlocks'
    spelling). Returns (ids, rows, header):
      ids    = {full_name -> id_local:int} - so diag_alloc REUSES each cabinet's stable ID_Local (on a
               duplicate FullName, last wins);
      rows   = {id_local:int -> row_number:int} - the worksheet row of each cabinet (for the derived edits);
      header = {normalized_header -> 0-based col index} of row 1 (named columns only).
    Columns resolved BY HEADER NAME (newline->space, lowercased). Absent/header-only -> ({}, {}, {});
    non-numeric id / empty FullName rows are skipped."""
    name = next((s for s in wb.sheetnames
                 if s.strip().lower() in (DIAGBLOCKS_SHEET.lower(), DIAGBLOCKS_LEGACY.lower())), None)
    if name is None:
        return {}, {}, {}

    def _norm(v):
        return str(v).replace("\n", " ").strip() if v is not None else ""

    grid = [[c.value for c in row] for row in wb[name].iter_rows()]
    if not grid:
        return {}, {}, {}
    header = {_norm(v).lower(): i for i, v in enumerate(grid[0]) if _norm(v)}
    ci_id, ci_fn = header.get("id_local"), header.get("fullname")
    if ci_id is None or ci_fn is None:
        return {}, {}, {}
    ids, rows = {}, {}
    for ri, row in enumerate(grid[1:], 2):
        raw = _norm(row[ci_id]) if ci_id < len(row) else ""
        fn = _norm(row[ci_fn]) if ci_fn < len(row) else ""
        if not (fn and raw.lstrip("-").isdigit()):
            continue
        cid = int(raw)
        ids[fn] = cid
        rows[cid] = ri
    return ids, rows, header

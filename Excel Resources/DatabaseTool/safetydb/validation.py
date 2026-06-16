"""Validation: cross-check the C&E matrix and AREA sheets against the I/O List, and
sanity-check the diagnosis bit map of the in-diagnosis signals.

Match key = FUNCTIONAL UNIT + LOCATION + DEVICE; address = the Bit/address cell.
  I/O List : functional_unit (O) + location (P) + device (Q), address = bit (G)
  C&E      : J + K + L,                              address = F
  AREA n   : column A (already concatenated),        address = column C
Every C&E / AREA reference must exist in the I/O List with a matching address.
Only the CAUSE&EFFECT MATRIX and AREA n sheets are checked - all other sheets
are ignored.

Diagnosis bit map (I/O List, columns Diag Cabinet AE / Diag Bit AF): every signal
flagged in-diagnosis must carry a numeric Diag Cabinet + Diag Bit (else it cannot be
placed in the OPC diagnosis DWords), and no two may share the same cabinet/bit within
the same alarm/warning family (they would overwrite one another in the packed DWord).

Reverse C&E (I/O List -> C&E): every I/O signal that *should* be in the C&E must appear
there, matched by BOTH its device key (FLD) and its address. A typed row uses its signal
type's `ce_mandatory` (yes -> ERROR if not fully present, warn -> WARNING, no -> ignored);
an untyped/unknown row is checked when it carries a device designation (FLD = FU+LOC+DEV) -
or, device-less, a non-empty desc_l1/desc_l1b - plus an address, an absent one being an
ERROR when its description names a safety concept (the params.json `ce_mandatory_words`,
default emergency/safety/relay/contactor/enable) else a WARNING. A partial match - only the
FLD or only the address differs - is logged at the same severity, printing both sides.
Fuzzy word matching uses params.json `ce_fuzzy_chars` (Levenshtein tolerance; 0 disables).
Untyped rows whose description matches `ce_excluded_words` (params.json) are skipped - but a
`ce_mandatory_words` match wins, and typed rows are never excluded (signal-type rules
prevail); `ce_full_check` (params.json, default false) ignores that list. `ce_always_excluded_words`
(substring only, NO fuzzy) ALWAYS skips a row (typed or untyped), overriding everything
(e.g. 'ch2' to drop channel-2 rows). Every PASS/SKIP is logged; `ce_full_print` (params.json)
controls whether the live display (GUI/console) shows the passing/skipped rows (greyed) - the
`validation_log.txt` and the colour-coded `validation_log.html` (a dark page mirroring the log
viewer, renders in any browser) always hold the full record.

The log is split into three clearly separated phases (`validate`):
  1. C&E in IOList             - the forward check (check_ce_matrix + check_area_sheets);
  2. IOList in C&E             - the reverse check (check_ce_mandatory);
  3. Diagnosis Coherence Check - the diagnosis bit map (check_diagnosis_bits).
Every check is logged (pass AND fail); each entry carries an info block
`bit | desc_l1 desc_l1b | FLD | drawing | script_type-index` (from the I/O row, or a C&E
pseudo-row for unmatched forward references) and the offending workbook (`path`) so the GUI
can link the I/O List vs the C&E document.
"""
from __future__ import annotations
import json
import os
import re
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

from . import config

CE_MANDATORY_WORDS = ("emergency", "safety", "relay", "contactor", "enable")


class LogEntry:
    __slots__ = ("level", "location", "key", "address", "message", "path", "row")

    def __init__(self, level, location, key, address, message, path=None, row=None):
        self.level = level          # PASS / FAIL / WARN / INFO / PHASE
        self.location = location    # "Sheet!Cell"
        self.key = key
        self.address = address
        self.message = message
        self.path = path            # workbook the location refers to (None -> the C&E doc)
        self.row = row or {}        # the I/O (or C&E ref) row, for the per-entry info block

    def info(self) -> str:
        """The shared per-entry identifier: bit | desc_l1 desc_l1b | FLD | drawing | st-index."""
        return _row_info(self.row)

    def format(self) -> str:
        if self.level == "PHASE":   # a phase banner separating the validation log
            bar = "=" * 78
            return f"\n{bar}\n{self.message}\n{bar}"
        head = f"[{self.level:4}] {self.location}"
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


def _row_info(row) -> str:
    """Per-entry identifier block (every log line carries it): `bit | desc_l1 desc_l1b | FLD |
    drawing | script_type-index`. '' when the row has nothing identifying (e.g. summary/INFO
    lines). FLD = functional_unit+location+device; works for an I/O row or a C&E ref pseudo-row."""
    if not row:
        return ""
    bit = _norm(row.get("bit"))
    desc = " ".join(p for p in (_norm(row.get("desc_l1")), _norm(row.get("desc_l1b"))) if p)
    fld = "".join(_norm(row.get(c)) for c in ("functional_unit", "location", "device"))
    drawing = _norm(row.get("drawing"))
    st, idx = _norm(row.get("script_type")), _norm(row.get("index"))
    sti = f"{st}-{idx}" if (st or idx) else ""
    if not any((bit, desc, fld, drawing, sti)):
        return ""
    return f"{bit} | {desc} | {fld} | {drawing} | {sti}"


def _banner(log: list, title: str) -> None:
    """Append a phase banner that visually separates the validation log into its phases."""
    log.append(LogEntry("PHASE", "", "", "", title))


def build_io_index(io_rows: list) -> dict:
    """key -> set of addresses found in the I/O List (only rows with a key)."""
    index: dict[str, set] = {}
    for r in io_rows:
        key = _key(r.get("functional_unit"), r.get("location"), r.get("device"))
        if key in ("", None):
            continue
        index.setdefault(key, set()).add(_addr(r.get("bit")))
    return index


def _check_reference(sheet, key_cells, key, addr_cell, address, io_index, info_row, log):
    """One C&E/AREA reference vs the I/O List; appends a PASS or FAIL entry. `info_row` (the
    matched I/O row, else a C&E pseudo-row) drives the per-entry info block."""
    location = f"{sheet}!{addr_cell}"
    keyloc = f"(key {key_cells})"
    if not key:
        log.append(LogEntry("FAIL", location, key, address, f"empty device key {keyloc}", row=info_row))
        return
    addrs = io_index.get(key)
    if addrs is None:
        log.append(LogEntry("FAIL", location, key, address,
                            f"device {keyloc} not found in I/O List", row=info_row))
    elif address not in addrs:
        log.append(LogEntry("FAIL", location, key, address,
                            f"device found {keyloc} but address mismatch; I/O List has {sorted(addrs)}", row=info_row))
    else:
        log.append(LogEntry("PASS", location, key, address, f"matches I/O List {keyloc}", row=info_row))


def check_ce_matrix(params: dict, io_index: dict, io_by_key: dict, log: list) -> None:
    spec = params["ce"]
    cols = {m["canonical"]: m["column"] for m in config.load_column_map("CE")}
    wb = load_workbook(spec["path"], data_only=True, read_only=True)
    sheet = spec["matrix_sheet"]
    if sheet not in wb.sheetnames:
        log.append(LogEntry("INFO", sheet, "", "", "sheet not found - skipped"))
        wb.close()
        return
    ws = wb[sheet]
    fu_c = column_index_from_string(cols["functional_unit"])
    loc_c = column_index_from_string(cols["location"])
    dev_c = column_index_from_string(cols["device"])
    addr_c = column_index_from_string(cols["address"])

    checked = 0
    for r in range(spec["matrix_data_row"], ws.max_row + 1):
        fu = ws.cell(r, fu_c).value
        loc = ws.cell(r, loc_c).value
        dev = ws.cell(r, dev_c).value
        address = _addr(ws.cell(r, addr_c).value)
        if not any(_norm(v) for v in (fu, loc, dev)) and not address:
            continue  # empty row
        key = _key(fu, loc, dev)
        key_cells = f"{cols['functional_unit']}{r}:{cols['device']}{r}"
        ref_row = {"functional_unit": _norm(fu), "location": _norm(loc), "device": _norm(dev), "bit": address}
        info_row = io_by_key.get(key) or ref_row     # prefer the matched I/O row (desc/drawing/type)
        _check_reference(sheet, key_cells, key, f"{cols['address']}{r}", address, io_index, info_row, log)
        checked += 1
    wb.close()
    log.append(LogEntry("INFO", sheet, "", "", f"{checked} reference(s) checked"))


def check_area_sheets(params: dict, io_index: dict, io_by_key: dict, log: list) -> None:
    spec = params["ce"]
    cols = {m["canonical"]: m["column"] for m in config.load_column_map("AREA")}
    wb = load_workbook(spec["path"], data_only=True, read_only=True)
    key_c = column_index_from_string(cols["concat_id"])
    addr_c = column_index_from_string(cols["address"])

    area_sheets = [s for s in wb.sheetnames if s.strip().upper().startswith("AREA")
                   and any(ch.isdigit() for ch in s)]
    for sheet in area_sheets:
        ws = wb[sheet]
        checked = 0
        for r in range(spec["area_data_row"], ws.max_row + 1):
            raw_key = ws.cell(r, key_c).value
            address = _addr(ws.cell(r, addr_c).value)
            if not _norm(raw_key) and not address:
                continue
            key = _key(raw_key)
            ref_row = {"functional_unit": _norm(raw_key), "location": "", "device": "", "bit": address}
            info_row = io_by_key.get(key) or ref_row
            _check_reference(sheet, f"{cols['concat_id']}{r}", key,
                             f"{cols['address']}{r}", address, io_index, info_row, log)
            checked += 1
        log.append(LogEntry("INFO", sheet, "", "", f"{checked} reference(s) checked"))
    wb.close()


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


def check_diagnosis_bits(params: dict, io_rows: list, log: list) -> None:
    """Validate the diagnosis bit map of the in-diagnosis signals: each must carry a numeric
    Diag Cabinet + Diag Bit, and (cabinet, bit) must be unique within its alarm/warning
    family. Missing/invalid -> FAIL; collision -> FAIL on every colliding row; otherwise PASS.
    Entries link back to the I/O List (Diag Cabinet col AE / Diag Bit col AF)."""
    try:
        cols = {m["canonical"]: m["column"] for m in config.load_column_map("IoList")}
    except Exception:  # noqa: BLE001 - fall back to the documented positions
        cols = {}
    cab_col, bit_col = cols.get("diag_cabinet", "AE"), cols.get("diag_bit", "AF")
    io_path = (params.get("io_list") or {}).get("path", "")

    diag_rows = [r for r in io_rows if (r.get("_type") or {}).get("in_diagnosis")]
    by_slot: dict[tuple, list] = {}
    for r in diag_rows:
        cab = str(r.get("diag_cabinet", "")).strip()
        bit = str(r.get("diag_bit", "")).strip()
        cab_ok, bit_ok = cab.lstrip("-").isdigit(), bit.lstrip("-").isdigit()
        if not cab_ok or not bit_ok:
            missing = ([f"Diag Cabinet ('{cab}')"] if not cab_ok else []) + \
                      ([f"Diag Bit ('{bit}')"] if not bit_ok else [])
            loc = _io_loc(r, cab_col if not cab_ok else bit_col)
            log.append(LogEntry("FAIL", loc, _dev_label(r), f"{cab}.{bit}",
                                f"in-diagnosis signal missing/invalid {', '.join(missing)}", io_path, row=r))
            continue
        fam = "WARNING" if _is_warning(r) else "ALARM"
        by_slot.setdefault((int(cab), int(bit), fam), []).append(r)

    for (cab, bit, fam), members in sorted(by_slot.items()):
        slot = f"{cab:03d}.{bit:02d} {fam}"
        if len(members) == 1:
            r = members[0]
            log.append(LogEntry("PASS", _io_loc(r, cab_col), _dev_label(r), slot,
                                "diagnosis slot unique", io_path, row=r))
        else:
            for r in members:
                others = ", ".join(_io_loc(m, bit_col) for m in members if m is not r)
                log.append(LogEntry("FAIL", _io_loc(r, bit_col), _dev_label(r), slot,
                                    f"duplicate diagnosis slot {slot} - also at {others}", io_path, row=r))

    if diag_rows:
        log.append(LogEntry("INFO", "Diagnosis", "", "", f"{len(diag_rows)} in-diagnosis signal(s) checked"))


# --- reverse C&E: I/O List signals that must appear in the C&E -------------- #
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


def _row_text(row) -> str:
    """The row's human description (where words like EMERGENCY / SAFETY / RELAY appear)."""
    return " ".join(str(row.get(c, "")) for c in
                    ("desc_l1", "desc_l1b", "desc_l2", "desc_l2b", "mnemonic"))


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


def build_ce_index(params: dict) -> tuple[dict, dict]:
    """Two indexes over the C&E document (CAUSE&EFFECT MATRIX rows + every AREA n sheet):
    by_key  = device key (FU+LOC+DEV) -> set of addresses referenced for it (a '' member
              means the C&E listed the device with no address),
    by_addr = address -> set of device keys referenced at it.
    A signal is fully 'in the C&E' when both its key and its address line up here."""
    spec = params["ce"]
    by_key: dict[str, set] = {}
    by_addr: dict[str, set] = {}

    def add(key, addr):
        if key:
            by_key.setdefault(key, set()).add(addr)
            if addr:
                by_addr.setdefault(addr, set()).add(key)

    wb = load_workbook(spec["path"], data_only=True, read_only=True)
    mcols = {m["canonical"]: m["column"] for m in config.load_column_map("CE")}
    sheet = spec["matrix_sheet"]
    if sheet in wb.sheetnames:
        ws = wb[sheet]
        fu_c = column_index_from_string(mcols["functional_unit"])
        loc_c = column_index_from_string(mcols["location"])
        dev_c = column_index_from_string(mcols["device"])
        addr_c = column_index_from_string(mcols["address"])
        for r in range(spec["matrix_data_row"], ws.max_row + 1):
            add(_key(ws.cell(r, fu_c).value, ws.cell(r, loc_c).value, ws.cell(r, dev_c).value),
                _addr(ws.cell(r, addr_c).value))
    acols = {m["canonical"]: m["column"] for m in config.load_column_map("AREA")}
    key_c = column_index_from_string(acols["concat_id"])
    addr_c = column_index_from_string(acols["address"])
    for s in wb.sheetnames:
        if s.strip().upper().startswith("AREA") and any(ch.isdigit() for ch in s):
            ws = wb[s]
            for r in range(spec["area_data_row"], ws.max_row + 1):
                add(_key(ws.cell(r, key_c).value), _addr(ws.cell(r, addr_c).value))
    wb.close()
    return by_key, by_addr


def _ce_match(key: str, addr: str, by_key: dict, by_addr: dict) -> tuple[str, str]:
    """Match an I/O (key, addr) against the C&E indexes. Returns (status, detail):
    'full'     - the device and (when it has one) its address both line up;
    'fld_only' - the device is in the C&E but at (a) different address(es);
    'addr_only'- the address is in the C&E but under a different device;
    'missing'  - neither is in the C&E.
    `detail` names what differs, printing BOTH sides (I/O vs C&E)."""
    ce_addrs = by_key.get(key)
    if ce_addrs is not None and (not addr or addr in ce_addrs or not (ce_addrs - {""})):
        return "full", ""
    if ce_addrs is not None:
        ce = sorted(ce_addrs - {""}) or ["(no address)"]
        return "fld_only", f"found in C&E with a different address: I/O '{addr}' vs C&E {ce}"
    if addr and addr in by_addr:
        return "addr_only", (f"address in C&E under a different device: "
                             f"I/O '{key}' vs C&E {sorted(by_addr[addr])}")
    return "missing", "not found in C&E"


def check_ce_mandatory(params: dict, io_rows: list, log: list) -> None:
    """Reverse C&E: every I/O signal that must be in the C&E has to appear there, matched by
    BOTH its device key (FLD) and its address. Typed rows use their type's `ce_mandatory`
    (yes -> FAIL when not fully present, warn -> WARN, no/'' -> skip); untyped/unknown rows
    are checked when they carry a device designation (FLD) - or, device-less, a non-empty
    desc_l1/desc_l1b - plus an address, an absent one being a FAIL when its description names
    a safety concept else a WARN. A partial match (only the FLD or only the address differs)
    is logged at the same severity, printing both sides. Links to the functional-unit cell.

    Untyped rows whose description matches `ce_excluded_words` (params) are skipped entirely -
    BUT a `ce_mandatory_words` match wins (still checked), and typed rows are never excluded
    (signal-type rules prevail). `ce_full_check` (params, default false) ignores that list.
    `ce_always_excluded_words` (params, substring only - NO fuzzy) ALWAYS skips a row (typed
    or untyped), taking precedence over everything (not overridden by a mandatory match, not
    bypassed by ce_full_check) - e.g. 'ch2' to drop paired channel-2 rows. Every PASS/SKIP is
    written to the log (the .txt/.md hold the full record, with reasons); `ce_full_print`
    (params) controls only whether the live display (GUI/console) shows them (greyed)."""
    spec = params.get("ce") or {}
    if not spec.get("path") or not os.path.exists(spec["path"]):
        return
    by_key, by_addr = build_ce_index(params)
    io_path = (params.get("io_list") or {}).get("path", "")
    words = params.get("ce_mandatory_words") or list(CE_MANDATORY_WORDS)
    fuzzy = int(params.get("ce_fuzzy_chars", 2) or 0)
    excluded = [] if params.get("ce_full_check") else (params.get("ce_excluded_words") or [])
    always = params.get("ce_always_excluded_words") or []       # substring only, no fuzzy, wins all
    try:
        cols = {m["canonical"]: m["column"] for m in config.load_column_map("IoList")}
    except Exception:  # noqa: BLE001
        cols = {}
    fu_col = cols.get("functional_unit", "O")

    # every PASS/SKIP is logged (the file + .md are the full record); the live display
    # filters them out unless params.json ce_full_print is set.
    def skip(r, key, addr, why):
        nonlocal skipped
        skipped += 1
        log.append(LogEntry("SKIP", _io_loc(r, fu_col), key, addr, f"skipped - {why}", io_path, row=r))

    checked = skipped = 0
    for r in io_rows:
        key = _key(r.get("functional_unit"), r.get("location"), r.get("device"))
        addr = _addr(r.get("bit"))
        text = _row_text(r)
        aw = _first_match(text, always, 0)         # ALWAYS excluded (substring, no fuzzy) - wins all
        if aw:
            skip(r, key, addr, f"matches ce_always_excluded_words '{aw}'")
            continue
        typ = r.get("_type")
        if typ:                                    # known signal type -> ce_mandatory governs
            mand = str(typ.get("ce_mandatory", "")).strip().lower()
            if mand not in ("yes", "warn") or not key:
                continue
            checked += 1
            status, detail = _ce_match(key, addr, by_key, by_addr)
            if status == "full":
                log.append(LogEntry("PASS", _io_loc(r, fu_col), key, addr,
                                    f"present in C&E (ce_mandatory={mand})", io_path, row=r))
            else:
                log.append(LogEntry("FAIL" if mand == "yes" else "WARN", _io_loc(r, fu_col),
                                    key, addr, f"ce_mandatory={mand} but {detail}", io_path, row=r))
        else:                                      # untyped / unknown
            # check a real device (FLD), or - device-less - a row that still carries a
            # description (desc_l1/desc_l1b); a bare spare channel (no device, no desc) is
            # ignored. An address is always required.
            has_desc = bool(_norm(r.get("desc_l1")) or _norm(r.get("desc_l1b")))
            if not key or not addr or not (_norm(r.get("device")) or has_desc):
                continue
            safety = _matches_words(text, words, fuzzy)
            ew = _first_match(text, excluded, fuzzy) if (not safety and excluded) else None
            if ew:
                skip(r, key, addr, f"matches ce_excluded_words '{ew}'")
                continue
            checked += 1
            status, detail = _ce_match(key, addr, by_key, by_addr)
            if status == "full":
                log.append(LogEntry("PASS", _io_loc(r, fu_col), key, addr,
                                    "present in C&E (untyped full match)", io_path, row=r))
                continue
            reason = "description names a safety concept" if safety else "no safety keyword in description"
            log.append(LogEntry("FAIL" if safety else "WARN", _io_loc(r, fu_col), key, addr,
                                f"untyped signal {detail} ({reason})", io_path, row=r))
    if checked:
        log.append(LogEntry("INFO", "IOList in C&E", "", "", f"{checked} I/O signal(s) checked vs C&E"))
    if skipped:
        log.append(LogEntry("INFO", "IOList in C&E", "", "", f"{skipped} row(s) skipped (excluded words)"))


def validate(params: dict, io_rows: list) -> list:
    """The validation log: the effective params.json is logged first (config audit), then
    three clearly separated phases:
      1. C&E in IOList            - every C&E / AREA reference exists in the I/O List
      2. IOList in C&E            - every mandatory I/O signal appears in the C&E (reverse)
      3. Diagnosis Coherence Check - the in-diagnosis cabinet/bit map is complete + unique."""
    io_index = build_io_index(io_rows)
    io_by_key: dict[str, dict] = {}                 # key -> a representative I/O row (for info)
    for r in io_rows:
        k = _key(r.get("functional_unit"), r.get("location"), r.get("device"))
        if k:
            io_by_key.setdefault(k, r)
    ce_path = (params.get("ce") or {}).get("path", "")
    ce_ok = bool(ce_path and os.path.exists(ce_path))
    log: list[LogEntry] = []

    # log the effective params.json at the start, so the validation log records the config
    # (paths, ce_* knobs) that produced it
    log.append(LogEntry("INFO", "params.json", "", "",
                        json.dumps(params, indent=2, default=str)))

    _banner(log, "PHASE 1 - C&E in IOList  (every C&E / AREA reference exists in the I/O List)")
    log.append(LogEntry("INFO", "I/O List", "", "", f"{len(io_index)} distinct device key(s) indexed"))
    if ce_ok:
        check_ce_matrix(params, io_index, io_by_key, log)
        check_area_sheets(params, io_index, io_by_key, log)
    else:
        log.append(LogEntry("INFO", "C&E", "", "", f"C&E document not found ({ce_path}) - skipped"))

    _banner(log, "PHASE 2 - IOList in C&E  (every mandatory I/O signal appears in the C&E)")
    if ce_ok:
        check_ce_mandatory(params, io_rows, log)
    else:
        log.append(LogEntry("INFO", "C&E", "", "", f"C&E document not found ({ce_path}) - skipped"))

    _banner(log, "PHASE 3 - Diagnosis Coherence Check  (in-diagnosis cabinet/bit map)")
    check_diagnosis_bits(params, io_rows, log)
    return log


# A dark log page (so the pastel PASS/INFO read well, mirroring the dark GUI log viewer):
# font colour per level, FAIL/WARN bold, SKIP/INFO italic.
_HTML_CSS = """
  body{background:#1e1e1e;color:#d4d4d4;font:13px/1.55 Consolas,'Courier New',monospace;padding:18px;}
  h1{color:#e6e6e6;font-size:18px;margin:0 0 4px;}
  .summary{color:#e6e6e6;font-weight:bold;margin:0 0 10px;}
  h2.phase{color:#4ea1ff;font-size:15px;border-top:1px solid #3c3c3c;padding-top:14px;margin:22px 0 8px;}
  .entry{white-space:pre-wrap;margin:1px 0;}
  .FAIL{color:#ff6b6b;font-weight:bold;}
  .WARN{color:#e0a458;font-weight:bold;}
  .PASS{color:#D7FFAF;}
  .SKIP{color:#a8a8a8;font-style:italic;}
  .INFO{color:#FFE697;font-style:italic;}
"""


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _html_line(e) -> str:
    """One HTML log line: a phase -> a <h2> header; every other entry a colour-coded <div>
    (CSS class = the level), reusing the exact `format()` text (so .txt and .html match).
    `white-space:pre-wrap` keeps the monospace column layout."""
    if e.level == "PHASE":
        return f'<h2 class="phase">{_html_escape(e.message)}</h2>'
    cls = e.level if e.level in ("FAIL", "WARN", "PASS", "SKIP", "INFO") else "INFO"
    return f'<div class="entry {cls}">{_html_escape(e.format())}</div>'


def write_log(log: list, out_dir: str) -> tuple[int, int, int]:
    os.makedirs(out_dir, exist_ok=True)
    passed = sum(1 for e in log if e.level == "PASS")
    failed = sum(1 for e in log if e.level == "FAIL")
    warned = sum(1 for e in log if e.level == "WARN")
    skipped = sum(1 for e in log if e.level == "SKIP")
    summary = f"{passed} passed, {failed} failed, {warned} warning(s), {skipped} skipped"
    with open(os.path.join(out_dir, "validation_log.txt"), "w", encoding="utf-8") as f:
        for e in log:
            f.write(e.format() + "\n")
        f.write(f"\nSUMMARY: {summary}\n")
    # an HTML twin that keeps the coloured log-viewer layout (dark page, phases as headers,
    # severity colours per line) - renders in any browser.
    html = ["<!DOCTYPE html>",
            "<html><head><meta charset='utf-8'><title>Validation log</title>",
            "<style>", _HTML_CSS, "</style></head><body>",
            "<h1>Validation log</h1>", f'<p class="summary">{_html_escape(summary)}</p>']
    html += [_html_line(e) for e in log]
    html.append("</body></html>")
    with open(os.path.join(out_dir, "validation_log.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(html) + "\n")
    md_path = os.path.join(out_dir, "validation_log.md")        # remove the superseded markdown twin
    if os.path.exists(md_path):
        try:
            os.remove(md_path)
        except OSError:
            pass
    return passed, failed, warned

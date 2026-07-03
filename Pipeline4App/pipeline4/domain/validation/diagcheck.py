"""150 - Validate Diagnosis Assignments: the validation workflow's STEP 4 (user spec:
1 doc-1, 2 doc-2 if present, 3 cross-checks, 4 diagnosis checks - the last REQUIRES A FILLED doc).

PL4-native over the SSOT (PL3's 150 read the raw doc + needed `diag_block_name` staged - the reason
it was deferred; this reads the staged `signals` + `diagnosis_cabinets` tables and touches no locked
staging surface). For every in-diagnosis signal (`type.in_diag`):
- the (Diag Cabinet, Diag Bit) pair must be NUMERIC (`v_diag_invalid` FAIL - a filled doc must carry
  both);
- the cabinet must EXIST in the DiagnosisBlocks sheet (`v_diag_unknown_cab` FAIL - a slot pointing
  at a nonexistent cabinet silently misses its OPC block);
- the slot must be UNIQUE within its alarm/warning family (`v_diag_dup_slot` FAIL / `v_diag_unique`
  PASS; family = WARNING when `type_hw` ends 'W', so a legitimate alarm+warning pair on one slot is
  not a collision - PL3's rule).
On a VIRGIN document (no in-diag row carries any assignment) the whole step SKIPs
(`v_diag_virgin`) pointing at 200 Documents Fill Out. PL3's `diag_container_check`
(FullName-contains-container) is NOT ported: it needs the per-type container config column + the
cabinet FullName, neither of which PL4 carries yet (a reviewed config addition when wanted)."""
from __future__ import annotations

import os

from pipeline4.core import config
from pipeline4.domain.validation import model as vm


def _int(s):
    """int from a cell that may be '', '12', '-3', or a float-read '12.0'; None when not numeric."""
    s = str(s if s is not None else "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return int(s) if s.lstrip("-").isdigit() else None


def _in_diag(row) -> bool:
    return bool((row.get("type") or {}).get("in_diag"))


def _is_warning(row) -> bool:
    """WARNING family when `type_hw` ends 'W' (an alarm + a warning may legitimately share a slot)."""
    return str(row.get("type_hw", "")).strip().upper().endswith("W")


def run_diag_checks(database, params) -> list:
    rows = list(database["signals"]) if (database is not None and "signals" in database) else []
    cabinets = set()
    if database is not None and "diagnosis_cabinets" in database:
        for r in database["diagnosis_cabinets"]:
            cid = _int(r.get("cabinet_id"))
            if cid is not None:
                cabinets.add(cid)
    colmap = {m["canonical"]: m["column"] for m in config.load_column_map("IoList")}
    cab_col, bit_col = colmap.get("diag_cabinet", "AE"), colmap.get("diag_bit", "AF")
    io_doc = os.path.basename(params.get("iolist_path") or "")

    def loc(row, col):
        sheet, srow = row.get("source_sheet", ""), row.get("source_row", "")
        return f"{sheet}!{col}{srow}" if sheet and srow else str(row.get("source_cell", ""))

    diag_rows = [r for r in rows if _in_diag(r)]
    n = len(diag_rows)
    filled = [r for r in diag_rows
              if str(r.get("diag_cabinet") or "").strip() or str(r.get("diag_bit") or "").strip()]
    if n and not filled:                       # a VIRGIN doc: step 4 requires the ph200 fill
        return [vm.entry("SKIP", 150, "diag_virgin"),
                vm.entry("INFO", 150, "diag_summary", n=0)]

    out, by_slot = [], {}
    for row in diag_rows:
        cab_raw = str(row.get("diag_cabinet") or "").strip()
        bit_raw = str(row.get("diag_bit") or "").strip()
        cab, bit = _int(cab_raw), _int(bit_raw)
        info = vm.info_for_row(row)
        if cab is None or bit is None:
            fields = []
            if cab is None:
                fields.append(f"Diag Cabinet ('{cab_raw}')")
            if bit is None:
                fields.append(f"Diag Bit ('{bit_raw}')")
            out.append(vm.entry("FAIL", 150, "diag_invalid", fields=", ".join(fields),
                                location=loc(row, cab_col if cab is None else bit_col),
                                doc=io_doc, info=info))
            continue
        if cabinets and cab not in cabinets:   # numeric, but no such cabinet in DiagnosisBlocks
            out.append(vm.entry("FAIL", 150, "diag_unknown_cab", cab=cab,
                                location=loc(row, cab_col), doc=io_doc, info=info))
        family = "WARNING" if _is_warning(row) else "ALARM"
        by_slot.setdefault((cab, bit, family), []).append((row, info))

    for (cab, bit, family), members in sorted(by_slot.items()):
        slot = f"{cab:03d}.{bit:02d} {family}"
        if len(members) == 1:
            row, info = members[0]
            out.append(vm.entry("PASS", 150, "diag_unique", slot=slot,
                                location=loc(row, cab_col), doc=io_doc, info=info))
        else:
            bit_locs = [loc(r, bit_col) for r, _i in members]
            for i, (row, info) in enumerate(members):
                others = ", ".join(l for j, l in enumerate(bit_locs) if j != i)
                out.append(vm.entry("FAIL", 150, "diag_dup_slot", slot=slot, others=others,
                                    location=loc(row, bit_col), doc=io_doc, info=info))

    out.append(vm.entry("INFO", 150, "diag_summary", n=n))
    return out

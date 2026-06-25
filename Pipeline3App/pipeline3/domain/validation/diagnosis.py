"""150 - Validate Diagnosis Assignments (built from scratch; P2 `check_diagnosis_bits` intent).

For every in-diagnosis signal (its resolved type has `in_diagnosis`), the (Diag Cabinet, Diag Bit)
pair must be numeric and unique within its alarm/warning family. Family = WARNING when the type
letter ends 'W', else ALARM (so a legitimate alarm+warning pair on one slot is not a collision).
"""
from __future__ import annotations
import os

from pipeline3.core import config
from pipeline3.domain import identity
from pipeline3.domain.validation import model as vm


def _int(s):
    """int from a cell that may be '', '12', '-3', or a float-read '12.0'; None when not numeric."""
    s = (s or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return int(s) if s.lstrip("-").isdigit() else None


def _container_finding(ctx, row, info, sheet, srow, cab_col, io_doc):
    """The cabinet's DiagnosisBlocks FullName (staged as `diag_block_name`) must CONTAIN the signal type's
    expected diagnosis container - `diag_container_check` (signal_types.csv): a `{canonical}` template, `|`
    = any-of, matched case-insensitively (so `breaker` matches `+SafetyBreakers_1`, and
    `{functional_unit}{location}|Field` covers a lone field device). Returns a PASS/FAIL entry, or None when
    the type defines no container (or it resolves to nothing)."""
    tmpl = (row.get("_type") or {}).get("diag_container_check", "")
    accepted = [a for a in (identity.interp(alt, row) for alt in tmpl.split("|")) if a]
    if not accepted:
        return None
    fullname = vm.raw(row.get("diag_block_name"))
    loc = f"{sheet}!{cab_col}{srow}" if sheet and srow else row.get("source_cell", "")
    if any(a.lower() in fullname.lower() for a in accepted):
        return vm.entry("PASS", 150, "diag_container_ok", ctx.lang, location=loc, doc=io_doc, info=info)
    return vm.entry("FAIL", 150, "diag_container_bad", ctx.lang, expected=" | ".join(accepted),
                    actual=fullname or "(none)", location=loc, doc=io_doc, info=info)


def run_diagnosis(ctx) -> list:
    colmap = {m["canonical"]: m["column"] for m in config.load_column_map("IoList")}
    cab_col, bit_col = colmap.get("diag_cabinet", "AE"), colmap.get("diag_bit", "AF")
    io_doc = os.path.basename(ctx.io_list_path())

    out, by_slot, n = [], {}, 0
    for row in ctx.rows or []:
        if not (row.get("_type") or {}).get("in_diagnosis"):
            continue
        n += 1
        cab_raw, bit_raw = vm.raw(row.get("diag_cabinet")), vm.raw(row.get("diag_bit"))
        cab, bit = _int(cab_raw), _int(bit_raw)
        sheet, srow, info = row.get("_source_sheet", ""), row.get("_source_row", ""), vm.info_for_row(row)
        if cab is not None:                                  # the cabinet's FullName must hold the expected container
            c = _container_finding(ctx, row, info, sheet, srow, cab_col, io_doc)
            if c is not None:
                out.append(c)
        if cab is None or bit is None:
            fields = []
            if cab is None:
                fields.append(f"Diag Cabinet ('{cab_raw}')")
            if bit is None:
                fields.append(f"Diag Bit ('{bit_raw}')")
            badcol = cab_col if cab is None else bit_col
            loc = f"{sheet}!{badcol}{srow}" if sheet and srow else row.get("source_cell", "")
            out.append(vm.entry("FAIL", 150, "diag_invalid", ctx.lang, fields=", ".join(fields),
                                location=loc, doc=io_doc, info=info))
            continue
        fam = "WARNING" if vm.raw(row.get("type_hw")).upper().endswith("W") else "ALARM"
        by_slot.setdefault((cab, bit, fam), []).append((sheet, srow, info, row))

    for (cab, bit, fam), members in sorted(by_slot.items()):
        slot = f"{cab:03d}.{bit:02d} {fam}"
        if len(members) == 1:
            sheet, srow, info, row = members[0]
            loc = f"{sheet}!{cab_col}{srow}" if sheet and srow else row.get("source_cell", "")
            out.append(vm.entry("PASS", 150, "diag_unique", ctx.lang, slot=slot, location=loc, doc=io_doc, info=info))
        else:
            af_locs = [f"{s}!{bit_col}{sr}" if s and sr else r.get("source_cell", "")
                       for (s, sr, _i, r) in members]
            for i, (sheet, srow, info, row) in enumerate(members):
                others = ", ".join(l for j, l in enumerate(af_locs) if j != i)
                loc = f"{sheet}!{bit_col}{srow}" if sheet and srow else row.get("source_cell", "")
                out.append(vm.entry("FAIL", 150, "diag_dup_slot", ctx.lang, slot=slot, others=others,
                                    location=loc, doc=io_doc, info=info))

    out.append(vm.entry("INFO", 150, "diag_summary", ctx.lang, n=n))
    return out

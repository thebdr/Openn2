"""120 - Validate C&E Matrix standalone (new design; no P2 equivalent).

Single-document checks on the Cause & Effect workbook: the CAUSE&EFFECT MATRIX lists *inputs*
(I-addresses) - an output/internal address there is an error; the AREA n sheets list *outputs*
(Q/O-addresses) - an input address there is an error; and no address may repeat within one sheet.
C&E absent -> the sub-phase is skipped (one SKIP), never raises.
"""
from __future__ import annotations
import os

from pipeline3.core import config
from pipeline3.core.model import InfoBlock
from pipeline3.io import workbook as wbk
from pipeline3.io.workbook import FileLockedError
from pipeline3.domain.validation import model as vm, address as adr


def run_ce_matrix(ctx) -> list:
    ce = ctx.params.get("ce") or {}
    if not (ce.get("path") and os.path.exists(ce["path"])):
        return [vm.entry("SKIP", 120, "ce_absent", ctx.lang)]
    path = ce["path"]
    doc = os.path.basename(path)
    cemap = {m["canonical"]: m["column"] for m in config.load_column_map("CE")}
    areamap = {m["canonical"]: m["column"] for m in config.load_column_map("AREA")}
    out, sheets, refs = [], 0, 0

    try:
        # --- CAUSE&EFFECT MATRIX: inputs only, no dup --- #
        mhr = int(ce.get("matrix_header_row", 2) or 2)
        mdr = int(ce.get("matrix_data_row", 5) or 5)
        try:
            mv = wbk.open_sheet(path, ce.get("matrix_sheet"), header_row=mhr, first_data_row=mdr, doc_label=doc)
        except ValueError:
            mv = None
            out.append(vm.entry("WARN", 120, "ce_sheet_missing", ctx.lang, sheet=str(ce.get("matrix_sheet"))))
        if mv is not None:
            sheets += 1
            seen = {}
            for r in mv.data_rows():
                raw_a = mv.text(r, cemap["address"])
                a = adr.norm(raw_a)
                if not a:
                    continue
                refs += 1
                loc, info = mv.location(r, cemap["address"]), InfoBlock(bit=raw_a)
                if adr.is_output(a):
                    out.append(vm.entry("FAIL", 120, "matrix_addr_kind", ctx.lang, addr=raw_a, location=loc, doc=doc, info=info))
                if a in seen:
                    out.append(vm.entry("FAIL", 120, "dup_addr", ctx.lang, addr=raw_a, first=seen[a], location=loc, doc=doc, info=info))
                else:
                    seen[a] = loc
            mv.close()

        # --- AREA n sheets: outputs only, no dup --- #
        ahr = int(ce.get("area_header_row", 3) or 3)
        adrow = int(ce.get("area_data_row", 4) or 4)
        area_pat = ctx.params.get("areas")
        avs = wbk.open_sheets(path, area_pat, header_row=ahr, first_data_row=adrow, doc_label=doc) if area_pat else []
        for av in avs:
            sheets += 1
            seen = {}
            for r in av.data_rows():
                raw_a = av.text(r, areamap["address"])
                a = adr.norm(raw_a)
                if not a:
                    continue
                refs += 1
                loc, info = av.location(r, areamap["address"]), InfoBlock(bit=raw_a)
                if adr.is_input(a):
                    out.append(vm.entry("FAIL", 120, "area_addr_kind", ctx.lang, addr=raw_a, location=loc, doc=doc, info=info))
                if a in seen:
                    out.append(vm.entry("FAIL", 120, "dup_addr", ctx.lang, addr=raw_a, first=seen[a], location=loc, doc=doc, info=info))
                else:
                    seen[a] = loc
        if avs:
            avs[0].close()
    except FileLockedError:
        return [vm.entry("FAIL", 120, "ce_locked", ctx.lang)]

    out.append(vm.entry("INFO", 120, "ce_summary", ctx.lang, refs=refs, sheets=sheets))
    return out

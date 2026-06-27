"""120 - Validate C&E Matrix standalone. Clean-room port of PL3's `domain/validation/matrix.py`.

Single-document checks on the Cause & Effect workbook: the CAUSE&EFFECT MATRIX lists *inputs*
(I-addresses) - an output/internal address there is an error; the AREA n sheets list *outputs*
(Q/O-addresses) - an input address there is an error; and no address may repeat within one sheet. C&E
absent -> the sub-phase is skipped (one SKIP), never raises. PL4: takes `params` (no `ctx`), reads the C&E
paths/rows from `matrix_params` via `get_param`.
"""
from __future__ import annotations

import os

from pipeline4.core import config
from pipeline4.core.model import InfoBlock
from pipeline4.io import workbook as wbk
from pipeline4.io.workbook import FileLockedError
from pipeline4.domain.validation import address as adr, model as vm


def run_ce_matrix(params: dict) -> list:
    """Validate the Cause&Effect workbook of `params['matrix_path']`. Returns a list of phase-120 Findings."""
    path = params.get("matrix_path") or ""
    if not (path and os.path.exists(path)):
        return [vm.entry("SKIP", 120, "ce_absent")]
    doc = os.path.basename(path)
    cemap = {m["canonical"]: m["column"] for m in config.load_column_map("CE")}
    areamap = {m["canonical"]: m["column"] for m in config.load_column_map("AREA")}
    out, sheets, refs = [], 0, 0

    try:
        # --- CAUSE&EFFECT MATRIX: inputs only, no dup --- #
        mhr = int(config.get_param(params, "matrix_params.ce_sheet.header_row", 2) or 2)
        mdr = int(config.get_param(params, "matrix_params.ce_sheet.data_row", 5) or 5)
        msheet = config.get_param(params, "matrix_params.ce_sheet.name")
        try:
            mv = wbk.open_sheet(path, msheet, mhr, first_data_row=mdr, doc_label=doc)
        except ValueError:
            mv = None
            out.append(vm.entry("WARN", 120, "ce_sheet_missing", sheet=str(msheet)))
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
                    out.append(vm.entry("FAIL", 120, "matrix_addr_kind", addr=raw_a, location=loc, doc=doc, info=info))
                if a in seen:
                    out.append(vm.entry("FAIL", 120, "dup_addr", addr=raw_a, first=seen[a], location=loc, doc=doc, info=info))
                else:
                    seen[a] = loc
            mv.close()

        # --- AREA n sheets: outputs only, no dup --- #
        ahr = int(config.get_param(params, "matrix_params.area_sheets.header_row", 3) or 3)
        adrow = int(config.get_param(params, "matrix_params.area_sheets.data_row", 4) or 4)
        area_pat = config.get_param(params, "matrix_params.area_sheets.name")
        avs = wbk.open_sheets(path, area_pat, ahr, first_data_row=adrow, doc_label=doc) if area_pat else []
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
                    out.append(vm.entry("FAIL", 120, "area_addr_kind", addr=raw_a, location=loc, doc=doc, info=info))
                if a in seen:
                    out.append(vm.entry("FAIL", 120, "dup_addr", addr=raw_a, first=seen[a], location=loc, doc=doc, info=info))
                else:
                    seen[a] = loc
        if avs:
            avs[0].close()
    except FileLockedError:
        return [vm.entry("FAIL", 120, "ce_locked")]

    out.append(vm.entry("INFO", 120, "ce_summary", refs=refs, sheets=sheets))
    return out

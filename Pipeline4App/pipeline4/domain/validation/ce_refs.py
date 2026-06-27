"""Indexes for the phase-100 cross-checks (130/140). Clean-room port of PL3's
`domain/validation/indexes.py`, reading the SSOT `signals` rows (130's I/O indexes) + the C&E workbook
(`read_ce_refs`, via the one reader + the PL4 `matrix_params`).

- `build_io_index(rows)` - the staged signals keyed by FLD, for the forward check (130).
- `build_io_addr_index(rows)` - the staged signals keyed by ADDRESS, for 130's 'search by I/O address'.
- `read_ce_refs(params)` - every (address, device) reference in the C&E workbook (CAUSE&EFFECT MATRIX rows
  + AREA n sheets); each ref carries its clickable `sheet!cell` location. May raise FileLockedError.
- `build_ce_index(refs)` - those refs indexed by FLD and by address, for the reverse check (140).
"""
from __future__ import annotations

import os

from pipeline4.core import config
from pipeline4.io import workbook as wbk
from pipeline4.domain.validation import model as vm


def build_io_index(rows) -> dict:
    """FLD key -> {addrs:set, raw_addr:{norm->raw}, raw_fld:str, source_cell:str}."""
    idx: dict = {}
    for r in rows or []:
        k = vm.key(r.get("functional_unit"), r.get("location"), r.get("device"))
        if not k:
            continue
        a = vm.addr(r.get("bit"))
        e = idx.setdefault(k, {"addrs": set(), "raw_addr": {}, "raw_fld": "", "source_cell": ""})
        if a:
            e["addrs"].add(a)
            e["raw_addr"].setdefault(a, vm.raw(r.get("bit")))
        if not e["raw_fld"]:
            e["raw_fld"] = vm.fld_text(r.get("functional_unit"), r.get("location"), r.get("device"))
        if not e["source_cell"]:
            e["source_cell"] = r.get("source_cell", "")
    return idx


def build_io_addr_index(rows) -> dict:
    """address key -> {keys:set(FLD), raw_fld:{FLD->raw}, source_cell:str} - the staged signals keyed by
    ADDRESS, for the forward check's 'search by I/O address' (130)."""
    idx: dict = {}
    for r in rows or []:
        a = vm.addr(r.get("bit"))
        if not a:
            continue
        k = vm.key(r.get("functional_unit"), r.get("location"), r.get("device"))
        e = idx.setdefault(a, {"keys": set(), "raw_fld": {}, "source_cell": ""})
        if k:
            e["keys"].add(k)
            e["raw_fld"].setdefault(k, vm.fld_text(r.get("functional_unit"), r.get("location"), r.get("device")))
        if not e["source_cell"]:
            e["source_cell"] = r.get("source_cell", "")
    return idx


def read_ce_refs(params: dict) -> tuple:
    """Read every C&E reference -> (refs, sheet_count). Each ref:
    {sheet, addr(norm), raw_addr, key(FLD), raw_fld, loc('sheet!cell')}. Reads the CAUSE&EFFECT MATRIX
    (address col F + FLD cols J/K/L) + the AREA n sheets (address col C keyed by concat_id col A) via the
    PL4 matrix_params. May raise FileLockedError."""
    path = params.get("matrix_path") or ""
    doc = os.path.basename(path)
    cemap = {m["canonical"]: m["column"] for m in config.load_column_map("CE")}
    areamap = {m["canonical"]: m["column"] for m in config.load_column_map("AREA")}
    refs, sheets = [], 0

    # --- CAUSE&EFFECT MATRIX: address (col F) + matrix-side FLD (cols J/K/L) --- #
    mhr = int(config.get_param(params, "matrix_params.ce_sheet.header_row", 2) or 2)
    mdr = int(config.get_param(params, "matrix_params.ce_sheet.data_row", 5) or 5)
    msheet = config.get_param(params, "matrix_params.ce_sheet.name")
    try:
        mv = wbk.open_sheet(path, msheet, mhr, first_data_row=mdr, doc_label=doc)
    except ValueError:
        mv = None
    if mv is not None:
        sheets += 1
        for r in mv.data_rows():
            raw_a = mv.text(r, cemap["address"])
            fu, lo, de = (mv.text(r, cemap["functional_unit"]), mv.text(r, cemap["location"]),
                          mv.text(r, cemap["device"]))
            a, k = vm.addr(raw_a), vm.key(fu, lo, de)
            if not a and not k:
                continue
            refs.append({"sheet": mv.name, "addr": a, "raw_addr": raw_a, "key": k,
                         "raw_fld": vm.fld_text(fu, lo, de), "loc": mv.location(r, cemap["address"])})
        mv.close()

    # --- AREA n sheets: output address (col C) keyed by its sigla (col A) --- #
    ahr = int(config.get_param(params, "matrix_params.area_sheets.header_row", 3) or 3)
    adrow = int(config.get_param(params, "matrix_params.area_sheets.data_row", 4) or 4)
    area_pat = config.get_param(params, "matrix_params.area_sheets.name")
    avs = wbk.open_sheets(path, area_pat, ahr, first_data_row=adrow, doc_label=doc) if area_pat else []
    for av in avs:
        sheets += 1
        for r in av.data_rows():
            raw_a = av.text(r, areamap["address"])
            a = vm.addr(raw_a)
            if not a:
                continue
            cid = av.text(r, areamap["concat_id"])
            refs.append({"sheet": av.name, "addr": a, "raw_addr": raw_a, "key": vm.key(cid),
                         "raw_fld": vm.raw(cid), "loc": av.location(r, areamap["address"])})
    if avs:
        avs[0].close()
    return refs, sheets


def build_ce_index(refs) -> dict:
    """Index C&E refs by FLD and by address, with first-seen `sheet!cell` locations."""
    by_key, by_addr, loc_by_key, loc_by_addr = {}, {}, {}, {}
    raw_fld_by_key, raw_addr_by_key = {}, {}
    for ref in refs:
        k, a = ref["key"], ref["addr"]
        if k:
            by_key.setdefault(k, set())
            loc_by_key.setdefault(k, ref["loc"])
            raw_fld_by_key.setdefault(k, ref["raw_fld"])
            raw_addr_by_key.setdefault(k, {})
            if a:
                by_key[k].add(a)
                raw_addr_by_key[k].setdefault(a, ref["raw_addr"])
        if a:
            by_addr.setdefault(a, set())
            loc_by_addr.setdefault(a, ref["loc"])
            if k:
                by_addr[a].add(k)
    return {"by_key": by_key, "by_addr": by_addr, "loc_by_key": loc_by_key,
            "loc_by_addr": loc_by_addr, "raw_fld_by_key": raw_fld_by_key, "raw_addr_by_key": raw_addr_by_key}

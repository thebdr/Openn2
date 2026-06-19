"""Annotate staged rows with their C&E data: `matrix_areas`, the C&E-side FLD
(`ce_functional_unit`/`ce_location`/`ce_device`), and `numerazione_linea`. Derived from the Cause &
Effect workbook (best-effort: blanks when the C&E doc is absent).

  * input signal  (I-address): matched by address (col F) on the CAUSE&EFFECT MATRIX → the AREA
    columns marked "X" (area columns = headers matching the `areas` regex) + the matrix-side FLD
    (cols J/K/L).
  * output signal (Q-address): matched by address (col C) on the AREA n sheets → those sheet names
    + `numerazione_linea` (col B).

Area columns + AREA sheets are detected via the `areas` regex param (JS `/…/flags` accepted). Paired
channels of one device share the union of their C&E data (the matrix lists the device once).
"""
from __future__ import annotations
import os
import re

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string as _ci

from pipeline3.core import config


def _norm(value) -> str:
    """Address/marker key: whitespace removed, upper-cased."""
    return "".join(str(value or "").split()).upper()


def _s(value) -> str:
    return str(value if value is not None else "").strip()


def _areas_re(params):
    pat = params.get("areas")
    if not pat:
        return None
    try:
        return re.compile(config.js_to_re(pat), re.IGNORECASE)
    except re.error:
        return None


def area_lookup(params: dict) -> tuple:
    """(inputs, outputs):
      inputs:  norm(I-addr) -> {areas:[names], ce_functional_unit, ce_location, ce_device}
      outputs: norm(Q-addr) -> {areas:[sheet names], numerazione_linea}
    Empty dicts when the C&E document is missing."""
    ce = params.get("ce") or {}
    if not ce.get("path") or not os.path.exists(ce["path"]):
        return {}, {}
    wb = load_workbook(ce["path"], data_only=True, read_only=True)
    inputs, outputs = {}, {}
    cemap = {m["canonical"]: m["column"] for m in config.load_column_map("CE")}
    areamap = {m["canonical"]: m["column"] for m in config.load_column_map("AREA")}
    area_re = _areas_re(params)

    # --- CAUSE&EFFECT MATRIX: input address -> areas marked X + matrix-side FLD ---
    area_cols = []   # ordered (col_index, area_name) of the matrix EFFECT/area columns
    msheet = config.resolve_sheet(ce.get("matrix_sheet"), wb.sheetnames)
    if msheet:
        ws = wb[msheet]
        hr, dr = int(ce.get("matrix_header_row", 2)), int(ce.get("matrix_data_row", 5))
        addr_c = _ci(cemap["address"])
        fu_c, loc_c, dev_c = _ci(cemap["functional_unit"]), _ci(cemap["location"]), _ci(cemap["device"])
        # area columns = headers (on the matrix header row) matching the areas regex
        for c in range(1, ws.max_column + 1):
            nm = _s(ws.cell(hr, c).value)
            if nm and (area_re is None or area_re.search(nm)):
                area_cols.append((c, nm))
        for r in range(dr, ws.max_row + 1):
            addr = _norm(ws.cell(r, addr_c).value)
            if not addr:
                continue
            areas = [nm for c, nm in area_cols
                     if _s(ws.cell(r, c).value).upper() == "X"]
            inputs[addr] = {
                "areas": areas,
                "ce_functional_unit": _s(ws.cell(r, fu_c).value),
                "ce_location": _s(ws.cell(r, loc_c).value),
                "ce_device": _s(ws.cell(r, dev_c).value),
            }

    # --- AREA n sheets: output Q address -> sheet names + numerazione_linea ---
    area_sheets = config.resolve_sheets(params.get("areas"), wb.sheetnames) if area_re else \
        [s for s in wb.sheetnames if s.strip().upper().startswith("AREA") and any(ch.isdigit() for ch in s)]
    out_addr_c = _ci(areamap["address"])
    num_c = _ci(areamap["numerazione_linea"]) if "numerazione_linea" in areamap else None
    adr = int(ce.get("area_data_row", 4))
    for s in area_sheets:
        a = wb[s]
        for r in range(adr, a.max_row + 1):
            q = _norm(a.cell(r, out_addr_c).value)
            if not q:
                continue
            d = outputs.setdefault(q, {"areas": [], "numerazione_linea": ""})
            d["areas"].append(s.strip())
            if not d["numerazione_linea"] and num_c:
                d["numerazione_linea"] = _s(a.cell(r, num_c).value)

    # --- CONCEPT sheet: one description per area on `concept_row`, positionally aligned with the
    # ordered matrix area columns; newlines collapsed to spaces ---
    area_desc = {}
    csheet = config.resolve_sheet(ce.get("concept_sheet"), wb.sheetnames) if ce.get("concept_sheet") else None
    if csheet and area_cols:
        cs = wb[csheet]
        crow = int(ce.get("concept_row", 2))
        descs = [" ".join(_s(cs.cell(crow, c).value).split())
                 for c in range(1, cs.max_column + 1) if _s(cs.cell(crow, c).value)]
        for name, desc in zip([nm for _, nm in area_cols], descs):
            area_desc[name] = desc
    wb.close()
    return inputs, outputs, area_desc


_FIELDS = ("ce_functional_unit", "ce_location", "ce_device", "numerazione_linea")


def annotate(params: dict, rows: list) -> list:
    """Set matrix_areas + ce_FLD + numerazione_linea on every staged row by its I/Q address. Paired
    channels (same pair_key + FLD) share the union of areas and each other's C&E fields."""
    inputs, outputs, area_desc = area_lookup(params)
    found = {}
    for row in rows:
        bit = _norm(row.get("bit"))
        head = bit[:1]
        if head == "I":
            found[id(row)] = dict(inputs.get(bit) or {})
        elif head == "Q":
            found[id(row)] = dict(outputs.get(bit) or {})
        else:
            found[id(row)] = {}

    # pair inheritance: union areas + share ce fields across a device's channels
    groups: dict = {}
    for row in rows:
        pk = ((row.get("_type") or {}).get("pair_key") or "").strip().upper()
        if not pk:
            continue
        key = (pk, _norm(row.get("functional_unit")), _norm(row.get("location")), _norm(row.get("device")))
        groups.setdefault(key, []).append(row)
    for members in groups.values():
        union = []
        merged = {}
        for m in members:
            d = found[id(m)]
            for a in d.get("areas", []):
                if a not in union:
                    union.append(a)
            for f in _FIELDS:
                if not merged.get(f) and d.get(f):
                    merged[f] = d[f]
        for m in members:
            if union:
                found[id(m)]["areas"] = union
            for f in _FIELDS:
                if not found[id(m)].get(f) and merged.get(f):
                    found[id(m)][f] = merged[f]

    for row in rows:
        d = found[id(row)]
        areas = d.get("areas", [])
        row["matrix_areas"] = "|".join(areas)
        row["areas_description"] = "|".join(area_desc.get(a, "") for a in areas if area_desc.get(a))
        for f in _FIELDS:
            row[f] = d.get(f, "")
    return rows

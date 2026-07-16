"""Staging (phase 300): read the I/O List into the `signals` table - PL4's SSOT fact table.

First cut: read each matched IoList sheet through the one workbook reader (by column position per
column_map), keep the real rows (drop Skip-Reason + struck rows per `strike_handling`), attach the
resolved `type`, and derive the DOCUMENT-side identity (the FLDs + the PLC tag name/table). Then build
the `signals` table (one row each, content-hash `uid`) and save the Database.

Now also: the C&E enrichment (`matrix.annotate`), the POSITIONAL node address ranges
(`I_/Q_startByte/endByte`), and `IsSorterArea`. Still deferred to their phases (then the full real-data
parity vs PL3 closes): the registry-derived names (`name_in_db` / `datablocks` / `plc_binding`),
`subnet_name`, and the diagnosis / interface identity.

Staging is split into two independently runnable legs (the oracle 310 / 320 buttons): `stage_iolist`
reads the I/O List into the `signals` table WITHOUT the C&E (so `combined_FLD` == `iol_FLD`), and
`annotate_cematrix` layers the Cause&Effect data on top, re-stamping the uid. `stage` runs both and is
byte-identical to the former monolith; every downstream phase still just calls `stage`.
"""
from __future__ import annotations

import os

from pipeline5.core import config
from pipeline5.core import phase_gate as run
from pipeline5.core.ssot_database import Database
from pipeline5.core.finding import Finding, record
from pipeline5.core.content_hash import uid as content_uid
from pipeline5.domain import signal_identity as identity
from pipeline5.domain import cematrix_annotation as matrix
from pipeline5.domain.diagnosis_schema import diagnosis_cabinets_table
from pipeline5.domain.signals_schema import signals_table
from pipeline5.io import xlsx_reader as workbook

_DIAGBLOCKS_SHEETS = frozenset({"diagnosisblocks", "diagnosticblocks"})   # current + legacy spelling


def _f(type: str, severity: str, detail: str, location: str = "", source_uid: str = "") -> Finding:
    """A phase-300 Finding - staging's report container (the no-I/O-sheet FAIL + the duplicate-uid WARN)."""
    return Finding(phase=300, type=type, severity=severity, detail=detail,
                   location=location, source_uid=source_uid)


def _dup_findings(table) -> list:
    """One `stg_dup_signal_uid` WARN per signal uid shared by more than one row (the content-hash key needs a
    tiebreak). Pure over the built `signals` table - replaces the GUI's post-stage duplicate_uids() check."""
    return [_f("stg_dup_signal_uid", "WARN",
               f"signal uid {dup} is shared by more than one row - the key needs a tiebreak", dup)
            for dup in sorted(table.duplicate_uids())]


def _dup_type_index_findings(table) -> list:
    """One `stg_dup_type_index` FAIL per signal sharing its (script_type, index) with another - the pair
    MUST be unique. The index-grouping builders (05 Output Feedback / 07 Speed Control / 08 Gate Manager)
    key units on `index`, so a duplicate is silently MERGED into one unit (e.g. two KQ-5 become a bogus
    2-contactor unit) instead of being flagged - so this HALTS (a raw FAIL) rather than corrupt generation.
    A blank index is skipped (only indexed signals participate); one finding per occurrence, each located at
    its own I/O-List cell + naming the sibling cell(s) so both/all duplicates are individually clickable."""
    groups: dict = {}
    for row in table.rows:
        st, idx = _norm(row.get("script_type")), _norm(row.get("index"))
        if st and idx:
            groups.setdefault((st, idx), []).append(row)
    out = []
    for (st, idx), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        cells = [_norm(r.get("source_cell")) for r in rows]
        for i, row in enumerate(rows):
            others = ", ".join(c for j, c in enumerate(cells) if j != i and c)
            out.append(_f("stg_dup_type_index", "FAIL",
                          f"duplicated {st} index {idx} - a (script_type, index) pair must be unique"
                          + (f" (also at {others})" if others else ""), _norm(row.get("source_cell"))))
    return out


def _skip_reason_present(value) -> bool:
    return str(value or "").strip() not in ("", "0", "0.0")


def _norm(value) -> str:
    return "" if value is None else str(value).strip()


def _cabinet_id(value):
    """int cabinet id from a cell that may be 1, '1', '1.0', '001', or blank; None when not numeric."""
    s = _norm(value)
    if s.endswith(".0"):
        s = s[:-2]
    return int(s) if s.lstrip("-").isdigit() else None


def load_diagnosis_blocks(io_path: str) -> dict:
    """{cabinet_id:int -> {index, fld, template_type, swp}} from the DiagnosisBlocks sheet, keyed by
    ID_Local (= the row's diag_cabinet, the local cabinet); falls back to ID_SWP when ID_Local is absent.
    `template_type` drives the SCL's 01-04 cabinet variant; `swp` is the ID_SWP. {} when the sheet/column
    is missing. Clean-room port of PL3 `staging.load_diagnostic_blocks` - the parent of the
    `diagnosis_cabinets` SSOT table (read here at staging so phase 600 is a pure table read)."""
    if not io_path or not os.path.exists(io_path):
        return {}
    wb = workbook.open_workbook(io_path, data_only=True)
    try:
        sheet = next((s for s in wb.sheetnames if s.strip().lower() in _DIAGBLOCKS_SHEETS), None)
        if sheet is None:
            return {}
        grid = list(wb[sheet].iter_rows(values_only=True))
    finally:
        wb.close()
    if not grid:
        return {}
    header = [" ".join(_norm(c).split()).lower() for c in grid[0]]

    def col(name):
        key = " ".join(name.split()).lower()
        return next((i for i, h in enumerate(header) if h == key), None)

    c_local, c_swp, c_fld, c_tt = col("ID_Local"), col("ID_SWP"), col("FullName"), col("TemplateType")
    c_key = c_local if c_local is not None else c_swp
    if c_key is None:
        return {}
    out = {}
    for r in grid[1:]:
        cid = _cabinet_id(r[c_key]) if c_key < len(r) else None
        if cid is None:
            continue
        out[cid] = {
            "index": f"{cid:03d}",
            "fld": _norm(r[c_fld]) if c_fld is not None and c_fld < len(r) else "",
            "template_type": _norm(r[c_tt]) if c_tt is not None and c_tt < len(r) else "",
            "swp": _norm(r[c_swp]) if (c_swp is not None and c_swp < len(r) and _norm(r[c_swp])) else f"{cid}",
        }
    return out


def _read_view(view, colmap, strike_exclude, signal_types) -> list:
    """The kept rows of one sheet: a dict per data row keyed by canonical column, + source provenance +
    the resolved `type`. Drops fully-empty, Skip-Reason, and (when excluding) struck rows."""
    rows = []
    for r in view.data_rows():
        if all(view.text(r, m["column"]) == "" for m in colmap):
            continue
        row = {m["canonical"]: view.text(r, m["column"]) for m in colmap}
        row["source_row"] = r
        row["source_sheet"] = view.name
        if _skip_reason_present(row.get("skip_reason")):
            continue
        if strike_exclude and view.row_struck(r):
            continue
        row["type"] = config.resolve_type(signal_types, row.get("script_type"))
        rows.append(row)
    return rows


def _read_iolist(params: dict, signal_types: dict, io_path: str) -> tuple:
    """Read the matched IoList sheets into RAW staged rows (the canonical columns + source provenance + the
    resolved `type`), WITHOUT the C&E enrichment or the derived identity. Returns (rows, matched_sheets).
    This is the read-only leg shared by `stage_iolist` (310) and `load_io_list`."""
    colmap = config.load_column_map("IoList")
    header_row = int(config.get_param(params, "iolist_params.header_row", 1) or 1)
    strike_exclude = str(config.get_param(params, "validation_params.global.strike_handling", "exclude")
                         ).strip().lower() == "exclude"
    sheet_pattern = config.get_param(params, "iolist_params.sheets")

    # merge the per-type diagnosis attrs onto each type record BEFORE resolving (so the staged `type`
    # object carries in_diag/diag_logic/tristate/tristate_desc - in_diag also lights up the phase-400
    # +DIAG auto-mirror). diag_desc is a template, resolved in _finalize_identity.
    signal_diag = config.load_signal_diagnosis()
    for t in signal_types.values():
        d = signal_diag.get(t["type_id"].upper(), {})
        t["in_diag"] = d.get("in_diag", False)
        t["diag_logic"] = d.get("diag_logic", "")
        t["tristate"] = d.get("tristate", False)
        t["tristate_desc"] = d.get("tristate_desc", "")

    views = workbook.open_sheets(io_path, sheet_pattern, header_row, doc_label=os.path.basename(io_path))
    matched = [v.name for v in views]
    if not matched:
        return [], matched          # the caller emits the blocking stg_no_io_sheet FAIL

    rows = []
    for view in views:
        rows.extend(_read_view(view, colmap, strike_exclude, signal_types))
    views[0].close()
    return rows, matched


def _finalize_identity(params: dict, rows: list) -> None:
    """Derive each row's staging identity from its CURRENT fields: the I/O-List FLD + the PLC tag
    name/table + the positional node ranges, AND the C&E-dependent `ce_FLD`/`combined_FLD`/`IsSorterArea`/
    `diag_desc` (which read the `ce_*`/`matrix_areas` fields that `matrix.annotate` writes).

    Idempotent and order-free, which is what makes the 310/320 split byte-exact: run it after the read
    (the C&E fields absent -> `ce_FLD` '' -> `combined_FLD` == `iol_FLD`, `IsSorterArea` '') and AGAIN after
    `matrix.annotate` (the C&E values now present overwrite the I/O-only ones) and you land on exactly the
    monolithic result. `combined_FLD` is part of the signals uid key, so the caller re-stamps the uid after
    the C&E pass."""
    colmap = config.load_column_map("IoList")
    signal_diag = config.load_signal_diagnosis()
    fu_col = next((m["column"] for m in colmap if m["canonical"] == "functional_unit"), "O")
    sorter_names = _sorter_area_names(params)
    for row in rows:
        if not row.get("source_cell") and row.get("source_row"):
            row["source_cell"] = f"{row.get('source_sheet', '')}!{fu_col}{row['source_row']}"
        row["iol_FLD"] = identity.fld(row)
        row["ce_FLD"] = identity.ce_fld(row)
        row["combined_FLD"] = identity.combined_fld(row)
        row["IsSorterArea"] = _is_sorter_area(row, sorter_names)
        diag_template = signal_diag.get(str((row.get("type") or {}).get("type_id", "")).upper(),
                                        {}).get("diag_desc", "")
        row["diag_desc"] = identity.interp(diag_template, row)   # the resolved per-type diagnosis text
        if identity.is_io_signal(row) and identity.tag_name(row):
            row["name_in_tagtable"] = identity.tag_name(row)
            row["tagtable"] = identity.tagtable(row)
        else:
            row["name_in_tagtable"] = ""
            row["tagtable"] = ""
    _add_node_address_ranges(rows)   # positional I/Q byte ranges: a node owns the rows beneath it


def load_io_list(params: dict, signal_types: dict, io_path: str) -> tuple:
    """Read the matched IoList sheets into FULLY enriched staged rows (read -> C&E annotate -> identity).
    Returns (rows, matched_sheets). Retained as the combined read (and the no-match guard); `stage` itself
    uses the `stage_iolist` / `annotate_cematrix` split, which reuses these same helpers."""
    rows, matched = _read_iolist(params, signal_types, io_path)
    if not matched:
        return rows, matched        # the caller (stage) emits the blocking stg_no_io_sheet FAIL
    matrix.annotate(params, rows)   # C&E enrichment: matrix_areas / ce_* / numerazione_linea / areas_description
    _finalize_identity(params, rows)
    return rows, matched


def _sorter_area_names(params: dict) -> set:
    """The Sorter area NAMES, built from the configured sorter area NUMBERS. The user keeps
    `matrix_params.sorter_areas` as numbers (`[1]`); a row IsSorterArea when its `matrix_areas` intersect
    these names (`1` -> "AREA 1"). Empty when nothing is configured."""
    numbers = config.get_param(params, "matrix_params.sorter_areas", []) or []
    return {f"AREA {n}" for n in numbers}


def _is_sorter_area(row: dict, sorter_names: set) -> str:
    """"yes" when the row's `matrix_areas` (a real list cell) names any Sorter area, else ""."""
    return "yes" if (set(row.get("matrix_areas") or []) & sorter_names) else ""


def _addr_byte(bit):
    """('I'|'Q', byte:int) for an I/Q `.bit` address (e.g. 'I12.3' -> ('I', 12)); None otherwise."""
    b = str(bit or "").strip().upper()
    if b[:1] in ("I", "Q") and "." in b:
        try:
            return b[0], int(b[1:b.index(".")])
        except ValueError:
            return None
    return None


def _add_node_address_ranges(rows) -> None:
    """A Profinet node's I/Q byte range is POSITIONAL: it owns every row beneath it - in I/O-List order -
    until the next node, or the end of its sheet. The range is the min/max byte address of those rows.
    NOT keyed by FLD/location: a safety module's emergency stops carry their OWN device location (a push
    button's +ES..), so a location key misses them and leaves the module's range empty - which then drops
    those signals from every node-of lookup (the 02/06/08 builders, diagnosis FL, coverage). Writes
    `I_/Q_startByte/endByte` on the node-head row (the one carrying `profinet_name`); '' on every other."""
    def _flush(node, ib, qb):
        if node is None:
            return
        node["I_startByte"] = min(ib) if ib else ""
        node["I_endByte"] = max(ib) if ib else ""
        node["Q_startByte"] = min(qb) if qb else ""
        node["Q_endByte"] = max(qb) if qb else ""

    for r in rows:
        r["I_startByte"] = r["I_endByte"] = r["Q_startByte"] = r["Q_endByte"] = ""
    cur, ib, qb, sheet = None, [], [], object()       # sentinel sheet -> the first row opens one
    for r in rows:
        rs = r.get("source_sheet")
        if rs != sheet:                                # a new sheet ends the current node's span
            _flush(cur, ib, qb); cur, ib, qb, sheet = None, [], [], rs
        if r.get("profinet_name"):                     # a node head opens a new span (and owns its own bit)
            _flush(cur, ib, qb); cur, ib, qb = r, [], []
        ab = _addr_byte(r.get("bit"))
        if ab and cur is not None:
            (ib if ab[0] == "I" else qb).append(ab[1])
    _flush(cur, ib, qb)


def _load_cabinets(io_path: str, cab_table) -> None:
    """Fill the `diagnosis_cabinets` table from the DiagnosisBlocks sheet (an I/O-List-side read, so it
    belongs to 310 / `stage_iolist`, not the C&E pass)."""
    cabinets = load_diagnosis_blocks(io_path)
    for cid in sorted(cabinets):
        c = cabinets[cid]
        cab_table.add(cabinet_id=cid, index=c["index"], fld=c["fld"],
                      template_type=c["template_type"], swp=c["swp"])


def stage_iolist(params: dict | None = None, save: bool = True) -> tuple:
    """Phase 310 - Stage I/O List: read the I/O List into the `signals` table WITHOUT the C&E enrichment
    (no matrix_areas / ce_* / numerazione_linea -> `combined_FLD` == `iol_FLD`, `IsSorterArea` ''), plus the
    `diagnosis_cabinets` table; save the Database and return (database, findings). A missing I/O sheet emits
    the blocking `stg_no_io_sheet` FAIL and returns WITHOUT writing (raw-FAIL guard). `annotate_cematrix`
    (320) layers the C&E on top; `stage_iolist` then `annotate_cematrix` == the full `stage`. `save=False`
    lets `stage` build in memory and write once after the C&E pass."""
    params = params or config.load_params()
    signal_types = config.load_signal_types()
    io_path = params.get("iolist_path")
    colmap = config.load_column_map("IoList")

    table = signals_table([m["canonical"] for m in colmap])
    cab_table = diagnosis_cabinets_table()
    database = Database([table, cab_table])

    rows, matched = _read_iolist(params, signal_types, io_path)
    if not matched:                                   # the required input is absent -> halt before anything
        return database, [_f("stg_no_io_sheet", "FAIL",
                             f"no I/O sheet matched {config.get_param(params, 'iolist_params.sheets')!r} "
                             f"in {io_path}", io_path or "")]   # raw-FAIL guard: nothing written

    _finalize_identity(params, rows)                  # the I/O-List identity (C&E fields still absent)
    for row in rows:
        table.add_row(row)
    _load_cabinets(io_path, cab_table)
    if save:
        database.save(config.database_dir())
    return database, []


def annotate_cematrix(database, params: dict | None = None, save: bool = True) -> tuple:
    """Phase 320 - Stage C&E Matrix: enrich the already-staged `signals` (built by `stage_iolist`) with the
    Cause&Effect data (`matrix_areas` / `ce_*` / `numerazione_linea` / `areas_description`) and the fields
    that depend on it (`ce_FLD` / `combined_FLD` / `IsSorterArea` / `diag_desc`); RE-STAMP each row's uid
    from the now-C&E `combined_FLD` (the uid key), record the `stg_dup_signal_uid` findings, save, and
    return (database, findings)."""
    params = params or config.load_params()
    table = database["signals"]
    matrix.annotate(params, table.rows)               # C&E enrichment, in place on the staged rows
    _finalize_identity(params, table.rows)            # recompute the C&E-dependent identity (the rest idempotent)
    for row in table.rows:                            # combined_FLD (the uid key) changed -> re-stamp
        row["uid"] = content_uid(*(row.get(key) for key in table.key_columns))
    findings = _dup_findings(table) + _dup_type_index_findings(table)   # dup uid WARN + (type,index) FAIL
    record(database, findings)                        # persist the facts to the validation_issues table
    if save:
        database.save(config.database_dir())
    return database, findings


def stage(params: dict | None = None) -> tuple:
    """Phase 300: the full staging - `stage_iolist` (310) then `annotate_cematrix` (320) - returning
    (database, findings) with `signals` + `diagnosis_cabinets` + `validation_issues` saved. The single
    staging entry point every downstream phase calls; BYTE-IDENTICAL to the pre-split monolith. A missing
    I/O sheet halts after 310 WITHOUT writing (the `run.has_blocking` guard)."""
    params = params or config.load_params()
    database, findings = stage_iolist(params, save=False)
    if run.has_blocking(findings):                    # no I/O sheet -> halt before the C&E pass, nothing written
        return database, findings
    return annotate_cematrix(database, params, save=True)

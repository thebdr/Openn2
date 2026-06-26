"""Staging (phase 300): read the I/O List into the `signals` table - PL4's SSOT fact table.

First cut: read each matched IoList sheet through the one workbook reader (by column position per
column_map), keep the real rows (drop Skip-Reason + struck rows per `strike_handling`), attach the
resolved `type`, and derive the DOCUMENT-side identity (the FLDs + the PLC tag name/table). Then build
the `signals` table (one row each, content-hash `uid`) and save the Database.

Now also: the C&E enrichment (`matrix.annotate`), the POSITIONAL node address ranges
(`I_/Q_startByte/endByte`), and `IsSorterArea`. Still deferred to their phases (then the full real-data
parity vs PL3 closes): the registry-derived names (`name_in_db` / `datablocks` / `plc_binding`),
`subnet_name`, and the diagnosis / interface identity.
"""
from __future__ import annotations

import os

from pipeline4.core import config
from pipeline4.core.database import Database
from pipeline4.domain import identity, matrix
from pipeline4.domain.signals import signals_table
from pipeline4.io import workbook


def _skip_reason_present(value) -> bool:
    return str(value or "").strip() not in ("", "0", "0.0")


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


def load_io_list(params: dict, signal_types: dict, io_path: str) -> tuple:
    """Read the matched IoList sheets of `io_path` into staged signal rows. Returns (rows, matched_sheets)."""
    colmap = config.load_column_map("IoList")
    header_row = int(config.get_param(params, "iolist_params.header_row", 1) or 1)
    strike_exclude = str(config.get_param(params, "validation_params.global.strike_handling", "exclude")
                         ).strip().lower() == "exclude"
    sheet_pattern = config.get_param(params, "iolist_params.sheets")

    views = workbook.open_sheets(io_path, sheet_pattern, header_row, doc_label=os.path.basename(io_path))
    matched = [v.name for v in views]
    if not matched:
        raise SystemExit(f"no I/O sheet matched {sheet_pattern!r} in {io_path}")

    rows = []
    for view in views:
        rows.extend(_read_view(view, colmap, strike_exclude, signal_types))
    views[0].close()

    matrix.annotate(params, rows)   # C&E enrichment: matrix_areas / ce_* / numerazione_linea / areas_description

    fu_col = next((m["column"] for m in colmap if m["canonical"] == "functional_unit"), "O")
    sorter_names = _sorter_area_names(params)
    for row in rows:
        if not row.get("source_cell") and row.get("source_row"):
            row["source_cell"] = f"{row.get('source_sheet', '')}!{fu_col}{row['source_row']}"
        row["iol_FLD"] = identity.fld(row)
        row["ce_FLD"] = identity.ce_fld(row)
        row["combined_FLD"] = identity.combined_fld(row)
        row["IsSorterArea"] = _is_sorter_area(row, sorter_names)
        if identity.is_io_signal(row) and identity.tag_name(row):
            row["name_in_tagtable"] = identity.tag_name(row)
            row["tagtable"] = identity.tagtable(row)
        else:
            row["name_in_tagtable"] = ""
            row["tagtable"] = ""
    _add_node_address_ranges(rows)   # positional I/Q byte ranges: a node owns the rows beneath it
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


def stage(params: dict | None = None) -> Database:
    """Phase 300: read the configured I/O List into a Database holding the `signals` table, save it to
    the Database folder, and return it. The single staging entry point."""
    params = params or config.load_params()
    signal_types = config.load_signal_types()
    io_path = params.get("iolist_path")
    rows, _matched = load_io_list(params, signal_types, io_path)

    colmap = config.load_column_map("IoList")
    table = signals_table([m["canonical"] for m in colmap])
    for row in rows:
        table.add_row(row)

    database = Database([table])
    database.save(config.database_dir())
    return database

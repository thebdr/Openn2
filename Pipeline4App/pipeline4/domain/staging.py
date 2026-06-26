"""Staging (phase 300): read the I/O List into the `signals` table - PL4's SSOT fact table.

First cut: read each matched IoList sheet through the one workbook reader (by column position per
column_map), keep the real rows (drop Skip-Reason + struck rows per `strike_handling`), attach the
resolved `type`, and derive the DOCUMENT-side identity (the FLDs + the PLC tag name/table). Then build
the `signals` table (one row each, content-hash `uid`) and save the Database.

Deferred to their phases (then the full real-data parity vs PL3 closes): the C&E enrichment
(`matrix_areas` / `ce_*` / `areas_description`), the registry-derived names (`name_in_db` / `datablocks`
/ `plc_binding`), and the node address ranges.
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
    for row in rows:
        if not row.get("source_cell") and row.get("source_row"):
            row["source_cell"] = f"{row.get('source_sheet', '')}!{fu_col}{row['source_row']}"
        row["iol_FLD"] = identity.fld(row)
        row["ce_FLD"] = identity.ce_fld(row)
        row["combined_FLD"] = identity.combined_fld(row)
        if identity.is_io_signal(row) and identity.tag_name(row):
            row["name_in_tagtable"] = identity.tag_name(row)
            row["tagtable"] = identity.tagtable(row)
        else:
            row["name_in_tagtable"] = ""
            row["tagtable"] = ""
    return rows, matched


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

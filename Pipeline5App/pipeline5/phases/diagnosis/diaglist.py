"""Phase 610 - project the unified `diagnosis_entries` table to `DiagList_IO.csv` + `DiagList_Logic.csv`.

PURE projection: filter the entries by `source` (io | logic) and write each entry's frozen `diag_columns`
snapshot under the config-driven headers (`config.load_diagnosis_columns`, in order). Comma CSV, CRLF, no
BOM (the OPn side reads by header). Output -> `config.diaglist_dir()` (ProjectDocumentation - DOCUMENTATION,
NOT a BuilderData import surface). Clean-room port of PL3's `generate_diag_list` (the table replaces the
re-derivation: the cells were rendered once at build, 600b).
"""
from __future__ import annotations

import csv
import os

from pipeline5 import config
from pipeline5.truth.database import Database
from pipeline5.truth.diagnosis import diagnosis_entries_table


def _write_csv(path: str, headers: list, rows: list) -> str:
    """Write `rows` (dicts keyed by header) under `headers` as a comma CSV (CRLF, no BOM)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)                       # csv default lineterminator is CRLF
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row.get(h, "") for h in headers])
    return path


def project(database: Database | None = None, out_dir: str | None = None) -> dict:
    """Write DiagList_IO.csv (source=io) + DiagList_Logic.csv (source=logic) from `diagnosis_entries`.
    Returns {'dir', 'io_count', 'logic_count', 'io_path', 'logic_path', 'findings'} - a pure projection,
    `findings` is empty (the snapshot was rendered + validated at build)."""
    if database is None:
        database = Database([diagnosis_entries_table()]).load(config.database_dir())
    out_dir = out_dir or config.diaglist_dir()
    headers = [c["header"] for c in config.load_diagnosis_columns()]
    io_rows = [e["diag_columns"] for e in database["diagnosis_entries"] if e["source"] == "io"]
    logic_rows = [e["diag_columns"] for e in database["diagnosis_entries"] if e["source"] == "logic"]
    io_path = _write_csv(os.path.join(out_dir, "DiagList_IO.csv"), headers, io_rows)
    logic_path = _write_csv(os.path.join(out_dir, "DiagList_Logic.csv"), headers, logic_rows)
    return {"dir": out_dir, "io_count": len(io_rows), "logic_count": len(logic_rows),
            "io_path": io_path, "logic_path": logic_path, "findings": []}

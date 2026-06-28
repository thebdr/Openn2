"""ph200 raw-row reader: read the matched IoList sheets into RAW per-row dicts (the canonical columns +
source provenance) - the input to classification (210) and, later, the in-place fill write-back. Reads
through the one workbook reader (`io.workbook`) by column position per `column_map`, like staging, but does
NOT enrich or drop rows (ph200 classifies/fills the source document as-is; staging is the SSOT build)."""
from __future__ import annotations

import os

from pipeline4.core import config
from pipeline4.io import workbook


def read_rows(params: dict | None = None) -> list:
    """Raw IoList rows as dicts keyed by canonical column (+ `source_sheet` / `source_row`). Fully-empty
    rows are skipped. Returns []  when no sheet matches the configured pattern."""
    params = params or config.load_params()
    colmap = config.load_column_map("IoList")
    header_row = int(config.get_param(params, "iolist_params.header_row", 1) or 1)
    sheet_pattern = config.get_param(params, "iolist_params.sheets")
    io_path = params.get("iolist_path")

    views = workbook.open_sheets(io_path, sheet_pattern, header_row, doc_label=os.path.basename(io_path or ""))
    if not views:
        return []
    rows = []
    for view in views:
        for r in view.data_rows():
            raw = {m["canonical"]: view.text(r, m["column"]) for m in colmap}
            if all(value == "" for value in raw.values()):
                continue
            raw["source_sheet"] = view.name
            raw["source_row"] = r
            rows.append(raw)
    views[0].close()
    return rows

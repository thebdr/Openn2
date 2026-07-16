"""Read a document revision (I/O List / C&E Matrix / AREA sheets) into plain comparison rows.

Every row is a dict of {field -> stripped str} PLUS the provenance keys `_sheet`/`_row`. The I/O List
reads the human columns A-Z by the column_map (the pipeline-owned AA-AH are excluded by definition); the
C&E matrix reads the fixed cause-row layout + the dynamic AREA effect columns; the AREA sheets are read
**with formulas** (`data_only=False`) because their device-tag/line cells are stored as `=...` strings -
a cached (`data_only=True`) read drops the un-recalculated ones and fabricates phantom deletions.
"""
from __future__ import annotations

from pipeline5 import config
from pipeline5.documents import xlsx_reader as workbook

# The C&E "CAUSE&EFFECT MATRIX" cause-row layout (fixed by the template; column_map only covers a subset).
_CE_FIELDS = {"module": "E", "address": "F", "slot": "G", "pin": "H", "description": "I",
              "functional_unit": "J", "location": "K", "device": "L", "concat_id": "M", "type": "N"}
# The AREA sheet layout (SIGLA CONTATTORE / NUMERAZIONE LINEA / DIGITAL OUTPUT / DESCRIZIONE).
_AREA_FIELDS = {"device_tag": "A", "line_numbering": "B", "digital_output": "C", "description": "D"}


def _iol_columns() -> list:
    """[(canonical, column_letter)] for the I/O List HUMAN columns (A-Z) - the pipeline-owned AA-AH
    (preliminary_check_exclude) are not compared."""
    return [(c["canonical"], c["column"]) for c in config.load_column_map("IoList")
            if not c["preliminary_check_exclude"] and c["canonical"]]


def read_iolist(path: str, params: dict) -> list:
    """The I/O List rows (one per non-empty data row across the configured sheet(s)), each a dict of the
    human columns + `_sheet`/`_row`. Reads the SAME sheets the pipeline stages."""
    sheets = config.get_param(params, "iolist_params.sheets")
    header_row = int(config.get_param(params, "iolist_params.header_row", 1) or 1)
    columns = _iol_columns()
    views = workbook.open_sheets(path, sheets, header_row)
    rows: list = []
    try:
        for view in views:
            for r in view.data_rows():
                row = {canon: view.text(r, letter) for canon, letter in columns}
                if not any(row.values()):
                    continue
                row["_sheet"], row["_row"] = view.name, r
                # `_struck` = the row has at least one struck-through cell that carries text (a formatting
                # practice the report flags - strike-through has no reliable meaning).
                row["_struck"] = any(view.cell_struck(r, letter) for canon, letter in columns if row.get(canon))
                rows.append(row)
    finally:
        if views:
            views[0].close()
    return rows


def read_ce_matrix(path: str, params: dict) -> tuple:
    """The C&E cause rows + the ordered list of effect-area column names. Each row carries the `_CE_FIELDS`
    plus an `effects` sub-dict {area_name -> "X"/""} for every column whose header (row 2) is `AREA n`.
    Returns (rows, area_names). A row with no identity (concat_id/FU/LOC/DEV/description all blank) is
    dropped (trailing template rows)."""
    sheet = config.get_param(params, "matrix_params.ce_sheet.name")
    header_row = int(config.get_param(params, "matrix_params.ce_sheet.header_row", 2) or 2)
    data_row = int(config.get_param(params, "matrix_params.ce_sheet.data_row", 5) or 5)
    view = workbook.open_sheet(path, sheet, header_row, first_data_row=data_row)
    try:
        effect_cols, area_names = [], []
        import re
        for col in range(1, view.max_col + 1):
            head = view.header(col)
            m = re.match(r"^AREA\s*\d+", head, re.IGNORECASE)
            if m:
                effect_cols.append((col, head))
                area_names.append(head)
        rows: list = []
        for r in view.data_rows():
            row = {name: view.text(r, letter) for name, letter in _CE_FIELDS.items()}
            identity = (row["concat_id"] or (row["functional_unit"] + row["location"] + row["device"])
                        or row["description"])
            if not identity.strip():
                continue
            row["effects"] = {name: view.text(r, col) for col, name in effect_cols}
            row["_sheet"], row["_row"] = view.name, r
            rows.append(row)
        return rows, area_names
    finally:
        view.close()


def read_area_sheets(path: str, params: dict) -> dict:
    """{area_sheet_name -> [rows]} across all AREA sheets, read WITH FORMULAS (data_only=False) so the
    `=...` device-tag/line cells survive. Each row carries the `_AREA_FIELDS` + `_sheet`/`_row`. An empty
    AREA sheet maps to []."""
    pattern = config.get_param(params, "matrix_params.area_sheets.name")
    header_row = int(config.get_param(params, "matrix_params.area_sheets.header_row", 3) or 3)
    data_row = int(config.get_param(params, "matrix_params.area_sheets.data_row", 4) or 4)
    views = workbook.open_sheets(path, pattern, header_row, first_data_row=data_row, data_only=False)
    out: dict = {}
    try:
        for view in views:
            rows = []
            for r in view.data_rows():
                row = {name: view.text(r, letter) for name, letter in _AREA_FIELDS.items()}
                if not any(row.values()):
                    continue
                row["_sheet"], row["_row"] = view.name, r
                rows.append(row)
            out[view.name] = rows
    finally:
        if views:
            views[0].close()
    return out

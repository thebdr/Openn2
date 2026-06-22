"""810 - the per-template shell workbook `CreationInfo/SoftwareBlocksBuilderShells.xlsx`.

The shell is the KEY INVENTORY (block_templates.json is deprecated). 810 scans the block template
`*.xml` files for `!!key$$` placeholders and writes one sheet per template holding ALL of that
template's keys. Each sheet:
  row 1:  $ | template=<abs path to the .xml>     (absolute - the apps ship as one package)
  row 2:  $ | <mode>                              (B2 = keep / fill / override)
  row 3:  % | TemplateType | !!key$$ ...          (the full key set - the inventory)
  rows 4+: empty (hand-author @ rows for an `override` template)

ADDITIVE: an existing sheet is preserved (your edits/mode/added keys survive); only missing
templates get a fresh shell. The engine reads modes + the key set (read_shells) and, for override,
the @ rows (read_override_table).
"""
from __future__ import annotations
import os
import re
import zipfile

from openpyxl import Workbook, load_workbook

from pipeline3.core import config

SHELL_NAME = "SoftwareBlocksBuilderShells.xlsm"   # .xlsm so the user can add VBA in place (see _save_xlsm)
DEFAULT_MODE = "fill"
_PLACEHOLDER = re.compile(r"!!(.+?)\$\$")
_PREFIX_RE = re.compile(r"^TEMPLATE--v\d+\.\d+--")
# openpyxl writes the xlsx content type even to a .xlsm; patch it to macro-enabled so Excel doesn't
# reject the extension/content mismatch as corrupt (a macro-less .xlsm is otherwise valid).
_XLSX_CT = b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
_XLSM_CT = b"application/vnd.ms-excel.sheet.macroEnabled.main+xml"

# Blocks whose shell sheet is the COIL-COLUMNS layout (one column per coil = the cause->effect linking)
# rather than the standard %/@ key inventory. fill rewrites it from the builder; override reads it back.
COIL_COLUMN_BLOCKS = {"03_Zone Cumulative"}
_COIL_MARK, _DB_MARK, _COMMENT_MARK = "%coil", "nameOfDB", "comment"   # the A-column row labels


def _short(stem: str) -> str:
    return _PREFIX_RE.sub("", stem)


def _shell_path(out_root: str) -> str:
    return os.path.join(config.out_path(out_root, "blocks_creation_dir"), SHELL_NAME)


def _save_xlsm(wb, path: str) -> None:
    """Save `wb` as a VALID .xlsm. openpyxl writes the xlsx content type even for a .xlsm path, so
    Excel flags the mismatch as corrupt; patch [Content_Types].xml to the macro-enabled type. (Load the
    shell with keep_vba=True so any VBA the user adds in Excel survives a pipeline re-run.)"""
    wb.save(path)
    items = []
    with zipfile.ZipFile(path) as z:
        items = [(i.filename, z.read(i.filename)) for i in z.infolist()]
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in items:
            out.writestr(name, data.replace(_XLSX_CT, _XLSM_CT) if name == "[Content_Types].xml" else data)
    os.replace(tmp, path)


def template_ref(stem: str) -> str:
    """Absolute path to a template's .xml (the $ template= reference)."""
    return os.path.join(config.BLOCK_TEMPLATES_DIR, f"{stem}.xml")


def _unwrap(header) -> str:
    h = str(header or "").strip()
    return h[2:-2] if h.startswith("!!") and h.endswith("$$") else h


def scan_templates() -> dict:
    """{stem: [keys...]} by scanning the block template *.xml for !!key$$ (distinct, first-seen
    order). The template XML is the source of truth now that block_templates.json is deprecated."""
    out = {}
    d = config.BLOCK_TEMPLATES_DIR
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.lower().endswith(".xml"):
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        keys = []
        for k in _PLACEHOLDER.findall(text):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
        out[fn[:-4]] = keys
    return out


def generate_shells(out_root: str, emit=print) -> dict:
    """Create/refresh SoftwareBlocksBuilderShells.xlsm (additive). Returns {path, created, kept}."""
    path = _shell_path(out_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        wb = load_workbook(path, keep_vba=True)               # preserve any VBA the user added in Excel
    else:
        wb = Workbook()
        wb.remove(wb.active)
    existing = set(wb.sheetnames)
    created, kept = [], []
    for stem, keys in scan_templates().items():
        name = _short(stem)[:31]                  # Excel sheet-name limit
        if name in existing:
            kept.append(name)
            continue
        ws = wb.create_sheet(title=name)
        ws["A1"] = "$"; ws["B1"] = f"template={template_ref(stem)}"
        ws["A2"] = "$"; ws["B2"] = DEFAULT_MODE
        if name in COIL_COLUMN_BLOCKS:                         # coil-columns layout; phase-800 fill populates it
            ws["A3"], ws["A4"], ws["A5"] = _COIL_MARK, _DB_MARK, _COMMENT_MARK
        else:
            ws["A3"] = "%"; ws["B3"] = "TemplateType"
            for i, k in enumerate(keys):
                ws.cell(row=3, column=3 + i, value=f"!!{k}$$")
        created.append(name)
    _save_xlsm(wb, path)
    emit(f"empty shells: {len(created)} new, {len(kept)} kept -> {path}")
    return {"path": path, "created": created, "kept": kept}


def read_shells(out_root: str) -> dict:
    """{short_name: {mode, stem, ref, keys}} from the shell. {} if absent.
    `keys` = TemplateType + the bare placeholder keys (the % header, unwrapped) = the inventory."""
    path = _shell_path(out_root)
    if not os.path.exists(path):
        return {}
    wb = load_workbook(path, data_only=True)
    out = {}
    for ws in wb.worksheets:
        b1 = str(ws["B1"].value or "")
        ref = b1[len("template="):] if b1.startswith("template=") else ""
        stem = os.path.splitext(os.path.basename(ref))[0] if ref else ws.title
        mode = str(ws["B2"].value or DEFAULT_MODE).strip().lower()
        keys = [_unwrap(c.value) for c in ws[3] if c.value not in (None, "")][1:]   # drop the "%" marker
        out[ws.title] = {"mode": mode, "stem": stem, "ref": ref or template_ref(stem), "keys": keys}
    wb.close()
    return out


def read_override_table(out_root: str, name: str):
    """Build a Table from the hand-authored @ rows of shell sheet `name` (override mode)."""
    from pipeline3.domain.blocks.table import Table
    path = _shell_path(out_root)
    if not os.path.exists(path):
        return None
    wb = load_workbook(path, data_only=True)
    if name not in wb.sheetnames:
        wb.close()
        return None
    ws = wb[name]
    columns = [_unwrap(c.value) for c in ws[3] if c.value not in (None, "")][1:]
    table = Table(name=name)
    for row in ws.iter_rows(min_row=4, values_only=True):
        if not row or row[0] != "@":
            continue
        vals = list(row)[1:]
        table.add_row({col: (vals[i] if i < len(vals) and vals[i] is not None else "")
                       for i, col in enumerate(columns)})
    wb.close()
    return table


def read_override_grid(out_root: str, name: str):
    """The standard shell sheet's % header (row 3) and @ rows (rows 4+) as raw B-onward cell strings -
    for writing the CreationInfo CSV VERBATIM from the (possibly hand-edited) sheet in override mode,
    preserving the full @ row incl. a horizontal ITERATOR spread. Returns (header_cells, at_rows)."""
    path = _shell_path(out_root)
    if not os.path.exists(path):
        return [], []
    wb = load_workbook(path, data_only=True)
    if name not in wb.sheetnames:
        wb.close()
        return [], []
    ws = wb[name]

    def cells(row):
        vals = [("" if c.value is None else str(c.value)) for c in row][1:]   # drop the A-column marker
        while vals and vals[-1] == "":                                        # trim trailing empties
            vals.pop()
        return vals

    header = cells(ws[3])
    at = [cells(r) for r in ws.iter_rows(min_row=4) if r and r[0].value == "@"]
    wb.close()
    return header, at


def write_coil_columns(out_root: str, name: str, table, ref: str) -> str:
    """Write shell sheet `name` in the COIL-COLUMNS layout - one column per @ row (a coil): row 3 the
    coil member (02_COM.{db_element}), row 4 nameOfDB, row 5 NetworkComment, rows 6+ the AND input
    members (ITERATOR_STRINGS) down each column. Preserves B1/B2 (template ref + mode); rewrites the
    body. Phase-800 `fill` calls this to seed/refresh the editable cause->effect sheet."""
    path = _shell_path(out_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        wb = load_workbook(path, keep_vba=True)               # preserve user VBA across re-runs
    else:
        wb = Workbook(); wb.remove(wb.active)
    if name in wb.sheetnames:
        ws = wb[name]
        for row in ws.iter_rows(min_row=3):                   # clear the old body; keep $ template / $ mode
            for c in row:
                c.value = None
    else:
        ws = wb.create_sheet(title=name[:31])
        ws["A1"] = "$"; ws["B1"] = f"template={ref}"
        ws["A2"] = "$"; ws["B2"] = DEFAULT_MODE
    ws["A3"], ws["A4"], ws["A5"] = _COIL_MARK, _DB_MARK, _COMMENT_MARK
    n_inputs = 0
    for j, row in enumerate(table.rows):
        col = 2 + j                                           # one column per coil, B onward
        ws.cell(row=3, column=col, value=str(row.get("02_COM.{db_element}", "") or ""))
        ws.cell(row=4, column=col, value=str(row.get("nameOfDB", "") or ""))
        ws.cell(row=5, column=col, value=str(row.get("NetworkComment", "") or ""))
        members = [str(m) for m in (row.get("ITERATOR_STRINGS") or []) if str(m).strip()]
        for i, m in enumerate(members):
            ws.cell(row=6 + i, column=col, value=m)
        n_inputs = max(n_inputs, len(members))
    for i in range(n_inputs):                                 # mark the input rows in column A
        ws.cell(row=6 + i, column=1, value="@")
    _save_xlsm(wb, path)
    wb.close()
    return path


def write_standard_sheet(out_root: str, name: str, header_cells, data_rows, ref: str) -> str:
    """Mirror the CreationInfo CSV into the standard shell sheet `name` ($/%/@ layout): row 1 $ template,
    row 2 $ mode (PRESERVED), row 3 % header, rows 4+ the @ data. fill calls this so the sheet starts as
    an exact copy of the CSV - the user can flip B2 to keep/override and edit. `header_cells`/`data_rows`
    are the already-serialized %/@ cells (from the engine) so they match the CSV exactly."""
    path = _shell_path(out_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        wb = load_workbook(path, keep_vba=True)
    else:
        wb = Workbook(); wb.remove(wb.active)
    if name in wb.sheetnames:
        ws = wb[name]
        mode = ws["B2"].value or DEFAULT_MODE                  # keep the user's keep/fill/override choice
        for row in ws.iter_rows(min_row=3):                    # clear the old %/@ body
            for c in row:
                c.value = None
    else:
        ws = wb.create_sheet(title=name[:31]); mode = DEFAULT_MODE
    ws["A1"] = "$"; ws["B1"] = f"template={ref}"
    ws["A2"] = "$"; ws["B2"] = mode
    ws["A3"] = "%"
    for i, h in enumerate(header_cells):
        ws.cell(row=3, column=2 + i, value=h)
    for r, cells in enumerate(data_rows, start=4):
        ws.cell(row=r, column=1, value="@")
        for i, v in enumerate(cells):
            ws.cell(row=r, column=2 + i, value=v)
    _save_xlsm(wb, path)
    wb.close()
    return path


def read_coil_columns(out_root: str, name: str):
    """Reconstruct a Table from the coil-columns shell sheet (override mode) - the inverse of
    write_coil_columns: each non-empty column B+ becomes one coil row (its rows 6+ = the AND inputs)."""
    from pipeline3.domain.blocks.table import Table
    path = _shell_path(out_root)
    if not os.path.exists(path):
        return None
    wb = load_workbook(path, data_only=True)
    if name not in wb.sheetnames:
        wb.close()
        return None
    ws = wb[name]
    table = Table(name=name)
    for col in range(2, ws.max_column + 1):
        coil = ws.cell(row=3, column=col).value
        if coil in (None, ""):
            continue
        members = [str(ws.cell(row=r, column=col).value)
                   for r in range(6, ws.max_row + 1) if ws.cell(row=r, column=col).value not in (None, "")]
        table.add(template_type="01",
                  nameOfDB=str(ws.cell(row=4, column=col).value or ""),
                  **{"02_COM.{db_element}": str(coil)},
                  NetworkComment=str(ws.cell(row=5, column=col).value or ""),
                  ITERATOR_STRINGS=members)
    wb.close()
    return table

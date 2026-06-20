"""810 - the per-template shell workbook `CreationInfo/SoftwareBlocks.xlsm`.

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

from openpyxl import Workbook, load_workbook

from pipeline3.core import config

SHELL_NAME = "SoftwareBlocks.xlsm"
DEFAULT_MODE = "fill"
_PLACEHOLDER = re.compile(r"!!(.+?)\$\$")
_PREFIX_RE = re.compile(r"^TEMPLATE--v\d+\.\d+--")


def _short(stem: str) -> str:
    return _PREFIX_RE.sub("", stem)


def _shell_path(out_root: str) -> str:
    return os.path.join(config.out_path(out_root, "blocks_creation_dir"), SHELL_NAME)


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
    """Create/refresh SoftwareBlocks.xlsm (additive). Returns {path, created:[names], kept:[names]}."""
    path = _shell_path(out_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        wb = load_workbook(path)
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
        ws["A3"] = "%"; ws["B3"] = "TemplateType"
        for i, k in enumerate(keys):
            ws.cell(row=3, column=3 + i, value=f"!!{k}$$")
        created.append(name)
    wb.save(path)
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

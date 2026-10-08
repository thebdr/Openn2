"""The CreationInfo csv - Siemens' template-fill delivery surface (contract v1 `sw/block-gen`) as the
system's "csv" emitter, the `InstanceDBs.csv` writer (`sw/instance-db`) and the shipped template copies
(`sw/block-template`).

Chapter: how a built block reaches TIA when it ships as data rather than ready code. Each block becomes
`<PLC>/Program blocks/<name>.csv` in the `$/#/%/@` layout the OP importer fills into the block's template
XML: the `#!openn` header first (the kind, the run, the PLC and the TIA folder), `$` names the template
(a RELATIVE `Templates/<file>.xml` - OP5 resolves it against the csv folder, then a `Templates/` folder
at each level up to the workspace root, then the shared templates; an absolute PL path is dead on the OP
machine), `#` is a comment, `%` the header (placeholders wrapped `!!key$$`), `@` one row per network - a
LIST cell spreads horizontally (the ITERATOR). The block's template XML is COPIED into the workspace's
`Templates/` folder, stamped `sw/block-template` with this run (a copy an older generation left behind
is Stale for OP5; the hand-maintained original is named in `source` - edit THAT one).

Where you meet it in the app: the 800 phase log's "CreationInfo CSV" surface lines; the files under
BuilderData/<PLC>/Program blocks. Registered as `SYSTEM.emitters["csv"]` (the block-gen csv) and
`SYSTEM.emitters["instance_dbs"]` (InstanceDBs.csv) - the build engine routes every non-ready block and
the collected instance-DB list here and never knows the format (PL4 coupling #2/#6, resolved).

Place in the flow: phase 800 / 820 + 830 (run_software in
src://pipeline5/systems/plc_based/siemens_s7/safety/main.py) - the build engine
(src://pipeline5/phases/software_blocks/build_engine.py) calls `write` for every block registered
`emit="csv"` in src://pipeline5/systems/plc_based/siemens_s7/safety/block_builders.py and
`write_instance_dbs_emit` for the collected instanceOf cells. Reads the reconstructed builder Table;
writes BuilderData/<PLC>/Program blocks/<name>.csv + InstanceDBs.csv and BuilderData/Templates/<file>.xml
(src://pipeline5/systems/plc_based/siemens_s7/output_layout.py; the headers from
src://pipeline5/systems/plc_based/siemens_s7/openn_header.py).

Decision history: the RELATIVE `$ template=Templates/<file>.xml` reference is a contract evolution
(2026-07-07, user report: the absolute PL-side path was dead on the OP machine) - the CreationInfo folder
became self-contained and OP4 resolved `template=` against the csv's own folder; with the VCI shape
(contract v1, 2026-10-08) the copies moved to the workspace root and OP5 resolves the same relative
reference by walking up to it.
"""
from __future__ import annotations

import csv
import os

from pipeline5 import config
from pipeline5.systems.plc_based.siemens_s7 import openn_header as header

PHASE_BLOCKS = 820
PHASE_INSTANCES = 830
INSTANCE_DBS_FILE = "InstanceDBs.csv"
INSTANCE_DBS_COLUMNS = ["Name", "InstanceOf", "Number", "Folder"]


def _wrap(col: str) -> str:
    """% / @ header form: TemplateType + #meta columns unwrapped; placeholders are !!key$$."""
    return col if (col == "TemplateType" or col.startswith("#")) else f"!!{col}$$"


def _ordered_columns(canonical_keys, table) -> list:
    """The template's full key set first (TemplateType leading), then any extra builder columns; list
    (ITERATOR) columns moved last."""
    cols = list(canonical_keys)
    for c in table.columns:
        if c not in cols:
            cols.append(c)

    def is_iter(c):
        return any(isinstance(r.get(c), (list, tuple)) for r in table.rows)
    iters = [c for c in cols if c != "TemplateType" and is_iter(c)]
    scal = [c for c in cols if c != "TemplateType" and c not in iters]
    head = ["TemplateType"] if "TemplateType" in cols else []
    return head + scal + iters


def _at_row_cells(row, ordered) -> list:
    """The @-row cells for `ordered` columns: scalars as-is, a list value spread across cells (the
    horizontal ITERATOR)."""
    cells = []
    for c in ordered:
        v = row.get(c, "")
        if isinstance(v, (list, tuple)):
            cells.extend("" if x is None else str(x) for x in v)
        else:
            cells.append("" if v is None else str(v))
    return cells


def template_source(template_ref: str) -> str:
    """The `source` a shipped template copy names: the FOLDER of the hand-maintained original, relative to
    the monorepo's `Shared/` (`Shared/Templates/Tia Portal Software Blocks`) - never a host path (contract
    §1.5) and never the file name: a template name holds `--`, which an XML comment cannot (the copy keeps
    the name anyway). '' (the key omitted) for an original outside Shared/."""
    folder = os.path.dirname(os.path.abspath(str(template_ref)))
    shared = os.path.abspath(config.SHARED)
    try:
        rel = os.path.relpath(folder, shared)
    except ValueError:                        # another drive on Windows
        return ""
    if rel.startswith(os.pardir):
        return ""
    return "Shared/" + rel.replace(os.sep, "/")


def ship_template(template_ref: str, tpl_dir: str) -> str:
    """Copy a csv-emitting block's template XML into the workspace's `Templates/` folder, stamped
    `sw/block-template` (the header as the first comment after the declaration; the original's BOM and
    line ends kept, an older stamp replaced), and return the RELATIVE reference written into the csv
    (`Templates/<file>.xml`, forward slash - machine-independent). A missing source ships nothing but still
    writes the relative ref (the OP import reports it, exactly like the old dangling absolute path did)."""
    base = os.path.basename(str(template_ref or ""))
    if not base:
        return ""
    if os.path.exists(template_ref):
        os.makedirs(tpl_dir, exist_ok=True)
        with open(template_ref, "rb") as original:
            text = original.read().decode("utf-8")        # a BOM stays `﻿` and is written back as it was
        stamp = header.fields("sw/block-template", PHASE_BLOCKS, source=template_source(template_ref))
        with open(os.path.join(tpl_dir, base), "w", encoding="utf-8", newline="") as copy:
            copy.write(header.stamp_xml(text, stamp))
    return f"{header.TEMPLATES_FOLDER}/{base}"


def write_creation_csv(creation_dir: str, name: str, template_ref: str, table, canonical_keys,
                       plc: str | None = None) -> str:
    """Serialize one reconstructed Table to <creation_dir>/<name>.csv in the $/#/%/@ layout - the `#!openn`
    header first (`sw/block-gen`, the run, `plc` + the TIA folder) - with the % header = the template's full
    key set (canonical_keys) + any extra builder columns."""
    ordered = _ordered_columns(canonical_keys, table)
    path = os.path.join(creation_dir, f"{name}.csv")
    os.makedirs(creation_dir, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(header.render_csv(header.fields("sw/block-gen", PHASE_BLOCKS, plc=plc,
                                                target=header.PROGRAM_BLOCKS, source="software_blocks")))
        w = csv.writer(f)
        w.writerow(["$", f"template={template_ref}"])
        w.writerow(["#", "generated by pipeline5 (phase 800)"])
        w.writerow(["%"] + [_wrap(c) for c in ordered])
        for r in table.rows:
            w.writerow(["@"] + _at_row_cells(r, ordered))
    return path


def write(block, table, ctx) -> str:
    """The SYSTEM.emitters["csv"] entry: ship the block's template into `ctx["tpl_dir"]`, write the CSV
    with the relative reference, return the CSV path. `ctx`: {"out_dir", "tpl_dir", "plc" (optional)}."""
    rel_ref = ship_template(block["template_ref"], ctx["tpl_dir"])
    return write_creation_csv(ctx["out_dir"], block["name"], rel_ref, table, block["keys"], plc=ctx.get("plc"))


# --- InstanceDBs.csv (the 830 CreateInstanceDB surface) ------------------------------------------ #
def write_instance_dbs(pairs, out_dir: str, plc: str | None = None) -> str:
    """Serialize the (name, fb) pairs to <out_dir>/InstanceDBs.csv (contract `sw/instance-db`): the
    `#!openn` header, a `#` comment, the `%` key row (Name, InstanceOf, Number, Folder - OP5 reads NAMED
    columns), one `@` row per instance (Number empty = TIA auto-numbers; Folder = the FB). Plain UTF-8
    (no BOM), csv.writer CRLF - NOT the GlobalDB-XML BOM rule. Returns the path."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, INSTANCE_DBS_FILE)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        handle.write(header.render_csv(header.fields("sw/instance-db", PHASE_INSTANCES, plc=plc,
                                                     target=header.PROGRAM_BLOCKS,
                                                     source="software_block_members + instance_dbs")))
        w = csv.writer(handle)
        w.writerow(["#", "Instance DBs created directly via CreateInstanceDB"])
        w.writerow(["%"] + INSTANCE_DBS_COLUMNS)
        for name, fb in pairs:
            w.writerow(["@", name, fb, "", fb])
    return path


def write_instance_dbs_emit(pairs, ctx) -> str:
    """The SYSTEM.emitters["instance_dbs"] entry (the 800 engine hands the deduped (name, fb) pairs):
    `ctx`: {"out_dir", "plc" (optional)}. Returns the csv path."""
    return write_instance_dbs(pairs, ctx["out_dir"], plc=ctx.get("plc"))

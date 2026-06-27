"""The phase-800 engine: run each registered builder over the `signals` Database into the
**`software_blocks`** + **`software_block_members`** SSOT tables (`build`), then serialize each block to
its `$/#/%/@` CreationInfo CSV (`project`). The `%` header is the template's full key inventory (scanned
from the shipped `*.xml`, `domain/blocks/templates`) so the CSV carries every placeholder, not just the
columns a builder filled. Clean-room port of the serialization in PL3's `domain/blocks/engine.py`; the
editable `.xlsm` shells (an operator surface) are deferred, so every block runs in `fill` mode.

A builder's `Table` row is stored verbatim as the member's `values` JSON cell (a list value stays the
horizontal ITERATOR); the projection reconstructs the Table from `software_blocks.columns` (the order) +
the members' values, so it is a pure function of the tables. The `02_COM` DB + `InstanceDBs.csv` (which
read these tables across all builders) + the direct-FC-XML emit land with 800c.
"""
from __future__ import annotations

import csv
import os

from pipeline4.core import config, run
from pipeline4.core.database import Database as DB
from pipeline4.core.finding import Finding, record
from pipeline4.core.table import Table as SsotTable
from pipeline4.domain import datablock_xml
from pipeline4.domain.blocks import builders as _builders  # noqa: F401  (import registers the builders)
from pipeline4.domain.blocks import templates, xml_emit
from pipeline4.domain.blocks.database import Database
from pipeline4.domain.blocks.registry import registry
from pipeline4.domain.blocks.table import Table
from pipeline4.domain.datablocks import DB_CONSTANTS
from pipeline4.domain.db_members import instance_dbs_table
from pipeline4.domain.signals import signals_table

INSTANCE_OF = "instanceOf-"
COM_MEMBER_COL = "02_COM.{db_element}"   # builders writing this column define the 02_COM custom DB members (800c)
COM_DB = "02_COM"                        # the zone-cumulative custom safe-DB (F_DB), phase-800-owned


def _f(type: str, severity: str, detail: str, location: str = "", source_uid: str = "") -> Finding:
    """A phase-800 Finding - the software-block report container (WARN-only in 800a)."""
    return Finding(phase=800, type=type, severity=severity, detail=detail,
                   location=location, source_uid=source_uid)


# --- the SSOT tables ----------------------------------------------------------------------------- #
def software_blocks_table() -> SsotTable:
    """One row per built block: the template stem + ref, the `%` key inventory, and the builder Table's
    column ORDER (so the projection can reconstruct the @ layout). The CreationInfo CSV is its projection."""
    return SsotTable(
        "software_blocks",
        columns=["uid", "name", "template_stem", "template_ref", "keys", "columns"],
        json_columns=["keys", "columns"],
        key_columns=["name"],
    )


def software_block_members_table() -> SsotTable:
    """One row per builder @ row (its full value dict, a list cell = the horizontal ITERATOR). Keyed by
    block + seq (the builder's emission order)."""
    return SsotTable(
        "software_block_members",
        columns=["uid", "block", "seq", "values"],
        json_columns=["values"],
        key_columns=["block", "seq"],
    )


# --- serialization (verbatim from PL3 engine; the $/#/%/@ CreationInfo CSV) ----------------------- #
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


def _write_creation_csv(creation_dir: str, name: str, template_ref: str, table, canonical_keys) -> str:
    """Serialize one reconstructed Table to CreationInfo/<name>.csv in the $/#/%/@ layout, with the %
    header = the template's full key set (canonical_keys) + any extra builder columns."""
    ordered = _ordered_columns(canonical_keys, table)
    path = os.path.join(creation_dir, f"{name}.csv")
    os.makedirs(creation_dir, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["$", f"template={template_ref}"])
        w.writerow(["#", "generated by pipeline4 (phase 800)"])
        w.writerow(["%"] + [_wrap(c) for c in ordered])
        for r in table.rows:
            w.writerow(["@"] + _at_row_cells(r, ordered))
    return path


# --- build (-> the SSOT tables) + project (-> the CreationInfo CSVs) ------------------------------ #
def build(database: DB | None = None) -> tuple:
    """Phase 800a (SSOT): run every registered builder over the `signals` table -> the `software_blocks` +
    `software_block_members` tables. Records the findings to `validation_issues` + saves. Returns
    (database, findings) - WARN-only (`blk_builder_no_rows` when a builder yields no rows)."""
    if database is None:
        colmap = config.load_column_map("IoList")
        database = DB([signals_table([m["canonical"] for m in colmap])]).load(config.database_dir())
    db = Database(list(database["signals"]))
    inventory = templates.template_keys()                    # {block name -> [keys]} from the shipped .xml

    blk, mem = software_blocks_table(), software_block_members_table()
    findings = []
    for name, fn in registry().items():
        table = fn(db) or Table(name)
        if len(table) == 0:
            findings.append(_f("blk_builder_no_rows", "WARN",
                               "builder returned no rows (stub or no matching signals) - header only", name))
        stem, ref = templates.stem_ref_by_name().get(name, (name, templates.template_ref(name)))
        keys = ["TemplateType"] + inventory.get(name, [])    # the % key inventory (TemplateType leads)
        blk.add(name=name, template_stem=stem, template_ref=ref, keys=keys, columns=list(table.columns))
        for seq, row in enumerate(table.rows):
            mem.add(block=name, seq=seq, values=dict(row))

    for table in (blk, mem):
        if table.name in database:
            database[table.name].rows = table.rows
        else:
            database.add_table(table)
    record(database, findings)
    database.save(config.database_dir())
    return database, findings


def project(database: DB | None = None, out_dir: str | None = None, import_dir: str | None = None) -> dict:
    """Project `software_blocks` + `software_block_members` -> the `$/#/%/@` CreationInfo CSVs in `out_dir`
    (defaults to `config.blocks_creation_dir()`). A block with a direct-XML emitter (03) instead ships a ready
    `SW.Blocks.FC` XML to `import_dir` (defaults to `config.blocks_import_dir()`) and its CSV is DROPPED (OP4
    imports the XML, not a template-fill CSV) - a stale CSV is removed. A pure projection (`findings: []`).
    Returns {'dir', 'files', 'xml_files', 'count', 'findings'} ('count'/'files' = the CSVs only)."""
    if database is None:
        database = DB([software_blocks_table(), software_block_members_table()]).load(config.database_dir())
    out_dir = out_dir or config.blocks_creation_dir()
    import_dir = import_dir or config.blocks_import_dir()
    os.makedirs(out_dir, exist_ok=True)
    members: dict = {}
    if "software_block_members" in database:
        for m in database["software_block_members"]:
            members.setdefault(m["block"], []).append(m)

    files, xml_files = [], []
    for b in (database["software_blocks"] if "software_blocks" in database else []):
        rows = [dict(m["values"]) for m in sorted(members.get(b["name"], []), key=lambda m: int(m["seq"]))]
        table = Table(b["name"], columns=list(b["columns"]), rows=rows)
        xml_path = xml_emit.write_fc_xml(b["name"], table, b["template_ref"], import_dir)
        if xml_path:                                             # 03 ships as FC XML -> drop its CSV (stale one too)
            xml_files.append(xml_path)
            stale_csv = os.path.join(out_dir, f"{b['name']}.csv")
            if os.path.exists(stale_csv):
                os.remove(stale_csv)
            continue
        files.append(_write_creation_csv(out_dir, b["name"], b["template_ref"], table, b["keys"]))
    return {"dir": out_dir, "files": files, "xml_files": xml_files, "count": len(files), "findings": []}


# --- 02_COM safe-DB + InstanceDBs.csv (the cross-builder 800c surfaces) --------------------------- #
def _com_members(database: DB) -> list:
    """The distinct `02_COM.{db_element}` cumulatives across all builder rows, in first-seen order (the
    zone-cumulative custom-DB members - phase 800 owns the 02_COM DB). Port of PL3 engine._com_members."""
    out = []
    if "software_block_members" not in database:
        return out
    for m in database["software_block_members"]:
        v = str((m["values"] or {}).get(COM_MEMBER_COL, "") or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def write_com_db(database: DB, out_dir: str | None = None) -> dict:
    """Emit the 02_COM custom safe-DB (a fail-safe F_DB GlobalDB XML) into `import_dir` (defaults to
    `config.blocks_import_dir()`): the standard seed constants (Always FALSE/TRUE/No Operation) followed by
    the builders' distinct 02_COM.{db_element} cumulatives. Reuses `datablock_xml.db_xml` (so the bytes +
    the F_DB OPC-lock match the 520 DBs). No cumulatives -> nothing written. Port of PL3 engine.write_com_db
    (its signals.write_safe_db primitive). A pure projection (`findings: []`)."""
    cumulatives = _com_members(database)
    out_dir = out_dir or config.blocks_import_dir()
    if not cumulatives:
        return {"path": "", "members": 0, "findings": []}
    names = [m for m in dict.fromkeys(str(x).strip() for x in (list(DB_CONSTANTS) + cumulatives)) if m]
    db = {"prog_lang": "F_DB", "members": [{"member": m} for m in names]}
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{COM_DB}.xml")
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(datablock_xml.db_xml(COM_DB, db, 1))
    return {"path": path, "members": len(names), "findings": []}


def _builder_instance_rows(database: DB) -> list:
    """(name, fb) for every non-empty `instanceOf-<FB>` cell across all builder tables, in PL3 order:
    block (table) order x the block's COLUMN order (software_blocks.columns) x member seq. Port of PL3
    engine._instance_rows (which reads the live Table columns; PL4 reads the SSOT members' value cells)."""
    out = []
    if "software_blocks" not in database:
        return out
    members_by_block: dict = {}
    for m in database["software_block_members"]:
        members_by_block.setdefault(m["block"], []).append(m)
    for b in database["software_blocks"]:
        cols = [c for c in b["columns"] if c.startswith(INSTANCE_OF)]
        if not cols:
            continue
        rows = sorted(members_by_block.get(b["name"], []), key=lambda m: int(m["seq"]))
        for c in cols:
            fb = c[len(INSTANCE_OF):]
            for m in rows:
                name = str((m["values"] or {}).get(c, "") or "").strip()
                if name:
                    out.append((name, fb))
    return out


def _config_instance_rows(database: DB) -> list:
    """(name, fb) for the 520 Instance-DB families - read from the `instance_dbs` SSOT table (PL4's
    decision: 520 already materialized generate's families in order, so 800 reads the table instead of
    re-running datablocks.generate as PL3's _config_instance_rows does)."""
    if "instance_dbs" not in database:
        return []
    return [(r["instance_name"], r["fb"]) for r in database["instance_dbs"]]


def write_instance_dbs(database: DB, out_dir: str | None = None) -> dict:
    """Write InstanceDBs.csv (the CreateInstanceDB surface) into `out_dir` (defaults to
    `config.blocks_creation_dir()`): the builders' instanceOf-<FB> cells FIRST, then the 520 config
    families, deduped by Name (first-seen). Plain UTF-8 (no BOM), csv.writer CRLF - NOT the GlobalDB-XML
    BOM rule. Port of PL3 engine.write_instance_dbs. A pure projection (`findings: []`)."""
    pairs = _builder_instance_rows(database) + _config_instance_rows(database)
    seen, deduped = set(), []
    for name, fb in pairs:
        if name and name not in seen:
            seen.add(name)
            deduped.append((name, fb))
    out_dir = out_dir or config.blocks_creation_dir()
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "InstanceDBs.csv")
    with open(path, "w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(["#", "Instance DBs created directly via CreateInstanceDB"])
        w.writerow(["%", "Name", "InstanceOf", "Number", "Folder"])
        for name, fb in deduped:
            w.writerow(["@", name, fb, "", fb])
    return {"path": path, "count": len(deduped), "findings": []}

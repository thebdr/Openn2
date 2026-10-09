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

import os
import shutil

from pipeline5 import config
from pipeline5.findings import gate as run
from pipeline5.truth.database import Database as DB
from pipeline5.findings.finding import Finding, record
from pipeline5.truth.table import Table as SsotTable
from pipeline5.phases.software_blocks.signals_view import Database
from pipeline5.phases.software_blocks.block_table import Table
from pipeline5.truth.datablocks import instance_dbs_table
from pipeline5.truth.signals import signals_table

INSTANCE_OF = "instanceOf-"


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


# --- build (-> the SSOT tables) + project (-> the CreationInfo CSVs) ------------------------------ #
def build(database: DB | None = None, system=None) -> tuple:
    """Phase 800a (SSOT): run every builder the SYSTEM registered over the `signals` table -> the
    `software_blocks` + `software_block_members` tables. Records the findings to `validation_issues`
    + saves. Returns (database, findings) - WARN-only (`blk_builder_no_rows` when a builder yields no
    rows). The engine knows no builder and no template by name: `system.builders` supplies the
    registry, `system.templates` the % key inventory (PL4 couplings #2/#5, resolved)."""
    if system is None:
        raise RuntimeError("engine.build requires a System (its builders + template inventory)")
    if database is None:
        colmap = config.load_column_map("IoList")
        database = DB([signals_table([m["canonical"] for m in colmap])]).load(config.database_dir())
    db = Database(list(database["signals"]),
                  members=list(database["db_members"]) if "db_members" in database else [])
    templates = system.templates
    inventory = templates.template_keys()                    # {block name -> [keys]} from the shipped .xml

    blk, mem = software_blocks_table(), software_block_members_table()
    findings = []
    for name, fn in system.builders.registry().items():
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


class _Delivery:
    """The system's delivery dirs for THIS generation (`output_layout.delivery_dirs(database)`), resolved
    LAZILY - the layout derives its PLC folder from the staged facts, so it is only asked for a dir that
    was not passed explicitly. `plc` = the resolved PLC name (the writers' header), None until asked."""

    def __init__(self, system, database):
        self._system, self._database, self._dirs = system, database, None

    def __getitem__(self, key: str) -> str:
        if self._dirs is None:
            self._dirs = self._system.output_layout.delivery_dirs(self._database)
        return self._dirs[key]

    @property
    def plc(self):
        return self._dirs.get("plc") if self._dirs else None


def _drop_stale_csv(out_dir: str, name: str) -> None:
    """Remove a block's leftover CreationInfo CSV (a ready-emitted block - FC XML / SCL - ships no CSV;
    a stale one from an earlier run must not survive as an apparent surface)."""
    stale = os.path.join(out_dir, f"{name}.csv")
    if os.path.exists(stale):
        os.remove(stale)


def project(database: DB | None = None, out_dir: str | None = None, import_dir: str | None = None,
            system=None, tpl_dir: str | None = None) -> dict:
    """Project `software_blocks` + `software_block_members` -> the `$/#/%/@` CreationInfo CSVs in `out_dir`,
    each block's template XML COPIED to `tpl_dir` and referenced RELATIVELY (`$ template=Templates/<file>.xml`
    - an absolute PL path is meaningless on the OP machine). A block with a READY-emit registration instead
    ships to `import_dir` and its CSV is DROPPED (a stale one removed; no template ships either):
    `emit="fc_xml"` -> a `SW.Blocks.FC` XML, `emit="scl"` -> an SCL FUNCTION source (`scl_emit`). A dir not
    passed comes from the system's `output_layout.delivery_dirs(database)` (the Siemens workspace: the csvs
    and the ready blocks under `<PLC>/Program blocks`, the templates under the workspace's `Templates/`);
    an explicit `out_dir` keeps its templates beside it (`<out_dir>/Templates`). The writers get the
    delivery's `plc` (their header's PLC) when the layout resolved it. A pure projection (`findings: []`).
    Returns {'dir', 'files', 'xml_files', 'scl_files', 'count', 'findings'} ('count'/'files' = the CSVs only)."""
    if system is None:
        raise RuntimeError("engine.project requires a System (its emitter table)")
    if database is None:
        database = DB([software_blocks_table(), software_block_members_table()]).load(config.database_dir())
    delivery = _Delivery(system, database)
    if out_dir is None:
        out_dir = delivery["blocks_creation"]
        tpl_dir = tpl_dir or delivery["templates"]
    tpl_dir = tpl_dir or os.path.join(out_dir, "Templates")
    os.makedirs(out_dir, exist_ok=True)
    members: dict = {}
    if "software_block_members" in database:
        for m in database["software_block_members"]:
            members.setdefault(m["block"], []).append(m)

    files, xml_files, scl_files = [], [], []
    for b in (database["software_blocks"] if "software_blocks" in database else []):
        rows = [dict(m["values"]) for m in sorted(members.get(b["name"], []), key=lambda m: int(m["seq"]))]
        table = Table(b["name"], columns=list(b["columns"]), rows=rows)
        # Emit-kind routing (PL4 coupling #2, final form): EVERY kind - including "csv" - resolves
        # through the system's emitter table; an undeclared kind raises, never a silent default.
        kind = system.builders.emit_kind(b["name"])
        if kind not in system.emitters:
            raise KeyError(f"system {system.id!r} declares no emitter for kind {kind!r} "
                           f"(block {b['name']!r})")
        if kind != "csv" and import_dir is None:
            import_dir = delivery["blocks_import"]
        ctx = {"import_dir": import_dir, "out_dir": out_dir, "tpl_dir": tpl_dir, "plc": delivery.plc}
        if kind == "scl":                                        # a ready SCL FUNCTION -> the PLC's Program blocks
            scl_files.append(system.emitters[kind](b, table, ctx))
            _drop_stale_csv(out_dir, b["name"])
            continue
        if kind == "csv":                                        # the template-fill CreationInfo surface
            files.append(system.emitters[kind](b, table, ctx))
            continue
        xml_path = system.emitters[kind](b, table, ctx)          # a ready XML -> the PLC's Program blocks, CSV dropped
        if xml_path:
            xml_files.append(xml_path)
        _drop_stale_csv(out_dir, b["name"])
    return {"dir": out_dir, "files": files, "xml_files": xml_files, "scl_files": scl_files,
            "count": len(files), "findings": []}


# --- InstanceDBs.csv (the cross-builder 800c surface) --------------------------------------------- #
# NOTE: 02_COM + 05_EM_STATE are ordinary 520 config DBs now (datablock_definitions.csv +
# per-area datablock_elements.csv rows over the signals table) - the transitional builder-column
# collector this section once held is retired; the 520 projector writes their XMLs.


def _members_by_block(database: DB) -> dict:
    """{block name -> its `software_block_members` rows} (unsorted; callers order by seq)."""
    members: dict = {}
    for m in database["software_block_members"]:
        members.setdefault(m["block"], []).append(m)
    return members


def _block_instances(b, members_by_block) -> list:
    """(name, fb) for ONE block's non-empty `instanceOf-<FB>` cells, in the block's COLUMN order x
    member seq - the per-block leg of `_builder_instance_rows`, reused by `block_report`."""
    cols = [c for c in b["columns"] if c.startswith(INSTANCE_OF)]
    if not cols:
        return []
    rows = sorted(members_by_block.get(b["name"], []), key=lambda m: int(m["seq"]))
    out = []
    for c in cols:
        fb = c[len(INSTANCE_OF):]
        for m in rows:
            name = str((m["values"] or {}).get(c, "") or "").strip()
            if name:
                out.append((name, fb))
    return out


def _builder_instance_rows(database: DB) -> list:
    """(name, fb) for every non-empty `instanceOf-<FB>` cell across all builder tables, in PL3 order:
    block (table) order x the block's COLUMN order (software_blocks.columns) x member seq. Port of PL3
    engine._instance_rows (which reads the live Table columns; PL4 reads the SSOT members' value cells)."""
    if "software_blocks" not in database:
        return []
    members = _members_by_block(database)
    out = []
    for b in database["software_blocks"]:
        out.extend(_block_instances(b, members))
    return out


def block_report(database: DB, system=None) -> list:
    """One dict per built block - the data behind the verbose 800 log (user spec: an INFO line per
    generated block with its template, its output surface, and the builder function). Keys: `name`,
    `template_stem` ('' when the block has NO shipped template - the stem fell back to the name),
    `builder` ('builders.<fn>' from the registry; '-' for an unregistered block), `emit`
    ('csv' | 'fc_xml' - the declared output surface), `rows` (@-row count), `instances` (the block's
    non-empty instanceOf-<FB> cells -> its InstanceDBs.csv contribution). A pure read of the SSOT
    tables + the registry."""
    if "software_blocks" not in database:
        return []
    members = _members_by_block(database)
    if system is None:
        raise RuntimeError("engine.block_report requires a System (its builder registry)")
    reg = system.builders.registry()
    out = []
    for b in database["software_blocks"]:
        fn = reg.get(b["name"])
        builder = f"{fn.__module__.rsplit('.', 1)[-1]}.{fn.__name__}" if fn else "-"
        out.append({"name": b["name"],
                    "template_stem": b["template_stem"] if b["template_stem"] != b["name"] else "",
                    "builder": builder, "emit": system.builders.emit_kind(b["name"]),
                    "rows": len(members.get(b["name"], [])),
                    "instances": len(_block_instances(b, members))})
    return out


def _config_instance_rows(database: DB) -> list:
    """(name, fb) for the 520 Instance-DB families - read from the `instance_dbs` SSOT table (PL4's
    decision: 520 already materialized generate's families in order, so 800 reads the table instead of
    re-running datablocks.generate as PL3's _config_instance_rows does)."""
    if "instance_dbs" not in database:
        return []
    return [(r["instance_name"], r["fb"]) for r in database["instance_dbs"]]


def write_instance_dbs(database: DB, out_dir: str | None = None, system=None) -> dict:
    """Collect the instance DBs (the CreateInstanceDB surface): the builders' instanceOf-<FB> cells FIRST,
    then the 520 config families, deduped by Name (first-seen) - and hand the (name, fb) pairs to the
    system's `instance_dbs` emitter, which owns the file format (Siemens: `InstanceDBs.csv` with the
    contract-v1 header). `out_dir` defaults to the system's delivery dir (the PLC's Program blocks). Port
    of PL3 engine.write_instance_dbs. A pure projection (`findings: []`). Returns {'path', 'count',
    'findings'}."""
    if system is None:
        raise RuntimeError("engine.write_instance_dbs requires a System (its instance_dbs emitter)")
    if "instance_dbs" not in system.emitters:
        raise KeyError(f"system {system.id!r} declares no emitter for kind 'instance_dbs'")
    pairs = _builder_instance_rows(database) + _config_instance_rows(database)
    seen, deduped = set(), []
    for name, fb in pairs:
        if name and name not in seen:
            seen.add(name)
            deduped.append((name, fb))
    delivery = _Delivery(system, database)
    if out_dir is None:
        out_dir = delivery["blocks_creation"]
    path = system.emitters["instance_dbs"](deduped, {"out_dir": out_dir, "plc": delivery.plc})
    return {"path": path, "count": len(deduped), "findings": []}

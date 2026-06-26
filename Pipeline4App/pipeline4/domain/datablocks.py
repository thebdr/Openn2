"""Config-driven data-block generation (phase 520) - clean-room port of PL3's `datablocks`.

Three registry CSVs (`datablock_definitions` / `datablock_elements` / `datablock_types`) declare every DB,
its members, and the valid data types. `generate` VALIDATES the config up front - collecting ALL errors
(unknown datatype / a member's DB not declared / a bad template or for_each / only-load-memory + Optimized)
- and on any error the phase HALTS before the OP4 import ever sees a malformed name. With a clean config it
produces the Global DBs (their TIA attribute set + members) and the Instance-DB families ((name, FB) pairs).

`build` is the PL4 SSOT wrapper: it runs `generate` over the **signals** table, writes the result into the
**`db_members`** and **`instance_dbs`** tables, and WRITES BACK each signal's `name_in_db` / `datablocks` /
`plc_binding` (the registry is the single evaluator; downstream phases read the staged fields). The
`<DB>.xml` / `InstanceDBs.csv` projection of these tables is phase 520c.

CSV 1 is the AUTHORITATIVE registry: a member whose `db_name` is not a declared Global is an error. The two
grammars (PEP-3101 templates + the `for_each` DSL) live in `domain/dbtemplate.py`.
"""
from __future__ import annotations

from pipeline4.core import config
from pipeline4.core.database import Database
from pipeline4.domain import dbtemplate as T
from pipeline4.domain.db_members import db_members_table, instance_dbs_table
from pipeline4.domain.signals import signals_table

DB_CONSTANTS = ["Always FALSE", "Always TRUE", "No Operation"]   # the DB seed (Bool); space, not underscore


def _seed_member(name) -> dict:
    return {"name": name, "datatype": "Bool", "retain": False, "start_value": "", "comment": "",
            "ext_accessible": True, "ext_visible": True, "ext_writable": True, "setpoint": False,
            "source": "seed", "source_row": None, "seq": -1}


def _ctx(binding, rep_row) -> dict:
    return {**(rep_row or {}), **(binding or {})}


def _check_columns(fe, row_cols, where, warnings) -> None:
    """A for_each referencing a column present in NO row yields nothing - WARN (a likely typo) rather than
    halt, since a minimal/partial row set may legitimately omit a column. Only checks when rows are present."""
    if row_cols:
        for c in (fe.columns | ({fe.column} if fe.column else set())):
            if c not in row_cols:
                warnings.append(f"{where}: for_each references column {c!r} present in no row - it matches nothing")


def generate(rows, definitions, elements, types) -> tuple:
    """-> (global_dbs, instance_dbs, errors, warnings).
      global_dbs   = {db_name: {prog_lang, memory_layout, opc_ua, webserver, only_load_memory,
                     write_protected, retain_reserve, memory_reserve, create_when, members: [member, ...]}}
      instance_dbs = [(name, fb), ...]   (-> InstanceDBs.csv)
    A non-empty `errors` means the phase must halt; the dbs are then partial/ignored. Each member carries the
    PL4 bookkeeping `source` / `source_row` / `seq` (the write-back uses them; the XML projection ignores them)."""
    rows = list(rows or [])
    errors, warnings = [], []
    type_map = {t["name"].strip().lower(): t["name"].strip() for t in (types or []) if t.get("name")}
    row_cols = set().union(*[set(r) for r in rows]) if rows else set()

    # 1. compile + validate the definitions; split Global (literal) vs Instance families
    global_defs, instance_defs, declared = [], [], set()
    for d in definitions or []:
        name, dt = d["db_name"], (d.get("db_type") or "Global").strip().lower()
        try:
            fe = T.compile_for_each(d.get("for_each", ""))
        except T.DbTemplateError as e:
            errors.append(f"DB {name!r}: {e}")
            continue
        _check_columns(fe, row_cols, f"DB {name!r}", warnings)
        if d.get("only_load_memory") and (d.get("memory_layout") or "Optimized").strip().lower() == "optimized":
            errors.append(f"DB {name!r}: only_load_memory requires Standard (non-Optimized) block access")
        if dt == "instance":
            if not d.get("instance_of"):
                errors.append(f"DB {name!r}: db_type=Instance requires instance_of (the FB)")
            instance_defs.append((d, fe))
        else:
            if fe.kind != "literal":
                errors.append(f"DB {name!r}: a Global DB must have a literal name (no for_each)")
            pl = (d.get("db_programming_language") or "DB").strip()           # the prog-lang guardrails:
            if pl and pl != "DB" and pl.upper() != "F_DB":                    # an unrecognized lang is a likely typo
                warnings.append(f"DB {name!r}: db_programming_language {pl!r} written verbatim as "
                                f"<ProgrammingLanguage> (expected 'DB' or 'F_DB') - TIA may reject the import")
            if pl.upper() == "F_DB" and d.get("opc_ua"):                      # a fail-safe DB is hard-locked OPC-off
                warnings.append(f"DB {name!r}: opc_ua=true ignored on a fail-safe (F_DB) DB - it is kept "
                                f"OPC-inaccessible for safety (an OPC write can fault the CPU to STOP)")
            declared.add(name)
            global_defs.append(d)

    # 2. validate the elements against the declared Globals + the type registry; compile their for_each
    elem_compiled = []
    for el in elements or []:
        db = el["db_name"]
        where = f"element {el.get('member','')!r} -> DB {db!r}"
        if db not in declared:
            errors.append(f"{where}: DB not declared in datablock_definitions.csv")
        dtype = (el.get("datatype") or "Bool").strip()
        if type_map and dtype.lower() not in type_map:
            errors.append(f"{where}: unknown datatype {dtype!r} (add it to datablock_types.csv)")
        try:
            fe = T.compile_for_each(el.get("for_each", ""))
            _check_columns(fe, row_cols, where, warnings)
            elem_compiled.append((el, fe, type_map.get(dtype.lower(), dtype)))
        except T.DbTemplateError as e:
            errors.append(f"{where}: {e}")

    if errors:
        return {}, [], errors, warnings

    # 3. build the Global DB shells (seeds prepended)
    global_dbs = {}
    for d in global_defs:
        if (d.get("create_when") or "if_elements").strip().lower() == "never":
            continue
        seeds = [_seed_member(c) for c in DB_CONSTANTS] if d.get("seed") else []
        global_dbs[d["db_name"]] = {
            "prog_lang": d.get("db_programming_language") or "DB",
            "memory_layout": d.get("memory_layout") or "Optimized",
            "opc_ua": d.get("opc_ua", True), "webserver": d.get("webserver", True),
            "only_load_memory": d.get("only_load_memory", False),
            "write_protected": d.get("write_protected", False),
            "retain_reserve": d.get("retain_reserve", False),
            "memory_reserve": d.get("memory_reserve", ""),
            "create_when": (d.get("create_when") or "if_elements").strip().lower(),
            "members": list(seeds), "_seen": {m["name"] for m in seeds},
            "_nseed": len(seeds),
        }

    # 4. members (CSV 2) -> the Global DBs. `seq` is a global append counter (= element-row order, then row
    #    order) so the write-back can pick a signal's LEFTMOST (earliest-matching) member.
    seq = 0
    for el, fe, dtype in elem_compiled:
        g = global_dbs.get(el["db_name"])
        if g is None:                                          # a 'never' DB declared but not emitted
            continue
        for binding, rep in fe.evaluate(rows):
            ctx = _ctx(binding, rep)
            try:
                name = T.render(el["member"], ctx)
                start = T.render(el["start_value"], ctx) if el.get("start_value") else ""
                comment = T.render(el["comment"], ctx) if el.get("comment") else ""
            except T.DbTemplateError as e:                     # unreachable post-validate, but be safe
                errors.append(f"DB {el['db_name']!r}: {e}")
                continue
            if not name or name in g["_seen"]:
                if name:
                    warnings.append(f"{el['db_name']}: member {name!r} produced more than once - kept 1")
                continue
            g["_seen"].add(name)
            if fe.kind == "row":                               # one signal -> this member (attributes back)
                source, source_row = (rep or {}).get("uid", ""), rep
            elif fe.kind == "unique":                          # an aggregate over a distinct value (a cabinet)
                source, source_row = "|".join(str(v) for v in binding.values()), None
            else:                                              # a literal member (no source row)
                source, source_row = "literal", None
            g["members"].append({
                "name": name, "datatype": dtype, "retain": el.get("retain", False),
                "start_value": start, "comment": comment,
                "ext_accessible": el.get("ext_accessible", True), "ext_visible": el.get("ext_visible", True),
                "ext_writable": el.get("ext_writable", True), "setpoint": el.get("setpoint", False),
                "source": source, "source_row": source_row, "seq": seq,
            })
            seq += 1

    # 5. instance families (CSV 1, db_type=Instance) -> (name, FB)
    instance_dbs, seen_inst = [], set()
    for d, fe in instance_defs:
        for binding, rep in fe.evaluate(rows):
            try:
                name = T.render(d["db_name"], _ctx(binding, rep))
            except T.DbTemplateError as e:
                errors.append(f"DB {d['db_name']!r}: {e}")
                continue
            if name and name not in seen_inst:
                seen_inst.add(name)
                instance_dbs.append((name, d["instance_of"]))

    if errors:
        return {}, [], errors, warnings

    # 6. create_when=if_elements drops a Global with no REAL member (seeds alone don't count); strip bookkeeping
    for name in [n for n, g in global_dbs.items()
                 if g["create_when"] == "if_elements" and len(g["members"]) <= g["_nseed"]]:
        del global_dbs[name]
    for g in global_dbs.values():
        g.pop("_seen", None)
        g.pop("_nseed", None)
    return global_dbs, instance_dbs, errors, warnings


def write_back(rows, global_dbs) -> None:
    """Denormalize each signal's DB membership back onto it: `datablocks` (the ordered DBs it joins),
    `name_in_db` (its member in the LEFTMOST DB), `plc_binding` (`"<leftmost db>"."<name_in_db>"`, else the
    tag `"<name_in_tagtable>"`, else ''). Only `row`-kind members (one signal -> one member) attribute to a
    signal; seeds + `unique` aggregates do not. Leftmost = the earliest element row that matched (the `seq`)."""
    contributions = []
    for db_name, g in global_dbs.items():
        for m in g["members"]:
            if m.get("source_row") is not None:
                contributions.append((m["seq"], id(m["source_row"]), db_name, m["name"]))
    contributions.sort(key=lambda c: c[0])
    by_signal: dict = {}
    for _seq, rid, db_name, member in contributions:
        by_signal.setdefault(rid, []).append((db_name, member))

    for row in rows:
        members = by_signal.get(id(row))
        if members:
            dbs: list = []
            for db_name, _member in members:
                if db_name not in dbs:
                    dbs.append(db_name)
            row["name_in_db"] = members[0][1]
            row["datablocks"] = dbs
            row["plc_binding"] = f'"{dbs[0]}"."{members[0][1]}"'
        else:
            tag = (row.get("name_in_tagtable") or "").strip()
            row["name_in_db"] = ""
            row["datablocks"] = []
            row["plc_binding"] = f'"{tag}"' if tag else ""


def _fill_db_members(table, global_dbs) -> None:
    for db_name, g in global_dbs.items():
        for m in g["members"]:
            table.add(db_name=db_name, member=m["name"], datatype=m["datatype"],
                      start_value=m["start_value"], comment=m["comment"], retain=m["retain"],
                      ext_accessible=m["ext_accessible"], ext_visible=m["ext_visible"],
                      ext_writable=m["ext_writable"], setpoint=m["setpoint"], source=m.get("source", ""))


def build(database: Database | None = None) -> tuple:
    """Phase 520 (SSOT): evaluate the registry over the signals table -> the `db_members` + `instance_dbs`
    tables + the write-back. Loads the staged Database from the Database folder when none is passed; on a
    validation error returns WITHOUT writing (the caller logs + halts). Saves on success.
    Returns (database, errors, warnings)."""
    if database is None:
        colmap = config.load_column_map("IoList")
        database = Database([signals_table([m["canonical"] for m in colmap])]).load(config.database_dir())
    rows = list(database["signals"])
    global_dbs, instance_dbs, errors, warnings = generate(
        rows, config.load_db_definitions(), config.load_db_elements(), config.load_db_types())
    if errors:
        return database, errors, warnings

    dbm, idb = db_members_table(), instance_dbs_table()
    _fill_db_members(dbm, global_dbs)
    for name, fb in instance_dbs:
        idb.add(instance_name=name, fb=fb)
    write_back(rows, global_dbs)

    for table in (dbm, idb):
        if table.name in database:
            database[table.name].rows = table.rows
        else:
            database.add_table(table)
    database.save(config.database_dir())
    return database, errors, warnings

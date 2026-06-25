"""Config-driven data-block generation (phase 520).

Three CSVs (`datablock_definitions` / `datablock_elements` / `datablock_types`) declare every DB, its
members, and the valid data types. `generate` VALIDATES the config up front - collecting ALL errors
(unknown datatype / a member's DB not declared / a bad template or for_each / the only-load-memory + Optimized
clash) - and on any error the phase HALTS before the Openn3 import ever sees a malformed name. With a clean
config it produces:
  - the **Global DBs** (their full TIA attribute set + members) -> written by `signals._db_xml`;
  - the **Instance-DB families** ((name, FB) pairs) -> `InstanceDBs.csv`.

CSV 1 is the AUTHORITATIVE registry: a member whose `db_name` is not a declared Global is an error. Pure +
data-independent; the two grammars (PEP-3101 templates + the `for_each` DSL) live in `domain/dbtemplate.py`.
"""
from __future__ import annotations

from pipeline3.domain import dbtemplate as T

DB_CONSTANTS = ["Always FALSE", "Always TRUE", "No Operation"]   # the legacy DB seed (Bool); == signals.DB_CONSTANTS


def _seed_member(name) -> dict:
    return {"name": name, "datatype": "Bool", "retain": False, "start_value": "", "comment": "",
            "ext_accessible": True, "ext_visible": True, "ext_writable": True, "setpoint": False}


def _ctx(binding, rep_row) -> dict:
    return {**(rep_row or {}), **(binding or {})}


def _check_columns(fe, row_cols, where, warnings):
    """A for_each referencing a column present in NO row yields nothing - WARN (a likely typo) rather than
    halt, since a minimal/partial row set may legitimately omit a column. Only checks when rows are present."""
    if row_cols:
        for c in (fe.columns | ({fe.column} if fe.column else set())):
            if c not in row_cols:
                warnings.append(f"{where}: for_each references column {c!r} present in no row - it matches nothing")


def generate(rows, definitions, elements, types) -> tuple:
    """-> (global_dbs, instance_dbs, errors, warnings).
      global_dbs  = {db_name: {prog_lang, memory_layout, opc_ua, webserver, only_load_memory,
                    write_protected, retain_reserve, memory_reserve, members: [member dict, ...]}}
      instance_dbs = [(name, fb), ...]   (-> InstanceDBs.csv)
    A non-empty `errors` means the phase must halt; `global_dbs`/`instance_dbs` are then partial/ignored."""
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
            pl = (d.get("db_programming_language") or "DB").strip()  # guardrail (moved from build_data_blocks):
            if pl and pl != "DB" and pl.upper() != "F_DB":           # an unrecognized ProgrammingLanguage is a typo
                warnings.append(f"DB {name!r}: db_programming_language {pl!r} written verbatim as "
                                f"<ProgrammingLanguage> (expected 'DB' or 'F_DB') - TIA may reject the import")
            if pl.upper() == "F_DB" and d.get("opc_ua"):             # a fail-safe DB is hard-locked OPC-off anyway
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

    # 3. build the Global DB shells
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
            "members": list(seeds), "_seen": {m["name"] for m in seeds},  # seeds prepended (legacy parity)
            "_nseed": len(seeds),
        }

    # 4. members (CSV 2) -> the Global DBs
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
            g["members"].append({
                "name": name, "datatype": dtype, "retain": el.get("retain", False),
                "start_value": start, "comment": comment,
                "ext_accessible": el.get("ext_accessible", True), "ext_visible": el.get("ext_visible", True),
                "ext_writable": el.get("ext_writable", True), "setpoint": el.get("setpoint", False),
            })

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

    # 6. create_when=if_elements drops a Global with no REAL members (seeds alone don't count - the legacy
    #    path never created a DB that no row contributed to)
    for name in [n for n, g in global_dbs.items()
                 if g["create_when"] == "if_elements" and len(g["members"]) <= g["_nseed"]]:
        del global_dbs[name]
    for g in global_dbs.values():
        g.pop("_seen", None)
        g.pop("_nseed", None)
    return global_dbs, instance_dbs, errors, warnings

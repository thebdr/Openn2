"""Phase 900 / 910 - Pipeline Coverage Report. Clean-room port of PL3's `domain/coverage.py`.

Traces each staged signal's life from staging (300) through every downstream phase to flag two
cross-check defects:
  - **ORPHAN**  : a staged SIGNAL whose identity appears in NO output (staged, but nothing consumes it);
  - **UNPLACED**: an output emits a qualified `"<db>"."<member>"` reference whose DB the pipeline
                  generates but whose member was never created in that DB.
Two row kinds are never ORPHAN: raw I/O **channels** (untyped rows with an I/Q address - physical module
points, covered by hardware) and **structural** rows (headers / node-meta with no address).

**PL4 read source (user decision): the SSOT TABLES, not the on-disk artifacts.** PL3 re-read the produced
BuilderData files because its phases admit user edits (editable .xlsm shells, ...); PL4 DEFERRED the shells
and every BuilderData export is a byte-stable PROJECTION of an SSOT table, so coverage over the tables ==
coverage over the artifacts by construction - hermetic, no openpyxl/glob/XML re-parse, and UNPLACED is exact
(db_members is the truth, not a regex over *.xml). The one fact NOT in a table is a hand-filled interface
Side-2 row (it lives only in the inserted IF_ sheet) - a documented gap; see DESIGN. The per-signal trace is
PERSISTED as a `coverage` SSOT table (every created datum is written - the PL4 thesis); the CSV is its
projection. ORPHAN/UNPLACED are emitted as WARN Findings into `validation_issues` (the severity model),
rendered (never halts). 920 (TIA project coverage) stays deferred.
"""
from __future__ import annotations

import csv
import os

from pipeline4.core import config
from pipeline4.core.finding import Finding, record
from pipeline4.core.table import Table
from pipeline4.domain import datablocks, diagnosis, identity, interfaces

import re

# the downstream outputs a signal can land in (the lifecycle stages after staging).
STAGES = ("interfaces", "io_tags", "data_blocks", "diagnosis", "hardware", "software")
_STAGE_LABEL = {"interfaces": "400 interfaces", "io_tags": "510 I/O tags",
                "data_blocks": "520 data blocks", "diagnosis": "600 diagnosis",
                "hardware": "700 hardware", "software": "800 software"}

_QUALREF = re.compile(r'"([^"]+)"\."([^"]+)"')        # a TIA-qualified "<db>"."<member>" reference


def _pads() -> set:
    """The seed constants (Always FALSE/TRUE/No Operation) - from generation_params.yaml, the same
    values the 520 seeds and the builder-owned DBs prepend."""
    return set(datablocks.seed_members())


# --- the SSOT table (the persisted per-signal trace) --------------------------------------------- #
def coverage_table() -> Table:
    """One row per staged row: its identity + per-stage placement + ORPHAN flag. The report CSV is its
    projection (`source_cell` is the CSV's `source` column)."""
    return Table(
        "coverage",
        columns=["uid", "source_cell", "kind", "script_type", "FLD", "address", "type",
                 "name_in_db", "tag", "binding", *STAGES, "outputs", "flag"],
        json_columns=[],
        key_columns=["source_cell"],
    )


# --- row classification (PL4: reads the `type` object cell, not PL3's `_type`) ------------------- #
def is_signal(row) -> bool:
    """A staged row is a SIGNAL (traceable, ORPHAN-able) when it resolved to a type OR carries a
    DB-member / PLC-tag identity. Untyped raw channels and structural rows are not signals."""
    if (row.get("type") or {}).get("type_id"):
        return True
    return any(str(row.get(k, "") or "").strip() for k in ("name_in_db", "name_in_tagtable"))


def row_kind(row) -> str:
    """'signal' | 'channel' (untyped row with an I/Q address = a raw module point) | 'structural'."""
    if is_signal(row):
        return "signal"
    return "channel" if str(row.get("bit", "") or "").strip()[:1].upper() in ("I", "Q") else "structural"


# --- reading the SSOT tables into the emitted-identity sets (replaces PL3's on-disk readers) ------ #
def collect_outputs(database) -> dict:
    """Read every SSOT table into the emitted-identity sets the trace attributes against - the same dict
    shape PL3's `collect_outputs(out_root)` produced from disk. A missing table degrades to empty +
    found=False (noted in the report)."""
    # (510) the tag names 510 would emit: io-signal name_in_tagtable + interface_elements signal_name.
    tags = set()
    for r in (database["signals"] if "signals" in database else []):
        if identity.is_io_signal(r):
            n = str(r.get("name_in_tagtable") or "").strip()
            if n:
                tags.add(n)
    for e in (database["interface_elements"] if "interface_elements" in database else []):
        n = str(e.get("signal_name") or "").strip()
        if n:
            tags.add(n)

    # (520) {db_name: set(member)} from db_members (02_COM/05_EM_STATE included - they are ordinary
    # config DBs whose per-area element rows evaluate over the signals table).
    dbm: dict = {}
    for m in (database["db_members"] if "db_members" in database else []):
        dbm.setdefault(str(m.get("db_name") or ""), set()).add(str(m.get("member") or ""))

    # (600) diagnosis bindings (the in_binding + the DiagList PLC_Binding cell) + consumed refs.
    diagb, consumed = set(), []
    for e in (database["diagnosis_entries"] if "diagnosis_entries" in database else []):
        for b in (str(e.get("in_binding") or "").strip(),
                  str((e.get("diag_columns") or {}).get("PLC_Binding") or "").strip()):
            if b:
                diagb.add(b)
                for mm in _QUALREF.finditer(b):
                    consumed.append(("diagnosis", mm.group(1), mm.group(2)))

    # (400) interface mirror Expressions + the interface instance names + consumed refs.
    ifx, ifi = set(), set()
    for e in (database["interface_elements"] if "interface_elements" in database else []):
        v = str(e.get("expression") or "").strip()
        if v:
            ifx.add(v)
            for mm in _QUALREF.finditer(v):
                consumed.append(("interface-mirror", mm.group(1), mm.group(2)))
    for iface in (database["interfaces"] if "interfaces" in database else []):
        inst = str(iface.get("instance") or "").strip()
        if inst:
            ifi.add(inst)

    # (700) the generated station names.
    stations = set()
    for tname in ("hardware_stations", "hardware_modules"):
        for s in (database[tname] if tname in database else []):
            n = str(s.get("station_name") or "").strip()
            if n:
                stations.add(n)

    # (800) {emitted value: set(block id)} from the builder @ rows (the block id = name before '_'),
    # ITERATOR cells spread; pads dropped. The 03 FC-XML refs are covered here (its rows are in the table).
    swrefs: dict = {}
    pads = _pads()
    block_id = {b["name"]: str(b["name"]).split("_", 1)[0]
                for b in (database["software_blocks"] if "software_blocks" in database else [])}
    for m in (database["software_block_members"] if "software_block_members" in database else []):
        bid = block_id.get(m["block"], str(m["block"]).split("_", 1)[0])
        for v in (m.get("values") or {}).values():
            for c in (v if isinstance(v, (list, tuple)) else [v]):
                c = str(c).strip()
                if c and c not in pads:
                    swrefs.setdefault(c, set()).add(bid)

    found = {
        "interfaces": bool(len(database["interface_elements"]) if "interface_elements" in database else 0),
        "io_tags": bool(tags),
        "data_blocks": bool(dbm),
        "diagnosis": bool(len(database["diagnosis_entries"]) if "diagnosis_entries" in database else 0),
        "hardware": bool(stations),
        "software": bool(len(database["software_block_members"]) if "software_block_members" in database else 0),
    }
    return {"tags": tags, "db_members": dbm, "diag_bindings": diagb, "iface_exprs": ifx,
            "iface_instances": ifi, "stations": stations, "sw_refs": swrefs,
            "consumed": consumed, "found": found}


# --- UNPLACED (pure - ports verbatim) ----------------------------------------------------------- #
def find_unplaced(produced: dict, consumed: list) -> list:
    """Each consumed `(origin, db, member)` whose db is generated (db in `produced`) but whose member is
    NOT among that DB's actual members. Refs to DBs the pipeline does NOT generate are ignored (920 scope).
    Deduped on (db, member), origins joined. Returns [{'db','member','referenced_by'}] sorted."""
    unplaced_map: dict = {}
    for origin, d, m in consumed:
        if d in produced and m not in produced[d]:
            unplaced_map.setdefault((d, m), set()).add(origin)
    return [{"db": d, "member": m, "referenced_by": "|".join(sorted(origins))}
            for (d, m), origins in sorted(unplaced_map.items())]


# --- attribution (pure: rows + the read outputs -> per-row placement + findings) ----------------- #
def attribute(rows, outputs) -> dict:
    """Attribute each staged row to the output stages whose artifacts carry its identity, and compute the
    ORPHAN / UNPLACED findings. Pure over `rows` + `outputs` (collect_outputs' result). PL4: `binding` is
    the STORED `plc_binding` column (not re-derived); `type` is the object cell."""
    rows = list(rows or [])
    tags = outputs["tags"]
    dbm = outputs["db_members"]
    diagb = outputs["diag_bindings"]
    ifx, ifi = outputs["iface_exprs"], outputs["iface_instances"]
    stations = outputs["stations"]
    swrefs = outputs["sw_refs"]

    records, orphans = [], []
    for r in rows:
        member = str(r.get("name_in_db", "") or "").strip()
        tag = str(r.get("name_in_tagtable", "") or "").strip()
        binding = str(r.get("plc_binding", "") or "").strip()
        pname = str(r.get("profinet_name", "") or "").strip()
        place = {s: set() for s in STAGES}

        if tag and tag in tags:
            place["io_tags"].add(str(r.get("tagtable", "") or "").strip() or "yes")
        if member:
            place["data_blocks"].update(d for d, ms in dbm.items() if member in ms)
        if binding and binding in diagb:
            place["diagnosis"].add("yes")
        if str(r.get("script_type", "")).strip().upper() == interfaces.TRIGGER_TYPE \
                and str(r.get("index", "") or "").strip() in ifi:
            place["interfaces"].add("defines")
        if binding and binding in ifx:
            place["interfaces"].add("mirror")
        if pname and pname in stations:
            place["hardware"].add("station")
        elif diagnosis._addr_byte(r.get("bit")):
            node = diagnosis.node_of(rows, r)
            if node and str(node.get("profinet_name", "") or "").strip() in stations:
                place["hardware"].add("module")
        for ident in {member, tag, binding}:
            if ident and ident in swrefs:
                place["software"].update(swrefs[ident])

        landed = [s for s in STAGES if place[s]]
        kind = row_kind(r)
        rec = {
            "source": str(r.get("source_cell", "") or ""),
            "kind": kind,
            "script_type": str(r.get("script_type", "") or ""),
            "FLD": str(r.get("iol_FLD", "") or ""),
            "address": str(r.get("bit", "") or ""),
            "type": (r.get("type") or {}).get("type_id", ""),
            "name_in_db": member,
            "tag": tag,
            "binding": binding,
        }
        for s in STAGES:
            rec[s] = "|".join(sorted(place[s]))
        rec["outputs"] = len(landed)
        rec["flag"] = "ORPHAN" if (kind == "signal" and not landed) else ""
        if rec["flag"] == "ORPHAN":
            orphans.append(rec)
        records.append(rec)

    unplaced = find_unplaced(outputs["db_members"], outputs["consumed"])
    stage_counts = {s: sum(1 for rec in records if rec[s]) for s in STAGES}
    kind_counts = {k: sum(1 for rec in records if rec["kind"] == k)
                   for k in ("signal", "channel", "structural")}
    stats = {"rows": len(records), "kinds": kind_counts, "stages": stage_counts,
             "orphans": len(orphans), "unplaced": len(unplaced),
             "generated_dbs": sorted(outputs["db_members"]),
             "missing": [s for s in STAGES if not outputs["found"].get(s)]}
    return {"records": records, "orphans": orphans, "unplaced": unplaced, "stats": stats}


def trace(database) -> dict:
    """Read the SSOT tables and attribute every staged row against them."""
    rows = list(database["signals"]) if "signals" in database else []
    return attribute(rows, collect_outputs(database))


# --- report rendering (verbatim from PL3) ------------------------------------------------------- #
_CSV_COLUMNS = ["source", "kind", "script_type", "FLD", "address", "type",
                "name_in_db", "tag", "binding", *STAGES, "outputs", "flag"]


def render_csv(result) -> tuple:
    """(header, rows) for the per-signal coverage CSV (one row per staged row)."""
    rows = [[rec.get(c, "") for c in _CSV_COLUMNS] for rec in result["records"]]
    return _CSV_COLUMNS, rows


def render_txt(result) -> str:
    """The human coverage summary."""
    st = result["stats"]
    L = ["PIPELINE COVERAGE REPORT  (phase 910)",
         "=" * 52,
         f"Staged rows: {st['rows']}   "
         f"(signals {st['kinds']['signal']}, raw I/O channels {st['kinds']['channel']}, "
         f"structural {st['kinds']['structural']})",
         "Source: the SSOT tables (the BuilderData exports are their projection).",
         ""]
    if st["missing"]:
        L.append("MISSING outputs (run the phase to populate; stage shown empty below): "
                 + ", ".join(_STAGE_LABEL[s] for s in st["missing"]))
        L.append("")
    L.append("Stage coverage (rows landing in each output):")
    for s in STAGES:
        miss = "  (not generated)" if s in st["missing"] else ""
        L.append(f"  {_STAGE_LABEL[s]:<16}{st['stages'][s]:>5}{miss}")
    L += ["", f"ORPHAN  (a signal that lands in no output): {st['orphans']}"]
    if result["orphans"]:
        for rec in result["orphans"]:
            L.append(f"  {rec['source']:<14} {rec['script_type']:<6} {rec['FLD']}  "
                     f"[{rec['address']}]  type={rec['type']}")
    else:
        L.append("  -- none: every staged signal lands in at least one output --")
    L += ["", f"UNPLACED  (an output references a generated-DB member that was never created): "
              f"{st['unplaced']}"]
    if result["unplaced"]:
        for u in result["unplaced"]:
            L.append(f'  [{u["db"]}] "{u["member"]}"   <- {u["referenced_by"]}')
    else:
        L.append("  -- none: every emitted DB-member reference resolves to an actual member --")
    L += ["",
          f"Pipeline-generated data blocks: {', '.join(st['generated_dbs']) or '(none found)'}",
          "",
          "Per-signal detail -> io_project_coverage_report.csv"]
    return "\n".join(L) + "\n"


# --- build (-> the coverage SSOT table + findings) + project (-> the report files) --------------- #
def _io_doc() -> str:
    """The I/O List basename - the GUI log resolves it for the clickable Sheet!Cell links."""
    try:
        return os.path.basename(str(config.load_params().get("iolist_path") or ""))
    except Exception:  # noqa: BLE001
        return ""


def _findings(result) -> list:
    """The WARN findings: one cov_orphan_signal per ORPHAN signal + one cov_unplaced_member per UNPLACED
    (db, member). Informational - the GUI renders them, never gates."""
    out = []
    for rec in result["orphans"]:
        out.append(Finding(phase=900, type="cov_orphan_signal", severity="WARN",
                           detail=f"{rec['FLD']} [{rec['address']}] type={rec['type']} - lands in no output",
                           location=str(rec["source"]), source_uid="", doc=_io_doc()))
    for u in result["unplaced"]:
        out.append(Finding(phase=900, type="cov_unplaced_member", severity="WARN",
                           detail=f'"{u["member"]}" referenced by {u["referenced_by"]} - never created in the DB',
                           location=f'DB {u["db"]}', source_uid=""))
    return out


def build(database) -> tuple:
    """Phase 900 (SSOT): trace the signals across the tables -> the `coverage` table + the
    cov_orphan_signal / cov_unplaced_member WARN findings (recorded to validation_issues). Saves.
    Returns (database, findings)."""
    result = trace(database)
    tbl = coverage_table()
    for rec in result["records"]:
        tbl.add(source_cell=rec["source"], kind=rec["kind"], script_type=rec["script_type"],
                FLD=rec["FLD"], address=rec["address"], type=rec["type"], name_in_db=rec["name_in_db"],
                tag=rec["tag"], binding=rec["binding"], outputs=str(rec["outputs"]), flag=rec["flag"],
                **{s: rec[s] for s in STAGES})
    if tbl.name in database:
        database[tbl.name].rows = tbl.rows
    else:
        database.add_table(tbl)
    findings = _findings(result)
    record(database, findings)
    database.save(config.database_dir())
    return database, findings


def project(database, out_dir: str | None = None) -> dict:
    """Project the coverage trace -> `io_project_coverage_report.{csv,txt}` (documentation, NOT a
    BuilderData surface). A pure projection (`findings: []`). Returns {'csv','txt','stats','findings'}."""
    result = trace(database)
    out_dir = out_dir or config.coverage_dir()
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, config.COVERAGE_REPORT_STEM)
    header, rows = render_csv(result)
    csv_path = base + ".csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    txt_path = base + ".txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(render_txt(result))
    return {"csv": csv_path, "txt": txt_path, "stats": result["stats"], "findings": []}

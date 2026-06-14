"""Outputs: I/O tag tables (one per Script Type) and the DBs some types need.

Tag name = <name part> + FLD, where FLD = FUNCTIONAL UNIT + LOCATION + DEVICE
and <name part> is the signal type's description (signal_types.csv), except for
PA/PW/A/W where it is "Description language 1 part 1 + part 2" (cols K + L).
Comment   = [<Script Type> <Index>] <descL1 p1><descL1 p2> [<drawing> <sheet>]
Each Script Type goes to its own tag table (file). Types whose db_kind is set
also get a DB / safe DB whose members keep the same names as the tags.
"""
from __future__ import annotations
import os

# types whose tag name uses the row description instead of the type description
DESC_NAME_TYPES = {"PA", "PW", "A", "W"}
NAME_SEP = " "  # between the name part and the FLD  (see README / confirm)


def fld(row) -> str:
    """The FUNCTIONAL UNIT + LOCATION + DEVICE concatenation, as written."""
    return (str(row.get("functional_unit") or "").strip()
            + str(row.get("location") or "").strip()
            + str(row.get("device") or "").strip())


def _descr(row) -> str:
    """Description language 1 part 1 + part 2 (cols K + L), joined with a space."""
    p1 = str(row.get("desc_l1") or "").strip()
    p2 = str(row.get("desc_l1b") or "").strip()
    return " ".join(p for p in (p1, p2) if p)


def _is_io_signal(row) -> bool:
    """A taggable I/O point: resolved non-interface type with an I/Q bit address."""
    t = row.get("_type")
    if not t or t["category"] == "Interface":
        return False
    bit = str(row.get("bit") or "").strip().upper()
    return bit[:1] in ("I", "Q")


def tag_name(row) -> str:
    t = row["_type"]
    script = str(row.get("script_type") or "").strip().upper()
    name_part = _descr(row).strip() if script in DESC_NAME_TYPES else t["description"]
    return f"{name_part}{NAME_SEP}{fld(row)}".strip()


def tag_comment(row) -> str:
    script = str(row.get("script_type") or "").strip()
    index = str(row.get("index") or "").strip()
    drawing = str(row.get("drawing") or "").strip()
    sheet = str(row.get("sheet") or "").strip()
    return f"[{script} {index}] {_descr(row)} [{drawing} {sheet}]"


def build_io_tags(io_rows: list) -> dict:
    """Script Type -> list of tag dicts (name, data_type, address, comment, fld)."""
    tables: dict[str, list] = {}
    for row in io_rows:
        if not _is_io_signal(row):
            continue
        script = str(row.get("script_type") or "").strip()
        tables.setdefault(script, []).append({
            "name": tag_name(row),
            "data_type": "Bool",
            "address": str(row.get("bit") or "").strip(),
            "comment": tag_comment(row),
            "fld": fld(row),
            "source_row": row.get("_source_row"),
        })
    return tables


def _safe(name: str) -> str:
    bad = '\\/:*?"<>[]|'
    return "".join("_" if ch in bad else ch for ch in name).strip()


def write_io_tags(tables: dict, out_dir: str) -> int:
    """One ';'-CSV per type: Name;Data Type;Logical Address;Comment."""
    tag_dir = os.path.join(out_dir, "IoTags")
    os.makedirs(tag_dir, exist_ok=True)
    total = 0
    for script, tags in sorted(tables.items()):
        path = os.path.join(tag_dir, _safe(script) + ".csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write("Name;Data Type;Logical Address;Comment\n")
            for t in tags:
                f.write(f"{t['name']};{t['data_type']};{t['address']};{t['comment']}\n")
        total += len(tags)
    return total


def _descr2(row) -> str:
    """Description language 2 part 1 + part 2 (cols M + N), joined with a space."""
    p1 = str(row.get("desc_l2") or "").strip()
    p2 = str(row.get("desc_l2b") or "").strip()
    return " ".join(p for p in (p1, p2) if p)


# Diagnosis List_IO layout (mirrors the SWP_04 ">List_IO" sheet); each column is
# (header, value-from-staged-row).
DIAG_COLUMNS = [
    ("Diag Cabinet", lambda r: r.get("diag_cabinet", "")),
    ("Diag Bit", lambda r: r.get("diag_bit", "")),
    ("DevType", lambda r: r.get("script_type", "")),
    ("Index", lambda r: r.get("index", "")),
    ("Type", lambda r: r.get("type_hw", "")),
    ("Address", lambda r: r.get("bit", "")),
    ("ID", lambda r: r.get("id_node", "")),
    ("Desc L1", _descr),
    ("Desc L2", _descr2),
    ("Functional unit", lambda r: r.get("functional_unit", "")),
    ("Location", lambda r: r.get("location", "")),
    ("Device", lambda r: r.get("device", "")),
    ("Drawing name", lambda r: r.get("drawing", "")),
    ("Sheet", lambda r: r.get("sheet", "")),
    ("IP", lambda r: r.get("profinet_ip", "")),
    ("PnName", lambda r: r.get("profinet_name", "")),
    ("TsRef", lambda r: r.get("ts_ref", "")),
]


def build_diagnosis_list_io(io_rows: list) -> list:
    """The diagnosis-relevant rows (types flagged in_diagnosis) in the List_IO
    column order. Includes rows without a bit address (e.g. PA fieldbus alarms)."""
    out = []
    for r in io_rows:
        t = r.get("_type")
        if not t or not t.get("in_diagnosis"):
            continue
        out.append({name: fn(r) for name, fn in DIAG_COLUMNS})
    return out


def write_diagnosis_list_io(rows: list, out_dir: str) -> int:
    diag_dir = os.path.join(out_dir, "Diagnosis")
    os.makedirs(diag_dir, exist_ok=True)
    headers = [c[0] for c in DIAG_COLUMNS]
    with open(os.path.join(diag_dir, "List_IO.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write(";".join(headers) + "\n")
        for r in rows:
            f.write(";".join(str(r[h]) for h in headers) + "\n")
    return len(rows)


def build_dbs(tables: dict, signal_types: dict) -> dict:
    """For Script Types whose db_kind is set, a DB whose members reuse the tag
    names. Returns dbname -> {kind, members}."""
    dbs: dict[str, dict] = {}
    for script, tags in tables.items():
        rec = signal_types.get(script.upper())
        kind = rec["db_kind"] if rec else ""
        if kind not in ("db", "safe_db"):
            continue
        prefix = "FDB" if kind == "safe_db" else "DB"
        dbs[f"{prefix}_{_safe(script)}"] = {
            "kind": kind,
            "members": [t["name"] for t in tags],
        }
    return dbs


def write_dbs(dbs: dict, out_dir: str) -> int:
    if not dbs:
        return 0
    db_dir = os.path.join(out_dir, "DBs")
    os.makedirs(db_dir, exist_ok=True)
    for dbname, db in dbs.items():
        safety = ' { S7_Optimized_Access := "TRUE" }' if db["kind"] == "safe_db" else ""
        lines = [f'DATA_BLOCK "{dbname}"{safety}', "VERSION : 0.1", "   STRUCT"]
        for m in db["members"]:
            lines.append(f'      "{m}" : Bool;')
        lines += ["   END_STRUCT;", "BEGIN", "END_DATA_BLOCK"]
        with open(os.path.join(db_dir, dbname + ".db"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return len(dbs)

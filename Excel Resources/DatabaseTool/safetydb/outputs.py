"""Outputs: the PLC tag table (one TIA-style xlsx) and the DBs some types need.

Tag name = <name part> + FLD, where FLD = FUNCTIONAL UNIT + LOCATION + DEVICE
and <name part> is the signal type's description (signal_types.csv), except for
PA/PW/A/W where it is "Description language 1 part 1 + part 2" (cols K + L).
Comment   = [<Script Type> <Index>] <descL1 p1> <descL1 p2> [<drawing> <sheet>]

I/O tags -> a single TIA "PLC Tags" workbook (Output/IoTags/PLCTags.xlsx); each tag's
Path is its signal type's `tagtable_name` (types may share a table). Logical addresses
are %-prefixed (%I20.0). DBs: a type with db_kind set feeds every name in its
`db_names` (| separated); every DB always starts with ALWAYS_FALSE + ALWAYS_TRUE; each
member carries the tag comment and its name gets the type's `add_to_name` appended
(with {canonical} tokens resolved from the source row).
"""
from __future__ import annotations
import csv
import glob
import os
import re

import openpyxl


def _clear(directory: str, *patterns: str) -> None:
    """Remove previously-generated files (by glob) so a re-run leaves only the
    current artifacts - DB/tag membership changes when the config changes."""
    for pat in patterns:
        for p in glob.glob(os.path.join(directory, pat)):
            try:
                os.remove(p)
            except OSError:
                pass

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


_TOKEN = re.compile(r"\{([A-Za-z0-9_]+)\}")


def _resolve_tokens(text: str, row) -> str:
    """Replace {canonical} tokens with that column's value from the staged row."""
    return _TOKEN.sub(lambda m: str(row.get(m.group(1), "") or ""), text or "")


def _logical_address(bit) -> str:
    """TIA logical address: %-prefixed (I20.0 -> %I20.0)."""
    bit = str(bit or "").strip()
    return ("%" + bit) if bit[:1].upper() in ("I", "Q") else bit


def _tagtable(row) -> str:
    """PLC tag-table (Path) for a row: its type's tagtable_name, else the type id."""
    t = row.get("_type") or {}
    return (t.get("tagtable_name") or "").strip() or str(row.get("script_type") or "").strip()


def build_io_tags(io_rows: list) -> dict:
    """tag-table name (Path) -> list of tag dicts (name, path, data_type, address,
    comment, fld). Types sharing a tagtable_name land in the same table."""
    tables: dict[str, list] = {}
    for row in io_rows:
        if not _is_io_signal(row):
            continue
        path = _tagtable(row)
        tables.setdefault(path, []).append({
            "name": tag_name(row),
            "path": path,
            "data_type": "Bool",
            "address": _logical_address(row.get("bit")),
            "comment": tag_comment(row),
            "fld": fld(row),
            "source_row": row.get("_source_row"),
        })
    return tables


def _safe(name: str) -> str:
    bad = '\\/:*?"<>[]|'
    return "".join("_" if ch in bad else ch for ch in name).strip()


# TIA "PLC Tags" export columns - every value written as text, like a real export.
TAG_COLUMNS = ["Name", "Path", "Data Type", "Logical Address", "Comment",
               "Hmi Visible", "Hmi Accessible", "Hmi Writeable", "Typeobject ID", "Version ID"]


def write_io_tags(tables: dict, out_dir: str) -> int:
    """Single TIA PLC-tags workbook Output/IoTags/PLCTags.xlsx: a 'PLC Tags' sheet
    (one row per tag, Path = tag-table name) + a 'TagTable Properties' sheet listing
    the distinct tables. Values are text, matching a real TIA export."""
    tag_dir = os.path.join(out_dir, "IoTags")
    os.makedirs(tag_dir, exist_ok=True)
    _clear(tag_dir, "*.csv", "PLCTags.xlsx")  # drop legacy per-type CSVs + last run
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PLC Tags"
    ws.append(TAG_COLUMNS)
    total = 0
    for path in sorted(tables):
        for t in tables[path]:
            ws.append([t["name"], path, t["data_type"], t["address"], t["comment"],
                       "True", "True", "True", "", ""])
            total += 1
    props = wb.create_sheet("TagTable Properties")
    props.append(["Path", "BelongsToUnit", "Accessibility"])
    for path in sorted(tables):
        props.append([path, "", ""])
    wb.save(os.path.join(tag_dir, "PLCTags.xlsx"))
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
        w = csv.writer(f, lineterminator="\n")
        w.writerow(headers)
        for r in rows:
            w.writerow([str(r[h]) for h in headers])
    return len(rows)


# every DB always opens with these two constant booleans
DB_CONSTANTS = ["ALWAYS_FALSE", "ALWAYS_TRUE"]


def _db_member_name(row, rec) -> str:
    """Tag name with the type's add_to_name appended ({canonical} tokens resolved)."""
    base = tag_name(row)
    add = _resolve_tokens(rec.get("add_to_name", ""), row).strip()
    return f"{base} {add}".strip() if add else base


def build_dbs(io_rows: list, signal_types: dict) -> dict:
    """Groups members into DBs by the type's db_names (| separated -> several
    identical DBs; types may also share a name, e.g. E1/2 + B1/2 -> 01_Pushbutton).
    Members are ALL rows of a flagged type (so address-less PA alarms still get a
    DB). Every DB opens with ALWAYS_FALSE + ALWAYS_TRUE; each member keeps the tag
    comment and gets the type's add_to_name suffix. A DB is fail-safe if any
    contributing type is safe_db. Returns name -> {kind, members:[{name, comment}]}."""
    dbs: dict[str, dict] = {}

    def ensure(name: str, kind: str) -> dict:
        if name not in dbs:
            dbs[name] = {"kind": kind, "members": [{"name": c, "comment": ""} for c in DB_CONSTANTS]}
        return dbs[name]

    for row in io_rows:
        t = row.get("_type")
        if not t or t["category"] == "Interface":
            continue
        script = str(row.get("script_type") or "").strip()
        rec = signal_types.get(script.upper())
        if not rec:
            continue
        kind = rec.get("db_kind", "")
        if kind not in ("db", "safe_db"):
            continue
        names = rec.get("db_names") or []
        if isinstance(names, str):  # tolerate a raw '|' string
            names = [n.strip() for n in names.split("|") if n.strip()]
        if not names:
            names = [_safe(script)]
        member = {"name": _db_member_name(row, rec), "comment": tag_comment(row)}
        if not member["name"]:
            continue
        for name in names:
            g = ensure(name, kind)
            if kind == "safe_db":
                g["kind"] = "safe_db"  # safety wins for a shared DB
            g["members"].append(member)
    return dbs


def write_dbs(dbs: dict, out_dir: str) -> int:
    if not dbs:
        return 0
    db_dir = os.path.join(out_dir, "DBs")
    os.makedirs(db_dir, exist_ok=True)
    _clear(db_dir, "*.db")  # remove DBs from a previous (differently-named) run
    for dbname, db in dbs.items():
        safety = ' { S7_Optimized_Access := "TRUE" }' if db["kind"] == "safe_db" else ""
        lines = [f'DATA_BLOCK "{dbname}"{safety}', "VERSION : 0.1", "   STRUCT"]
        for m in db["members"]:
            comment = f' //{m["comment"]}' if m.get("comment") else ""
            lines.append(f'      "{m["name"]}" : Bool;{comment}')
        lines += ["   END_STRUCT;", "BEGIN", "END_DATA_BLOCK"]
        with open(os.path.join(db_dir, _safe(dbname) + ".db"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return len(dbs)

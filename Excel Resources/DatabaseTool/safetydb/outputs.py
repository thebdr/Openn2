"""Outputs: the PLC tag table (one TIA-style xlsx) and the DBs some types need.

Names + comments come from per-type `{canonical}`-interpolation TEMPLATES in
signal_types.csv (resolved per row by `_interp`): `tag_name` (the I/O tag name; '' = the
type isn't tagged on its own, e.g. a channel-2 type), `db_element` (the DB member name),
`io_comment` (the tag + member comment), `diag_desc` (the diagnosis description).

I/O tags -> a single TIA "PLC Tags" workbook (Output/IoTags/PLCTags.xlsx); each tag's
Path is its signal type's `tagtable_name` (types may share a table). Logical addresses
are %-prefixed (%I20.0). DBs: a type with db_kind set feeds every name in its
`db_names` (| separated); every DB always starts with ALWAYS_FALSE + ALWAYS_TRUE; each
member name = the `db_element` template, carrying the `io_comment`.
"""
from __future__ import annotations
import csv
import glob
import os
import re

import openpyxl

from . import config


def _clear(directory: str, *patterns: str) -> None:
    """Remove previously-generated files (by glob) so a re-run leaves only the
    current artifacts - DB/tag membership changes when the config changes."""
    for pat in patterns:
        for p in glob.glob(os.path.join(directory, pat)):
            try:
                os.remove(p)
            except OSError:
                pass

def fld(row) -> str:
    """The FUNCTIONAL UNIT + LOCATION + DEVICE concatenation, as written."""
    return (str(row.get("functional_unit") or "").strip()
            + str(row.get("location") or "").strip()
            + str(row.get("device") or "").strip())


_TOKEN = re.compile(r"\{([A-Za-z0-9_]+)\}")


def _resolve_tokens(text: str, row) -> str:
    """Replace {canonical} tokens with that column's value from the staged row."""
    return _TOKEN.sub(lambda m: str(row.get(m.group(1), "") or ""), text or "")


def _interp(template: str, row) -> str:
    """Resolve a signal-type `{canonical}` template against the row; trim the outer
    whitespace (templates carry intentional inner spacing)."""
    return _resolve_tokens(template, row).strip()


def _tpl(row, key: str) -> str:
    return (row.get("_type") or {}).get(key, "")


def _is_io_signal(row) -> bool:
    """A taggable I/O point: resolved non-interface type with an I/Q bit address."""
    t = row.get("_type")
    if not t or t["category"] == "Interface":
        return False
    bit = str(row.get("bit") or "").strip().upper()
    return bit[:1] in ("I", "Q")


def tag_name(row) -> str:
    """The PLC I/O tag name from the type's `tag_name` template ('' when the type isn't
    tagged on its own, e.g. a channel-2 type sharing its sibling's device tag)."""
    return _interp(_tpl(row, "tag_name"), row)


def tag_comment(row) -> str:
    """The I/O tag + DB-member comment from the type's `io_comment` template."""
    return _interp(_tpl(row, "io_comment"), row)


def diag_desc(row) -> str:
    """The diagnosis alarm/warning description from the type's `diag_desc` template."""
    return _interp(_tpl(row, "diag_desc"), row)


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
        name = tag_name(row)
        if not name:                       # untagged type (empty tag_name, e.g. channel-2)
            continue
        path = _tagtable(row)
        tables.setdefault(path, []).append({
            "name": name,
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


# The >List_IO / >List_Logic column layout is config-driven (config/diagnosis_columns.csv);
# each column is (header, interpolation expression over the CentralDatabase row). The one
# hardcoded column is PLC_Binding (the IN_xx reference), via this sentinel:
PLC_BINDING_SENTINEL = "$PLC_Binding$"


def plc_binding(row) -> str:
    """The IN_xx PLC reference for a diagnosis row: '"<leftmost db_name>"."<name_in_db>"'
    when DB-backed, else '"<name_in_tagtable>"', else the bit address."""
    nid = (row.get("name_in_db") or "").strip()
    if nid:
        dbs = (row.get("_type") or {}).get("db_names") or []
        return f'"{dbs[0]}"."{nid}"' if dbs else f'"{nid}"'
    tag = (row.get("name_in_tagtable") or "").strip()
    if tag:
        return f'"{tag}"'
    return (row.get("bit") or "").strip()


def ml_value(row) -> str:
    """ML_xx (Mirror Logic): the type's diagnosis_logic mirror->TRUE / invert->FALSE;
    blank -> from normal_condition (set -> FALSE/invert, empty -> TRUE/mirror)."""
    logic = ((row.get("_type") or {}).get("diagnosis_logic") or "").strip().lower()
    if logic == "mirror":
        return "TRUE"
    if logic == "invert":
        return "FALSE"
    nc = str(row.get("normal_condition") or "").strip().lower()
    return "FALSE" if nc and nc not in ("0", "0.0", "false", "no") else "TRUE"


def _diag_cell(expr: str, row) -> str:
    if expr.strip() == PLC_BINDING_SENTINEL:
        return plc_binding(row)
    return _resolve_tokens(expr, row).strip()


def build_diagnosis_list_io(io_rows: list) -> list:
    """The diagnosis-relevant rows (types flagged in_diagnosis) as dicts keyed by the
    config/diagnosis_columns.csv headers (each cell interpolated from the CentralDatabase
    row; the `$PLC_Binding$` column via plc_binding). Address-less rows (e.g. PA) included."""
    cols = config.load_diagnosis_columns()
    out = []
    for r in io_rows:
        t = r.get("_type")
        if not t or not t.get("in_diagnosis"):
            continue
        out.append({h: _diag_cell(expr, r) for h, expr in cols})
    return out


def write_diagnosis_list_io(rows: list, out_dir: str, filename: str = "List_IO.csv") -> int:
    diag_dir = os.path.join(out_dir, "Diagnosis")
    os.makedirs(diag_dir, exist_ok=True)
    headers = [h for h, _ in config.load_diagnosis_columns()]
    with open(os.path.join(diag_dir, filename), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(headers)
        for r in rows:
            w.writerow([str(r.get(h, "")) for h in headers])
    return len(rows)


# every DB always opens with these two constant booleans
DB_CONSTANTS = ["ALWAYS_FALSE", "ALWAYS_TRUE"]


def member_name(row) -> str:
    """The name this row gets as a member of its DB in the generated .db files (the type's
    `db_element` template, interpolated), or '' if its type is not DB-backed. Same value
    build_dbs writes - used to enrich the CentralDatabase with `name_in_db`."""
    t = row.get("_type") or {}
    if t.get("db_kind") not in ("db", "safe_db"):
        return ""
    return _interp(t.get("db_element", ""), row)


def build_dbs(io_rows: list, signal_types: dict) -> dict:
    """Groups members into DBs by the type's db_names (| separated -> several
    identical DBs; types may also share a name, e.g. E1/2 + B1/2 -> 01_Pushbutton).
    Members are ALL rows of a flagged type (so address-less PA alarms still get a
    DB). Every DB opens with ALWAYS_FALSE + ALWAYS_TRUE; each member name is the type's
    `db_element` template and carries the `io_comment`. A DB is fail-safe if any
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
        member = {"name": member_name(row), "comment": tag_comment(row)}
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

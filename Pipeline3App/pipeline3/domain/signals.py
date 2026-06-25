"""Signals Mapping (phase 500): the PLC tag table (510) and the data blocks (520).

510 Generate I/O Tags -> a single TIA "PLC Tags" workbook (io_tags_dir/PLCTags.xlsx). Its rows are
TWO sources, both as plain text like a real TIA export:
  - the resolved I/O signals of the staged database - reusing the staged identity columns
    `name_in_tagtable` (tag name) + `tagtable` (the Path the tag lands in); the logical address is
    the row's I/Q bit, %-prefixed (I20.0 -> %I20.0);
  - the interface tags read from the IF_ sheets phase 400 inserted into the I/O List - per the
    interface columns `Signal Name Side 1` (tag name) and `I/O Address Side 1` (the resolved logical
    address, read from the formula's cached value via data_only). Each IF_ sheet is its own tag table
    (Path = the sheet name). Interface tags need phase 400 to have run with insert_interface_sheets;
    absent IF_ sheets simply yield no interface tags.

520 Generate Data Blocks -> blocks_import_dir: members from two sources (each row's staged
name_in_db into its datablocks; plus datablock_elements_rules additions), seeded with Always
FALSE/TRUE + a No Operation no-op (the builder pad). EVERY DB is written as a TIA Openness
SW.Blocks.GlobalDB XML (<name>.xml); the ONLY difference between a normal and a fail-safe DB is
<ProgrammingLanguage> = the type's db_kind VERBATIM ('DB' or 'F_DB', `|`-aligned with db_names by
position), with DBAccessibleFromOPCUA following it (false for F_DB - a fail-safe DB must not be
OPC-writable - else true).

Clean-room rebuild of Pipeline2's outputs.write_io_tags / build_io_tags (reference for INTENT only);
the interface-tag source + the F_DB XML are new in Pipeline3.
"""
from __future__ import annotations
import glob
import os

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter, range_boundaries

from pipeline3.core import config
from pipeline3.domain import identity

IF_PREFIX = "IF_"                       # the phase-400 inserted interface sheets (CLAUDE.md Phase 400)
TAG_TABLE_FILE = "PLCTags.xlsx"

# Interface signals-table columns the tag reader binds (by header name).
_H_NAME = "Signal Name Side 1"
_H_ADDR = "I/O Address Side 1"
_H_DTYPE = "Data Type"
_H_DESC = "Description"

# TIA "PLC Tags" export columns - every value written as text, like a real export.
TAG_COLUMNS = ["Name", "Path", "Data Type", "Logical Address", "Comment",
               "Hmi Visible", "Hmi Accessible", "Hmi Writeable", "Typeobject ID", "Version ID"]

# BOOL/WORD/... -> the TIA spelling; unknown types fall back to a capitalized form.
_TIA_DTYPE = {"bool": "Bool", "word": "Word", "dword": "DWord", "byte": "Byte",
              "int": "Int", "dint": "DInt", "real": "Real", "char": "Char"}


def _tia_dtype(raw) -> str:
    s = str(raw or "").strip()
    if not s:
        return "Bool"
    return _TIA_DTYPE.get(s.lower(), s.capitalize())


# --------------------------------------------------------------------------------------------- #
# (510a) the resolved I/O signals -> tags, from the staged identity columns
# --------------------------------------------------------------------------------------------- #

def build_io_tags(rows) -> list:
    """One tag per taggable I/O signal of the staged database. A row is taggable exactly when staging
    set a non-empty `name_in_tagtable` (i.e. is_io_signal AND a non-empty tag_name); its Path is the
    staged `tagtable`, its address the I/Q bit %-prefixed, its comment the type's io_comment."""
    tags = []
    for row in rows or []:
        name = str(row.get("name_in_tagtable") or "").strip()
        if not name:
            continue
        tags.append({
            "name": name,
            "path": str(row.get("tagtable") or "").strip() or str(row.get("script_type") or "").strip(),
            "data_type": "Bool",
            "address": identity.logical_address(row.get("bit")),
            "comment": identity.tag_comment(row),
            "source": "io",
        })
    return tags


# --------------------------------------------------------------------------------------------- #
# (510b) the interface tags, from the IF_ sheets phase 400 inserted into the I/O List
# --------------------------------------------------------------------------------------------- #

def _find_signals_table(ws):
    """The interface signals table on `ws` (the one whose header row carries both the Signal Name and
    I/O Address Side-1 columns), as (c1, r1, c2, r2, {header: col}). None if absent."""
    for name in list(ws.tables):
        c1, r1, c2, r2 = range_boundaries(ws.tables[name].ref)
        hdr = {str(ws.cell(r1, c).value).strip(): c
               for c in range(c1, c2 + 1) if ws.cell(r1, c).value not in (None, "")}
        if _H_NAME in hdr and _H_ADDR in hdr:
            return c1, r1, c2, r2, hdr
    return None


def interface_tags(iolist_path) -> tuple[list, list]:
    """One tag per named interface signal across every IF_ sheet of the I/O List. Returns (tags,
    warnings). data_only reads the cached value of the I/O Address Side 1 formula (Excel-resolved to
    e.g. 'Q10000.0'); the tag name is Signal Name Side 1, the Path the IF_ sheet name. A named row
    whose address didn't resolve is skipped with a warning. No IF_ sheets -> ([], [])."""
    tags, warnings = [], []
    if not iolist_path or not os.path.exists(iolist_path):
        return tags, warnings
    # tables are not exposed in read_only mode; data_only gives the cached formula values.
    wb = load_workbook(iolist_path, data_only=True)
    try:
        for sh in wb.sheetnames:
            if not sh.startswith(IF_PREFIX):
                continue
            ws = wb[sh]
            found = _find_signals_table(ws)
            if not found:
                warnings.append(f"{sh}: no interface signals table found - skipped")
                continue
            _c1, r1, _c2, r2, hdr = found
            nc, ac = hdr[_H_NAME], hdr[_H_ADDR]
            dc, dsc = hdr.get(_H_DTYPE), hdr.get(_H_DESC)
            for r in range(r1 + 1, r2 + 1):
                name = str(ws.cell(r, nc).value or "").strip()
                if not name:                              # blank/padding/separator row
                    continue
                addr = str(ws.cell(r, ac).value or "").strip()
                if not addr:
                    warnings.append(f"{sh}!{get_column_letter(ac)}{r}: '{name}' has no resolved "
                                    f"{_H_ADDR} - skipped")
                    continue
                tags.append({
                    "name": name,
                    "path": sh,
                    "data_type": _tia_dtype(ws.cell(r, dc).value if dc else ""),
                    "address": identity.logical_address(addr),
                    "comment": str(ws.cell(r, dsc).value or "").strip() if dsc else "",
                    "source": "interface",
                })
    finally:
        wb.close()
    return tags, warnings


# --------------------------------------------------------------------------------------------- #
# write the single PLC Tags workbook
# --------------------------------------------------------------------------------------------- #

def _clear(directory, *patterns, keep=()) -> None:
    """Drop previously-generated artifacts so a re-run leaves only the current ones (tag membership
    changes with the config / the inserted interfaces). `keep` basenames are preserved (e.g. the
    phase-800-owned 02_COM.xml in the shared blocks_import_dir)."""
    keep = {k.lower() for k in keep}
    for pat in patterns:
        for p in glob.glob(os.path.join(directory, pat)):
            if os.path.basename(p).lower() in keep:
                continue
            try:
                os.remove(p)
            except OSError:
                pass


def _append_text_row(ws, values) -> None:
    """append a row, forcing data_type='s' on any cell starting with =/+/- so a tag/address string is
    never read back as a formula (the I/O-List gotcha)."""
    ws.append(values)
    r = ws.max_row
    for c, v in enumerate(values, start=1):
        if isinstance(v, str) and v[:1] in ("=", "+", "-"):
            ws.cell(r, c).data_type = "s"


def group_tables(tags) -> dict:
    """Group tags by Path (tag-table name), preserving insertion order within each table."""
    tables: dict = {}
    for t in tags:
        tables.setdefault(t["path"], []).append(t)
    return tables


def write_plc_tags(tables, out_root) -> tuple[str, int]:
    """Write the single TIA PLC-tags workbook io_tags_dir/PLCTags.xlsx: a 'PLC Tags' sheet (one row
    per tag, Path = its tag-table) + a 'TagTable Properties' sheet of the distinct tables. Values are
    text. Returns (path, tag count). The io_tags_dir is swept of prior *.csv / PLCTags.xlsx first."""
    tag_dir = config.out_path(out_root, "io_tags_dir")
    os.makedirs(tag_dir, exist_ok=True)
    _clear(tag_dir, "*.csv", TAG_TABLE_FILE)
    wb = Workbook()
    ws = wb.active
    ws.title = "PLC Tags"
    ws.append(TAG_COLUMNS)
    total = 0
    for path in sorted(tables):
        for t in tables[path]:
            _append_text_row(ws, [t["name"], path, t["data_type"], t["address"], t["comment"],
                                  "True", "True", "True", "", ""])
            total += 1
    props = wb.create_sheet("TagTable Properties")
    props.append(["Path", "BelongsToUnit", "Accessibility"])
    for path in sorted(tables):
        _append_text_row(props, [path, "", ""])
    out = os.path.join(tag_dir, TAG_TABLE_FILE)
    wb.save(out)
    wb.close()
    return out, total


def generate_io_tags(rows, out_root, *, iolist_path=None) -> dict:
    """510 entry: build the I/O-signal tags + the interface tags, write the single PLCTags.xlsx.
    Returns {'path', 'total', 'io_count', 'iface_count', 'tables' (sorted names), 'warnings'}."""
    io_tags = build_io_tags(rows)
    iface_tags, warnings = interface_tags(iolist_path)
    tables = group_tables(io_tags + iface_tags)
    path, total = write_plc_tags(tables, out_root)
    return {"path": path, "total": total, "io_count": len(io_tags), "iface_count": len(iface_tags),
            "tables": sorted(tables), "warnings": warnings}


# ============================================================================================== #
# 520 Generate Data Blocks -> blocks_import_dir/*.xml (every DB a GlobalDB; F_DB vs DB = ProgrammingLanguage)
# ============================================================================================== #

# Every DB opens with these seed booleans (TIA spelling, with a space - no underscore). "No Operation"
# is the dedicated no-op member builders use to PAD a template's unused fixed slots, so an unused slot
# never references "Always TRUE"/"Always FALSE" (whose definite TRUE/FALSE could be misread).
DB_CONSTANTS = ["Always FALSE", "Always TRUE", "No Operation"]
_DB_RULES_FILE = "datablock_elements_rules.csv"

# The 02_COM zone-cumulative custom DB is OWNED by phase 800 (its members are the block builders'
# 02_COM.{db_element} cumulatives, not signal rows), but it lives in blocks_import_dir beside the 520
# DBs - so the 520 sweep below PRESERVES it. See write_zone_cumulative_db (called from the 800 engine).
COM_DB = "02_COM"


def _safe(name) -> str:
    bad = '\\/:*?"<>[]|'
    return "".join("_" if ch in bad else ch for ch in str(name)).strip()


def build_data_blocks(rows, db_rules) -> tuple[dict, list]:
    """Group DB members into named data blocks from TWO sources, returns (dbs, warnings):
      - type-based: each row's staged `name_in_db` is a member of every DB in its staged `datablocks`
        (the type's db_element / db_names; comment = the type io_comment);
      - rule-driven (datablock_elements_rules): each row whose script_type is in a rule's
        `required_types` adds the rule's interpolated `member` to the rule's `db_name`.
    A DB is created on first use and seeded with Always FALSE/TRUE. Each DB carries a `prog_lang` = its
    `db_kind`, the verbatim `<ProgrammingLanguage>` (e.g. 'DB' or 'F_DB' - see write_data_blocks; EVERY
    DB is now a GlobalDB XML, F_DB being the only fail-safe difference). db_kind is `|`-aligned with
    db_names BY POSITION - a single kind applies to every DB, multiple kinds map one-to-one - so one type
    may emit a normal DB and an F_DB (e.g. PA -> PROFINET_NODES_ALARM as `DB` + 00_Commissioning as
    `F_DB`); on a mixed contribution F_DB wins. A DATA_BLOCK cannot carry two members of the same name, so
    duplicates are dropped (kept once) and reported as a warning.
    Returns dbs = {name: {'prog_lang': str, 'members': [{'name', 'comment'}]}}."""
    dbs: dict = {}
    seen: dict = {}                       # name -> set of member names already added
    dup: dict = {}                        # (db, member) -> contribution count (>1 = collapsed)

    def ensure(name):
        if name not in dbs:
            dbs[name] = {"prog_lang": "", "members": [{"name": c, "comment": ""} for c in DB_CONSTANTS]}
            seen[name] = set(DB_CONSTANTS)
        return dbs[name]

    def add(name, member, comment, prog_lang):
        g = ensure(name)
        pl = (prog_lang or "").strip()                # strip to match the emit site (_db_xml) exactly,
        if pl and (pl.upper() == "F_DB" or not g["prog_lang"]):   # so F_DB never loses the race to padding
            g["prog_lang"] = pl                       # F_DB (fail-safe) wins; otherwise first non-empty
        if not member:
            return
        if member in seen[name]:
            dup[(name, member)] = dup.get((name, member), 1) + 1
            return
        seen[name].add(member)
        g["members"].append({"name": member, "comment": comment})

    # (a) type-based membership, from the staged identity columns. Each DB's safety is its OWN db_kind:
    # db_kind is `|`-aligned with db_names by position (a single kind applies to every DB).
    for r in rows or []:
        member = str(r.get("name_in_db") or "").strip()
        if not member:
            continue
        t = r.get("_type") or {}
        comment = identity.tag_comment(r)
        for db in [d.strip() for d in str(r.get("datablocks") or "").split("|") if d.strip()]:
            add(db, member, comment, identity.db_kind_of(t, db))

    # (b) rule-driven additions (any required_type present -> add the element to db_name)
    for r in rows or []:
        st = str(r.get("script_type") or "").strip()
        if not st:
            continue
        t = r.get("_type") or {}
        for rule in db_rules or []:
            if st in rule["required_types"]:
                member = identity.interp(rule["member"], r)
                if member:
                    add(rule["db_name"], member, "", identity.db_kind_of(t, rule["db_name"]))

    warnings = [f"{name}: member {member!r} contributed {count} times - kept 1 "
                f"(a DATA_BLOCK cannot repeat a member name)"
                for (name, member), count in sorted(dup.items())]
    for name, g in sorted(dbs.items()):                  # guardrail: an unrecognized <ProgrammingLanguage>
        pl = (g.get("prog_lang") or "").strip()          # (a db_kind typo) is written verbatim - flag it.
        if pl and pl != "DB" and pl.upper() != "F_DB":   # 'F_DB' is canonicalized on write, so it never warns
            warnings.append(f"{name}: db_kind {pl!r} written verbatim as <ProgrammingLanguage> "
                            f"(expected 'DB' or 'F_DB') - TIA may reject the import")
    return dbs, warnings


# --- every DB: the TIA Openness SW.Blocks.GlobalDB XML (<ProgrammingLanguage> = db_kind verbatim) ---- #
_XML_IFACE_NS = "http://www.siemens.com/automation/Openness/SW/Interface/v5"


def _xml_attr(value) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _xml_text(value) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _db_xml(name, db, number) -> str:
    """ONE DB as a TIA Openness SW.Blocks.GlobalDB export (UTF-8 BOM added on write; CRLF; no trailing
    newline - matching a real export). EVERY DB is emitted this way; the only difference between a normal
    and a fail-safe DB is `<ProgrammingLanguage>` = the type's db_kind VERBATIM (e.g. 'DB' or 'F_DB').
    DBAccessibleFromOPCUA follows: false for F_DB (a fail-safe DB must not be OPC-writable - an unexpected
    write can fault the CPU to STOP), true otherwise. Each member is Bool / NonRetain / Public with the
    system-default external-access attributes. AutoNumber lets TIA assign the real DB number on import
    (the emitted Number is a deterministic placeholder)."""
    prog_lang = (db.get("prog_lang") or "DB").strip()
    if prog_lang.upper() == "F_DB":
        prog_lang = "F_DB"           # canonicalize the fail-safe marker so TIA always recognizes it
    opc = "false" if prog_lang == "F_DB" else "true"
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<Document>',
        '  <Engineering version="V18" />',
        '  <SW.Blocks.GlobalDB ID="0">',
        '    <AttributeList>',
        '      <AutoNumber>true</AutoNumber>',
        f'      <DBAccessibleFromOPCUA>{opc}</DBAccessibleFromOPCUA>',
        '      <DBAccessibleFromWebserver>true</DBAccessibleFromWebserver>',
        '      <HeaderAuthor />',
        '      <HeaderFamily />',
        '      <HeaderName />',
        '      <HeaderVersion>0.1</HeaderVersion>',
        f'      <Interface><Sections xmlns="{_XML_IFACE_NS}">',
        '  <Section Name="Static">',
    ]
    for m in db["members"]:
        lines += [
            f'    <Member Name="{_xml_attr(m["name"])}" Datatype="Bool" Remanence="NonRetain" Accessibility="Public">',
            '      <AttributeList>',
            '        <BooleanAttribute Name="ExternalAccessible" SystemDefined="true">true</BooleanAttribute>',
            '        <BooleanAttribute Name="ExternalVisible" SystemDefined="true">true</BooleanAttribute>',
            '        <BooleanAttribute Name="ExternalWritable" SystemDefined="true">true</BooleanAttribute>',
            '        <BooleanAttribute Name="SetPoint" SystemDefined="true">false</BooleanAttribute>',
            '      </AttributeList>',
            '    </Member>',
        ]
    lines += [
        '  </Section>',
        '</Sections></Interface>',
        '      <MemoryLayout>Optimized</MemoryLayout>',
        f'      <Name>{_xml_text(name)}</Name>',
        '      <Namespace />',
        f'      <Number>{number}</Number>',
        f'      <ProgrammingLanguage>{_xml_text(prog_lang)}</ProgrammingLanguage>',
        '    </AttributeList>',
        '    <ObjectList>',
        '      <MultilingualText ID="1" CompositionName="Comment">',
        '        <ObjectList>',
        '          <MultilingualTextItem ID="2" CompositionName="Items">',
        '            <AttributeList>',
        '              <Culture>en-US</Culture>',
        '              <Text />',
        '            </AttributeList>',
        '          </MultilingualTextItem>',
        '        </ObjectList>',
        '      </MultilingualText>',
        '      <MultilingualText ID="3" CompositionName="Title">',
        '        <ObjectList>',
        '          <MultilingualTextItem ID="4" CompositionName="Items">',
        '            <AttributeList>',
        '              <Culture>en-US</Culture>',
        '              <Text />',
        '            </AttributeList>',
        '          </MultilingualTextItem>',
        '        </ObjectList>',
        '      </MultilingualText>',
        '    </ObjectList>',
        '  </SW.Blocks.GlobalDB>',
        '</Document>',
    ]
    return "\r\n".join(lines)


def write_data_blocks(dbs, out_root) -> tuple[str, int]:
    """Write each data block into blocks_import_dir as a TIA Openness SW.Blocks.GlobalDB XML <name>.xml
    (UTF-8 BOM + CRLF) - normal and fail-safe DBs alike; F_DB vs DB is just <ProgrammingLanguage> (see
    _db_xml). blocks_import_dir is swept of prior *.db / *.xml first (the phase-620 SCL is left untouched;
    a stale *.db from before the unification is removed). DBs are written name-sorted so the placeholder
    DB numbers are stable. Returns (dir, count)."""
    db_dir = config.out_path(out_root, "blocks_import_dir")
    os.makedirs(db_dir, exist_ok=True)
    _clear(db_dir, "*.db", "*.xml", keep={f"{COM_DB}.xml"})   # 02_COM is phase-800-owned, not swept here
    for number, (name, db) in enumerate(sorted(dbs.items()), start=1):
        with open(os.path.join(db_dir, _safe(name) + ".xml"), "w", encoding="utf-8-sig", newline="") as f:
            f.write(_db_xml(name, db, number))
    return db_dir, len(dbs)


def write_safe_db(out_root, name, member_names) -> str:
    """Write ONE custom SAFE DB (F_DB Openness XML) into blocks_import_dir WITHOUT sweeping. The
    DB-format primitive the phase-800 block engine uses to emit its custom DBs (e.g. 02_COM, whose
    members it decides) - the 520 sweep preserves a COM_DB.xml so it survives a standalone re-run.
    `member_names` are de-duplicated, order preserved. Returns the path, or '' when empty."""
    members = [m for m in dict.fromkeys(str(x).strip() for x in member_names) if m]
    if not members:
        return ""
    db = {"prog_lang": "F_DB", "members": [{"name": m, "comment": ""} for m in members]}
    db_dir = config.out_path(out_root, "blocks_import_dir")
    os.makedirs(db_dir, exist_ok=True)
    path = os.path.join(db_dir, _safe(name) + ".xml")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(_db_xml(name, db, 1))
    return path


def _is_fdb(d) -> bool:
    return (d.get("prog_lang") or "").strip().upper() == "F_DB"   # strip: match _db_xml's fail-safe test


def generate_data_blocks(rows, out_root) -> dict:
    """520 entry: build the data blocks (type-based + rule-driven) and write them - EVERY DB as a TIA
    Openness SW.Blocks.GlobalDB XML, F_DB vs DB being just <ProgrammingLanguage>. Returns {'dir', 'count',
    'dbs' (sorted names), 'safe' (the F_DB DBs), 'normal' (the rest), 'members' {name: count}, 'warnings'}."""
    db_rules = config.load_rules(_DB_RULES_FILE)
    dbs, warnings = build_data_blocks(rows, db_rules)
    db_dir, count = write_data_blocks(dbs, out_root)
    return {"dir": db_dir, "count": count, "dbs": sorted(dbs),
            "safe": sorted(n for n, d in dbs.items() if _is_fdb(d)),
            "normal": sorted(n for n, d in dbs.items() if not _is_fdb(d)),
            "members": {n: len(d["members"]) for n, d in dbs.items()}, "warnings": warnings}

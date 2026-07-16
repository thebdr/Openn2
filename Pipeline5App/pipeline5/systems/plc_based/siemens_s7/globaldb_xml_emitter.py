"""Phase 520c - project the `db_blocks` + `db_members` tables to the GlobalDB-XML BuilderData surface.

`project(database)` writes one TIA Openness `SW.Blocks.GlobalDB` `<DB>.xml` per surviving Global DB
(UTF-8 BOM, CRLF, no trailing newline - matching a real export). This is a PURE projection of the two
tables: `db_blocks` gives each DB's attributes, `db_members` (grouped by `db_name`, in row order) gives
its members. Clean-room port of PL3's `signals._db_xml` / `write_data_blocks`.

The bytes are stable to PL3 PER MEMBER + per DB-attribute; the member ORDER differs (PL4's per-type
element rows group members by type vs PL3's interleaved I/O-List order - accepted, functional parity for
Optimized DBs). `<Number>` is a placeholder assigned name-sorted at write time (TIA reassigns on import).
`<DBAccessibleFromOPCUA>` is code-locked false for an F_DB regardless of `db_blocks.opc_ua` (a safety
floor - an OPC write to a fail-safe DB can fault the CPU to STOP).

The projector writes ONLY the DBs in `db_blocks` (520's own SSOT record) - it never blanket-sweeps the
output dir, so a file another phase owns (e.g. the phase-800 `02_COM.xml`) is preserved simply by not being
one of 520's DBs. Ownership is driven by the database, not a hardcoded name list.
"""
from __future__ import annotations

import os

from pipeline5 import config

_XML_IFACE_NS = "http://www.siemens.com/automation/Openness/SW/Interface/v5"


def _xml_attr(value) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _xml_text(value) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def db_xml(name, db, number) -> str:
    """ONE Global DB as the SW.Blocks.GlobalDB XML string (no BOM - the writer adds it). `db` = the
    db_blocks attributes + `members` (db_members rows: member/datatype/retain/start_value/comment/ext_*/
    setpoint). An absent/blank attribute reproduces the historical default EXACTLY (byte parity)."""
    prog_lang = (db.get("prog_lang") or "DB").strip()
    if prog_lang.upper() == "F_DB":
        prog_lang = "F_DB"                                   # canonicalize the fail-safe marker
    opc = "false" if prog_lang == "F_DB" else ("true" if db.get("opc_ua", True) else "false")  # F_DB safety lock
    web = "true" if db.get("webserver", True) else "false"
    layout = (db.get("memory_layout") or "Optimized").strip() or "Optimized"
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<Document>',
        '  <Engineering version="V18" />',
        '  <SW.Blocks.GlobalDB ID="0">',
        '    <AttributeList>',
        '      <AutoNumber>true</AutoNumber>',
        f'      <DBAccessibleFromOPCUA>{opc}</DBAccessibleFromOPCUA>',
        f'      <DBAccessibleFromWebserver>{web}</DBAccessibleFromWebserver>',
        '      <HeaderAuthor />',
        '      <HeaderFamily />',
        '      <HeaderName />',
        '      <HeaderVersion>0.1</HeaderVersion>',
    ]
    if db.get("only_load_memory"):
        lines.append('      <IsOnlyStoredInLoadMemory>true</IsOnlyStoredInLoadMemory>')
    if db.get("retain_reserve"):
        lines.append('      <IsRetainMemResEnabled>true</IsRetainMemResEnabled>')
    if db.get("write_protected"):
        lines.append('      <IsWriteProtectedInAS>true</IsWriteProtectedInAS>')
    lines += [
        f'      <Interface><Sections xmlns="{_XML_IFACE_NS}">',
        '  <Section Name="Static">',
    ]
    for m in db["members"]:
        dtype = _xml_attr(m.get("datatype") or "Bool")
        rem = "Retain" if m.get("retain") else "NonRetain"
        ea = "true" if m.get("ext_accessible", True) else "false"
        ev = "true" if m.get("ext_visible", True) else "false"
        ew = "true" if m.get("ext_writable", True) else "false"
        sp = "true" if m.get("setpoint", False) else "false"
        lines += [
            f'    <Member Name="{_xml_attr(m["member"])}" Datatype="{dtype}" Remanence="{rem}" Accessibility="Public">',
            '      <AttributeList>',
            f'        <BooleanAttribute Name="ExternalAccessible" SystemDefined="true">{ea}</BooleanAttribute>',
            f'        <BooleanAttribute Name="ExternalVisible" SystemDefined="true">{ev}</BooleanAttribute>',
            f'        <BooleanAttribute Name="ExternalWritable" SystemDefined="true">{ew}</BooleanAttribute>',
            f'        <BooleanAttribute Name="SetPoint" SystemDefined="true">{sp}</BooleanAttribute>',
            '      </AttributeList>',
        ]
        if m.get("comment"):
            lines += ['      <Comment>',
                      f'        <MultiLanguageText Lang="en-US">{_xml_text(m["comment"])}</MultiLanguageText>',
                      '      </Comment>']
        if m.get("start_value"):
            lines.append(f'      <StartValue>{_xml_text(m["start_value"])}</StartValue>')
        lines.append('    </Member>')
    lines += [
        '  </Section>',
        '</Sections></Interface>',
        f'      <MemoryLayout>{layout}</MemoryLayout>',
    ]
    if str(db.get("memory_reserve") or "").strip():
        lines.append(f'      <MemoryReserve>{_xml_text(str(db["memory_reserve"]).strip())}</MemoryReserve>')
    lines += [
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


def project(database, output_dir: str | None = None) -> int:
    """Write every `db_blocks` DB as `<output_dir>/<db_name>.xml` (UTF-8 BOM + CRLF), members from
    `db_members` grouped by db_name in row order. Only the DBs `db_blocks` records are (over)written;
    files for DBs another phase owns are left untouched (no hardcoded keep-list - the table is the
    ownership record). DBs are name-sorted so the placeholder `<Number>` is stable. Defaults to the
    BuilderData ImportReady surface. Returns the count written."""
    output_dir = output_dir or config.blocks_import_dir()
    blocks = {r["db_name"]: r for r in database["db_blocks"]}
    members_by_db: dict = {}
    for m in database["db_members"]:
        members_by_db.setdefault(m["db_name"], []).append(m)

    os.makedirs(output_dir, exist_ok=True)
    count = 0
    for number, db_name in enumerate(sorted(blocks), start=1):
        attrs = blocks[db_name]
        db = {key: attrs.get(key) for key in
              ("prog_lang", "memory_layout", "opc_ua", "webserver", "only_load_memory",
               "write_protected", "retain_reserve", "memory_reserve")}
        db["members"] = members_by_db.get(db_name, [])
        with open(os.path.join(output_dir, f"{db_name}.xml"), "w", encoding="utf-8-sig", newline="") as handle:
            handle.write(db_xml(db_name, db, number))
        count += 1
    return count

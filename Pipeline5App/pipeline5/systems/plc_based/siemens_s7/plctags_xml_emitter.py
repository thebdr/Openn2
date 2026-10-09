"""Phase 510b - one TIA Openness tag-table XML per PLC tag table (contract v1 `sw/tag-table`; §9.1 decided
2026-10-09, option 1: PL5 emits the XML, the workbook stays the manual aid).

Chapter: how the collected I/O tags reach TIA through OP5. The workbook (`PLCTags.xlsx`, phase 510a) is a
`doc/plc-tags-workbook` - OP5 lists it and never imports it (the TIA GUI does). This emitter writes the SAME
tags as `<PLC>/PLC tags/<Table>.xml`, one `SW.Tags.PlcTagTable` per tag table, which OP5 imports through
`TagTableGroup.TagTables.Import` (Override). The shape mirrors a real TIA V18 export
(`Openn5App/TiaProjects/Openn2_Playground_VCI/<PLC>/PLC tags/*.xml`): `<Document>` -> `<Engineering
version="V18" />` -> `<SW.Tags.PlcTagTable ID="0">` with the table's `<Name>` and an `<ObjectList>` of
`<SW.Tags.PlcTag ID=".." CompositionName="Tags">`, each with `DataTypeName`, the three External* flags
(the workbook's Hmi columns), `LogicalAddress` (the %-prefixed address, as in the workbook) and `Name`,
plus the comment as `MultilingualText`/`MultilingualTextItem` (en-US) when there is one. IDs are unique
per document and written in hex, as TIA writes them. UTF-8 BOM + CRLF + no trailing newline, like every
XML surface; the contract-v1 `#!openn` header is the first comment after the declaration (`name` = the
exact table name - `--` in it becomes `- -`, the XML-comment rule).

The file name is the table name made file-safe the way OP5's export does it (`Path.GetInvalidFileNameChars`
-> `_`); two tables colliding on one file name is a pointed error, never a silent overwrite. Every table of
the workbook's "TagTable Properties" sheet gets a file, the tags in the workbook's order.

Place in the flow: phase 510 (run_data_blocks only=510 in src://pipeline5/systems/plc_based/siemens_s7/
safety/main.py) - the workbook writer (src://pipeline5/systems/plc_based/siemens_s7/plctags_xlsx_writer.py)
calls `write_tag_tables` right after the workbook, from the same collected tags
(src://pipeline5/phases/io_tags/collector.py) and under the same duplicate-tag gate (a duplicate = no
workbook AND no XML). Writes BuilderData/<PLC>/PLC tags/<Table>.xml (`plc_tags_dir` of
src://pipeline5/systems/plc_based/siemens_s7/output_layout.py; the header from
src://pipeline5/systems/plc_based/siemens_s7/openn_header.py).
"""
from __future__ import annotations

import os

from pipeline5.phases.io_tags.collector import HMI_DEFAULTS
from pipeline5.systems.plc_based.siemens_s7 import openn_header as header

PHASE = 510
ENGINEERING_VERSION = "V18"
# Path.GetInvalidFileNameChars() on Windows: the nine punctuation characters + the control range.
_INVALID_FILE_CHARS = frozenset('"<>|:*?\\/') | frozenset(chr(c) for c in range(32))


def safe_file_name(table: str) -> str:
    """The table name made file-safe the way OP5's export does it (every invalid file-name character -> `_`)."""
    return "".join("_" if ch in _INVALID_FILE_CHARS else ch for ch in str(table))


def _text(value) -> str:
    return str(value if value is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def group_tables(tags) -> dict:
    """{table: [tag, ...]} in insertion order within a table - the workbook's grouping."""
    out: dict = {}
    for t in tags:
        out.setdefault(t["path"], []).append(t)
    return out


def tag_table_xml(table: str, tags) -> str:
    """ONE tag table as `SW.Tags.PlcTagTable` XML (no BOM, CRLF, no trailing newline - the writer adds the BOM
    and the header). IDs: the table is 0, every tag / comment / comment item takes the next hex id."""
    counter = [0]

    def next_id() -> str:
        counter[0] += 1
        return format(counter[0], "X")

    visible, accessible, writable = ("true" if f else "false" for f in HMI_DEFAULTS)
    lines = ['<?xml version="1.0" encoding="utf-8"?>',
             "<Document>",
             f'  <Engineering version="{ENGINEERING_VERSION}" />',
             '  <SW.Tags.PlcTagTable ID="0">',
             "    <AttributeList>",
             f"      <Name>{_text(table)}</Name>",
             "    </AttributeList>"]
    if tags:
        lines.append("    <ObjectList>")
    for t in tags:
        lines += [f'      <SW.Tags.PlcTag ID="{next_id()}" CompositionName="Tags">',
                  "        <AttributeList>",
                  f"          <DataTypeName>{_text(t.get('data_type') or 'Bool')}</DataTypeName>",
                  f"          <ExternalAccessible>{accessible}</ExternalAccessible>",
                  f"          <ExternalVisible>{visible}</ExternalVisible>",
                  f"          <ExternalWritable>{writable}</ExternalWritable>",
                  f"          <LogicalAddress>{_text(t.get('address') or '')}</LogicalAddress>",
                  f"          <Name>{_text(t['name'])}</Name>",
                  "        </AttributeList>"]
        comment = str(t.get("comment") or "")
        if comment:
            lines += ["        <ObjectList>",
                      f'          <MultilingualText ID="{next_id()}" CompositionName="Comment">',
                      "            <ObjectList>",
                      f'              <MultilingualTextItem ID="{next_id()}" CompositionName="Items">',
                      "                <AttributeList>",
                      "                  <Culture>en-US</Culture>",
                      f"                  <Text>{_text(comment)}</Text>",
                      "                </AttributeList>",
                      "              </MultilingualTextItem>",
                      "            </ObjectList>",
                      "          </MultilingualText>",
                      "        </ObjectList>"]
        lines.append("      </SW.Tags.PlcTag>")
    if tags:
        lines.append("    </ObjectList>")
    lines += ["  </SW.Tags.PlcTagTable>", "</Document>"]
    return "\r\n".join(lines)


def tag_table_files(tags) -> dict:
    """{table: file name} for every table of the collected tags - the file-safe names, checked for collisions
    (two table names that differ only by invalid characters would overwrite each other: a pointed error)."""
    out, owners = {}, {}
    for table in sorted(group_tables(tags)):
        name = safe_file_name(table) + ".xml"
        key = name.casefold()
        if key in owners and owners[key] != table:
            raise ValueError(f"tag tables {owners[key]!r} and {table!r} both map onto the file {name!r} - "
                             "rename one of them (the file name is the table name made file-safe)")
        owners[key] = table
        out[table] = name
    return out


def write_tag_tables(tags, out_dir: str, plc: str | None = None) -> list:
    """Write `<out_dir>/<Table>.xml` for every tag table of `tags` (the workbook's tables, the workbook's
    order within a table): UTF-8 BOM, CRLF, no trailing newline, the `#!openn` header (`sw/tag-table`,
    `name` = the exact table name, the run, `plc` + `PLC tags`) as the first comment after the declaration.
    Returns the paths, table-sorted."""
    tables = group_tables(tags)
    files = tag_table_files(tags)
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for table in sorted(tables):
        stamp = header.fields("sw/tag-table", PHASE, plc=plc, target=header.PLC_TAGS, name=table,
                              source="signals + interface_elements")
        path = os.path.join(out_dir, files[table])
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:    # single BOM; our CRLF kept
            handle.write(header.stamp_xml(tag_table_xml(table, tables[table]), stamp))
        paths.append(path)
    return paths

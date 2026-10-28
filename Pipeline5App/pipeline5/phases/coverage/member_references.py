"""Phase 800 - every Global-DB member a generated block references is one the generated DBs declare ([[C-053]]).

The block builders spell some member names in code (the 03 zone cumulatives' labels, the 04_ESTOP power coil), while
the DB members come from the project's own copy of `datablocks/datablock_members.csv`, made when the project was
created. A project older than a rename keeps the old rows: its 03 / 04 blocks then read `"02_COM"."AREA 1 <new>"`
while 02_COM declares `AREA 1 <old>` - a block TIA only rejects at compile time. The run would pass (the 900
coverage's UNPLACED scans the diagnosis bindings and the interface expressions, not the blocks), so this check makes
it a located blocking finding before any block is written.

What a block references - its global symbols as TIA will read them, every pad included:
  * a block PL5 renders READY as FC XML (03 Zone Cumulative): every variable its networks wire
    (`signal_paths.ready_networks`), located by network;
  * a template-filled block (CreationInfo CSV): each @ row's template network (the row's `TemplateType`) with the
    row's values put in (`signal_paths.template_variants` / `network_symbols` - the wiring the signal-paths report
    traces), located by row;
  * a block PL5 renders READY as SCL (03_Diagnostic Nodes): every `"db"."member"` of its source
    (`system.symbols.find_bindings`), located by REGION.
Only the Global DBs PL5 generates (`db_blocks`) are checked - instance DBs, PLC tags and the DBs kept by hand on the
TIA side (`SPEED_STATE_REC`, `10_PN_NETWORK`) are no member list PL5 holds. TIA names are case-insensitive, so are
the comparisons. A member inside a Struct ([[C-042]]) is `"db"."struct"."member"`; a part past that (an array
index, a UDT's element) is not PL5's to check.

Place in the flow: run_software (src://pipeline5/systems/plc_based/siemens_s7/safety/main.py) runs `check` after
`build_engine.build`, on the same in-memory database, and gates on it with the builders' own findings - a FAIL halts
800 before any block is projected. Reads db_blocks / db_members / software_blocks / software_block_members; records
its findings to validation_issues (run_software saves them).
"""
from __future__ import annotations

import json

from pipeline5.findings.finding import Finding, record
from pipeline5.phases.coverage import signal_paths

TYPE = "blk_undeclared_member"


def _rows(database, name) -> list:
    return list(database[name]) if name in database else []


def _values(member_row) -> dict:
    values = member_row.get("values") or {}
    return json.loads(values) if isinstance(values, str) else dict(values)


def declared(database) -> dict:
    """{db name (case-folded): {member path (case-folded parts)}} of every generated Global DB: a top-level member
    `(member,)`, a Struct `(struct,)` and a member inside it `(struct, member)`."""
    out = {str(b.get("db_name") or "").strip().lower(): set() for b in _rows(database, "db_blocks")}
    for m in _rows(database, "db_members"):
        paths = out.setdefault(str(m.get("db_name") or "").strip().lower(), set())
        member, struct = str(m.get("member") or "").strip().lower(), str(m.get("struct") or "").strip().lower()
        paths.update({(struct,), (struct, member)} if struct else {(member,)})
    out.pop("", None)
    return out


def _template_rows(database, skip) -> list:
    """[(block, where, parts)] of the template-filled blocks: each @ row through its template network."""
    templates = {str(b.get("name")): str(b.get("template_ref") or "") for b in _rows(database, "software_blocks")
                 if str(b.get("name")) not in skip}
    variants = {ref: signal_paths.template_variants(ref) for ref in set(templates.values()) if ref}
    out = []
    for row in sorted(_rows(database, "software_block_members"), key=lambda r: (str(r.get("block")), int(r["seq"]))):
        block = str(row.get("block"))
        networks = variants.get(templates.get(block, ""), []) if block in templates else []
        values = _values(row)
        kind = str(values.get("TemplateType") or "").strip()
        if not networks or not kind.isdigit() or not 1 <= int(kind) <= len(networks):
            continue                                     # untraceable - the signal-paths report notes those
        comment = str(values.get("NetworkComment") or "").strip()
        where = f"row {int(row['seq']) + 1}" + (f" ({comment})" if comment else "")
        out.extend((block, where, parts) for parts, _d, _c in
                   signal_paths.network_symbols(networks[int(kind) - 1], values, pads=set()))
    return out


def references(database, ready_xml=None, ready_scl=None, find_bindings=None) -> list:
    """[(block, where, symbol parts)] - every global symbol the generated blocks reference: `ready_xml` = {block: the
    FC XML PL5 renders}, `ready_scl` = {block: the SCL source PL5 renders} (with `find_bindings`, the system's
    `"db"."member"` parser), then every other block from its template and rows (by block name, in row order)."""
    ready_xml, ready_scl = ready_xml or {}, ready_scl or {}
    out = []
    for block, xml_text in ready_xml.items():
        for k, (title, resolved) in enumerate(signal_paths.ready_networks(xml_text)):
            where = f"network {k + 1}" + (f" ({title})" if title else "")
            out.extend((block, where, parts) for parts, _d, _c in resolved)
    for block, text in ready_scl.items():
        where = ""
        for line in str(text).splitlines():
            if line.strip().upper().startswith("REGION "):
                where = line.strip()
            out.extend((block, where, pair) for pair in (find_bindings(line) if find_bindings else []))
    return out + _template_rows(database, set(ready_xml) | set(ready_scl))


def undeclared(database, refs) -> list:
    """[(block, where, symbol)] of each reference into a generated Global DB whose member path is not declared
    there, deduplicated, in reference order. `symbol` = the TIA spelling of the undeclared path."""
    known, out = declared(database), []
    for block, where, parts in refs:
        paths = known.get(str(parts[0]).strip().lower()) if len(parts) >= 2 else None
        if paths is None:
            continue                                     # a tag, or a DB PL5 does not generate
        path = tuple(str(p).strip().lower() for p in parts[1:3])
        if path[:1] not in paths:
            missing = parts[:2]
        elif len(path) == 2 and _is_struct(paths, path[0]) and path not in paths:
            missing = parts[:3]
        else:
            continue
        hit = (block, where, signal_paths.symbol(missing))
        if hit not in out:
            out.append(hit)
    return out


def _is_struct(paths, name) -> bool:
    """Whether `name` is a Struct of the DB whose member paths are `paths` (some `(name, member)` sits in it)."""
    return any(len(p) == 2 and p[0] == name for p in paths)


def check(database, ready_xml=None, ready_scl=None, find_bindings=None) -> list:
    """The `blk_undeclared_member` FAILs (phase 800) of `references` against the generated DBs - one per block
    network / row and missing symbol, located `<block> / <network or row>`. Records them to validation_issues (the
    caller saves). Returns the findings ([] when every reference is declared)."""
    findings = []
    for block, where, sym in undeclared(database, references(database, ready_xml, ready_scl, find_bindings)):
        db = signal_paths.parse_symbol(sym)[0]
        findings.append(Finding(
            phase=800, type=TYPE, severity="FAIL", location=f"{block} / {where}" if where else block,
            detail=f"references {sym}, which DB {db} does not declare - TIA rejects the block at compile time. The "
                   "DB's members come from the project's datablocks/datablock_members.csv, copied when the project was "
                   "created: a member the block builders renamed since is still the old name there"))
    record(database, findings)
    return findings

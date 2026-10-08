"""The 800 SCL emitter: a builder registered with `emit="scl"` ships a READY SCL FUNCTION source to the
PLC's `Program blocks` (UTF-8 BOM + CRLF - the 620 `Diagnostic_for_OPC.scl` conventions; the contract-v1
`#!openn` header as its first `//` lines) instead of a CreationInfo CSV; the engine drops the block's stale
CSV like it does for the FC-XML emitters.

03_Diagnostic Nodes (user spec 2026-07-07): one assignment per PROFINET node member -
    "PROFINET_NODES_ALARM"."n0005-ms1-cc1-k65001 192.168.50.5" := "10_PN_NETWORK".SUBNET_50[5];
(a PW node lands in "PROFINET_NODES_WARNING"), grouped one REGION per subnet:
    REGION Subnet 50 192.168.50.xxx
The source array is indexed by the node's LAST IP octet; `10_PN_NETWORK` is the hand-maintained
per-subnet network-status DB on the TIA side.

Place in the flow: phase 800 / 820 "Generate Blocks" (run_software in
src://pipeline5/systems/plc_based/siemens_s7/safety/main.py) - the build engine
(src://pipeline5/phases/software_blocks/build_engine.py) routes a block registered
`@builds(name, emit="scl")` (today only `03_Diagnostic Nodes`, in
src://pipeline5/systems/plc_based/siemens_s7/safety/block_builders.py) through
`SYSTEM.emitters["scl"]` (src://pipeline5/systems/plc_based/siemens_s7/safety/system.py) to
`write_scl`. Reads the builder's Table (reconstructed from `software_blocks` +
`software_block_members`); writes BuilderData/<PLC>/Program blocks/<name>.scl
(src://pipeline5/systems/plc_based/siemens_s7/output_layout.py; the header from
src://pipeline5/systems/plc_based/siemens_s7/openn_header.py).
"""
from __future__ import annotations

import os

from pipeline5.systems.plc_based.siemens_s7 import openn_header as header

PHASE = 820


def diagnostic_nodes_scl(table, name: str) -> str:
    """The 03_Diagnostic Nodes FUNCTION body from the builder Table (rows: db / member / subnet /
    prefix / octet). Regions sorted by subnet number; the rows keep their staged order within one."""
    regions: dict = {}
    for r in table.rows:
        s = int(r["subnet"])
        reg = regions.setdefault(s, {"prefix": r["prefix"], "lines": []})
        reg["lines"].append(f'    "{r["db"]}"."{r["member"]}" := '
                            f'"10_PN_NETWORK".SUBNET_{s}[{int(r["octet"])}];')
    out = [f'FUNCTION "{name}" : Void',
           "{ S7_Optimized_Access := 'TRUE' }",
           "VERSION : 0.1",
           "",
           "BEGIN"]
    for s in sorted(regions):
        reg = regions[s]
        out.append(f"\tREGION Subnet {s} {reg['prefix']}.xxx")
        out.extend(reg["lines"])
        out.append("\tEND_REGION")
        out.append("")
    out.append("END_FUNCTION")
    return "\r\n".join(out) + "\r\n"


# block name -> its SCL renderer (table, name) -> text. WHICH blocks emit SCL is declared at
# registration (`@builds(name, emit="scl")`); a registered scl block MUST have a renderer here -
# a missing one raises at project time (fail-loud, a registration error).
SCL_RENDERERS = {"03_Diagnostic Nodes": diagnostic_nodes_scl}


def write_scl(name: str, table, out_dir: str, plc: str | None = None) -> str:
    """Render + write `out_dir`/<name>.scl as UTF-8 BOM + CRLF (the exported-TIA-source convention
    the 620 SCL also uses), the `#!openn` header (`sw/source`, the run, `plc` + the TIA folder) first.
    Returns the path."""
    stamp = header.fields("sw/source", PHASE, plc=plc, target=header.PROGRAM_BLOCKS, source="software_blocks")
    text = header.stamp_source(SCL_RENDERERS[name](table, name), stamp)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.scl")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:    # single BOM; keep our CRLF
        f.write(text)
    return path

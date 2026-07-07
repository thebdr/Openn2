"""The 800 SCL emitter: a builder registered with `emit="scl"` ships a READY SCL FUNCTION source to
ImportReady (UTF-8 BOM + CRLF - the 620 `Diagnostic_for_OPC.scl` conventions) instead of a
CreationInfo CSV; the engine drops the block's stale CSV like it does for the FC-XML emitters.

03_Diagnostic Nodes (user spec 2026-07-07): one assignment per PROFINET node member -
    "PROFINET_NODES_ALARM"."n0005-ms1-cc1-k65001 192.168.50.5" := "10_PN_NETWORK".SUBNET_50[5];
(a PW node lands in "PROFINET_NODES_WARNING"), grouped one REGION per subnet:
    REGION Subnet 50 192.168.50.xxx
The source array is indexed by the node's LAST IP octet; `10_PN_NETWORK` is the hand-maintained
per-subnet network-status DB on the TIA side.
"""
from __future__ import annotations

import os


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


def write_scl(name: str, table, out_dir: str) -> str:
    """Render + write `out_dir`/<name>.scl as UTF-8 BOM + CRLF (the exported-TIA-source convention
    the 620 SCL also uses). Returns the path."""
    text = SCL_RENDERERS[name](table, name)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.scl")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:    # single BOM; keep our CRLF
        f.write(text)
    return path

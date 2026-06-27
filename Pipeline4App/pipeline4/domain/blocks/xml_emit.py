"""Direct TIA Openness FC XML emission (phase 800c) - clean-room port of PL3's `domain/blocks/xml_emit.py`.

For blocks whose logic is simple and uniform, PL4 builds the `SW.Blocks.FC` XML itself - one network sized
EXACTLY to its inputs - instead of stopping at a fixed-capacity CreationInfo CSV for OP4 to fill. The source
of the per-network data is a `Table` (the 800b builder's, reconstructed by the engine from the SSOT tables),
so this is source-agnostic.

First (only) emitter: `and_coil_fc` for **03_Zone Cumulative** - one `A`(AND)->`Coil` network per @ row, the
AND of the row's `nameOfDB.<member>` inputs driving the `02_COM.<output>` coil. The FlgNet is modelled on the
template's own network: N input Access (UId 21..), one output Access, then the AND chain. TIA caps an
instruction at 100 inputs, so for N > AND_CHUNK the inputs are split into LEAF ANDs of <= AND_CHUNK whose
outputs feed ONE combiner AND -> the Coil (the template's two-level topology); for N <= AND_CHUNK it stays a
single `A Card=N`. UIds restart at 21 per network, global object IDs run sequentially (TIA reassigns on import).

Output format MATCHES the exported-template byte conventions: **UTF-8 BOM + CRLF + indented multi-line** (a
double BOM / LF-only / single-line file fails the Openness importer at line 1). The PL4 `blocks.table.Table`
has the same interface PL3's emitter expects (rows are plain dicts; `ITERATOR_STRINGS` is a real list), so the
emitter body is a verbatim port. The engine emits these to `blocks_import_dir` and DROPS the block's CSV.
"""
from __future__ import annotations

import os

FLGNET_NS = "http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v4"
_ATTR_END = "</AttributeList>"
NL = "\r\n"


def _attr(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _text(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# TIA rejects an instruction with >100 additional inputs ("The permitted number 100 of additional inputs
# or outputs was exceeded"). So an AND of N inputs is split into LEAF ANDs of <= AND_CHUNK inputs whose
# outputs are ANDed by ONE combiner AND -> the coil (the template's own topology; it chunks at 25).
AND_CHUNK = 50


def _flgnet_lines(inputs, out_db, out_member, ind) -> list:
    """The FlgNet inner lines (Parts + Wires) for AND(inputs) -> Coil(out_db.out_member), each line
    prefixed with `ind`. `inputs` = [(db, member), ...] (N>=1). Up to AND_CHUNK inputs -> a single `A`;
    beyond that -> leaf ANDs of <= AND_CHUNK + one combiner AND of their outputs (TIA caps an instruction
    at 100 inputs). UIds restart at 21 per network: inputs 21.., output 21+N, the leaf ANDs, the combiner
    (when >1 leaf), the Coil; wires follow. The caller wraps these with <NetworkSource><FlgNet>...."""
    n = len(inputs)
    in_uids = list(range(21, 21 + n))
    out_uid = 21 + n
    L = [f"{ind}  <Parts>"]
    for uid, (db, member) in zip(in_uids, inputs):                  # input Access: UId 21..20+N
        L += [f'{ind}    <Access Scope="GlobalVariable" UId="{uid}">',
              f"{ind}      <Symbol>",
              f'{ind}        <Component Name="{_attr(db)}" />',
              f'{ind}        <Component Name="{_attr(member)}" />',
              f"{ind}      </Symbol>",
              f"{ind}    </Access>"]
    L += [f'{ind}    <Access Scope="GlobalVariable" UId="{out_uid}">',  # output Access
          f"{ind}      <Symbol>",
          f'{ind}        <Component Name="{_attr(out_db)}" />',
          f'{ind}        <Component Name="{_attr(out_member)}" />',
          f"{ind}      </Symbol>",
          f"{ind}    </Access>"]

    chunks = [in_uids[i:i + AND_CHUNK] for i in range(0, n, AND_CHUNK)]   # leaf input groups
    uid = out_uid + 1
    leaf_uids = []
    for ch in chunks:                                              # one leaf AND per chunk
        leaf_uids.append(uid)
        L += [f'{ind}    <Part Name="A" UId="{uid}">',
              f'{ind}      <TemplateValue Name="Card" Type="Cardinality">{len(ch)}</TemplateValue>',
              f"{ind}    </Part>"]
        uid += 1
    combiner_uid = None
    if len(leaf_uids) > 1:                                         # combiner ANDs the leaf outputs
        combiner_uid = uid
        L += [f'{ind}    <Part Name="A" UId="{combiner_uid}">',
              f'{ind}      <TemplateValue Name="Card" Type="Cardinality">{len(leaf_uids)}</TemplateValue>',
              f"{ind}    </Part>"]
        uid += 1
    coil_uid = uid
    L += [f'{ind}    <Part Name="Coil" UId="{coil_uid}" />',
          f"{ind}  </Parts>",
          f"{ind}  <Wires>"]

    w = coil_uid + 1
    for li, ch in enumerate(chunks):                               # input wires -> each leaf's in1..ink
        for pin, in_uid in enumerate(ch, start=1):
            L += [f'{ind}    <Wire UId="{w}">',
                  f'{ind}      <IdentCon UId="{in_uid}" />',
                  f'{ind}      <NameCon UId="{leaf_uids[li]}" Name="in{pin}" />',
                  f"{ind}    </Wire>"]
            w += 1
    final_uid = leaf_uids[0]
    if combiner_uid is not None:
        for ci, luid in enumerate(leaf_uids, start=1):             # leaf.out -> combiner.in1..inK
            L += [f'{ind}    <Wire UId="{w}">',
                  f'{ind}      <NameCon UId="{luid}" Name="out" />',
                  f'{ind}      <NameCon UId="{combiner_uid}" Name="in{ci}" />',
                  f"{ind}    </Wire>"]
            w += 1
        final_uid = combiner_uid
    L += [f'{ind}    <Wire UId="{w}">',                            # final AND out -> coil in
          f'{ind}      <NameCon UId="{final_uid}" Name="out" />',
          f'{ind}      <NameCon UId="{coil_uid}" Name="in" />',
          f"{ind}    </Wire>"]
    w += 1
    L += [f'{ind}    <Wire UId="{w}">',                            # output -> coil operand
          f'{ind}      <IdentCon UId="{out_uid}" />',
          f'{ind}      <NameCon UId="{coil_uid}" Name="operand" />',
          f"{ind}    </Wire>",
          f"{ind}  </Wires>"]
    return L


def _mltext_lines(comp, text, ids, ind) -> list:
    """A MultilingualText (Comment/Title) with one en-US item, indented at `ind`."""
    return [f'{ind}<MultilingualText ID="{ids()}" CompositionName="{comp}">',
            f"{ind}  <ObjectList>",
            f'{ind}    <MultilingualTextItem ID="{ids()}" CompositionName="Items">',
            f"{ind}      <AttributeList>",
            f"{ind}        <Culture>en-US</Culture>",
            f"{ind}        <Text>{_text(text)}</Text>",
            f"{ind}      </AttributeList>",
            f"{ind}    </MultilingualTextItem>",
            f"{ind}  </ObjectList>",
            f"{ind}</MultilingualText>"]


def and_coil_fc(table, template_path, block_name,
                block_comment="v1.0 First Emission", block_title="AND blocks with one output") -> str:
    """Build the full SW.Blocks.FC XML for an AND->Coil block from `table`. Reuses the template's
    header (DocumentInfo + the FC AttributeList incl. the F_FBD Interface) verbatim, swapping <Name>;
    emits one CompileUnit per @ row. Read with utf-8-sig so the template BOM is NOT carried into the
    body; returns a CRLF-joined multi-line string (no BOM - the BOM is added on write)."""
    with open(template_path, encoding="utf-8-sig", newline="") as f:
        src = f.read()
    head = src[: src.index(_ATTR_END) + len(_ATTR_END)]
    i, j = head.index("<Name>"), head.index("</Name>") + len("</Name>")
    head = head[:i] + f"<Name>{_text(block_name)}</Name>" + head[j:]

    n = [0]

    def ids():
        n[0] += 1
        return n[0]

    L = ["    <ObjectList>"]
    L += _mltext_lines("Comment", block_comment, ids, "      ")
    for row in table.rows:
        db = str(row.get("nameOfDB", "") or "")
        members = [str(m) for m in (row.get("ITERATOR_STRINGS") or []) if str(m).strip()]
        out_member = str(row.get("02_COM.{db_element}", "") or "")
        comment = str(row.get("NetworkComment", "") or "")
        if not members:
            continue
        L.append(f'      <SW.Blocks.CompileUnit ID="{ids()}" CompositionName="CompileUnits">')
        L.append("        <AttributeList>")
        L.append(f'          <NetworkSource><FlgNet xmlns="{FLGNET_NS}">')
        L += _flgnet_lines([(db, m) for m in members], "02_COM", out_member, "          ")
        L.append("          </FlgNet></NetworkSource>")
        L.append("          <ProgrammingLanguage>F_FBD</ProgrammingLanguage>")
        L.append("        </AttributeList>")
        L.append("        <ObjectList>")
        L += _mltext_lines("Comment", "", ids, "          ")
        L += _mltext_lines("Title", comment, ids, "          ")
        L.append("        </ObjectList>")
        L.append("      </SW.Blocks.CompileUnit>")
    L += _mltext_lines("Title", block_title, ids, "      ")
    L += ["    </ObjectList>", "  </SW.Blocks.FC>", "</Document>"]
    return head + NL + NL.join(L)


# block name -> emitter. The engine emits these to blocks_import_dir (UTF-8 BOM + CRLF) and drops the CSV.
EMITTERS = {"03_Zone Cumulative": and_coil_fc}


def write_fc_xml(name, table, template_path, out_dir) -> str:
    """Emit `name`'s FC XML (if it has an emitter) into out_dir/<name>.xml as UTF-8 BOM + CRLF (the
    exported-Openness convention). Returns the path or ''."""
    emit = EMITTERS.get(name)
    if emit is None or not template_path or not os.path.exists(template_path):
        return ""
    xml = emit(table, template_path, name)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.xml")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:    # single BOM; newline='' keeps our CRLF
        f.write(xml)
    return path

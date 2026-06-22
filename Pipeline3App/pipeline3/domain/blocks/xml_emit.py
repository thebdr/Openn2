"""Direct TIA Openness FC XML emission (phase 800, task 2).

For blocks whose logic is simple and uniform, Pipeline3 builds the SW.Blocks.FC XML itself - one
network sized EXACTLY to its inputs - instead of stopping at the CSV for Open2App to fill a
fixed-capacity template. The source of the per-network data is a `Table` (the builder's, or a
shell-override sheet's), so this is source-agnostic ("from logic AND from the shell override").

First emitter: `and_coil_fc` for **03_Zone Cumulative** - one `A`(AND)->`Coil` network per @ row, the
AND of the row's `nameOfDB.<member>` inputs driving the `02_COM.<output>` coil. The FlgNet is modelled
on the template's own network (verified): N input Access (UId 21..), one output Access, an `A` Part
with `Card=N` wired `in1..inN`, a `Coil` wired `out->in` / output->`operand`; UIds restart at 21 per
network, global object IDs run sequentially (TIA reassigns them on import).

Output format MATCHES the exported template byte-conventions: **UTF-8 BOM + CRLF + indented multi-line**
(a real Openness ML file - a double BOM or LF-only / single-line content fails the importer with
"Data at the root level is invalid").
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


def _flgnet_lines(inputs, out_db, out_member, ind) -> list:
    """The FlgNet inner lines (Parts + Wires) for AND(inputs) -> Coil(out_db.out_member), each line
    prefixed with `ind`. `inputs` = [(db, member), ...] (N>=1). The caller wraps these with
    <NetworkSource><FlgNet ...> ... </FlgNet></NetworkSource> (FlgNet adjacent to NetworkSource)."""
    n = len(inputs)
    out_uid, a_uid, coil_uid = 21 + n, 22 + n, 23 + n
    L = [f"{ind}  <Parts>"]
    for k, (db, member) in enumerate(inputs):                       # input Access: UId 21..20+N
        L += [f'{ind}    <Access Scope="GlobalVariable" UId="{21 + k}">',
              f"{ind}      <Symbol>",
              f'{ind}        <Component Name="{_attr(db)}" />',
              f'{ind}        <Component Name="{_attr(member)}" />',
              f"{ind}      </Symbol>",
              f"{ind}    </Access>"]
    L += [f'{ind}    <Access Scope="GlobalVariable" UId="{out_uid}">',
          f"{ind}      <Symbol>",
          f'{ind}        <Component Name="{_attr(out_db)}" />',
          f'{ind}        <Component Name="{_attr(out_member)}" />',
          f"{ind}      </Symbol>",
          f"{ind}    </Access>",
          f'{ind}    <Part Name="A" UId="{a_uid}">',
          f'{ind}      <TemplateValue Name="Card" Type="Cardinality">{n}</TemplateValue>',
          f"{ind}    </Part>",
          f'{ind}    <Part Name="Coil" UId="{coil_uid}" />',
          f"{ind}  </Parts>",
          f"{ind}  <Wires>"]
    w = 24 + n
    for k in range(n):                                              # input wires -> the A box pins in1..inN
        L += [f'{ind}    <Wire UId="{w}">',
              f'{ind}      <IdentCon UId="{21 + k}" />',
              f'{ind}      <NameCon UId="{a_uid}" Name="in{k + 1}" />',
              f"{ind}    </Wire>"]
        w += 1
    L += [f'{ind}    <Wire UId="{w}">',
          f'{ind}      <NameCon UId="{a_uid}" Name="out" />',
          f'{ind}      <NameCon UId="{coil_uid}" Name="in" />',
          f"{ind}    </Wire>"]
    w += 1
    L += [f'{ind}    <Wire UId="{w}">',
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


# block name -> emitter. The engine emits these to ImportReady (UTF-8 BOM + CRLF).
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

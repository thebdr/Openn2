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


# --- FDBACK (05_Output Feedback) dynamic network -------------------------------------------------- #
# The alternative to the 12 fixed-capacity template variants: build each unit's FDBACK network sized to
# its EXACT element counts (any number of on-conditions / feedbacks / contactors), so a unit that
# overflows the template (>2 areas, >4 feedbacks, >2 contactors) is expressible. The wiring is a verified
# parametric reproduction of the template's own 12 networks (each of the 12 (A,F,C) sizes is byte-exact),
# extrapolated by the same rules. One `F_FDBACK` FB per unit: ON = AND(areas), FEEDBACK = AND(feedbacks),
# ACK = OR(resets), QBAD_FIO = the qbad(s) [C=1: direct + FB pin Negated; C>1: AND of NEGATED qbads],
# Q -> the contactor output(s) [C=1: direct; C>1: FB.Q open + a instanceOf-F_FDBACK.Q read-back driving a
# chain of C coils]. ACK_NEC=true, FDB_TIME=T#300ms, ERROR->03_FDBACK_RAW, en/ACK_REQ/DIAG open.
_NOOP = "No Operation"   # the AND-neutral DB filler a CSV variant pads unused fixed slots with (dropped here)


def _fdback_flgnet_lines(areas, feedbacks, qbads, resets, outputs, error_member, instance, ind) -> list:
    """FlgNet inner (Parts + Wires) for ONE FDBACK unit at indent `ind`. areas/resets: 05_EM_STATE members
    (A of each); feedbacks/qbads/outputs: tags (F, C, C); error_member: the 03_FDBACK_RAW member; instance:
    the F_FDBACK instance name. Reproduces the template's exact UId scheme + part/wire order for any (A,F,C)."""
    A, F, C = len(areas), len(feedbacks), len(qbads)
    P, Wl = [], []
    uid = 21

    def sym2(db, member):                                    # a 2-component Access (DB.member)
        nonlocal uid
        u = uid; uid += 1
        P.extend([f'{ind}    <Access Scope="GlobalVariable" UId="{u}">', f"{ind}      <Symbol>",
                  f'{ind}        <Component Name="{_attr(db)}" />',
                  f'{ind}        <Component Name="{_attr(member)}" />',
                  f"{ind}      </Symbol>", f"{ind}    </Access>"])
        return u

    def sym1(tag):                                           # a 1-component Access (a tag)
        nonlocal uid
        u = uid; uid += 1
        P.extend([f'{ind}    <Access Scope="GlobalVariable" UId="{u}">', f"{ind}      <Symbol>",
                  f'{ind}        <Component Name="{_attr(tag)}" />',
                  f"{ind}      </Symbol>", f"{ind}    </Access>"])
        return u

    def const(scope, lines):
        nonlocal uid
        u = uid; uid += 1
        P.append(f'{ind}    <Access Scope="{scope}" UId="{u}">')
        P.append(f"{ind}      <Constant>")
        P.extend(f"{ind}        {ln}" for ln in lines)
        P.append(f"{ind}      </Constant>")
        P.append(f"{ind}    </Access>")
        return u

    # Access parts, in the template's exact order
    area_u = [sym2("05_EM_STATE", m) for m in areas]
    fb_u = [sym1(t) for t in feedbacks]
    qbad_u = [sym1(t) for t in qbads]
    true_u = const("LiteralConstant", ["<ConstantType>Bool</ConstantType>", "<ConstantValue>true</ConstantValue>"])
    reset_u = [sym2("05_EM_STATE", m) for m in resets]
    time_u = const("TypedConstant", ["<ConstantValue>T#300ms</ConstantValue>"])
    if C == 1:
        out_u = [sym1(outputs[0])]
        err_u = sym2("03_FDBACK_RAW", error_member)
        q_read_u = None
    else:
        err_u = sym2("03_FDBACK_RAW", error_member)
        q_read_u = sym2(instance, "Q")
        out_u = [sym1(t) for t in outputs]

    # instruction Parts: ON-A, FB-A, QBAD-A(neg), ACK-O, FDBACK(+Instance), Coils
    def and_part(card, negated=False):
        nonlocal uid
        u = uid; uid += 1
        P.append(f'{ind}    <Part Name="A" UId="{u}">')
        P.append(f'{ind}      <TemplateValue Name="Card" Type="Cardinality">{card}</TemplateValue>')
        if negated:
            P.extend(f'{ind}      <Negated Name="in{k}" />' for k in range(1, card + 1))
        P.append(f"{ind}    </Part>")
        return u

    def or_part(card):
        nonlocal uid
        u = uid; uid += 1
        P.extend([f'{ind}    <Part Name="O" UId="{u}">',
                  f'{ind}      <TemplateValue Name="Card" Type="Cardinality">{card}</TemplateValue>',
                  f"{ind}    </Part>"])
        return u

    on_and = and_part(A) if A > 1 else None
    fb_and = and_part(F) if F > 1 else None
    qbad_and = and_part(C, negated=True) if C > 1 else None
    ack_or = or_part(A) if A > 1 else None

    fb_uid = uid; uid += 1
    inst_uid = uid; uid += 1
    P.append(f'{ind}    <Part Name="FDBACK" Version="1.5" UId="{fb_uid}">')
    P.append(f'{ind}      <Instance Scope="GlobalVariable" UId="{inst_uid}">')
    P.append(f'{ind}        <Component Name="{_attr(instance)}" />')
    P.append(f"{ind}      </Instance>")
    P.append(f'{ind}      <TemplateValue Name="f_user_card" Type="Cardinality">1</TemplateValue>')
    P.append(f'{ind}      <TemplateValue Name="f_image_card" Type="Cardinality">0</TemplateValue>')
    if C == 1:
        P.append(f'{ind}      <Negated Name="QBAD_FIO" />')
    P.append(f"{ind}    </Part>")

    coil_u = []
    if C > 1:
        for _ in range(C):
            u = uid; uid += 1
            P.append(f'{ind}    <Part Name="Coil" UId="{u}" />')
            coil_u.append(u)

    # OpenCons: en, [Q if C>1], ACK_REQ, DIAG
    en_open = uid; uid += 1
    q_open = None
    if C > 1:
        q_open = uid; uid += 1
    ackreq_open = uid; uid += 1
    diag_open = uid; uid += 1

    wuid = [uid]                                              # wire UIds continue after all parts/opencons

    def wire(a, b):
        Wl.append(f'{ind}    <Wire UId="{wuid[0]}">')
        Wl.append(f"{ind}      {a}")
        Wl.append(f"{ind}      {b}")
        Wl.append(f"{ind}    </Wire>")
        wuid[0] += 1

    def ident(u):
        return f'<IdentCon UId="{u}" />'

    def ncon(u, pin):
        return f'<NameCon UId="{u}" Name="{pin}" />'

    def opencon(u):
        return f'<OpenCon UId="{u}" />'

    # combine gates first (inputs, then gate.out -> FB.pin), in part order ON, FEEDBACK, QBAD, ACK
    if on_and is not None:
        for k, au in enumerate(area_u, 1):
            wire(ident(au), ncon(on_and, f"in{k}"))
        wire(ncon(on_and, "out"), ncon(fb_uid, "ON"))
    if fb_and is not None:
        for k, fu in enumerate(fb_u, 1):
            wire(ident(fu), ncon(fb_and, f"in{k}"))
        wire(ncon(fb_and, "out"), ncon(fb_uid, "FEEDBACK"))
    if qbad_and is not None:
        for k, qu in enumerate(qbad_u, 1):
            wire(ident(qu), ncon(qbad_and, f"in{k}"))
        wire(ncon(qbad_and, "out"), ncon(fb_uid, "QBAD_FIO"))
    if ack_or is not None:
        for k, ru in enumerate(reset_u, 1):
            wire(ident(ru), ncon(ack_or, f"in{k}"))
        wire(ncon(ack_or, "out"), ncon(fb_uid, "ACK"))

    # FB direct pin wires, in pin order, skipping combine-driven pins
    wire(opencon(en_open), ncon(fb_uid, "en"))
    if on_and is None:
        wire(ident(area_u[0]), ncon(fb_uid, "ON"))
    if fb_and is None:
        wire(ident(fb_u[0]), ncon(fb_uid, "FEEDBACK"))
    if qbad_and is None:
        wire(ident(qbad_u[0]), ncon(fb_uid, "QBAD_FIO"))
    wire(ident(true_u), ncon(fb_uid, "ACK_NEC"))
    if ack_or is None:
        wire(ident(reset_u[0]), ncon(fb_uid, "ACK"))
    wire(ident(time_u), ncon(fb_uid, "FDB_TIME"))
    if C == 1:
        wire(ncon(fb_uid, "Q"), ident(out_u[0]))
    else:
        wire(ncon(fb_uid, "Q"), opencon(q_open))
    wire(ncon(fb_uid, "ERROR"), ident(err_u))
    wire(ncon(fb_uid, "ACK_REQ"), opencon(ackreq_open))
    wire(ncon(fb_uid, "DIAG"), opencon(diag_open))

    # coil chain (C>1): Q-readback -> coil1.in, out_k -> coil_k.operand, coil_k.out -> coil_{k+1}.in
    for k, cu in enumerate(coil_u):
        src = ncon(coil_u[k - 1], "out") if k > 0 else ident(q_read_u)
        wire(src, ncon(cu, "in"))
        wire(ident(out_u[k]), ncon(cu, "operand"))

    return [f"{ind}  <Parts>"] + P + [f"{ind}  </Parts>", f"{ind}  <Wires>"] + Wl + [f"{ind}  </Wires>"]


def _fdback_row(row):
    """Reconstruct one unit's element lists from the builder's flat @ cells (the same template
    placeholders the CSV fills), dropping the AND-neutral 'No Operation' pad. None if no contactor output."""
    def scan(make):
        out, k = [], 1
        while make(k) in row:
            v = str(row.get(make(k), "") or "").strip()
            if v and v != _NOOP:
                out.append(v)
            k += 1
        return out
    outputs = scan(lambda k: f"tagName:Contactor{k}_Output")
    if not outputs:
        return None
    return {
        "areas": scan(lambda k: f"05_EM_STATE.{{matrix_areas.{k}}}"),
        "resets": scan(lambda k: f"05_EM_STATE.{{matrix_areas.{k}}}_RESET"),
        "feedbacks": scan(lambda k: f"tagName:Contactor{k}_FeedbackInput"),
        "qbads": scan(lambda k: f"tagName:Contactor{k}_QBadInput"),
        "outputs": outputs,
        "error_member": str(row.get("03_FDBACK_RAW.{db_element}", "") or ""),
        "instance": str(row.get("instanceOf-F_FDBACK", "") or ""),
    }


def fdback_fc(table, template_path, block_name,
              block_comment="v1.1 Dynamic FDBACK (one network sized to each unit)",
              block_title="Output Feedback") -> str:
    """Build the SW.Blocks.FC XML for 05_Output Feedback - one FDBACK CompileUnit per @ row, each sized to
    the unit's exact element counts (`_fdback_row` + `_fdback_flgnet_lines`). Reuses the template head like
    `and_coil_fc`; CRLF multi-line, no BOM (added on write)."""
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
        u = _fdback_row(row)
        if u is None:
            continue
        comment = str(row.get("NetworkComment", "") or "")
        L.append(f'      <SW.Blocks.CompileUnit ID="{ids()}" CompositionName="CompileUnits">')
        L.append("        <AttributeList>")
        L.append(f'          <NetworkSource><FlgNet xmlns="{FLGNET_NS}">')
        L += _fdback_flgnet_lines(u["areas"], u["feedbacks"], u["qbads"], u["resets"], u["outputs"],
                                  u["error_member"], u["instance"], "          ")
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


# emit KIND -> renderer. WHICH blocks use an emitter is declared at registration
# (`@builds(name, emit="fc_xml"|"fdback_xml")` in the user-coded builders.py) - the hardcoded name-set is
# retired (UI_REFRESH_PLAN F). The engine emits these to blocks_import_dir (UTF-8 BOM + CRLF) and drops the CSV.
EMIT_FUNCS = {"fc_xml": and_coil_fc, "fdback_xml": fdback_fc}


def write_fc_xml(name, table, template_path, out_dir, kind) -> str:
    """Emit `name`'s FC XML for the declared `kind` ('fc_xml' | 'fdback_xml') into out_dir/<name>.xml
    as UTF-8 BOM + CRLF (the exported-Openness convention). The KIND arrives from the caller (the
    system's emitter table routes it) - this module no longer consults any registry. Returns the
    path, or '' when the template is missing."""
    emit = EMIT_FUNCS.get(kind)
    if emit is None or not template_path or not os.path.exists(template_path):
        return ""
    xml = emit(table, template_path, name)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.xml")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:    # single BOM; newline='' keeps our CRLF
        f.write(xml)
    return path

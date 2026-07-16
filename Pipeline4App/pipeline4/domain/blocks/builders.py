"""The hand-written software-block builders (phase 800 / 820) - the per-template edit point.

One function per template, registered with `@builds("<output name>")`. Each builder receives the
`Database` (the staged `signals` rows) and returns a `Table`; the engine serializes the Table into the
`$/#/%/@` CreationInfo CSV. NO rules, NO sidecars - the builder's Python does whatever the template needs.
Clean-room port of PL3's `domain/blocks/builders.py` (800a = the simple builders 00/06/07; 800b = the
complex builders 02/03/04/05/08). The two PL4 adaptations vs PL3: the multi-valued cells
(`matrix_areas`/`areas_description`/`datablocks`) are real JSON list cells here (read via `_as_list`, not
`.split("|")`), and PL3's `_source_row` is PL4's `source_row` (the staging bookkeeping field, no prefix).

The Database helpers: `db.rows` · `db.by_type("KQ")` · `db.by_db("03_FDBACK")` · `db.by_area("AREA 1")` ·
`db.by_tagtable(...)` · `db.where(pred)` · `db.areas()`. The Table: `t.add(template_type="01", <key>=<value>,
...)` per @ row (a placeholder key -> `!!<key>$$`, a list value -> the horizontal ITERATOR, placed last).
"""
from __future__ import annotations

import re

from pipeline4.domain.blocks.database import Database, _as_list
from pipeline4.domain.blocks.registry import builds
from pipeline4.domain.blocks.table import Table

PAD = "No Operation"   # iterator filler for a template's unused fixed slots (a DB no-op member, ph520)


# --------------------------------------------------------------------------- #
# small shared helpers (node-by-address grouping, chunking) - free-form Python #
# --------------------------------------------------------------------------- #
def _addr_byte(bit):
    b = str(bit or "").strip().upper()
    if b[:1] in ("I", "Q") and "." in b:
        try:
            return b[0], int(b[1:b.index(".")])
        except ValueError:
            return None
    return None


def _nodes(db: Database) -> list:
    """The Profinet node rows (those carrying a profinet_name)."""
    return [r for r in db.rows if r.get("profinet_name")]


def _node_of(db: Database, row):
    """The node whose I/Q byte range contains this signal's address (else None)."""
    ab = _addr_byte(row.get("bit"))
    if not ab:
        return None
    kind, byte = ab
    for n in _nodes(db):
        s, e = n.get(f"{kind}_startByte", ""), n.get(f"{kind}_endByte", "")
        if s != "" and int(s) <= byte <= int(e):
            return n
    return None


def _group_by_node(db: Database, *script_types) -> list:
    """[(node_row, [rows of those script_types on the node])], in first-seen node order."""
    order, groups = [], {}
    for r in db.by_type(*script_types):
        n = _node_of(db, r)
        if n is None:
            continue
        if id(n) not in groups:
            groups[id(n)] = (n, [])
            order.append(id(n))
        groups[id(n)][1].append(r)
    return [groups[k] for k in order]


def _chunked(seq, n) -> list:
    seq = list(seq)
    return [seq[i:i + n] for i in range(0, len(seq), n)]


@builds("00_Only for Commissioning")
def build_00_commissioning(db: Database) -> Table:
    """One commissioning-bypass network per Profinet IO-device node - the nodes that carry a diagnosis
    member (a non-empty name_in_db, i.e. those in PROFINET_NODES_ALARM/WARNING); the PLC/CM heads + their
    partner cards are skipped. Both the `00_Commissioning` DB member and the network title are the node's
    "<profinet_name> <profinet_ip>"."""
    t = Table("00_Only for Commissioning")
    for n in db.where(lambda r: r.get("profinet_name") and r.get("name_in_db")):
        node = f"{n['profinet_name']} {n['profinet_ip']}".strip()
        t.add(
            template_type="01",
            **{"00_Commissioning.{db_element}": node},
            NetworkComment=node,
        )
    return t


@builds("02_EM Push Button")
def build_02_em_push_button(db: Database) -> Table:
    """One 00_Push-Button_Input FB instance per node: the node's emergency-stop INPUTS - both
    E1/2 emergency-push-buttons AND B1/2 safety-breakers (grouped by node, in address order),
    chunked to the FB's 4 channels. The v1.1 template carries 8 !!ITERATOR_STRINGS$$ in document
    order - the IN_1..4 bare-symbol quartet, then the 01_PushButton.<member> quartet - so the iterator
    is the padded name_in_db quartet emitted TWICE (same values, padded identically). Bypass_ET200 is
    the node's '<profinet_name> <profinet_ip>' (the same 00_Commissioning member as block 00)."""
    SLOTS = 4   # the FB's 4 channels (IN_1..4 / 01_PushButton.<member>_1..4)
    t = Table("02_EM Push Button")
    for node, members in _group_by_node(db, "E1/2", "B1/2"):
        ident = f"{node['profinet_name']} {node['profinet_ip']}".strip()
        for i, chunk in enumerate(_chunked(members, SLOTS), start=1):
            inst = f"EMPB_{node['profinet_name']}_{i}"
            names = [m["name_in_db"] for m in chunk]
            names += [PAD] * (SLOTS - len(names))            # pad the quartet to the 4 fixed slots
            t.add(
                template_type="01",
                **{"instanceOf-00_Push-Button_Input": inst},
                **{"00_Commissioning.{db_element}": ident},
                NetworkComment=f"{inst} {node['profinet_ip']}",
                ITERATOR_STRINGS=names + names,              # 2 quartets: IN_1..4 then 01_PushButton.<member>
            )
    return t


# Zone-cumulative groups (03): per AREA, AND the group's DB members -> a 02_COM."AREA n <LABEL>" coil.
# Each group is ONE signal type -> ONE DB, so nameOfDB is scalar and the iterator is sized exactly.
ZONE_GROUPS = [
    ("PB",              ("E1/2",)),     # always (every area has push buttons)
    ("FDB",             ("KQ",)),       # always (every area has contactor feedback)
    ("SAFETY_BREAKERS", ("B1/2",)),     # only when the area has a breaker
    ("DOORS",           ("DI1/2",)),    # only when the area has a door safety input
]


def _area_descriptions(db: Database) -> dict:
    """{area: CONCEPT description} - PL4's `areas_description` list cell is built (matrix.annotate) by the
    SAME `if area_desc.get(a)` filter as PL3's `|`-join, so its i-th entry maps to the i-th area that HAS
    a description (first non-empty wins). `matrix_areas` is read via `_as_list` (PL3 drops empties too);
    `areas_description` is read KEEPING empties (PL3's `descs` strips but does not filter) to preserve the
    positional indexing exactly."""
    out = {}
    for r in db.rows:
        areas = _as_list(r.get("matrix_areas"))
        ad = r.get("areas_description")
        descs = ([str(d).strip() for d in ad] if isinstance(ad, (list, tuple))
                 else [d.strip() for d in str(ad or "").split("|")])
        for i, a in enumerate(areas):
            if a not in out and i < len(descs) and descs[i]:
                out[a] = descs[i]
    return out


@builds("03_Zone Cumulative", emit="fc_xml")   # ships a ready FC XML (800c), not a CreationInfo CSV
def build_03_zone_cumulative(db: Database) -> Table:
    """Per AREA, one AND-cumulative per signal group that has members: the coil writes
    02_COM."AREA n <LABEL>" = AND of that group's DB members in the area. Each group is one type -> one
    DB, so nameOfDB is a scalar and ITERATOR_STRINGS is just the member list, sized to the exact input
    count (no fixed-capacity tiers, no padding). NetworkComment leads with the 02_COM element (the coil
    member this network writes) and appends the area's CONCEPT description: "<element> - <description>",
    or just "<element>" when the area has no description."""
    descs = _area_descriptions(db)
    t = Table("03_Zone Cumulative")
    for area in db.areas():
        desc = descs.get(area, "")
        for label, types in ZONE_GROUPS:
            want = {x.upper() for x in types}
            srcs = [r for r in db.by_area(area)
                    if str(r.get("script_type", "")).upper() in want and r.get("name_in_db")]
            if not srcs:
                continue
            db_name = next(iter(_as_list(srcs[0].get("datablocks"))), "")   # the leftmost DB (list cell)
            element = f"{area} {label}"                          # the 02_COM.{db_element} member
            t.add(
                template_type="01",
                nameOfDB=db_name,
                **{"02_COM.{db_element}": element},
                NetworkComment=f"{element} - {desc}" if desc else element,
                ITERATOR_STRINGS=[r["name_in_db"] for r in srcs],
            )
    return t


def _sorter_areas(db: Database) -> set:
    """Areas that are sorter areas - inferred from single-area rows flagged IsSorterArea (the staged
    flag is per-row: a row touches a sorter area, so only a single-area row pins it to one area)."""
    s = set()
    for r in db.rows:
        areas = _as_list(r.get("matrix_areas"))
        if len(areas) == 1 and r.get("IsSorterArea") == "yes":
            s.add(areas[0])
    return s


def _area_nn(area) -> str:
    m = re.search(r"(\d+)\s*$", str(area))
    return f"{int(m.group(1)):02d}" if m else str(area)


@builds("03_Diagnostic Nodes", emit="scl")
def build_03_diagnostic_nodes(db: Database) -> Table:
    """One SCL assignment per PROFINET node - the PROFINET_NODES member mirror (user spec 2026-07-07):
    a PA head -> "PROFINET_NODES_ALARM", a PW head -> "PROFINET_NODES_WARNING" (the same `row where
    $script_type` domains as the 520 config members), member = '<profinet_name> <profinet_ip>', source
    = "10_PN_NETWORK".SUBNET_<subnet>[<last octet>]. `scl_emit` renders it as a ready SCL FUNCTION,
    one REGION per subnet - the block ships as ImportReady/<name>.scl, no CreationInfo CSV."""
    t = Table("03_Diagnostic Nodes")
    for r in db.rows:
        st = str(r.get("script_type", "")).strip().upper()
        if st not in ("PA", "PW"):
            continue
        name = str(r.get("profinet_name", "") or "").strip()
        ip = str(r.get("profinet_ip", "") or "").strip()
        parts = ip.split(".")
        if not name or len(parts) != 4 or not all(p.isdigit() for p in parts):
            continue                                   # not a resolvable node address (110 flags it)
        t.add(db="PROFINET_NODES_ALARM" if st == "PA" else "PROFINET_NODES_WARNING",
              member=f"{name} {ip}", subnet=str(int(parts[2])),
              prefix=".".join(parts[:3]), octet=str(int(parts[3])))
    return t


@builds("04_ESTOP")
def build_04_estop(db: Database) -> Table:
    """One ESTOP network per AREA (template v1.1: the door/breaker cumulatives now live in 02_COM, so
    there is NO iterator - the block references the finished 02_COM."<area> DOORS" / "<area>
    SAFETY_BREAKERS" coils that block 03 builds). The TemplateType selects the network by the area's
    SAFETY FEATURES (feature presence, not door count): a SORTER area -> TT06 (E-STOP + doors +
    breakers + encoder; the template keeps this network's T#10s FB delay, vs T#150ms on the others);
    else doors+breakers -> TT05, breakers-only -> TT04, doors-only -> TT03, bare -> TT02 (Emergency
    STOP, reset required). TT01 ('Safety STOP', reset-not-required / ACK_NEC=FALSE) is reserved for the
    future. Per area: the 02_COM PB/FDB cumulatives (always) + DOORS/SAFETY_BREAKERS (only when the
    area has them), the 05_EM_STATE Q/Q_DELAYED/RESET state members + the per-area POWER_CUT coil, and
    the sorter's encoder-healthy SPEED_STATE_REC member (TT06 only)."""
    sorter = _sorter_areas(db)
    t = Table("04_ESTOP")
    for area in db.areas():
        inarea = db.by_area(area)
        is_sorter = area in sorter
        has_doors = any(str(r.get("script_type", "")).upper() == "DI1/2" and r.get("name_in_db")
                        for r in inarea)
        has_breakers = any(str(r.get("script_type", "")).upper() == "B1/2" and r.get("name_in_db")
                           for r in inarea)
        if is_sorter:                                            # E-STOP + doors + breakers + encoder
            tt = "06"
        elif has_doors and has_breakers:
            tt = "05"
        elif has_breakers:
            tt = "04"
        elif has_doors:
            tt = "03"
        else:
            tt = "02"                                            # Emergency STOP (reset required); TT01 = future
        nn = _area_nn(area)                                      # the SORTER number (zero-padded), TT06 only
        encoder = f"SORTER_{nn}_ENCODER_HEALTHY" if is_sorter else ""
        t.add(
            template_type=tt,
            **{"instanceOf-F_ESTOP1": f"ESTOP_{area}"},
            NetworkComment=f"{area} ESTOP",
            **{"02_COM.{matrix_area} PB": f"{area} PB"},          # raw-area: matches the 03 02_COM members
            **{"02_COM.{matrix_area} FDB": f"{area} FDB"},
            **{"05_EM_STATE.{matrix_area}_Q": f"{area} Q"},       # UNPADDED area, consistent with 02_COM + 05
            **{"05_EM_STATE.{matrix_area}_Q_DELAYED": f"{area} Q_Delayed"},
            **{"05_EM_STATE.{matrix_areas.1}_RESET": f"{area} RESET"},
            **{"05_EM_STATE.{matrix_area}_POWER_CUT": f"{area} POWER_CUT"},   # per area now (was sorter-only)
            **{"02_COM.{matrix_area} DOORS": f"{area} DOORS" if has_doors else ""},
            **{"02_COM.{matrix_area} SAFETY_BREAKERS": f"{area} SAFETY_BREAKERS" if has_breakers else ""},
            **{"SPEED_STATE_REC.SORTER_{index}_ENCODER_HEALTHY": encoder},
        )
    return t


# 05_Output Feedback: the capacity variants of the template's 12 FDBACK networks. Each tuple is
# (OnCondition cap, FeedbackInput cap, ContactorOutput cap, TemplateType); the builder picks the smallest
# variant whose capacities all cover the unit's counts. The grid is oncond {1,2} x (fb,co) in
# {(1,1),(2,1),(4,1),(1,2),(2,2),(4,2)}: TT1-6 the 1-area row, TT7-12 the 2-area row. NOTE: the shipped
# sidecar CSV mislabeled TT9-12 as oncond=1 (a copy of TT3-6), but the actual template networks 9-12 have
# TWO matrix_areas slots - so a 2-area unit with co=2 or fb=4 matched nothing -> an empty TemplateType.
# Corrected here + in the sidecar to the real (2,4,1)/(2,1,2)/(2,2,2)/(2,4,2) (verified vs the XML).
OUTPUT_FEEDBACK_VARIANTS = [
    (1, 1, 1, 1), (1, 2, 1, 2), (1, 4, 1, 3), (1, 1, 2, 4), (1, 2, 2, 5), (1, 4, 2, 6),
    (2, 1, 1, 7), (2, 2, 1, 8), (2, 4, 1, 9), (2, 1, 2, 10), (2, 2, 2, 11), (2, 4, 2, 12),
]


def _of_variant(oncond, fb, co):
    """Smallest (OnCondition, FeedbackInput, ContactorOutput, TemplateType) variant covering the
    unit's counts, or None if none is large enough."""
    cands = [v for v in OUTPUT_FEEDBACK_VARIANTS if v[0] >= oncond and v[1] >= fb and v[2] >= co]
    return min(cands, key=lambda v: (v[0] + v[1] + v[2], v[3])) if cands else None


# SURFACE FLAG (user decision - a code setting). False -> the fixed-capacity template CSV (the corrected
# 12-variant path above); True -> the DYNAMIC FDBACK FC XML (xml_emit.fdback_fc), one network sized to each
# unit's EXACT element counts (no 12-variant ceiling - a unit with >2 areas / >4 feedbacks / >2 contactors
# is expressible). Flip + re-run to switch the whole 05 block's output surface: the builder Table is
# IDENTICAL either way (the emitter reconstructs each unit's element lists from the same flat @ cells,
# dropping the AND-neutral 'No Operation' pad, so a fitting unit still yields its exact-size network).
FDBACK_XML = False


@builds("05_Output Feedback", emit="fdback_xml" if FDBACK_XML else "csv")
def build_05_output_feedback(db: Database) -> Table:
    """One 03_FDBACK (FDBACK) FB instance per contactor unit = the K-family signals sharing one
    (global) index: all KQ outputs + KI feedback inputs of that index. Three fixed-slot families:
      ContactorOutput = the unit's KQ(s) - 1 or a KQ1/2+KQ2/2 pair (Contactor{n}_Output = name_in_tagtable,
        QBadInput = 'QBAD_'+tag),
      FeedbackInput   = the unit's KI(s) incl. a KIx/n series, in row order (Contactor{n}_FeedbackInput),
      OnCondition     = the union of the KQ matrix areas -> 05_EM_STATE."AREA nn POWER_CUT" / "..._RESET"
                        (the per-area power-cut coil the 04_ESTOP v1.1 block writes; was "AREA nn Q_Delayed").
    TemplateType = the smallest variant covering (OnCondition, FeedbackInput, ContactorOutput); unused
    FeedbackInput slots (a count between the 1/2/4 tiers) pad with PAD. Error member = the first KQ's
    name_in_db in 03_FDBACK_RAW; instanceOf-F_FDBACK = 'FDBACK_'+that KQ's FLD (+ '_<device>' per extra KQ)."""
    groups, order = {}, []                                          # index -> {'kq': [...], 'ki': [...]}
    for r in db.rows:
        st = str(r.get("script_type", "")).upper()
        idx = str(r.get("index", "")).strip()
        if not idx or not (st.startswith("KQ") or st.startswith("KI")):
            continue
        if idx not in groups:
            groups[idx] = {"kq": [], "ki": []}
            order.append(idx)
        groups[idx]["kq" if st.startswith("KQ") else "ki"].append(r)

    def _row(r):
        return int(r.get("source_row", 0) or 0)                     # PL4: source_row (PL3's _source_row)

    t = Table("05_Output Feedback")
    for idx in order:
        kqs = sorted(groups[idx]["kq"], key=_row)
        kis = sorted(groups[idx]["ki"], key=_row)
        if not kqs:                                                 # an index with KIs but no KQ: skip
            continue
        kq0 = kqs[0]
        inst = "FDBACK_" + kq0.get("iol_FLD", "")
        for extra in kqs[1:]:
            inst += "_" + str(extra.get("device", ""))
        areas = []                                                  # union of the KQ matrix areas
        for kq in kqs:
            for a in _as_list(kq.get("matrix_areas")):
                if a not in areas:
                    areas.append(a)
        variant = _of_variant(len(areas), len(kis), len(kqs))
        fb_cap = variant[1] if variant else len(kis)

        areas_str = "|".join(_as_list(kq0.get("matrix_areas")))    # PL3 rendered the |-joined string here
        row = {
            "TemplateType": f"{variant[3]:02d}" if variant else "",
            "instanceOf-F_FDBACK": inst,
            "NetworkComment": re.sub(r"\s+", " ", f"{areas_str} Contactor Output "
                                     f"{kq0.get('combined_FLD', '')} {kq0.get('numerazione_linea', '')}").strip(),
            "03_FDBACK_RAW.{db_element}": kq0.get("name_in_db", ""),
        }
        for n, kq in enumerate(kqs, start=1):                       # ContactorOutput + QBadInput slots
            tag = kq.get("name_in_tagtable", "")
            row[f"tagName:Contactor{n}_Output"] = tag
            row[f"tagName:Contactor{n}_QBadInput"] = f"QBAD_{tag}" if tag else ""
        for n in range(1, fb_cap + 1):                              # FeedbackInput slots (filled + padded)
            ki = kis[n - 1] if n - 1 < len(kis) else None
            row[f"tagName:Contactor{n}_FeedbackInput"] = ki.get("name_in_tagtable", "") if ki else PAD
        for i, area in enumerate(areas, start=1):                   # OnCondition: area number UNPADDED (-> "AREA 1")
            row[f"05_EM_STATE.{{matrix_areas.{i}}}"] = f"{area} POWER_CUT"   # the per-area power-cut coil (04 v1.1)
            row[f"05_EM_STATE.{{matrix_areas.{i}}}_RESET"] = f"{area} RESET"
        t.add_row(row)
    return t


@builds("06_Feedback Error")
def build_06_feedback_error(db: Database) -> Table:
    """One 03_FDBACK error FB instance per node: the node's KQ contactor-feedback members (grouped by
    address range), chunked to the FB's 8 IN/OUT slots. The iterator (each KQ's name_in_db) names a member
    in BOTH 03_FDBACK_RAW (the FDBACK ERROR n inputs) and 03_FDBACK (the ERROR n outputs) - it carries the
    padded 8-slot bank TWICE (16 cells: the 8 slots + an exact copy, so the template consumes one bank per
    side instead of re-reading the same cells - user spec 2026-07-07). Padded to 8 with PAD.
    Commissioning_bypass is the node's '<profinet_name> <profinet_ip>'."""
    SLOTS = 8   # the FB's FDBACK ERROR 1..8 / ERROR 1..8
    t = Table("06_Feedback Error")
    for node, members in _group_by_node(db, "KQ"):
        ident = f"{node['profinet_name']} {node['profinet_ip']}".strip()
        for i, chunk in enumerate(_chunked(members, SLOTS), start=1):
            inst = f"FDBK_ERR_{node['profinet_name']}_{i}"
            names = [m["name_in_db"] for m in chunk]
            names += [PAD] * (SLOTS - len(names))
            t.add(
                template_type="01",
                **{"instanceOf-03_FDBACK error": inst},
                **{"00_Commissioning.{db_element}": ident},
                NetworkComment=f"{inst} {node['profinet_ip']}",
                ITERATOR_STRINGS=names + names,          # the 8-slot bank, then its exact copy
            )
    return t


@builds("07_Speed Control")
def build_07_speed_control(db: Database) -> Table:
    """One 01_Speed_Control_SLS FB instance per safety-encoder pair (N1/2 + N2/2 grouped by numeric index =
    the sorter number nn). The 04_SPEED outputs are the sensors' healthy members + the 'Safety Encoder
    Failure [ <FLD> ]' member; SPEED_ZERO -> SPEED_STATE_REC.SORTER_{nn}_STOPPED."""
    enc1_by_idx, enc2_by_idx, order = {}, {}, []
    for r in db.rows:
        st = str(r.get("script_type", "")).upper()
        idx = str(r.get("index", "")).strip()
        if not idx.isdigit():
            continue
        if st == "N1/2" and idx not in enc1_by_idx:
            enc1_by_idx[idx] = r
            order.append(idx)
        elif st == "N2/2":
            enc2_by_idx.setdefault(idx, r)

    t = Table("07_Speed Control")
    for idx in order:
        enc1 = enc1_by_idx[idx]
        enc2 = enc2_by_idx.get(idx)
        nn = f"{int(idx):02d}"
        t.add(
            template_type="01",
            **{"instanceOf-01_Speed_Control_SLS": f"SLS_SORTER_{nn}"},
            **{"tagName:EncoderSensor1": enc1.get("name_in_tagtable", "")},
            **{"tagName:EncoderSensor2": enc2.get("name_in_tagtable", "") if enc2 else ""},
            **{"tagName:SorterRunningIOC": f"PNC_I_SORTER-{nn} SORTER RUNNING"},
            **{"04_SPEED.{db_element:ENC1/2}": enc1.get("name_in_db", "")},
            **{"04_SPEED.{db_element:ENC2/2}": enc2.get("name_in_db", "") if enc2 else ""},
            **{"04_SPEED.{db_element:ENC}": f"Safety Encoder Failure [ {enc1.get('iol_FLD', '')} ]"},
            **{"SPEED_STATE_REC.SORTER_{index}_STOPPED": f"SORTER_{nn}_STOPPED"},
            NetworkComment=f"SORTER {nn} SPEED CONTROL",
        )
    return t


@builds("08_Gate Manager")
def build_08_gate_manager(db: Database) -> Table:
    """Two purposes (TemplateType): TT01 = one per sorter (the speed-control summary - SorterRunning,
    SORTER_nn_STOPPED / SORTER_nn_NOT_RUNNING; nn = the encoder index, as in 07), TT02 = one per Door
    DQ (the 02_Safety_Door FB; DI1/2 DI2/2 DD DR DL matched by the DQ's index). The commissioning
    bypass is the DI's node (the safety input is what gets bypassed). choice:IsSorterDoor = the door's
    IsSorterArea; choice:DoorResetNecessary = whether a same-index DR (reset input) exists. The door
    network ALSO consumes the sorter interlock (template evolution, user spec 2026-07-07):
    tagName:SorterRunningIOC + the 05_EM_STATE SORTER_nn_NOT_RUNNING member, nn resolved via the DI's
    matrix_areas x the N1/2 encoders (`sorter_nn`); tagName:DoorReset = the DR tag (the one reset
    button feeds both the open-request and the reset FB pins)."""
    t = Table("08_Gate Manager")

    # TT01 - one @ row per sorter (distinct N1/2 index), no door instance / bypass
    seen = []
    for r in db.by_type("N1/2"):
        idx = str(r.get("index", "")).strip()
        if idx.isdigit() and idx not in seen:
            seen.append(idx)
    for idx in seen:
        nn = f"{int(idx):02d}"
        t.add(
            template_type="01",
            **{"instanceOf-02_Safety_Door": ""},
            NetworkComment=f"SORTER {nn} SPEED CONTROL",
            **{"tagName:SorterRunningIOC": f"PNC_I_SORTER-{nn} SORTER- RUNNING"},
            **{"SPEED_STATE_REC.SORTER_{index}_STOPPED": f"SORTER_{nn}_STOPPED"},
            **{"05_EM_STATE.{matrix_area}_SORTER_NOT_RUNNING": f"SORTER_{nn}_NOT_RUNNING"},
            **{"00_Commissioning.{db_element}": ""},
        )

    # TT02 - one @ row per Door DQ (DI1/2 DI2/2 DD DR DL matched by the DQ's index)
    def first_of(st, idx):
        return db.first(lambda r: str(r.get("script_type", "")).upper() == st
                        and str(r.get("index", "")).strip() == idx)

    def tag(r):
        return r.get("name_in_tagtable", "") if r else ""

    def member(r):
        return r.get("name_in_db", "") if r else ""

    def sorter_nn(anchor_row):
        """The door's SORTER number, via the DI's area (user decision 2026-07-07): the first N1/2
        encoder whose matrix_areas intersect the door anchor's -> its index, 2-digit. FALLBACK (the
        real encoders are cabinet-mounted and carry NO areas): the anchor's sorter AREA number
        (`_sorter_areas` x `_area_nn` - 'AREA 1' -> '01', the area number == the sorter number).
        '' when nothing matches - a non-sorter door, which the user rules out in practice (the OP
        import flags one if it ever appears)."""
        areas = set(_as_list((anchor_row or {}).get("matrix_areas")))
        if not areas:
            return ""
        for r in db.by_type("N1/2"):
            idx = str(r.get("index", "")).strip()
            if idx.isdigit() and areas & set(_as_list(r.get("matrix_areas"))):
                return f"{int(idx):02d}"
        for area in sorted(areas & _sorter_areas(db)):
            return _area_nn(area)
        return ""

    for dq in db.by_type("DQ"):
        idx = str(dq.get("index", "")).strip()
        di1, di2, dd = first_of("DI1/2", idx), first_of("DI2/2", idx), first_of("DD", idx)
        dr, dl = first_of("DR", idx), first_of("DL", idx)
        anchor = di1 or dq
        node = _node_of(db, di1 or dq)                       # bypass the DI's node (the safety input)
        bypass = f"{node['profinet_name']} {node['profinet_ip']}".strip() if node else ""
        inst = f"SFDOOR_{anchor.get('iol_FLD', '')}"
        nn = sorter_nn(anchor)                               # the door's sorter, via the DI's area
        t.add(
            template_type="02",
            **{"instanceOf-02_Safety_Door": inst},
            NetworkComment=inst,
            **{"00_Commissioning.{db_element}": bypass},
            **{"tagName:DoorClosedCh1": tag(di1)},
            **{"tagName:DoorClosedCh2": tag(di2)},
            **{"tagName:DoorClosedDiagInput": tag(dd)},
            **{"tagName:DoorOpenRequest": tag(dr)},
            **{"tagName:DoorReset": tag(dr)},                # the one reset button feeds both FB pins
            **{"tagName:DoorSolenoidUnlock": tag(dq)},
            **{"tagName:DoorResetLamp": tag(dl)},
            # the door network consumes the sorter interlock itself (the template's TT02 references
            # these; empty Component slots break the TIA import - user spec 2026-07-07). The tag
            # spelling ('SORTER- RUNNING') is the MachineInterfaces template's native row - the tag
            # that actually exists in PLCTags (not 'SORTER RUNNING').
            **{"tagName:SorterRunningIOC": f"PNC_I_SORTER-{nn} SORTER- RUNNING" if nn else ""},
            **{"05_EM_STATE.{matrix_area}_SORTER_NOT_RUNNING": f"SORTER_{nn}_NOT_RUNNING" if nn else ""},
            **{"07_DOOR.{db_element:DI1/2}": member(di1)},
            **{"07_DOOR.{db_element:DI2/2}": member(di2)},
            **{"07_DOOR.{db_element:DD}": member(dd)},
            **{"choice:IsSorterDoor": "AlwaysTRUE" if (di1 and di1.get("IsSorterArea") == "yes") else "AlwaysFALSE"},
            **{"choice:DoorResetNecessary": "AlwaysTRUE" if dr else "AlwaysFALSE"},
        )
    return t

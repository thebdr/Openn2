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


ESTOP_SORTER_TIERS = [(4, "01"), (8, "02"), (12, "03"), (16, "04"), (20, "05")]   # (door cap, TemplateType)
ESTOP_GENERIC_RESET = "06"   # <GENERIC>:<ResetRequired>


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


@builds("04_ESTOP")
def build_04_estop(db: Database) -> Table:
    """One ESTOP network per AREA. A SORTER area (config sorter_areas) picks a door-capacity tier
    (4/8/12/16/20 = TT01-05 by its DI1/2 door count, doors padded with PAD); a GENERIC area uses
    <ResetRequired> (TT06, no door slots). Per area: the 02_COM PB/FDB cumulatives (from 03, raw-area
    naming), the 05_EM_STATE state members (UNPADDED area, as 05 + 02_COM name them), the area's B1/2 breakers
    (SafetyBreaker1/2, padded 'Always TRUE' - AND-neutral), the encoder-healthy SPEED_STATE_REC member,
    and the DI1/2 doors iterator."""
    sorter = _sorter_areas(db)
    t = Table("04_ESTOP")
    for area in db.areas():
        nn = _area_nn(area)
        is_sorter = area in sorter
        inarea = db.by_area(area)
        doors = [r["name_in_db"] for r in inarea
                 if str(r.get("script_type", "")).upper() == "DI1/2" and r.get("name_in_db")]
        breakers = [r["name_in_db"] for r in inarea
                    if str(r.get("script_type", "")).upper() == "B1/2" and r.get("name_in_db")]
        if is_sorter or doors:                                   # SORTER tier when a sorter area OR it has doors
            tier = next(((tt_, cap) for cap, tt_ in ESTOP_SORTER_TIERS if cap >= len(doors)), None)
            tt, cap = tier or (ESTOP_SORTER_TIERS[-1][1], ESTOP_SORTER_TIERS[-1][0])
            door_cells = doors + [PAD] * (cap - len(doors))      # pad the doors to the tier's slots
        else:
            tt, door_cells = ESTOP_GENERIC_RESET, doors          # GENERIC (no doors): TT06, no door slots
        # the SORTER-specific fields apply only to a real sorter area (else there is no sorter encoder).
        # nn (zero-padded) is the SORTER number (matches 07/08); the area number itself is UNPADDED below.
        encoder = f"SORTER_{nn}_ENCODER_HEALTHY" if is_sorter else ""
        power_cut = f"{area} POWER_CUT" if is_sorter else ""
        t.add(
            template_type=tt,
            **{"instanceOf-ESTOP1": f"ESTOP_{area}"},
            NetworkComment=f"{area} ESTOP",
            **{"02_COM.{matrix_area} PB": f"{area} PB"},          # raw-area: matches the 03 02_COM members
            **{"02_COM.{matrix_area} FDB": f"{area} FDB"},
            **{"05_EM_STATE.{matrix_area}_Q": f"{area} Q"},       # UNPADDED area, consistent with 02_COM + 05
            **{"05_EM_STATE.{matrix_area}_Q_DELAYED": f"{area} Q_Delayed"},
            **{"05_EM_STATE.{matrix_areas.1}_RESET": f"{area} RESET"},
            **{"05_EM_STATE.{matrix_area}_SAFETY_BREAKERS_COM": f"{area} SAFETY_BREAKERS_COM"},
            **{"05_EM_STATE.{matrix_area}_SAFETY_DOORS_COM": f"{area} SAFETY_DOORS_COM"},
            **{"05_EM_STATE.{matrix_area}_SORTER_POWER_CUT": power_cut},
            **{"SPEED_STATE_REC.SORTER_{index}_ENCODER_HEALTHY": encoder},
            **{"01_PushButton.SafetyBreaker1": breakers[0] if len(breakers) > 0 else "Always TRUE"},
            **{"01_PushButton.SafetyBreaker2": breakers[1] if len(breakers) > 1 else "Always TRUE"},
            ITERATOR_STRINGS=door_cells,
        )
    return t


# 05_Output Feedback: the 3-family capacity variants (mirrors the template's sidecar). Each tuple is
# (OnCondition cap, FeedbackInput cap, ContactorOutput cap, TemplateType); the builder picks the
# smallest variant whose capacities all cover the unit's counts.
OUTPUT_FEEDBACK_VARIANTS = [
    (1, 1, 1, 1), (1, 2, 1, 2), (1, 4, 1, 3), (1, 1, 2, 4), (1, 2, 2, 5), (1, 4, 2, 6),
    (2, 1, 1, 7), (2, 2, 1, 8), (1, 4, 1, 9), (1, 1, 2, 10), (1, 2, 2, 11), (1, 4, 2, 12),
]


def _of_variant(oncond, fb, co):
    """Smallest (OnCondition, FeedbackInput, ContactorOutput, TemplateType) variant covering the
    unit's counts, or None if none is large enough."""
    cands = [v for v in OUTPUT_FEEDBACK_VARIANTS if v[0] >= oncond and v[1] >= fb and v[2] >= co]
    return min(cands, key=lambda v: (v[0] + v[1] + v[2], v[3])) if cands else None


@builds("05_Output Feedback")
def build_05_output_feedback(db: Database) -> Table:
    """One 03_FDBACK (FDBACK) FB instance per contactor unit = the K-family signals sharing one
    (global) index: all KQ outputs + KI feedback inputs of that index. Three fixed-slot families:
      ContactorOutput = the unit's KQ(s) - 1 or a KQ1/2+KQ2/2 pair (Contactor{n}_Output = name_in_tagtable,
        QBadInput = 'QBAD_'+tag),
      FeedbackInput   = the unit's KI(s) incl. a KIx/n series, in row order (Contactor{n}_FeedbackInput),
      OnCondition     = the union of the KQ matrix areas -> 05_EM_STATE."AREA nn Q_Delayed" / "..._RESET".
    TemplateType = the smallest variant covering (OnCondition, FeedbackInput, ContactorOutput); unused
    FeedbackInput slots (a count between the 1/2/4 tiers) pad with PAD. Error member = the first KQ's
    name_in_db in 03_FDBACK_RAW; instanceOf-FDBACK = 'FDBACK_'+that KQ's FLD (+ '_<device>' per extra KQ)."""
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
            "instanceOf-FDBACK": inst,
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
            row[f"05_EM_STATE.{{matrix_areas.{i}}}"] = f"{area} Q_Delayed"
            row[f"05_EM_STATE.{{matrix_areas.{i}}}_RESET"] = f"{area} RESET"
        t.add_row(row)
    return t


@builds("06_Feedback Error")
def build_06_feedback_error(db: Database) -> Table:
    """One 03_FDBACK error FB instance per node: the node's KQ contactor-feedback members (grouped by
    address range), chunked to the FB's 8 IN/OUT slots. The iterator (each KQ's name_in_db) names a member
    in BOTH 03_FDBACK_RAW (the FDBACK ERROR n inputs) and 03_FDBACK (the ERROR n outputs); it is padded to
    8 with PAD. Commissioning_bypass is the node's '<profinet_name> <profinet_ip>'."""
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
                ITERATOR_STRINGS=names,
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
    IsSorterArea; choice:DoorResetNecessary = whether a same-index DR (reset input) exists."""
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
            **{"tagName:SorterRunningIOC": f"PNC_I_SORTER-{nn} SORTER RUNNING"},
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

    for dq in db.by_type("DQ"):
        idx = str(dq.get("index", "")).strip()
        di1, di2, dd = first_of("DI1/2", idx), first_of("DI2/2", idx), first_of("DD", idx)
        dr, dl = first_of("DR", idx), first_of("DL", idx)
        anchor = di1 or dq
        node = _node_of(db, di1 or dq)                       # bypass the DI's node (the safety input)
        bypass = f"{node['profinet_name']} {node['profinet_ip']}".strip() if node else ""
        inst = f"SFDOOR_{anchor.get('iol_FLD', '')}"
        t.add(
            template_type="02",
            **{"instanceOf-02_Safety_Door": inst},
            NetworkComment=inst,
            **{"00_Commissioning.{db_element}": bypass},
            **{"tagName:DoorClosedCh1": tag(di1)},
            **{"tagName:DoorClosedCh2": tag(di2)},
            **{"tagName:DoorClosedDiagInput": tag(dd)},
            **{"tagName:DoorOpenRequest": tag(dr)},
            **{"tagName:DoorSolenoidUnlock": tag(dq)},
            **{"tagName:DoorResetLamp": tag(dl)},
            **{"07_DOOR.{db_element:DI1/2}": member(di1)},
            **{"07_DOOR.{db_element:DI2/2}": member(di2)},
            **{"07_DOOR.{db_element:DD}": member(dd)},
            **{"choice:IsSorterDoor": "Always TRUE" if (di1 and di1.get("IsSorterArea") == "yes") else "Always FALSE"},
            **{"choice:DoorResetNecessary": "Always TRUE" if dr else "Always FALSE"},
        )
    return t

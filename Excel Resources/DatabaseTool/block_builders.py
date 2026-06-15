#!/usr/bin/env python3
"""block_builders.py — YOU edit this. One function per Software Block template.

Each builder receives `db` (the CentralDatabase: a list of staged row dicts — canonical
columns + matrix_areas + IsSorterArea + name_in_db + subnet_name + the per-node I/Q
byte-range columns) and returns a list of INSTANCES, one per @row in the generated CSV.

An instance is a dict { "<!!key$$ name>": value }:
  * value = str          -> one cell (a scalar placeholder)
  * value = list[str]    -> the horizontal ITERATOR (one such key per instance; the
                            writer pads it to capacity and computes TemplateType)
  * optional "_pad": str -> override the pad element for this instance (default PAD)

Markers above each builder: `# $keep` preserve, `# $replace` re-stub on scan.
"""
from __future__ import annotations
import csv
import os
import re

PAD = "AlwaysTRUE"   # default ITERATOR padding element (override per-instance via "_pad")

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES = os.path.join(_HERE, "Templates", "Tia Portal Software Blocks")


# --------------------------------------------------------------------------- #
# helpers you may use (or ignore and write your own)                          #
# --------------------------------------------------------------------------- #
def unique_areas(db: list) -> list:
    """Distinct AREA n across the CentralDatabase (matrix_areas is '|'-joined)."""
    areas = set()
    for r in db:
        for a in str(r.get("matrix_areas", "")).split("|"):
            if a.strip():
                areas.add(a.strip())
    return sorted(areas)


def area_index(area: str) -> str:
    """'AREA 1' -> '1' (trailing digits)."""
    m = re.search(r"(\d+)\s*$", str(area))
    return m.group(1) if m else ""


def names_in_db(db: list, *, script_type=None, area=None) -> list:
    """name_in_db of rows matching the given filters (each filter optional)."""
    out = []
    for r in db:
        if script_type is not None and r.get("script_type") != script_type:
            continue
        if area is not None and area not in str(r.get("matrix_areas", "")).split("|"):
            continue
        if r.get("name_in_db"):
            out.append(r["name_in_db"])
    return out


def template_capacity(stem: str) -> int:
    """Largest #Templates Capacity from the template's sidecar CSV (the chunk size)."""
    caps = []
    p = os.path.join(_TEMPLATES, stem + ".csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and str(row[0]).strip().isdigit():
                    caps.append(int(row[0]))
    return max(caps) if caps else 0


def chunked(seq, n) -> list:
    """Split into chunks of <= n (n<=0 -> a single chunk)."""
    seq = list(seq)
    if n and n > 0:
        return [seq[i:i + n] for i in range(0, len(seq), n)] or [[]]
    return [seq] if seq else []


def _addr_byte(bit):
    b = str(bit or "").strip().upper()
    if b[:1] in ("I", "Q") and "." in b:
        try:
            return b[0], int(b[1:b.index(".")])
        except ValueError:
            return None
    return None


def nodes(db: list) -> list:
    """The I/O node rows (those carrying a profinet_name)."""
    return [r for r in db if r.get("profinet_name")]


def node_of(db: list, row) -> dict | None:
    """The node whose I/Q byte range contains this signal's address (else None)."""
    ab = _addr_byte(row.get("bit"))
    if not ab:
        return None
    kind, byte = ab
    sk, ek = f"{kind}_startByte", f"{kind}_endByte"
    for n in nodes(db):
        s, e = n.get(sk, ""), n.get(ek, "")
        if s != "" and int(s) <= byte <= int(e):
            return n
    return None


def group_by_node(db: list, script_type: str) -> list:
    """[(node_row, [name_in_db of that script_type on the node])], grouped by node."""
    groups = {}
    for r in db:
        if r.get("script_type") == script_type and r.get("name_in_db"):
            n = node_of(db, r)
            if n is not None:
                groups.setdefault(id(n), (n, []))[1].append(r["name_in_db"])
    return list(groups.values())


def sorters(db: list) -> list:
    """[(ioc_row, index:int)] for IOC rows whose Index is SORTER-nn."""
    out = []
    for r in db:
        if str(r.get("script_type", "")).upper() == "IOC":
            m = re.match(r"^\s*SORTER-?(\d+)\s*$", str(r.get("index", "")), re.I)
            if m:
                out.append((r, int(m.group(1))))
    return out


def rows_by_index(db: list, index_value, script_type=None) -> list:
    """Rows whose Index column equals index_value (optionally of a script_type)."""
    return [r for r in db
            if str(r.get("index", "")) == str(index_value)
            and (script_type is None or r.get("script_type") == script_type)]


def _num_index(r):
    """Numeric element Index, e.g. '0001' -> 1; None when not numeric (e.g. 'SORTER-01')."""
    s = str(r.get("index", "")).strip()
    return int(s) if s.isdigit() else None


def encoders_of(db: list, sorter_num: int, channel: str) -> list:
    """ENC rows of `channel` ('ENC1/2'/'ENC2/2') belonging to sorter `sorter_num` - the
    encoders carry a numeric Index ('0001') equal to the sorter's number (SORTER-01)."""
    return [r for r in db
            if r.get("script_type") == channel and _num_index(r) == sorter_num]


def _first(seq):
    return seq[0] if seq else None


def _fld(r) -> str:
    """FUNCTIONAL UNIT + LOCATION + DEVICE, as written (matches outputs.fld)."""
    return (str(r.get("functional_unit") or "").strip()
            + str(r.get("location") or "").strip()
            + str(r.get("device") or "").strip())


def rows_of(db: list, prefix: str) -> list:
    """Rows whose script_type starts with `prefix` (e.g. 'KQ' matches KQ, KQ1/2, KQ2/2)."""
    return [r for r in db if str(r.get("script_type", "")).upper().startswith(prefix.upper())]


# --------------------------------------------------------------------------- #
# one builder per template — EDIT THESE                                       #
# --------------------------------------------------------------------------- #

# $keep
def build_00_only_for_commissioning(db: list) -> list:
    """TEMPLATE--v1.0--00_Only for Commissioning.xml  (one @row; the commissioning-bypass
    member of every I/O node as the horizontal ITERATOR). No sidecar -> no padding.
    keys: Bypass_memberOf:00_Commissioning"""
    bypasses = [f"{n['profinet_name']}_{n['subnet_name']}" for n in nodes(db)]
    if not bypasses:
        return []
    return [{"Bypass_memberOf:00_Commissioning": bypasses}]


# $keep
def build_02_em_push_button(db: list) -> list:
    """TEMPLATE--v1.0--02_EM Push Button.xml  (one @row per I/O node carrying E1/2 inputs,
    chunked so the ITERATOR never exceeds the template capacity).
    keys: Bypass_memberOf:00_Commissioning, instanceOf:00_Push-Button_Input, NetworkComment, ITERATOR_STRINGS"""
    cap = template_capacity("TEMPLATE--v1.0--02_EM Push Button")
    out = []
    for node, members in group_by_node(db, "E1/2"):                 # node <- address-range match
        for i, chunk in enumerate(chunked(members, cap), start=1):  # split if > capacity
            inst = f"EMPB_{node['profinet_name']}_{i}"               # unique instance name
            out.append({
                "instanceOf:00_Push-Button_Input":  inst,
                "NetworkComment":                   f"{inst} {node['profinet_ip']}",
                "Bypass_memberOf:00_Commissioning": f"{node['profinet_name']}_{node['subnet_name']}",
                "ITERATOR_STRINGS":                 chunk,           # name_in_db of the E1/2's
            })
    return out


# $keep
def build_03_zone_cumulative(db: list) -> list:
    """TEMPLATE--v1.0--03_Zone Cumulative.xml
    keys: NetworkComment, nameOfDB, memberOf:02_COM, ITERATOR_STRINGS

    EXAMPLE gathering (adjust to your real rules): for each AREA, one @row per
    memberOf — pushbuttons (E1/2) and feedback (KQ); the ITERATOR is the name_in_db
    of the matching rows in that area."""

    instances = []
    for area in unique_areas(db):
        areaIdx = area_index(area)
        for suffix, stype in (("PB", "E1/2"), ("FDB", "KQ")):
            instances.append({
                "NetworkComment":  f"{area} - SYSTEM",
                "nameOfDB":        "02_COM",
                "memberOf:02_COM": f"A{areaIdx}_{suffix}",
                "ITERATOR_STRINGS": names_in_db(db, script_type=stype, area=area),
            })
    return instances


# $keep
def build_04_estop(db: list) -> list:
    """TEMPLATE--v1.0--04_ESTOP.xml  (one @row per AREA).

      areaPB/areaFDB_memberOf:02_COM     = A{n}_PB / A{n}_FDB  (the members 03 creates)
      SafetyBreaker1/2_memberOf:01_PushButton = the area's B1/2 name_in_db (slots 1, 2)
      ITERATOR_STRINGS                   = the area's DI1/2 door name_in_db
      areaEncoderBroken_memberOf:SPEED_STATE_REC = 'SORTER{nn}_ENCODER_BROKEN' (nn=area_index;
                                           encoders aren't in the C&E, so default to area_index)
      the 05_EM_STATE members            = 'AREA {nn} <suffix>' (Q / Q_Delayed / RESET /
                                           SAFETY_BREAKERS_COM / SAFETY_DOORS_COM / POWER_CUT)
      instanceOf:ESTOP1 = 'ESTOP_{area}'; NetworkComment = '{area} ESTOP'
    keys: areaPB_memberOf:02_COM, areaFDB_memberOf:02_COM, Reset1_memberOf:05_EM_STATE,
    areaQ_memberOf:05_EM_STATE, areaQDelayed_memberOf:05_EM_STATE, SafetyBreaker1_memberOf:01_PushButton,
    SafetyBreaker2_memberOf:01_PushButton, areaSafetyBreakersCom_memberOf:05_EM_STATE, ITERATOR_STRINGS,
    areaSafetyDoorsCom_memberOf:05_EM_STATE, areaEncoderBroken_memberOf:SPEED_STATE_REC,
    areaPowerCut_memberOf:05_EM_STATE, instanceOf:ESTOP1, NetworkComment
    """
    out = []
    for area in unique_areas(db):
        idx = area_index(area)
        nn = f"{int(idx):02d}" if idx else area
        breakers = names_in_db(db, script_type="B1/2", area=area)     # safety breakers in the area
        doors = names_in_db(db, script_type="DI1/2", area=area)       # door safety inputs (ITERATOR)
        out.append({
            "instanceOf:ESTOP1":                          f"ESTOP_{area}",
            "NetworkComment":                             f"{area} ESTOP",
            "areaPB_memberOf:02_COM":                     f"A{idx}_PB",
            "areaFDB_memberOf:02_COM":                    f"A{idx}_FDB",
            "areaQ_memberOf:05_EM_STATE":                 f"AREA {nn} Q",
            "areaQDelayed_memberOf:05_EM_STATE":          f"AREA {nn} Q_Delayed",
            "Reset1_memberOf:05_EM_STATE":                f"AREA {nn} RESET",
            "areaSafetyBreakersCom_memberOf:05_EM_STATE": f"AREA {nn} SAFETY_BREAKERS_COM",
            "areaSafetyDoorsCom_memberOf:05_EM_STATE":    f"AREA {nn} SAFETY_DOORS_COM",
            "areaPowerCut_memberOf:05_EM_STATE":          f"AREA {nn} POWER_CUT",
            "areaEncoderBroken_memberOf:SPEED_STATE_REC": f"SORTER{nn}_ENCODER_BROKEN",
            "SafetyBreaker1_memberOf:01_PushButton":      breakers[0] if len(breakers) > 0 else "",
            "SafetyBreaker2_memberOf:01_PushButton":      breakers[1] if len(breakers) > 1 else "",
            "ITERATOR_STRINGS":                           doors,
        })
    return out


# $keep
def build_05_output_feedback(db: list) -> list:
    """TEMPLATE--v1.1--05_Output Feedback.xml  (one @row per KQ unit).

    Families (fixed numbered slots, not one ITERATOR):
      ContactorOutput  <- the unit's KQ channel(s); Contactor{n}_Output = KQ name_in_tagtable
      FeedbackInput    <- KI rows of the same device(s); Contactor{n}_FeedbackInput = KI name_in_tagtable
      OnCondition      <- one per matrix_area of the KQ; value 'AREA {nn} Q_Delayed' (+ Reset 'AREA {nn} RESET')
    Contactor{n}_QBadInput = 'QBAD_' + that output's name_in_tagtable.
    Error_memberOf:03_FDBACK_RAW = the KQ's name_in_db (it's a member of 03_FDBACK_RAW).
    instanceOf:FDBACK = 'FDBACK_' + the KQ's FLD (+ '_<device>' per extra KQ channel of the unit).

    NOTE: TemplateType is NOT set here - it comes from the 3-family capacity sidecar
    (OnCondition / FeedbackInput / ContactorOutput), which needs its #Templates Index
    column finished + a multi-family engine pass. Slots are filled; sizing is pending.
    keys: OnCondition1_memberOf:05_EM_STATE, tagName:Contactor1_FeedbackInput, tagName:Contactor1_QBadInput,
    Reset1_memberOf:05_EM_STATE, tagName:Contactor1_Output, Error_memberOf:03_FDBACK_RAW, instanceOf:FDBACK,
    NetworkComment, tagName:Contactor2_FeedbackInput, tagName:Contactor3_FeedbackInput,
    tagName:Contactor4_FeedbackInput, tagName:Contactor2_QBadInput, tagName:Contactor2_Output,
    OnCondition2_memberOf:05_EM_STATE, Reset2_memberOf:05_EM_STATE
    """
    out = []
    # group KQ rows into units by device (channels KQ1/2+KQ2/2 of one device -> one unit)
    units = {}
    for kq in rows_of(db, "KQ"):
        units.setdefault(kq.get("device", ""), []).append(kq)

    for dev, kqs in units.items():
        kq0 = kqs[0]
        inst_name = "FDBACK_" + _fld(kq0)
        for extra in kqs[1:]:                       # extra KQ channels of the unit
            inst_name += "_" + str(extra.get("device", ""))
        inst = {
            "instanceOf:FDBACK":            inst_name,
            "NetworkComment":               inst_name,                 # TODO: confirm comment format
            "Error_memberOf:03_FDBACK_RAW": kq0.get("name_in_db", ""),
        }
        # ContactorOutput + its QBadInput, one slot per KQ channel
        for n, kq in enumerate(kqs, start=1):
            tag = kq.get("name_in_tagtable", "")
            inst[f"tagName:Contactor{n}_Output"] = tag
            inst[f"tagName:Contactor{n}_QBadInput"] = f"QBAD_{tag}" if tag else ""
        # FeedbackInput, one slot per KI of the unit's device(s)
        devices = {kq.get("device", "") for kq in kqs}
        kis = [r for r in rows_of(db, "KI") if r.get("device", "") in devices]
        for n, ki in enumerate(kis, start=1):
            inst[f"tagName:Contactor{n}_FeedbackInput"] = ki.get("name_in_tagtable", "")
        # OnCondition + Reset, one slot per area the KQ belongs to
        areas = [a for a in str(kq0.get("matrix_areas", "")).split("|") if a]
        for i, area in enumerate(areas, start=1):
            nn = f"{int(area_index(area)):02d}" if area_index(area) else area
            inst[f"OnCondition{i}_memberOf:05_EM_STATE"] = f"AREA {nn} Q_Delayed"
            inst[f"Reset{i}_memberOf:05_EM_STATE"] = f"AREA {nn} RESET"
        # per-family counts -> the engine picks TemplateType from the 3-family sidecar
        inst["_sizes"] = {"OnCondition": len(areas), "FeedbackInput": len(kis),
                          "ContactorOutput": len(kqs)}
        out.append(inst)
    return out


# $keep
def build_06_feedback_error(db: list) -> list:
    """TEMPLATE--v1.0--06_Feedback Error.xml  (one @row per I/O node carrying KQ feedback).
    keys: Bypass_memberOf:00_Commissioning, instanceOf:03_FDBACK error, NetworkComment, ITERATOR_STRINGS"""
    cap = template_capacity("TEMPLATE--v1.0--06_Feedback Error")
    out = []
    for node, members in group_by_node(db, "KQ"):
        for i, chunk in enumerate(chunked(members, cap), start=1):
            inst = f"FDBK_ERR_{node['profinet_name']}_{i}"
            out.append({
                "instanceOf:03_FDBACK error":       inst,
                "NetworkComment":                   f"{inst} {node['profinet_ip']}",
                "Bypass_memberOf:00_Commissioning": f"{node['profinet_name']}_{node['subnet_name']}",
                "ITERATOR_STRINGS":                 chunk,
            })
    return out


# $keep
def build_07_speed_control(db: list) -> list:
    """TEMPLATE--v1.0--07_Speed Control.xml  (one @row per sorter; encoders linked by Index).
    keys: tagName:EncoderSensor1, tagName:EncoderSensor2, tagName:SorterRunningIOC,
    areaSorterStopped_memberOf:SPEED_STATE_REC, EncoderSensor1Faulty_memberOf:04_SPEED,
    EncoderSensor2Faulty_memberOf:04_SPEED, EncoderBroken_memberOf:04_SPEED, NetworkComment"""
    out = []
    for ioc, num in sorters(db):
        nn = f"{num:02d}"                                # zero-padded sorter number (01, 02, ...)
        enc1 = _first(encoders_of(db, num, "ENC1/2"))   # encoders linked by numeric Index == num
        enc2 = _first(encoders_of(db, num, "ENC2/2"))
        member1 = enc1["name_in_db"] if enc1 else ""    # DB member (with 'Working - No Fault')
        member2 = enc2["name_in_db"] if enc2 else ""
        broken = re.sub(r"\s*Sensor\s*[12]\b", "", member1).strip()   # drop 'Sensor N' -> common name
        out.append({
            "tagName:EncoderSensor1":                      enc1["name_in_tagtable"] if enc1 else "",
            "tagName:EncoderSensor2":                      enc2["name_in_tagtable"] if enc2 else "",
            "tagName:SorterRunningIOC":                    f"PNC_I_Sorter{nn} SORTER RUNNING",
            "EncoderSensor1Faulty_memberOf:04_SPEED":      member1,
            "EncoderSensor2Faulty_memberOf:04_SPEED":      member2,
            "EncoderBroken_memberOf:04_SPEED":             broken,
            "areaSorterStopped_memberOf:SPEED_STATE_REC":  f"SORTER_{nn}_STOPPED",
            "NetworkComment":                              f"SORTER {nn} SPEED CONTROL",
        })
    return out


# $keep
def build_08_gate_manager(db: list) -> list:
    """TEMPLATE--v1.0--08_Gate Manager.xml  (purpose sidecar: 1 per Sorter = TemplateType 1,
    1 per Door DQ = TemplateType 2; the builder sets _template_type per @row).

    Sorter @row (TT 1, one per IOC SORTER-nn):
      tagName:SorterRunningIOC = 'PNC_I_Sorter{nn} SORTER RUNNING'         (from 07)
      areaSorterStopped_memberOf:SPEED_STATE_REC = 'SORTER_{nn}_STOPPED'    (from 07)
      areaSorterNotRunning_memberOf:05_EM_STATE  = 'SORTER_{nn}_NOT_RUNNING'
    Door @row (TT 2, one per DQ; DI1/2 DI2/2 DD DR DL matched by the DQ's Index):
      tagName Door* = name_in_tagtable of DI1/2(Ch1) DI2/2(Ch2) DD(DiagInput) DR(OpenRequest)
                      DQ(SolenoidUnlock) DL(ResetLamp)
      doorIsClosedSafe/Info/doorAlarm_memberOf:07_DOOR = name_in_db of DI1/2 / DI2/2 / DD
      choice:IsSorterDoor / choice:DoorResetNecessary = 'Always TRUE' if a same-Index DR
                      exists, else 'Always FALSE'
      instanceOf:02_Safety_Door = 'DOOR_' + DQ fld; Bypass = the DQ node's bypass
    Sorter @row: instanceOf = 'SFDOOR_' + FLD of the sorter's DI1/2 (linked by index);
      Bypass = the node that DI1/2 is wired to.
    Bypass_memberOf:00_Commissioning = {profinet_name}_{subnet_name} of the @row's node.
    keys: areaSorterStopped_memberOf:SPEED_STATE_REC, areaSorterNotRunning_memberOf:05_EM_STATE,
    Bypass_memberOf:00_Commissioning, tagName:DoorClosedDiagInput, tagName:DoorClosedCh1,
    tagName:DoorClosedCh2, tagName:SorterRunningIOC, tagName:DoorOpenRequest, choice:IsSorterDoor,
    choice:DoorResetNecessary, tagName:DoorSolenoidUnlock, doorIsClosedSafe_memberOf:07_DOOR,
    doorIsClosedInfo_memberOf:07_DOOR, doorAlarm_memberOf:07_DOOR, tagName:DoorResetLamp,
    instanceOf:02_Safety_Door, NetworkComment
    """
    def tag(r):
        return r["name_in_tagtable"] if r else ""

    def member(r):
        return r["name_in_db"] if r else ""

    out = []
    # template 01 - one @row per sorter
    for ioc, num in sorters(db):
        nn = f"{num:02d}"
        # the sorter's safety door = the DI1/2 linked by index (fall back to the first);
        # instanceOf + Bypass come from it (FLD + the node it's wired to)
        di1 = _first([r for r in rows_of(db, "DI1/2") if _num_index(r) == num]) or _first(rows_of(db, "DI1/2"))
        node = node_of(db, di1) if di1 else None
        out.append({
            "_template_type":                              1,
            "instanceOf:02_Safety_Door":                   f"SFDOOR_{_fld(di1)}" if di1 else f"SFDOOR_SORTER_{nn}",
            "NetworkComment":                              f"SORTER {nn} GATE MANAGER",
            "tagName:SorterRunningIOC":                    f"PNC_I_Sorter{nn} SORTER RUNNING",
            "areaSorterStopped_memberOf:SPEED_STATE_REC":  f"SORTER_{nn}_STOPPED",
            "areaSorterNotRunning_memberOf:05_EM_STATE":   f"SORTER_{nn}_NOT_RUNNING",
            "Bypass_memberOf:00_Commissioning":            f"{node['profinet_name']}_{node['subnet_name']}" if node else "",
        })

    # template 02 - one @row per Door DQ (DI1/2 DI2/2 DD DR DL matched by the DQ's Index)
    for dq in rows_of(db, "DQ"):
        idx = dq.get("index", "")
        di1 = _first(rows_by_index(db, idx, "DI1/2"))
        di2 = _first(rows_by_index(db, idx, "DI2/2"))
        dd = _first(rows_by_index(db, idx, "DD"))
        dr = _first(rows_by_index(db, idx, "DR"))
        dl = _first(rows_by_index(db, idx, "DL"))
        has_dr = "Always TRUE" if dr else "Always FALSE"
        node = node_of(db, dq)
        bypass = f"{node['profinet_name']}_{node['subnet_name']}" if node else ""
        inst = f"DOOR_{_fld(dq)}"
        out.append({
            "_template_type":                    2,
            "instanceOf:02_Safety_Door":         inst,
            "NetworkComment":                    inst,
            "Bypass_memberOf:00_Commissioning":  bypass,
            "tagName:DoorClosedCh1":             tag(di1),
            "tagName:DoorClosedCh2":             tag(di2),
            "tagName:DoorClosedDiagInput":       tag(dd),
            "tagName:DoorOpenRequest":           tag(dr),
            "tagName:DoorSolenoidUnlock":        tag(dq),
            "tagName:DoorResetLamp":             tag(dl),
            "doorIsClosedSafe_memberOf:07_DOOR": member(di1),
            "doorIsClosedInfo_memberOf:07_DOOR": member(di2),
            "doorAlarm_memberOf:07_DOOR":        member(dd),
            "choice:IsSorterDoor":               has_dr,
            "choice:DoorResetNecessary":         has_dr,
        })
    return out


# template file stem -> builder
BUILDERS = {
    "TEMPLATE--v1.0--00_Only for Commissioning": build_00_only_for_commissioning,
    "TEMPLATE--v1.0--02_EM Push Button":         build_02_em_push_button,
    "TEMPLATE--v1.0--03_Zone Cumulative":        build_03_zone_cumulative,
    "TEMPLATE--v1.0--04_ESTOP":                  build_04_estop,
    "TEMPLATE--v1.1--05_Output Feedback":        build_05_output_feedback,
    "TEMPLATE--v1.0--06_Feedback Error":         build_06_feedback_error,
    "TEMPLATE--v1.0--07_Speed Control":          build_07_speed_control,
    "TEMPLATE--v1.0--08_Gate Manager":           build_08_gate_manager,
}

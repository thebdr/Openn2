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


def _first(seq):
    return seq[0] if seq else None


# --------------------------------------------------------------------------- #
# one builder per template — EDIT THESE                                       #
# --------------------------------------------------------------------------- #

# $replace
def build_00_only_for_commissioning(db: list) -> list:
    """TEMPLATE--v1.0--00_Only for Commissioning.xml - TODO: gather instances.
    keys: Bypass_memberOf:00_Commissioning
    """
    return []


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


# $replace
def build_04_estop(db: list) -> list:
    """TEMPLATE--v1.0--04_ESTOP.xml - TODO: gather instances.
    keys: areaPB_memberOf:02_COM, areaFDB_memberOf:02_COM, Reset1_memberOf:05_EM_STATE,
    areaQ_memberOf:05_EM_STATE, areaQDelayed_memberOf:05_EM_STATE, SafetyBreaker1_memberOf:01_PushButton,
    SafetyBreaker2_memberOf:01_PushButton, areaSafetyBreakersCom_memberOf:05_EM_STATE, ITERATOR_STRINGS,
    areaSafetyDoorsCom_memberOf:05_EM_STATE, areaEncoderBroken_memberOf:SPEED_STATE_REC,
    areaPowerCut_memberOf:05_EM_STATE, instanceOf:ESTOP1, NetworkComment
    """
    return []


# $replace
def build_05_output_feedback(db: list) -> list:
    """TEMPLATE--v1.1--05_Output Feedback.xml - TODO: gather instances.
    keys: OnCondition1_memberOf:05_EM_STATE, tagName:Contactor1_FeedbackInput, tagName:Contactor1_QBadInput,
    Reset1_memberOf:05_EM_STATE, tagName:Contactor1_Output, Error_memberOf:03_FDBACK_RAW, instanceOf:FDBACK,
    NetworkComment, tagName:Contactor2_FeedbackInput, tagName:Contactor3_FeedbackInput,
    tagName:Contactor4_FeedbackInput, tagName:Contactor2_QBadInput, tagName:Contactor2_Output,
    OnCondition2_memberOf:05_EM_STATE, Reset2_memberOf:05_EM_STATE
    """
    return []


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
        x = num                                   # sorter number (1, 2, ...); adjust format if needed
        idx = ioc.get("index", "")                # e.g. SORTER-01
        enc1 = _first(rows_by_index(db, idx, "ENC1/2"))   # TODO: confirm the encoders carry this Index
        enc2 = _first(rows_by_index(db, idx, "ENC2/2"))
        s1 = enc1["name_in_db"] if enc1 else ""
        s2 = enc2["name_in_db"] if enc2 else ""
        broken = re.sub(r"\s*Sensor\s*[12]\b", "", s1).strip()   # drop 'Sensor N' -> encoder common name
        out.append({
            "tagName:EncoderSensor1":                      s1,
            "tagName:EncoderSensor2":                      s2,
            "tagName:SorterRunningIOC":                    ioc.get("name_in_db", ""),  # TODO: the sorter-running signal
            "EncoderSensor1Faulty_memberOf:04_SPEED":      s1,
            "EncoderSensor2Faulty_memberOf:04_SPEED":      s2,
            "EncoderBroken_memberOf:04_SPEED":             broken,
            "areaSorterStopped_memberOf:SPEED_STATE_REC":  f"SORTER_{x}_STOPPED",
            "NetworkComment":                              f"SORTER {x} SPEED CONTROL",
        })
    return out


# $replace
def build_08_gate_manager(db: list) -> list:
    """TEMPLATE--v1.0--08_Gate Manager.xml - TODO: gather instances.
    keys: areaSorterStopped_memberOf:SPEED_STATE_REC, areaSorterNotRunning_memberOf:05_EM_STATE,
    Bypass_memberOf:00_Commissioning, tagName:DoorClosedDiagInput, tagName:DoorClosedCh1,
    tagName:DoorClosedCh2, tagName:SorterRunningIOC, tagName:DoorOpenRequest, choice:IsSorterDoor,
    choice:DoorResetNecessary, tagName:DoorSolenoidUnlock, doorIsClosedSafe_memberOf:07_DOOR,
    doorIsClosedInfo_memberOf:07_DOOR, doorAlarm_memberOf:07_DOOR, tagName:DoorResetLamp,
    instanceOf:02_Safety_Door, NetworkComment
    """
    return []


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

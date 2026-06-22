"""Data-independent cases for the per-template software-block builders (domain/blocks/builders.py).

These are SMALL synthetic-row checks of each hand-written builder's mapping logic - the green-gate
counterpart to the real-document CSVs the user reviews. One group of cases per template, added as
each builder is blessed. (test_blocks.py covers the skeleton; this covers the builders.)
"""
from _harness import run, eq, ok

from pipeline3.domain.blocks.database import Database
from pipeline3.domain.blocks.builders import (
    build_00_commissioning, build_02_em_push_button, build_03_zone_cumulative,
    build_04_estop, build_05_output_feedback, build_06_feedback_error,
    build_07_speed_control, build_08_gate_manager, PAD)


# --------------------------------------------------------------------------- 00 --------------- #
def _commissioning_rows():
    """Two diag IO-device nodes (carry a name_in_db), one PLC head + one partner card (profinet_name
    but no name_in_db -> excluded), and a plain signal (no profinet_name -> excluded)."""
    return [
        {"profinet_name": "n0010-aaa", "profinet_ip": "192.168.50.10",
         "name_in_db": "n0010-aaa 192.168.50.10"},                       # diag node
        {"profinet_name": "head-plc",  "profinet_ip": "192.168.50.1",  "name_in_db": ""},   # head: out
        {"profinet_name": "card-k2",   "profinet_ip": "192.168.50.1",  "name_in_db": ""},   # partner: out
        {"profinet_name": "n0006-bbb", "profinet_ip": "192.168.50.6",
         "name_in_db": "n0006-bbb 192.168.50.6"},                        # diag node
        {"script_type": "A", "name_in_db": "Some Signal"},               # not a node (no profinet_name): out
    ]


def test_00_commissioning_filters_to_diag_nodes():
    t = build_00_commissioning(Database(_commissioning_rows()))
    eq(len(t), 2, "only the two name_in_db-carrying nodes (heads/partner-cards/plain signals dropped)")
    eq(t.columns, ["TemplateType", "00_Commissioning.{db_element}", "NetworkComment"])


def test_00_commissioning_member_and_title_are_pname_ip():
    t = build_00_commissioning(Database(_commissioning_rows()))
    eq([r["00_Commissioning.{db_element}"] for r in t.rows],
       ["n0010-aaa 192.168.50.10", "n0006-bbb 192.168.50.6"], "member = '<profinet_name> <profinet_ip>'")
    for r in t.rows:
        eq(r["NetworkComment"], r["00_Commissioning.{db_element}"], "title mirrors the member")
        eq(r["TemplateType"], "01")


def test_00_commissioning_empty_when_no_nodes():
    eq(len(build_00_commissioning(Database([{"script_type": "A", "name_in_db": "x"}]))), 0)


# --------------------------------------------------------------------------- 02 --------------- #
def _pb_node(pname, ip, lo, hi):
    return {"profinet_name": pname, "profinet_ip": ip,
            "I_startByte": lo, "I_endByte": hi, "Q_startByte": "", "Q_endByte": ""}


def _pb(bit, name):
    return {"script_type": "E1/2", "bit": bit, "name_in_db": name}


def test_02_one_instance_per_node_padded_to_four():
    rows = [_pb_node("n5-ms1", "192.168.50.5", 20, 23), _pb("I20.0", "PB one"), _pb("I21.0", "PB two")]
    t = build_02_em_push_button(Database(rows))
    eq(len(t), 1, "one instance for a node with <=4 push buttons")
    r = t.rows[0]
    eq(r["instanceOf-00_Push-Button_Input"], "EMPB_n5-ms1_1")
    eq(r["00_Commissioning.{db_element}"], "n5-ms1 192.168.50.5", "Bypass = node '<pname> <ip>'")
    eq(r["NetworkComment"], "EMPB_n5-ms1_1 192.168.50.5")
    eq(r["ITERATOR_STRINGS"], ["PB one", "PB two", PAD, PAD], "iterator padded to the 4 fixed slots")


def test_02_chunks_over_four_into_multiple_instances():
    node = _pb_node("nbig", "10.0.0.9", 0, 9)
    pbs = [_pb(f"I{b}.0", f"PB{b}") for b in range(5)]      # 5 push buttons on one node
    t = build_02_em_push_button(Database([node, *pbs]))
    eq(len(t), 2, "5 PBs -> 2 instances (4 + 1)")
    eq([r["instanceOf-00_Push-Button_Input"] for r in t.rows], ["EMPB_nbig_1", "EMPB_nbig_2"])
    eq(len(t.rows[0]["ITERATOR_STRINGS"]), 4)
    eq(t.rows[1]["ITERATOR_STRINGS"], ["PB4", PAD, PAD, PAD], "second chunk padded")


def test_02_pad_is_no_operation():
    eq(PAD, "No Operation", "pad uses the ph520 DB no-op member, not Always TRUE/FALSE")


# --------------------------------------------------------------------------- 04 --------------- #
def test_04_estop_variant_and_sorter_fields():
    rows = [
        # AREA 1 = sorter (a single-area row flagged IsSorterArea pins it); 1 door + 1 breaker
        {"matrix_areas": "AREA 1", "script_type": "E1/2", "IsSorterArea": "yes", "name_in_db": "PB1"},
        {"matrix_areas": "AREA 1", "script_type": "DI1/2", "name_in_db": "Door A1"},
        {"matrix_areas": "AREA 1", "script_type": "B1/2", "name_in_db": "Breaker A1"},
        # AREA 2 = NON-sorter but WITH a door
        {"matrix_areas": "AREA 2", "script_type": "E1/2", "IsSorterArea": "", "name_in_db": "PB2"},
        {"matrix_areas": "AREA 2", "script_type": "DI1/2", "name_in_db": "Door A2"},
        # AREA 3 = non-sorter, no doors
        {"matrix_areas": "AREA 3", "script_type": "E1/2", "IsSorterArea": "", "name_in_db": "PB3"},
    ]
    by_area = {r["instanceOf-ESTOP1"]: r for r in build_04_estop(Database(rows)).rows}
    a1 = by_area["ESTOP_AREA 1"]
    eq(a1["TemplateType"], "01", "sorter area, 1 door -> SORTER tier (cap 4)")
    eq(a1["02_COM.{matrix_area} PB"], "AREA 1 PB", "raw-area 02_COM (matches 03)")
    eq(a1["05_EM_STATE.{matrix_area}_Q"], "AREA 1 Q", "UNPADDED area (matches 02_COM + 05)")
    eq(a1["SPEED_STATE_REC.SORTER_{index}_ENCODER_HEALTHY"], "SORTER_01_ENCODER_HEALTHY", "SORTER number stays padded")
    eq(a1["05_EM_STATE.{matrix_area}_SORTER_POWER_CUT"], "AREA 1 POWER_CUT")
    eq(a1["01_PushButton.SafetyBreaker1"], "Breaker A1")
    eq(a1["01_PushButton.SafetyBreaker2"], "Always TRUE", "2nd breaker slot AND-neutral default (kept)")
    eq(a1["ITERATOR_STRINGS"], ["Door A1", PAD, PAD, PAD], "1 door padded to the tier's 4 slots")
    a2 = by_area["ESTOP_AREA 2"]
    eq(a2["TemplateType"], "01", "non-sorter WITH doors -> still a SORTER tier")
    eq(a2["SPEED_STATE_REC.SORTER_{index}_ENCODER_HEALTHY"], "", "non-sorter -> blank sorter encoder")
    eq(a2["05_EM_STATE.{matrix_area}_SORTER_POWER_CUT"], "", "non-sorter -> blank SORTER_POWER_CUT")
    a3 = by_area["ESTOP_AREA 3"]
    eq(a3["TemplateType"], "06", "non-sorter, no doors -> GENERIC ResetRequired (TT06)")
    eq(a3["ITERATOR_STRINGS"], [], "no doors")


# --------------------------------------------------------------------------- 05 --------------- #
def _ofkq(idx, dev, areas, src, tag, db_name, fld="", numl=""):
    return {"script_type": "KQ", "index": idx, "device": dev, "matrix_areas": areas, "_source_row": src,
            "name_in_tagtable": tag, "name_in_db": db_name, "iol_FLD": fld or tag,
            "combined_FLD": fld or tag, "numerazione_linea": numl}


def _ofki(idx, src, tag, st="KI", dev=""):
    return {"script_type": st, "index": idx, "device": dev, "_source_row": src, "name_in_tagtable": tag}


def test_05_output_feedback_index_grouping_variant_and_pair():
    rows = [
        # unit A (index 0001): 1 KQ + 1 KI, 1 area -> variant 01
        _ofkq("0001", "-Q1", "AREA 1", 10, "Out Q1", "Err Q1", fld="=S1+L-Q1", numl="LN1"),
        _ofki("0001", 1, "FB Q1"),
        # unit B (index 0002): 1 KQ + a 2-channel KI series, 2 areas -> variant (2,2,1)=08
        _ofkq("0002", "-Q2", "AREA 1|AREA 2", 11, "Out Q2", "Err Q2", fld="=S1+L-Q2"),
        _ofki("0002", 2, "FB1", st="KI1/4"), _ofki("0002", 3, "FB2", st="KI2/4"),
        # unit C (index 0003): a KQ1/2+KQ2/2 channel pair + 1 KI, 1 area -> co=2 -> variant (1,1,2)=04
        _ofkq("0003", "-Q5", "AREA 1", 12, "Out Q5", "Err Q5", fld="=S1+L-Q5"),
        _ofkq("0003", "-Q6", "AREA 1", 13, "Out Q6", "Err Q6"),   # 2nd contactor of the same index
        _ofki("0003", 4, "FB Q5"),
    ]
    t = build_05_output_feedback(Database(rows))
    by_inst = {r["instanceOf-FDBACK"]: r for r in t.rows}
    eq(sorted(by_inst), ["FDBACK_=S1+L-Q1", "FDBACK_=S1+L-Q2", "FDBACK_=S1+L-Q5_-Q6"],
       "one unit per index; the channel pair appends the 2nd device to the instance name")
    a = by_inst["FDBACK_=S1+L-Q1"]
    eq(a["TemplateType"], "01", "(1 area, 1 fb, 1 co) -> variant 1")
    eq(a["tagName:Contactor1_QBadInput"], "QBAD_Out Q1")
    eq(a["tagName:Contactor1_FeedbackInput"], "FB Q1")
    eq(a["05_EM_STATE.{matrix_areas.1}"], "AREA 1 Q_Delayed", "UNPADDED area")
    eq(a["NetworkComment"], "AREA 1 Contactor Output =S1+L-Q1 LN1")
    b = by_inst["FDBACK_=S1+L-Q2"]
    eq(b["TemplateType"], "08", "(2 areas, 2 fb, 1 co) -> variant (2,2,1)=8")
    eq([b["tagName:Contactor1_FeedbackInput"], b["tagName:Contactor2_FeedbackInput"]], ["FB1", "FB2"])
    eq(b["05_EM_STATE.{matrix_areas.2}"], "AREA 2 Q_Delayed", "second OnCondition slot, UNPADDED area")
    c = by_inst["FDBACK_=S1+L-Q5_-Q6"]
    eq(c["TemplateType"], "04", "(1 area, 1 fb, 2 co) -> variant (1,1,2)=4")
    eq([c["tagName:Contactor1_Output"], c["tagName:Contactor2_Output"]], ["Out Q5", "Out Q6"],
       "both KQ channels fill the two ContactorOutput slots")


# --------------------------------------------------------------------------- 06 --------------- #
def _kq(bit, name):
    return {"script_type": "KQ", "bit": bit, "name_in_db": name}


# --------------------------------------------------------------------------- 03 --------------- #
def _area_row(area, st, name, db, desc=""):
    return {"matrix_areas": area, "script_type": st, "name_in_db": name, "datablocks": db,
            "areas_description": desc}


def test_03_zone_cumulative_groups_per_area():
    rows = [
        _area_row("AREA 1", "E1/2", "PB a", "01_Pushbutton", "Sorter Zone"),
        _area_row("AREA 1", "E1/2", "PB b", "01_Pushbutton", "Sorter Zone"),
        _area_row("AREA 1", "KQ", "FDB a", "03_FDBACK|03_FDBACK_RAW", "Sorter Zone"),
        _area_row("AREA 1", "B1/2", "BRK a", "01_Pushbutton", "Sorter Zone"),
        _area_row("AREA 1", "DI1/2", "DOOR a", "07_DOOR", "Sorter Zone"),
        _area_row("AREA 2", "E1/2", "PB c", "01_Pushbutton"),   # AREA 2: only PB+FDB, no description
        _area_row("AREA 2", "KQ", "FDB b", "03_FDBACK|03_FDBACK_RAW"),
    ]
    t = build_03_zone_cumulative(Database(rows))
    rowmap = {r["02_COM.{db_element}"]: r for r in t.rows}
    eq(sorted(rowmap), ["AREA 1 DOORS", "AREA 1 FDB", "AREA 1 PB", "AREA 1 SAFETY_BREAKERS",
                        "AREA 2 FDB", "AREA 2 PB"], "PB/FDB always; BREAKERS/DOORS only where present")
    pb = rowmap["AREA 1 PB"]
    eq(pb["nameOfDB"], "01_Pushbutton", "scalar nameOfDB = the group's leftmost datablock")
    eq(pb["ITERATOR_STRINGS"], ["PB a", "PB b"], "exact-size iterator, NO padding")
    eq(pb["NetworkComment"], "AREA 1 PB - Sorter Zone", "comment = 02_COM element + ' - ' + description")
    eq(rowmap["AREA 2 PB"]["NetworkComment"], "AREA 2 PB", "no description -> just the 02_COM element")
    eq(rowmap["AREA 1 FDB"]["nameOfDB"], "03_FDBACK", "KQ leftmost datablock")
    eq(rowmap["AREA 1 DOORS"]["nameOfDB"], "07_DOOR")


def test_06_one_instance_per_node_padded_to_eight():
    node = {"profinet_name": "n12-pc1", "profinet_ip": "192.168.50.12",
            "I_startByte": "", "I_endByte": "", "Q_startByte": 130, "Q_endByte": 140}
    rows = [node, _kq("Q130.0", "FB a"), _kq("Q130.1", "FB b"), _kq("Q140.0", "FB c")]
    t = build_06_feedback_error(Database(rows))
    eq(len(t), 1, "one instance for a node with <=8 contactors")
    r = t.rows[0]
    eq(r["instanceOf-03_FDBACK error"], "FDBK_ERR_n12-pc1_1")
    eq(r["00_Commissioning.{db_element}"], "n12-pc1 192.168.50.12")
    eq(r["NetworkComment"], "FDBK_ERR_n12-pc1_1 192.168.50.12")
    eq(r["ITERATOR_STRINGS"], ["FB a", "FB b", "FB c"] + [PAD] * 5, "padded to the FB's 8 slots")


# --------------------------------------------------------------------------- 07 --------------- #
def _enc(st, idx, fld, name_db, name_tag):
    return {"script_type": st, "index": idx, "iol_FLD": fld,
            "name_in_db": name_db, "name_in_tagtable": name_tag}


def test_07_speed_control_per_encoder_pair():
    rows = [
        _enc("N1/2", "0001", "=S1+A", "Enc 0001 S1 Healthy", "Enc 0001 S1"),
        _enc("N2/2", "0001", "=S1+A", "Enc 0001 S2 Healthy", "Enc 0001 S2"),
        _enc("N1/2", "0002", "=S2+B", "Enc 0002 S1 Healthy", "Enc 0002 S1"),
        _enc("N2/2", "0002", "=S2+B", "Enc 0002 S2 Healthy", "Enc 0002 S2"),
    ]
    t = build_07_speed_control(Database(rows))
    eq(len(t), 2, "one instance per encoder pair (grouped by numeric index)")
    r = t.rows[0]
    eq(r["instanceOf-01_Speed_Control_SLS"], "SLS_SORTER_01", "nn = zero-padded encoder index")
    eq(r["tagName:EncoderSensor1"], "Enc 0001 S1")
    eq(r["tagName:EncoderSensor2"], "Enc 0001 S2")
    eq(r["tagName:SorterRunningIOC"], "PNC_I_SORTER-01 SORTER RUNNING")
    eq(r["04_SPEED.{db_element:ENC1/2}"], "Enc 0001 S1 Healthy")
    eq(r["04_SPEED.{db_element:ENC2/2}"], "Enc 0001 S2 Healthy")
    eq(r["04_SPEED.{db_element:ENC}"], "Safety Encoder Failure [ =S1+A ]", "matches the 04_SPEED rule member")
    eq(r["SPEED_STATE_REC.SORTER_{index}_STOPPED"], "SORTER_01_STOPPED")
    eq(r["NetworkComment"], "SORTER 01 SPEED CONTROL")
    eq(t.rows[1]["instanceOf-01_Speed_Control_SLS"], "SLS_SORTER_02")


# --------------------------------------------------------------------------- 08 --------------- #
def test_08_gate_manager_sorter_and_door_rows():
    node = {"profinet_name": "n-pc1", "profinet_ip": "10.0.0.12",
            "I_startByte": 100, "I_endByte": 110, "Q_startByte": "", "Q_endByte": ""}
    rows = [
        node,
        {"script_type": "N1/2", "index": "0001"},                          # one sorter -> TT01
        # door A (index 0002): full set; DI1/2 in the node's I-range, sorter area, has a DR
        {"script_type": "DQ", "index": "0002", "name_in_tagtable": "Unlock A", "iol_FLD": "=S1+PC-Q1"},
        {"script_type": "DI1/2", "index": "0002", "bit": "I100.0", "iol_FLD": "=S1+SG1-B1",
         "IsSorterArea": "yes", "name_in_tagtable": "DoorCh1 A", "name_in_db": "Door SAFE A"},
        {"script_type": "DI2/2", "index": "0002", "name_in_tagtable": "DoorCh2 A", "name_in_db": "Door DIAG A"},
        {"script_type": "DD", "index": "0002", "name_in_tagtable": "DoorDiag A", "name_in_db": "Door Alarm A"},
        {"script_type": "DR", "index": "0002", "name_in_tagtable": "Reset A"},
        {"script_type": "DL", "index": "0002", "name_in_tagtable": "Lamp A"},
        # door B (index 0003): no DR, not a sorter area
        {"script_type": "DQ", "index": "0003", "name_in_tagtable": "Unlock B", "iol_FLD": "=S1+PC-Q2"},
        {"script_type": "DI1/2", "index": "0003", "bit": "I105.0", "iol_FLD": "=S1+SG2-B1",
         "IsSorterArea": "", "name_in_tagtable": "DoorCh1 B", "name_in_db": "Door SAFE B"},
    ]
    by_tt = {}
    for r in build_08_gate_manager(Database(rows)).rows:
        by_tt.setdefault(r["TemplateType"], []).append(r)
    eq(len(by_tt["01"]), 1, "one sorter row")
    s = by_tt["01"][0]
    eq(s["NetworkComment"], "SORTER 01 SPEED CONTROL")
    eq(s["tagName:SorterRunningIOC"], "PNC_I_SORTER-01 SORTER RUNNING")
    eq(s["05_EM_STATE.{matrix_area}_SORTER_NOT_RUNNING"], "SORTER_01_NOT_RUNNING")
    doors = {r["instanceOf-02_Safety_Door"]: r for r in by_tt["02"]}
    eq(sorted(doors), ["SFDOOR_=S1+SG1-B1", "SFDOOR_=S1+SG2-B1"], "one door per DQ, SFDOOR_<DI1/2 FLD>")
    a = doors["SFDOOR_=S1+SG1-B1"]
    eq(a["00_Commissioning.{db_element}"], "n-pc1 10.0.0.12", "bypass = the DI1/2's node")
    eq(a["choice:IsSorterDoor"], "Always TRUE", "DI in a sorter area")
    eq(a["choice:DoorResetNecessary"], "Always TRUE", "a same-index DR exists")
    eq(a["tagName:DoorClosedCh1"], "DoorCh1 A"); eq(a["tagName:DoorSolenoidUnlock"], "Unlock A")
    eq(a["07_DOOR.{db_element:DI1/2}"], "Door SAFE A")
    b = doors["SFDOOR_=S1+SG2-B1"]
    eq(b["choice:IsSorterDoor"], "Always FALSE", "not a sorter area")
    eq(b["choice:DoorResetNecessary"], "Always FALSE", "no DR")


if __name__ == "__main__":
    raise SystemExit(run("builders", [
        ("00_commissioning_filters_to_diag_nodes", test_00_commissioning_filters_to_diag_nodes),
        ("00_commissioning_member_and_title_are_pname_ip", test_00_commissioning_member_and_title_are_pname_ip),
        ("00_commissioning_empty_when_no_nodes", test_00_commissioning_empty_when_no_nodes),
        ("02_one_instance_per_node_padded_to_four", test_02_one_instance_per_node_padded_to_four),
        ("02_chunks_over_four_into_multiple_instances", test_02_chunks_over_four_into_multiple_instances),
        ("02_pad_is_no_operation", test_02_pad_is_no_operation),
        ("03_zone_cumulative_groups_per_area", test_03_zone_cumulative_groups_per_area),
        ("04_estop_variant_and_sorter_fields", test_04_estop_variant_and_sorter_fields),
        ("05_output_feedback_index_grouping_variant_and_pair", test_05_output_feedback_index_grouping_variant_and_pair),
        ("06_one_instance_per_node_padded_to_eight", test_06_one_instance_per_node_padded_to_eight),
        ("07_speed_control_per_encoder_pair", test_07_speed_control_per_encoder_pair),
        ("08_gate_manager_sorter_and_door_rows", test_08_gate_manager_sorter_and_door_rows),
    ]))

"""Phase 400 (Interfaces). 400a: the per-signal interface_tagname (identity + annotate). 400f: the
template-native interface-signal capture. Data-independent."""
import os
import tempfile

from openpyxl import Workbook
from openpyxl.worksheet.table import Table as XlTable

from _harness import run, eq, ok
from pipeline5.core.ssot_database import Database
from pipeline5.domain import signal_identity as identity
from pipeline5.domain import interface_builder as interfaces
from pipeline5.domain.signals_schema import signals_table


def test_interp_keep_keeps_unknown_tokens():
    eq(identity.interp_keep("a {$x} {$y} b", {"x": "1"}), "a 1 {$y} b", "a missing key's token is kept literal")
    eq(identity.interp_keep("{$x}", {"x": None}), "", "a present-but-None key substitutes to ''")


def test_interface_tagname_tag_name_and_kept_tokens():
    # {$tag_name} resolves to name_in_tagtable; {$interface_name}/{$interface_id} are KEPT for the generator
    row = {"name_in_tagtable": "Safety Breaker [ S1-B1 ]"}
    out = identity.interface_tagname(row, "PNC_Q_{$interface_name}-{$interface_id}_{$tag_name}")
    eq(out, "PNC_Q_{$interface_name}-{$interface_id}_Safety Breaker [ S1-B1 ]")


def test_interface_tagname_db_element_from_name_in_db():
    # the door types template uses {$db_element}, which in PL4 is the 520-written name_in_db
    row = {"name_in_db": "Door Closed SAFE_STATE [ =S1+SG1-B1 ]"}
    out = identity.interface_tagname(row, "PNC_Q_{$interface_name}-{$interface_id}_{$db_element}")
    eq(out, "PNC_Q_{$interface_name}-{$interface_id}_Door Closed SAFE_STATE [ =S1+SG1-B1 ]")


def test_interface_tagname_row_tokens_and_empty_template():
    row = {"desc_l1": "EMERGENCY", "desc_l1b": "PUSH BUTTON", "iol_FLD": "S1-E1"}
    out = identity.interface_tagname(row, "PNC_Q_{$interface_name}-{$interface_id}_{$desc_l1} {$desc_l1b} [ {$iol_FLD} ]")
    eq(out, "PNC_Q_{$interface_name}-{$interface_id}_EMERGENCY PUSH BUTTON [ S1-E1 ]")
    eq(identity.interface_tagname(row, ""), "", "no template -> ''")


def test_annotate_writes_per_type_from_config():
    tagnames = {"E1/2": "PNC_Q_{$interface_name}-{$interface_id}_{$tag_name}",
                "DI1/2": "PNC_Q_{$interface_name}-{$interface_id}_{$db_element}",
                "IOC": ""}
    table = signals_table(["script_type"])
    table.add(script_type="E1/2", type={"type_id": "E1/2"}, name_in_tagtable="Emergency Push Button [ X ]")
    table.add(script_type="DI1/2", type={"type_id": "DI1/2"}, name_in_db="Door Closed SAFE_STATE [ Y ]")
    table.add(script_type="IOC", type={"type_id": "IOC"})
    db = Database([table])
    interfaces.annotate_interface_tagnames(db, tagnames)
    rows = list(db["signals"])
    eq(rows[0]["interface_tagname"], "PNC_Q_{$interface_name}-{$interface_id}_Emergency Push Button [ X ]")
    eq(rows[1]["interface_tagname"], "PNC_Q_{$interface_name}-{$interface_id}_Door Closed SAFE_STATE [ Y ]")
    eq(rows[2]["interface_tagname"], "", "an IOC (no template) gets ''")


# --- 400b: the mirror set + byte layout ---------------------------------------------------------- #
def test_parse_instance_and_detect_diag():
    eq(interfaces.parse_instance("SORTER-01"), ("SORTER", "01"))
    eq(interfaces.parse_instance("SORTER+DIAG-02"), ("SORTER", "02"), "+DIAG stripped before parsing")
    eq(interfaces._detect_diag("SORTER+DIAG-02"), True)
    eq(interfaces._detect_diag("SORTER-01"), False)


def test_index_membership_normalizes():
    from _harness import ok
    ok(interfaces._index_in("01", "01|02"))
    ok(interfaces._index_in("1", "01|02"), "'1' matches '01' (numeric-normalized)")
    ok(not interfaces._index_in("03", "01|02"))


def test_find_interfaces_from_ioc_rows():
    rows = [{"script_type": "IOC", "index": "SORTER-01", "bit": "10000", "id_node": "10",
             "device": "-K1", "profinet_ip": "1.2.3.4", "source_sheet": "S", "source_row": 5},
            {"script_type": "IOC", "index": "", "source_sheet": "S", "source_row": 6},
            {"script_type": "DI1/2", "index": "x"}]
    recs, findings = interfaces.find_interfaces(rows)
    eq(len(recs), 1, "one IOC record (the blank-index IOC warned, the DI1/2 ignored)")
    eq((recs[0]["machine_type"], recs[0]["index"], recs[0]["base"]), ("SORTER", "01", "10000"))
    eq(len(findings), 1, "the blank-Index IOC is a finding")
    eq((findings[0].phase, findings[0].type, findings[0].severity), (400, "if_ioc_no_index", "WARN"),
       "the no-index report container")


def test_allocate_bytes_bool_block_and_word():
    E = interfaces._Elem
    bools = [E("X", "a"), E("X", "b"), E("X", "c")]                       # 3 BOOL, one group
    interfaces.allocate_bytes(bools, {"Q": 1}, 8)                          # start = 1+1+8 = 10
    eq([(e.offset_byte, e.bit) for e in bools], [(10, 0), (10, 1), (10, 2)], "BOOL low bits from byte 10")
    word = [E("W", "w", data_type="WORD")]
    interfaces.allocate_bytes(word, {"Q": -1}, 8)                          # start = -1+1+8 = 8
    eq((word[0].offset_byte, word[0].bit), (8, None), "a WORD takes an even byte, no bit")


def test_collect_mirror_set_direct_follower_iflrule_and_dedup():
    rows = [{"script_type": "DI1/2", "interface_mapping": "01", "plc_binding": '"07_DOOR"."Door Closed [ X ]"',
             "interface_tagname": "PNC_Q_{$interface_name}-{$interface_id}_door", "functional_unit": "S1",
             "location": "+SG1", "device": "-B1", "type": {"tag_name": "Door [ {$iol_FLD} ]"}, "iol_FLD": "S1-B1"}]
    diag_rules = [{"name": "Safety Door Alarm", "required_types": ["DI1/2", "DI"], "db_name": "07_DOOR",
                   "member": "Door Alarm [ {$functional_unit}{$location}{$device} ]", "interface_tagname": "PNC_Q_{$member}"}]
    if_rules = [{"name": "Door Open Request", "required_types": ["DI1/2", "DI2/2"], "direction": "I",
                 "data_type": "BOOL", "script_type": "IF_DOOR_CMD",
                 "member": "Open Door Request [ {$functional_unit}{$location}{$device} ]", "interface_tagname": "PNC_{$direction}_{$member}"}]
    elems, _findings = interfaces.collect_mirror_set(rows, index="01", is_diag=False,
                                                     diag_rules=diag_rules, if_rules=if_rules)
    eq(len(elems), 3, "the direct mirror + 1 diag follower + 1 interface-element follower")
    eq((elems[0].direction, elems[0].mirror_name), ("Q", '"07_DOOR"."Door Closed [ X ]"'), "direct mirror Q")
    eq((elems[1].source, elems[1].direction, elems[1].mirror_name),
       ("follow", "Q", '"07_DOOR"."Door Alarm [ S1+SG1-B1 ]"'), "diag follower, TIA-qualified")
    eq((elems[2].source, elems[2].direction, elems[2].mirror_name),
       ("if_rule", "I", "Open Door Request [ S1+SG1-B1 ]"), "interface_elements follower is the only I source")
    # dedup: a second identical row contributes nothing new
    elems2, _ = interfaces.collect_mirror_set(rows + [dict(rows[0])], index="01", is_diag=False,
                                              diag_rules=diag_rules, if_rules=if_rules)
    eq(len(elems2), 3, "(direction, script_type, mirror_name) dedups duplicates")


def test_collect_mirror_set_not_mirrored_finding():
    """A picked signal with no plc_binding (no db_element/tag) is an if_signal_not_mirrored WARN, not mirrored."""
    rows = [{"script_type": "DI1/2", "interface_mapping": "01", "plc_binding": "",
             "functional_unit": "S1", "location": "+SG1", "device": "-B1", "source_sheet": "S", "source_row": 9}]
    elems, findings = interfaces.collect_mirror_set(rows, index="01", is_diag=False, diag_rules=[], if_rules=[])
    eq(elems, [], "no plc_binding -> nothing mirrored")
    eq(len(findings), 1, "the un-mirrorable picked signal is a finding")
    eq((findings[0].phase, findings[0].type, findings[0].severity), (400, "if_signal_not_mirrored", "WARN"))


def _native_template(path):
    """A minimal MachineInterfaces-style sheet: a 'Category'-headed data table with two native rows that
    carry a Signal Name Side 1 (one with <index>), offsets/bits, direction, and an Expression Side 1."""
    wb = Workbook(); ws = wb.active; ws.title = "SORTER"
    headers = ["Category", "Description", "Data Type", "Direction </>", "I/O Offset Byte", "I/O Bit",
               "I/O Address Side 1", "Signal Name Side 1", "Expression Side 1"]      # A..I
    for c, h in enumerate(headers, 1):
        ws.cell(1, c, h)
    # row2: an output BOOL native signal with <index> + an expression
    ws.cell(2, 1, "WATCHDOG"); ws.cell(2, 3, "BOOL"); ws.cell(2, 4, ">"); ws.cell(2, 5, "0"); ws.cell(2, 6, "0")
    ws.cell(2, 8, "PNC_Q_SORTER-<index> HEARTBEAT"); ws.cell(2, 9, '"Clock 1Hz"')
    # row3: an input BOOL native signal, no expression
    ws.cell(3, 1, "SORTER_STATE"); ws.cell(3, 3, "BOOL"); ws.cell(3, 4, "<"); ws.cell(3, 5, "0"); ws.cell(3, 6, "0")
    ws.cell(3, 8, "PNC_I_SORTER-<index> RUNNING")
    ws.add_table(XlTable(displayName="SORTER_SIGNALS", ref="A1:I3"))
    wb.save(path)


def test_template_native_elements():
    with tempfile.TemporaryDirectory() as d:
        tpl = os.path.join(d, "t.xlsx"); _native_template(tpl)
        isynt = "I<base+offset>/.<bit>"
        elems = interfaces.template_native_elements(tpl, "SORTER", "01", 10000, isynt)
        eq(len(elems), 2, "the two native rows (with a Signal Name) are captured")
        hb = next(e for e in elems if "HEARTBEAT" in e.signal_name)
        eq(hb.signal_name, "PNC_Q_SORTER-01 HEARTBEAT", "<index> resolved to the interface_id")
        eq(hb.source, "template")
        eq(hb.direction, "Q", "'>' -> Q")
        eq((hb.offset_byte, hb.bit), (0, 0))
        eq(hb.mirror_name, '"Clock 1Hz"', "the Expression Side 1 is kept (the key value)")
        run_ = next(e for e in elems if "RUNNING" in e.signal_name)
        eq(run_.direction, "I", "'<' -> I")
        eq(run_.mirror_name, "PNC_I_SORTER-01 RUNNING", "an empty expression falls back to the signal_name (unique key)")
        # the stored address is computed for THIS base via io_address_side1
        eq(interfaces.io_address_side1(isynt, 10000, hb.direction, hb.data_type, hb.offset_byte, hb.bit),
           "Q10000.0", "HEARTBEAT address for base 10000")
        eq(interfaces.io_address_side1(isynt, 20000, hb.direction, hb.data_type, hb.offset_byte, hb.bit),
           "Q20000.0", "the SAME native row computes per-base (20000 -> Q20000.0)")


if __name__ == "__main__":
    import sys
    sys.exit(run("interfaces", [
        ("interp_keep_keeps_unknown_tokens", test_interp_keep_keeps_unknown_tokens),
        ("interface_tagname_tag_name_and_kept_tokens", test_interface_tagname_tag_name_and_kept_tokens),
        ("interface_tagname_db_element_from_name_in_db", test_interface_tagname_db_element_from_name_in_db),
        ("interface_tagname_row_tokens_and_empty_template", test_interface_tagname_row_tokens_and_empty_template),
        ("annotate_writes_per_type_from_config", test_annotate_writes_per_type_from_config),
        ("parse_instance_and_detect_diag", test_parse_instance_and_detect_diag),
        ("index_membership_normalizes", test_index_membership_normalizes),
        ("find_interfaces_from_ioc_rows", test_find_interfaces_from_ioc_rows),
        ("allocate_bytes_bool_block_and_word", test_allocate_bytes_bool_block_and_word),
        ("collect_mirror_set_direct_follower_iflrule_and_dedup", test_collect_mirror_set_direct_follower_iflrule_and_dedup),
        ("collect_mirror_set_not_mirrored_finding", test_collect_mirror_set_not_mirrored_finding),
        ("template_native_elements", test_template_native_elements),
    ]))

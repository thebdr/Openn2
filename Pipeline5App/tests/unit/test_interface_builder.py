"""Phase 400 (Interfaces). 400a: the per-signal interface_tagname (identity + annotate). 400f: the
template-native interface-signal capture. Data-independent."""
import os
import tempfile

from openpyxl import Workbook
from openpyxl.worksheet.table import Table as XlTable

from _harness import run, eq, ok
from pipeline5.truth.database import Database
from pipeline5.truth import identity
from pipeline5.phases.interfaces import builder as interfaces
from pipeline5.truth.signals import signals_table


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
    """C-031 (user 2026-10-09): an interface is named in its IOC row's Mnemonic - the Index is not read; an IOC row
    without a Mnemonic is an `if_ioc_no_mnemonic` WARN (pointing at its Index when the PL3 place holds the name)."""
    rows = [{"script_type": "IOC", "mnemonic": "SORTER-01", "index": "0007", "bit": "10000", "id_node": "10",
             "device": "-K1", "profinet_ip": "1.2.3.4", "source_sheet": "S", "source_row": 5},
            {"script_type": "IOC", "mnemonic": "", "index": "SORTER-02", "source_sheet": "S", "source_row": 6},
            {"script_type": "IOC", "source_sheet": "S", "source_row": 7},
            {"script_type": "DI1/2", "mnemonic": "x"}]
    recs, findings = interfaces.find_interfaces(rows)
    eq(len(recs), 1, "one IOC record (the unnamed IOC rows warned, the DI1/2 ignored)")
    eq((recs[0]["instance"], recs[0]["machine_type"], recs[0]["index"], recs[0]["base"]),
       ("SORTER-01", "SORTER", "01", "10000"), "named by the Mnemonic, never by the Index '0007'")
    eq([(f.phase, f.type, f.severity, f.location) for f in findings],
       [(400, "if_ioc_no_mnemonic", "WARN", "S!6"), (400, "if_ioc_no_mnemonic", "WARN", "S!7")])
    ok("its Index 'SORTER-02' is not read - write the name in Mnemonic" in findings[0].detail, findings[0].detail)
    ok("Index" not in findings[1].detail, findings[1].detail)


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


# --- C-031: the interface is a transfer area ------------------------------------------------------ #
def _ta_dtd(in_len="128", out_len="128"):
    return {"by_id": {"TRANSFERAREA-IN": {"model_id": "TransferArea-IN", "params": f"PartnerToLocalLength={in_len}"},
                      "TRANSFERAREA-OUT": {"model_id": "TransferArea-OUT", "params": f"LocalToPartnerLength={out_len}"}},
            "default_cards": {}}


def test_interface_name_and_base_byte():
    eq(interfaces.interface_name("SORTER+DIAG-02"), "SORTER-02", "the +DIAG marker is no part of the name")
    eq(interfaces.interface_name(" FVTGENERIC-03 "), "FVTGENERIC-03")
    eq([interfaces.base_byte(v) for v in ("10000", " 20000 ", "I10000.0", "Q20.0", "AREA", "", None, "1.5", "I10000.5")],
       [10000, 20000, 10000, 20, None, None, None, None, None],
       "a bare byte or an address's byte (the notation, bit 0 - an area starts on a whole byte); else None")


def test_ioc_base_is_its_own_bit():
    """C-031 (user 2026-10-09: AB dropped): an interface's base is its IOC row's own Bit - no head column is read
    (`coupler_start`, a Mnemonic on the head); a bit-less row has no base (the blocking FAIL); two interfaces at one
    base overlap."""
    rows = [{"script_type": "PA", "type_hw": "PA", "coupler_start": "14000", "mnemonic": "CABINETAL00834"},
            {"script_type": "IOC", "mnemonic": "FVTGENERIC-05", "source_cell": "S!O3"},
            {"script_type": "IOC", "mnemonic": "FVTGENERIC-06", "bit": "16000", "source_cell": "S!O4"},
            {"script_type": "IOC", "mnemonic": "SORTER-01", "bit": "I16000.0", "source_cell": "S!O5"}]
    records, _f = interfaces.find_interfaces(rows)
    eq([(r["instance"], r["base"]) for r in records],
       [("FVTGENERIC-05", ""), ("FVTGENERIC-06", "16000"), ("SORTER-01", "I16000.0")])
    size = {r["instance"]: {"I": 2, "Q": 2} for r in records}
    length = {r["instance"]: {"I": 128, "Q": 128} for r in records}
    found = interfaces.area_findings(records, size, length, [])
    eq([(f.type, f.location) for f in found],
       [("if_base_invalid", "S!O3"), ("if_area_overlap", "S!O4"), ("if_area_overlap", "S!O4")],
       "no Bit = no base; the two areas at 16000 overlap (IN and OUT)")


def test_area_lengths_default_and_override():
    eq(interfaces.area_lengths({}, _ta_dtd()), {"I": 128, "Q": 128}, "the database defaults")
    eq(interfaces.area_lengths({"hardware_params": "partnertolocallength = 64"}, _ta_dtd()), {"I": 64, "Q": 128},
       "the IOC row's own key wins in any spelling (700 writes it in the database's - the importer matches exactly)")
    eq(interfaces.area_lengths({"hardware_params": "PartnerToLocalLength=64 | PartnerToLocalLength=32"}, _ta_dtd()),
       {"I": 32, "Q": 128}, "the LAST entry wins - the importer applies them in order")
    for bad in ("abc", "0", "-8", "128.0", ""):
        eq(interfaces.area_lengths({"hardware_params": f"LocalToPartnerLength={bad}"}, _ta_dtd()), {"I": 128, "Q": None},
           f"{bad!r}: an own value that is no length is NOT replaced by the default")
    eq(interfaces.area_lengths({}, {"by_id": {}}), {"I": None, "Q": None}, "nothing configured -> unknown")
    eq(interfaces.area_params("LocalToPartnerLength=32 | Foo=1 | PartnerToLocalLength = 16 | Bar"),
       ({"I": "16", "Q": "32"}, ["Foo=1", "Bar"]))


def test_mapping_by_name_number_and_diag_name():
    """C-031: the `Interfaces` cell names an interface by `<TYPE>-<NN>` (any case, the `+DIAG` marker optional) or,
    as the PL3 column did, by its number; several names per cell, `|`-separated."""
    names = ("SORTER+DIAG-02", "SORTER-02")
    for cell in ("sorter-02", "SORTER+DIAG-02", "02", "FVTGENERIC-03 | SORTER-02"):
        ok(interfaces._maps_to("02", names, cell), cell)
    for cell in ("SORTER-03", "SORTER-022", "", None, "FVTGENERIC-03"):
        ok(not interfaces._maps_to("02", names, cell), cell)
    rows = [{"script_type": "DI1/2", "interface_mapping": "FVTGENERIC-03|sorter-02", "plc_binding": '"07_DOOR"."D1"'},
            {"script_type": "DI1/2", "interface_mapping": "SORTER-01", "plc_binding": '"07_DOOR"."D2"'}]
    elems, _f = interfaces.collect_mirror_set(rows, index="02", is_diag=False, diag_rules=[], if_rules=[], names=names)
    eq([e.mirror_name for e in elems], ['"07_DOOR"."D1"'], "only the door that names SORTER-02")


def test_unknown_interface_name_warns():
    rows = [{"script_type": "IOC", "mnemonic": "SORTER-01", "bit": "10000", "source_cell": "NET!O7"},
            {"script_type": "IOC", "mnemonic": "FVTGENERIC-03", "bit": "11000", "source_cell": "NET!O8"},
            {"script_type": "DI1/2", "interface_mapping": "SORTER-01|SORTR-01|03|04", "functional_unit": "=A",
             "location": "-B", "device": "-C", "source_cell": "NET!O20", "uid": "u1"},
            {"script_type": "DI1/2", "interface_mapping": "fvtgeneric-03", "source_cell": "NET!O21"}]
    records, _f = interfaces.find_interfaces(rows)
    found = interfaces.mapping_findings(rows, records)
    eq([(f.type, f.severity, f.location, f.source_uid) for f in found], [("if_mapping_unknown", "WARN", "NET!O20", "u1")])
    ok(found[0].detail.endswith("names no interface: SORTR-01, 04"), found[0].detail)


def _recs(*iocs):
    rows = [{"script_type": "IOC", "mnemonic": index, "bit": bit, "source_cell": f"NET!O{n}", "uid": f"i{n}"}
            for n, (index, bit) in enumerate(iocs, 1)]
    return interfaces.find_interfaces(rows)[0]


def test_area_findings_overflow_overlap_and_base():
    """C-031's blocking checks: a layout past its area (quiet at the exact limit), two areas overlapping (quiet
    when adjacent), an area over an I/O-List address of ITS direction, a base that is no byte; an area of unknown
    length a WARN."""
    a = interfaces.area_findings
    recs = _recs(("SORTER-01", "10000"))
    eq(a(recs, {"SORTER-01": {"I": 128, "Q": 128}}, {"SORTER-01": {"I": 128, "Q": 128}}, []), [], "exactly full")
    found = a(recs, {"SORTER-01": {"I": 2, "Q": 130}}, {"SORTER-01": {"I": 128, "Q": 128}}, [])
    eq([(f.type, f.severity, f.location) for f in found], [("if_area_overflow", "FAIL", "NET!O1")])
    ok("130 bytes laid out on SORTER-01_OUT, the area holds 128 (LocalToPartnerLength)" in found[0].detail,
       found[0].detail)

    two = _recs(("SORTER-01", "10000"), ("SORTER+DIAG-02", "I10100.0"))
    sizes = {"SORTER-01": {"I": 2, "Q": 2}, "SORTER+DIAG-02": {"I": 2, "Q": 2}}
    lens = {"SORTER-01": {"I": 128, "Q": 128}, "SORTER+DIAG-02": {"I": 128, "Q": 128}}
    found = a(two, sizes, lens, [])
    eq([f.type for f in found], ["if_area_overlap"] * 2, "the IN pair and the OUT pair")
    ok("SORTER-01_IN (I10000..10127) and SORTER-02_IN (I10100..10227) overlap" in found[0].detail, found[0].detail)
    adjacent = _recs(("SORTER-01", "10000"), ("SORTER+DIAG-02", "10128"))
    eq(a(adjacent, sizes, lens, []), [], "adjacent areas do not overlap")

    signals = [{"script_type": "DI1/2", "bit": "I10050.3", "source_cell": "NET!O30", "uid": "s1"},
               {"script_type": "A", "bit": "I10051.0", "source_cell": "NET!O31"},
               {"script_type": "KQ", "bit": "Q9999.7", "source_cell": "NET!O32"},
               {"script_type": "IOC", "bit": "I10000.0", "source_cell": "NET!O33"}]
    found = a(recs, {"SORTER-01": {"I": 2, "Q": 2}}, {"SORTER-01": {"I": 128, "Q": 128}}, signals)
    eq([(f.type, f.severity, f.location, f.source_uid) for f in found], [("if_area_overlap", "FAIL", "NET!O30", "s1")],
       "the I area over two input rows (reported once, at the first); the Q row below the area; the IOC row is the base")
    ok("overlaps 2 I/O-List addresses, the first I10050.3" in found[0].detail, found[0].detail)

    found = a(_recs(("SORTER-01", "AREA")), {"SORTER-01": {"I": 999, "Q": 999}}, {"SORTER-01": {"I": 1, "Q": 1}}, [])
    eq([(f.type, f.severity) for f in found], [("if_base_invalid", "FAIL")], "no base: nothing else checked")
    found = a(recs, {"SORTER-01": {"I": 999, "Q": 2}}, {"SORTER-01": {"I": None, "Q": 128}}, [])
    eq([(f.type, f.severity) for f in found], [("if_area_length_unknown", "WARN")], "an unknown length is not checked")
    bad = _recs(("SORTER-01", "10000"))
    bad[0]["row"]["hardware_params"] = "LocalToPartnerLength=0"
    found = a(bad, {"SORTER-01": {"I": 2, "Q": 99}}, {"SORTER-01": {"I": 128, "Q": None}}, [])
    eq([(f.type, f.severity) for f in found], [("if_area_length_invalid", "FAIL")],
       "refute round 1: an own length of 0 is a blocking FAIL, not the unknown-length WARN")
    ok("LocalToPartnerLength='0'" in found[0].detail, found[0].detail)

    same = _recs(("FVTGENERIC-05", "14000"), ("FVTGENERIC-06", "14000"))
    unknown = {r["instance"]: {"I": None, "Q": None} for r in same}
    found = a(same, {r["instance"]: {"I": 2, "Q": 2} for r in same}, unknown, [])
    eq(sorted({(f.type, f.severity) for f in found}), [("if_area_length_unknown", "WARN"), ("if_area_overlap", "FAIL")],
       "refute round 2: two areas at one start collide whatever their (unknown) lengths")
    eq(sum(f.type == "if_area_overlap" for f in found), 2, "the IN pair and the OUT pair")
    ok("(I14000..? (length unknown))" in next(f.detail for f in found if f.type == "if_area_overlap"))

    twins = _recs(("SORTER-01", "10000"), ("SORTER+DIAG-01", "20000"))
    found = a(twins, {r["instance"]: {"I": 2, "Q": 2} for r in twins},
              {r["instance"]: {"I": 128, "Q": 128} for r in twins}, [])
    eq([(f.type, f.severity, f.location) for f in found], [("if_name_duplicate", "FAIL", "NET!O2")],
       "refute round 2: SORTER-01 and SORTER+DIAG-01 are both SORTER-01")


def test_io_address_side1_generic_syntax():
    """The <GENERIC> / FVTGENERIC sheets' syntax, `I<size_modifier><base+offset>[.<bit>]` - their LET mirrored
    (found by C-031's FVT run: the old reader left `Q<size_modifier>3256[.2]`); the SORTER syntax unchanged."""
    f = interfaces.io_address_side1
    g = "I<size_modifier><base+offset>[.<bit>]"
    eq(f(g, 3256, "Q", "BOOL", 0, 2), "Q3256.2", "a BOOL keeps the optional bit, no size letter")
    eq(f(g, 10000, "<", "BOOL", 1, None), "I10001.0", "a blank bit is 0")
    eq(f(g, 10000, "I", "WORD", 4, None), "IW10004", "a WORD drops the optional part and takes W")
    eq(f(g, 10000, ">", "WORD", 6, None), "QW10006")
    eq(f("I<base+offset>/.<bit>", 10000, "Q", "BOOL", 1, 3), "Q10001.3", "the SORTER syntax as before")
    eq(f("I<base+offset>/.<bit>", 10000, "I", "WORD", 4, None), "I10004", "(its LET: TEXTBEFORE '/')")


def test_layout_extent_words():
    E = interfaces._Elem
    eq(interfaces.layout_extent(0, []), 0)
    eq(interfaces.layout_extent(1, []), 2, "a template's lone BOOL byte rounds up to its word")
    eq(interfaces.layout_extent(2, [E("X", "a", offset_byte=10, bit=0)]), 12, "a mirrored BOOL block is a word")
    eq(interfaces.layout_extent(8, [E("W", "w", data_type="WORD", offset_byte=16)]), 18, "a WORD is 2 bytes")


def _signals_db(rows):
    table = signals_table(sorted({k for r in rows for k in r}))
    for r in rows:
        table.add(**r)
    return Database([table])


def test_build_interfaces_checks_the_real_layout():
    """C-031 through the real 400 build: the template's rows + the mirrored block measured against the area (the
    IOC row's own length key, routed), the `<GENERIC>` fallback warned for a machine type with no sheet; tables
    written either way (the handler's gate halts the projections)."""
    from pipeline5 import config
    rows = [{"script_type": "IOC", "mnemonic": "SORTER-01", "bit": "10000", "source_cell": "NET!O7", "uid": "i1",
             "hardware_params": "LocalToPartnerLength=2"},
            {"script_type": "IOC", "mnemonic": "FVT_GENERIC-03", "bit": "11000", "source_cell": "NET!O8", "uid": "i2"},
            {"script_type": "DI1/2", "interface_mapping": "SORTER-01", "plc_binding": '"07_DOOR"."D1"',
             "source_cell": "NET!O20", "uid": "d1"}]
    original_db = config.database_dir
    with tempfile.TemporaryDirectory() as d:
        tpl = os.path.join(d, "t.xlsx"); _native_template(tpl)
        config.database_dir = lambda: d                        # build_interfaces saves - never into the repo
        try:
            db, found = interfaces.build_interfaces(_signals_db(rows), template_path=tpl, dtd=_ta_dtd())
        finally:
            config.database_dir = original_db
    got = [(f.type, f.severity, f.location) for f in found if f.type.startswith(("if_area", "if_sheet", "if_base"))]
    eq(got, [("if_sheet_fallback", "WARN", "NET!O8"), ("if_area_overflow", "FAIL", "NET!O7")])
    ok("machine type 'FVT' has no sheet" in found[[f.type for f in found].index("if_sheet_fallback")].detail)
    ok("12 bytes laid out on SORTER-01_OUT, the area holds 2" in
       next(f.detail for f in found if f.type == "if_area_overflow"), "the door mirrored at Q10 (word -> 12)")
    eq(len(db["interfaces"]), 2, "the tables are written")


def test_the_if_workbook_gets_the_resolved_base():
    """C-031 refute round 1: an address-spelled base (`I20000.0`) is stored RESOLVED in
    `base_address` - the IF_ workbook's Base Address (and so its cached addresses and the inserted IF_ sheet) is the
    byte the area and the tags use, never the template's 10000."""
    from openpyxl import Workbook
    from pipeline5 import config
    from pipeline5.systems.plc_based.siemens_s7 import interface_xlsx_writer as writer
    rows = [{"script_type": "IOC", "mnemonic": "SORTER-01", "bit": "I20000.0", "source_cell": "NET!O7", "uid": "i1"},
            {"script_type": "IOC", "mnemonic": "SORTER-02", "bit": "14000", "source_cell": "NET!O9", "uid": "i2"}]
    original_db = config.database_dir
    with tempfile.TemporaryDirectory() as d:
        tpl = os.path.join(d, "t.xlsx"); _native_template(tpl)
        config.database_dir = lambda: d
        try:
            db, _found = interfaces.build_interfaces(_signals_db(rows), template_path=tpl, dtd=_ta_dtd())
        finally:
            config.database_dir = original_db
    eq([(i["instance"], i["base_address"]) for i in db["interfaces"]], [("SORTER-01", "20000"), ("SORTER-02", "14000")])
    wb = Workbook(); ws = wb.active
    for c, v in enumerate(["Side", "Index", "Base Node", "Base Address"], 1):
        ws.cell(1, c, v); ws.cell(2, c, [1, "01", 10, 10000][c - 1]); ws.cell(3, c, [2, "01", 10, 0][c - 1])
    writer._plug(ws, db["interfaces"].rows[0]["base_address"], "", "", "01")
    eq(ws.cell(2, 4).value, 20000, "the IF_ workbook's Side-1 Base Address")


def _build(rows, **kw):
    """build_interfaces on `rows` with the native template + the test DTD, saving into a temp dir."""
    from pipeline5 import config
    original_db = config.database_dir
    with tempfile.TemporaryDirectory() as d:
        tpl = os.path.join(d, "t.xlsx"); _native_template(tpl)
        config.database_dir = lambda: d                        # build_interfaces saves - never into the repo
        try:
            return interfaces.build_interfaces(_signals_db(rows), template_path=tpl, dtd=_ta_dtd(), **kw)
        finally:
            config.database_dir = original_db


_FVT_IOC = {"script_type": "IOC", "mnemonic": "SORTER-01", "bit": "I10000.0", "source_cell": "NET!O6", "uid": "i1",
            "desc_l1": "IO COUPLER - INTERFACE",
            "desc_l1b": "SAFETY (=TRIC) /\n  COY LOWER SORTER   (=TRIB-AEC01)"}


def test_interface_description_from_the_ioc_row():
    """C-033: each interface's `description` is its IOC row's, through the SHIPPED template - Description L1 + its
    second part, cleaned to one line (a line break would end the SCL comment); an IOC row with neither = blank."""
    eq(interfaces.description_template(), "{clean(join(' ', $desc_l1, $desc_l1b))}", "the shipped template")
    rows = [dict(_FVT_IOC),
            {"script_type": "IOC", "mnemonic": "SORTER-02", "bit": "11000", "source_cell": "NET!O8", "uid": "i2",
             "desc_l1": "", "desc_l1b": ""}]
    db, found = _build(rows)
    eq([(i["instance"], i["description"]) for i in db["interfaces"]],
       [("SORTER-01", "IO COUPLER - INTERFACE SAFETY (=TRIC) / COY LOWER SORTER (=TRIB-AEC01)"), ("SORTER-02", "")])
    eq([f.type for f in found if f.type == "if_description_invalid"], [], "a renderable template: no finding")
    eq(interfaces.interfaces_table().columns[:3], ["uid", "instance", "description"], "the SSOT column")


def test_interface_description_template_is_config():
    """C-033: the template is the project's choice - another column set is honored, its result still made ONE line
    (the comment's line break) even when the template does not clean; a template the row cannot
    render (a field it does not carry, a malformed hole) is ONE WARN at the first IOC row, every description blank,
    the tables still built (never a crash); a project config without the key is a located error."""
    from pipeline5 import config
    rows = [dict(_FVT_IOC), dict(_FVT_IOC, mnemonic="SORTER-02", bit="11000", source_cell="NET!O8", uid="i2",
                                  desc_l1b="UPPER")]
    db, found = _build(rows, describe_with="{$mnemonic}: {$desc_l1b}")     # no clean() - the builder's own
    eq([i["description"] for i in db["interfaces"]],
       ["SORTER-01: SAFETY (=TRIC) / COY LOWER SORTER (=TRIB-AEC01)", "SORTER-02: UPPER"])
    for bad in ("{$no_such_column}", "{clean($desc_l1}"):
        db, found = _build(rows, describe_with=bad)
        warned = [(f.type, f.severity, f.location) for f in found if f.type == "if_description_invalid"]
        eq(warned, [("if_description_invalid", "WARN", "NET!O6")], f"one WARN for {bad!r}")
        eq([i["description"] for i in db["interfaces"]], ["", ""], "blank descriptions")
    original = config.load_generation_params
    config.load_generation_params = lambda: {"interfaces": {"scl_file": "x.scl"}}
    try:
        interfaces.description_template()
        ok(False, "a missing key must raise")
    except RuntimeError as error:
        ok("interfaces.description_template" in str(error), str(error))
    finally:
        config.load_generation_params = original


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
        ("interface_name_and_base_byte", test_interface_name_and_base_byte),
        ("ioc_base_is_its_own_bit", test_ioc_base_is_its_own_bit),
        ("area_lengths_default_and_override", test_area_lengths_default_and_override),
        ("mapping_by_name_number_and_diag_name", test_mapping_by_name_number_and_diag_name),
        ("unknown_interface_name_warns", test_unknown_interface_name_warns),
        ("area_findings_overflow_overlap_and_base", test_area_findings_overflow_overlap_and_base),
        ("io_address_side1_generic_syntax", test_io_address_side1_generic_syntax),
        ("layout_extent_words", test_layout_extent_words),
        ("build_interfaces_checks_the_real_layout", test_build_interfaces_checks_the_real_layout),
        ("the_if_workbook_gets_the_resolved_base", test_the_if_workbook_gets_the_resolved_base),
        ("interface_description_from_the_ioc_row", test_interface_description_from_the_ioc_row),
        ("interface_description_template_is_config", test_interface_description_template_is_config),
    ]))

"""Phase 910 - the signal-paths report (phases/coverage/signal_paths.py): the template wiring (read / write per
access, FB channels), the variant a network row names, the iterator handed out in document order, the graph from the
SSOT tables traced end to end, and the self-contained page. Hermetic (synthetic FBD templates in a temp dir) plus the
shipped 02 EM Push Button template."""
import json
import os
import re
import tempfile

from _harness import run, eq, ok
from pipeline5.config import paths
from pipeline5.phases.coverage import signal_paths as sp

NS = 'xmlns="http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v4"'


def _access(uid, *components):
    comps = "".join(f'<Component Name="{c}" />' for c in components)
    return f'<Access Scope="GlobalVariable" UId="{uid}"><Symbol>{comps}</Symbol></Access>'


def _unit(accesses, parts, wires):
    return (f'<SW.Blocks.CompileUnit ID="3"><AttributeList><NetworkSource><FlgNet {NS}><Parts>{accesses}{parts}'
            f'</Parts><Wires>{wires}</Wires></FlgNet></NetworkSource></AttributeList></SW.Blocks.CompileUnit>')


def _wire(*ends):
    return "<Wire UId=\"99\">" + "".join(ends) + "</Wire>"


def _ident(uid):
    return f'<IdentCon UId="{uid}" />'


def _pin(uid, name):
    return f'<NameCon UId="{uid}" Name="{name}" />'


def _template(path, *units):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write('<?xml version="1.0" encoding="utf-8"?><Document><SW.Blocks.FB ID="0"><ObjectList>'
                     + "".join(units) + "</ObjectList></SW.Blocks.FB></Document>")
    return path


# a push-button FB with two channels: IN_n read, OUT_n (a DB member) and Lamp_n written; a bypass read on no channel
PUSH = _unit(
    _access(21, "00_Commissioning", "!!00_Commissioning.{db_element}$$")
    + _access(22, "!!ITERATOR_STRINGS$$") + _access(23, "!!ITERATOR_STRINGS$$")
    + _access(24, "01_PushButton", "!!ITERATOR_STRINGS$$") + _access(25, "01_PushButton", "!!ITERATOR_STRINGS$$")
    + _access(26, "!!ITERATOR_STRINGS$$") + _access(27, "!!ITERATOR_STRINGS$$"),
    '<Call UId="31"><CallInfo Name="00_Push-Button_Input" BlockType="FB" /></Call>',
    _wire(_ident(21), _pin(31, "Bypass_ET200")) + _wire(_ident(22), _pin(31, "IN_1")) + _wire(_ident(23), _pin(31, "IN_2"))
    + _wire(_pin(31, "OUT_1"), _ident(24)) + _wire(_pin(31, "OUT_2"), _ident(25))
    + _wire(_pin(31, "Lamp_1"), _ident(26)) + _wire(_pin(31, "Lamp_2"), _ident(27)))
# a zone: an AND of the iterator's members (gate inputs - no channels) driving a coil on 02_COM
ZONE = _unit(
    _access(21, "!!nameOfDB$$", "!!ITERATOR_STRINGS$$") + _access(22, "!!nameOfDB$$", "!!ITERATOR_STRINGS$$")
    + _access(23, "02_COM", "!!02_COM.{db_element}$$"),
    '<Part Name="A" UId="30" /><Part Name="Coil" UId="31" />',
    _wire(_ident(21), _pin(30, "in1")) + _wire(_ident(22), _pin(30, "in2")) + _wire(_pin(30, "out"), _pin(31, "in"))
    + _wire(_ident(23), _pin(31, "operand")))
# an output: reads the zone member through a contact, writes the contactor tag through a coil
OUTPUT = _unit(
    _access(21, "02_COM", "!!02_COM.{zone}$$") + _access(22, "!!tagName:Contactor$$"),
    '<Part Name="Contact" UId="30" /><Part Name="Coil" UId="31" />',
    _wire(_ident(21), _pin(30, "operand")) + _wire(_pin(30, "out"), _pin(31, "in")) + _wire(_ident(22), _pin(31, "operand")))
OTHER = _unit(_access(21, "!!tagName:Other$$"), '<Part Name="Coil" UId="31" />',
              _wire(_ident(21), _pin(31, "operand")))


def test_network_wiring_directions_and_channels():
    """An access feeding a pin is read, one a part output feeds is written, a coil's operand is written and a
    contact's operand read; an FB call's numbered pin names the channel (`IN_1` / `OUT_1` / `Lamp_1` = channel 1), a
    gate input (`in1`) none - in document order."""
    with tempfile.TemporaryDirectory() as d:
        push = sp.template_variants(_template(os.path.join(d, "push.xml"), PUSH))[0]
        zone = sp.template_variants(_template(os.path.join(d, "zone.xml"), ZONE))[0]
        output = sp.template_variants(_template(os.path.join(d, "out.xml"), OUTPUT))[0]
    eq([(c[-1], dr, ch[1] if ch else None) for c, dr, ch in push], [
        ("!!00_Commissioning.{db_element}$$", "read", None),
        ("!!ITERATOR_STRINGS$$", "read", 1), ("!!ITERATOR_STRINGS$$", "read", 2),
        ("!!ITERATOR_STRINGS$$", "write", 1), ("!!ITERATOR_STRINGS$$", "write", 2),
        ("!!ITERATOR_STRINGS$$", "write", 1), ("!!ITERATOR_STRINGS$$", "write", 2)])
    eq([(c, dr, ch) for c, dr, ch in zone], [
        (("!!nameOfDB$$", "!!ITERATOR_STRINGS$$"), "read", None), (("!!nameOfDB$$", "!!ITERATOR_STRINGS$$"), "read", None),
        (("02_COM", "!!02_COM.{db_element}$$"), "write", None)], "gate inputs are no channels; the coil writes")
    eq([dr for _c, dr, _ch in output], ["read", "write"], "a contact's operand is read, a coil's written")


def test_variants_follow_document_order():
    """Template network k is the variant `TemplateType` k (marker-less exports); a row naming no network is noted."""
    with tempfile.TemporaryDirectory() as d:
        path = _template(os.path.join(d, "t.xml"), OUTPUT, OTHER)
        eq(len(sp.template_variants(path)), 2)
        db = {"software_blocks": [{"name": "05_Out", "template_ref": path}],
              "software_block_members": [
                  {"block": "05_Out", "seq": "0", "values": {"TemplateType": "02", "tagName:Other": "Horn"}},
                  {"block": "05_Out", "seq": "1", "values": {"TemplateType": "07", "tagName:Other": "Ghost"}}]}
        g, notes = sp.build_graph(db)
    eq(sorted(label for kind, label, _s in g.nodes.values() if kind == "tag"), ['"Horn"'], "variant 2 wired; 07 none")
    eq(notes, ["networks whose TemplateType names no template network: 05_Out"])
    eq(sp.template_variants(os.path.join(tempfile.gettempdir(), "no-such-template.xml")), [], "a missing template")


def test_iterator_handed_out_in_order_and_pads_dropped():
    """Each iterator access takes the next list value in document order (OP5's generator does the same); a pad
    (`No Operation`) and a blank access give no symbol, the list still advancing."""
    with tempfile.TemporaryDirectory() as d:
        push = sp.template_variants(_template(os.path.join(d, "push.xml"), PUSH))[0]
    values = {"00_Commissioning.{db_element}": "", "ITERATOR_STRINGS":
              ["PB1", "No Operation", "PB1", "No Operation", "Lamp PB1", "No Operation"]}
    eq(sp.network_symbols(push, values, {"no operation"}), [
        (("PB1",), "read", (push[1][2][0], 1)), (("01_PushButton", "PB1"), "write", (push[1][2][0], 1)),
        (("Lamp PB1",), "write", (push[1][2][0], 1))])


def _estop_db(d):
    """Two push buttons in one 02 network (channels 1 and 2), their zone, the zone's contactor, a lamp, an
    interface element and an alarm on PB1's member - the FVT shape in miniature."""
    refs = {name: _template(os.path.join(d, f"{name}.xml"), unit)
            for name, unit in (("02_PB", PUSH), ("03_Zone", ZONE), ("05_Out", OUTPUT))}
    rows = [dict(uid="e1", kind="signal", script_type="E", FLD="=ES-1", address="I1.0", tag="PB1", source_cell="S!O1"),
            dict(uid="e2", kind="signal", script_type="E", FLD="=ES-2", address="I1.1", tag="PB2", source_cell="S!O2"),
            dict(uid="q1", kind="signal", script_type="KQ", FLD="=K1", address="Q2.0", tag="Contactor K1", source_cell="S!O3"),
            dict(uid="l1", kind="signal", script_type="EL", FLD="=ES-1", address="Q3.0", tag="Lamp PB1", source_cell="S!O4"),
            dict(uid="l2", kind="signal", script_type="EL", FLD="=ES-2", address="Q3.1", tag="Lamp PB2", source_cell="S!O5"),
            dict(uid="c1", kind="channel", script_type="", FLD="", address="I9.0", tag="", source_cell="S!O6")]
    return {
        "coverage": rows,
        "software_blocks": [{"name": n, "template_ref": r} for n, r in refs.items()],
        "software_block_members": [
            {"block": "02_PB", "seq": "0", "values": {"TemplateType": "01", "NetworkComment": "node 23",
                                                    "00_Commissioning.{db_element}": "n0023",
                                                    "ITERATOR_STRINGS": ["PB1", "PB2", "PB1", "PB2", "Lamp PB1", "Lamp PB2"]}},
            {"block": "03_Zone", "seq": "0", "values": {"TemplateType": "01", "NetworkComment": "AREA 1 PB",
                                                      "nameOfDB": "01_Pushbutton", "02_COM.{db_element}": "AREA 1 PB",
                                                      "ITERATOR_STRINGS": ["PB1", "PB2"]}},
            {"block": "05_Out", "seq": "0", "values": json.dumps({"TemplateType": "01", "02_COM.{zone}": "AREA 1 PB",
                                                                  "tagName:Contactor": "Contactor K1"})}],
        "interface_elements": [{"uid": "x1", "interface": "SORTER-01", "direction": "Q", "io_address_side1": "Q100.0",
                                "expression": '"01_PushButton"."PB1"', "signal_name": "PNC_Q_PB1"},
                               {"uid": "x2", "interface": "SORTER-01", "direction": "I", "io_address_side1": "I100.0",
                                "expression": "Open Request D1", "signal_name": "PNC_I_Open Request D1"}],
        "diagnosis_entries": [{"uid": "a1", "in_binding": '"01_Pushbutton"."PB1"', "cabinet": "2", "bit": "0",
                               "is_warning": "false", "rule_name": ""}]}


def test_the_graph_traces_an_estop_to_its_outputs():
    """End to end on the SSOT tables: an e-stop row -> its tag -> its own push-button channel -> its member (the
    template's `01_PushButton` IS the DB `01_Pushbutton` - TIA names are case-insensitive) and its lamp -> the zone
    -> the contactor; the member's interface assignment and alarm bit are ends too. The OTHER button of the same
    network never reaches PB1's member, lamp or alarm (the per-channel trace); a contactor row is driven, not
    driving; a channel row reaches nothing."""
    with tempfile.TemporaryDirectory() as d:
        db = _estop_db(d)
        g, notes = sp.build_graph(db)
    eq(notes, [])
    out, inn = g.adjacency(), g.adjacency(reverse=True)
    reached = lambda uid: {g.nodes[n][1] for n in sp.reach(out, f"r:{uid}")}
    eq(sp.ends(g, out, "r:e1", inn), {"outputs": 2, "alarms": 1, "interfaces": 1, "unread": 1, "steps": 13,
                                       "feeders": 0}, "contactor + lamp, the alarm, the interface, PNC_Q_PB1 unread")
    ok({"E  =ES-1", '"PB1"', '"01_PushButton"."PB1"', '"Lamp PB1"', '"02_COM"."AREA 1 PB"', '"Contactor K1"',
        "KQ  =K1", "EL  =ES-1", '"PNC_Q_PB1"'} <= reached("e1"), reached("e1"))
    ok(not ({'"Lamp PB1"', "EL  =ES-1", '"PNC_Q_PB1"'} & reached("e2")), "PB2 stays on its own channel")
    ok("KQ  =K1" in reached("e2"), "both buttons trip the zone's contactor")
    eq(sp.ends(g, out, "r:q1", inn)["steps"], 0, "an output row drives nothing")
    eq(sp.ends(g, out, "r:q1", inn)["feeders"], 2, "the contactor is driven by both buttons")
    eq(sp.ends(g, out, "r:c1", inn), {"outputs": 0, "alarms": 0, "interfaces": 0, "unread": 0, "steps": 0,
                                       "feeders": 0}, "an untyped channel: no path")
    upstream = {g.nodes[n][1] for n in sp.reach(inn, 'v:"open request d1"')}
    ok('"PNC_I_Open Request D1"' in upstream, "an incoming element: the interface tag feeds the expression")
    ok('"Open Request D1"' not in {g.nodes[n][1] for n in sp.reach(inn, 'v:"pnc_i_open request d1"')}, "not back")


def test_a_ready_block_is_traced_as_rendered():
    """A block PL5 renders READY (03 Zone Cumulative: an AND sized to all its inputs) is traced from that XML -
    every input as wired, the network titled as rendered - never from the template's slots: FVT's AREA 1 PB holds
    208 push buttons on the 10-input variant 01, and every one of them trips the zone. Its template rows are
    then not read."""
    zone = _unit(_access(21, "01_Pushbutton", "PB1") + _access(22, "01_Pushbutton", "PB2")
                 + _access(23, "01_Pushbutton", "PB3") + _access(24, "02_COM", "AREA 1 PB"),
                 '<Part Name="A" UId="30" /><Part Name="Coil" UId="31" />',
                 _wire(_ident(21), _pin(30, "in1")) + _wire(_ident(22), _pin(30, "in2")) + _wire(_ident(23), _pin(30, "in3"))
                 + _wire(_pin(30, "out"), _pin(31, "in")) + _wire(_ident(24), _pin(31, "operand")))
    zone = zone.replace("<AttributeList>", '<ObjectList><MultilingualText CompositionName="Title"><ObjectList>'
                        '<MultilingualTextItem><AttributeList><Text>AREA 1 PB - AREA 1</Text></AttributeList>'
                        '</MultilingualTextItem></ObjectList></MultilingualText></ObjectList><AttributeList>', 1)
    xml = '<?xml version="1.0" encoding="utf-8"?><Document><SW.Blocks.FC ID="0"><ObjectList>' + zone +           "</ObjectList></SW.Blocks.FC></Document>"
    eq([(t, [(p, d) for p, d, _c in acc]) for t, acc in sp.ready_networks(xml)],
       [("AREA 1 PB - AREA 1", [(("01_Pushbutton", "PB1"), "read"), (("01_Pushbutton", "PB2"), "read"),
                                (("01_Pushbutton", "PB3"), "read"), (("02_COM", "AREA 1 PB"), "write")])])
    with tempfile.TemporaryDirectory() as d:
        db = _estop_db(d)
        db["coverage"].append(dict(uid="e3", kind="signal", script_type="E", FLD="=ES-3", address="I1.2", tag="PB3",
                                   source_cell="S!O8"))
        db["software_block_members"].append({"block": "02_PB", "seq": "1", "values": {
            "TemplateType": "01", "00_Commissioning.{db_element}": "", "ITERATOR_STRINGS": ["PB3", "", "PB3", "", "", ""]}})
        before, _n = sp.build_graph(db)
        after, _n = sp.build_graph(db, ready={"03_Zone": xml})
    reached = lambda g: {g.nodes[n][1] for n in sp.reach(g.adjacency(), "r:e3")}
    ok("KQ  =K1" not in reached(before), "the template row (two slots) leaves PB3 out of the zone")
    ok("KQ  =K1" in reached(after), "the rendered zone wires PB3 - the e-stop trips its contactor")
    eq(sorted(sub for kind, label, sub in after.nodes.values() if kind == "net" and label == "03_Zone"),
       ["AREA 1 PB - AREA 1"], "one network, as rendered - the template row not read")
    eq(sp.ready_networks("not xml"), [], "no block XML: nothing")


def test_the_page_embeds_the_graph():
    """The page is one self-contained HTML: the data JSON (every coverage row, its ends) parses back from its script
    block - a `</script>` inside a name escaped - and the title is escaped; no external resource."""
    with tempfile.TemporaryDirectory() as d:
        db = _estop_db(d)
        db["coverage"].append(dict(uid="h1", kind="signal", script_type="X", FLD="=H", address="I8.0",
                                   tag="PB1 </script><b>", source_cell="S!O7"))
        res = sp.project(db, out_dir=os.path.join(d, "out"), title="Paths <8FVT>")
        text = open(res["html"], encoding="utf-8").read()
    eq((os.path.basename(res["html"]), res["signals"], res["traced"]), ("io_signal_paths.html", 7, 6),
       "7 rows; all but the channel have a path out or in")
    ok("<title>Paths &lt;8FVT&gt;</title>" in text, "the title escaped")
    payload = re.search(r'<script id="data" type="application/json">(.*?)</script>', text, re.S).group(1)
    data = json.loads(payload)
    eq([s[3] for s in data["signals"]], ["=ES-1", "=ES-2", "=K1", "=ES-1", "=ES-2", "", "=H"], "every coverage row")
    ok(any(s[5] == "PB1 </script><b>" for s in data["signals"]), "the hostile tag survives the round trip")
    ok(not re.search(r"<(script|link)[^>]+(src|href)=", text), "no external script or stylesheet")


def test_the_shipped_push_button_template_is_traced_per_channel():
    """The SHIPPED 02 EM Push Button template: IN_n read, OUT_n (01_PushButton members) and Lamp_n written on
    channels 1-4, the commissioning bypass read on none - what keeps one button out of its neighbours' paths."""
    path = os.path.join(paths.TEMPLATES_DIR, "Tia Portal Software Blocks", "TEMPLATE--v1.2--02_EM Push Button.xml")
    accesses = sp.template_variants(path)[0]
    eq([(c, d, ch[1] if ch else None) for c, d, ch in accesses],
       [(("00_Commissioning", "!!00_Commissioning.{db_element}$$"), "read", None)]
       + [(("!!ITERATOR_STRINGS$$",), "read", n) for n in (1, 2, 3, 4)]
       + [(("01_PushButton", "!!ITERATOR_STRINGS$$"), "write", n) for n in (1, 2, 3, 4)]
       + [(("!!ITERATOR_STRINGS$$",), "write", n) for n in (1, 2, 3, 4)])


if __name__ == "__main__":
    import sys
    sys.exit(run("signal_paths", [
        ("network_wiring_directions_and_channels", test_network_wiring_directions_and_channels),
        ("variants_follow_document_order", test_variants_follow_document_order),
        ("iterator_handed_out_in_order_and_pads_dropped", test_iterator_handed_out_in_order_and_pads_dropped),
        ("the_graph_traces_an_estop_to_its_outputs", test_the_graph_traces_an_estop_to_its_outputs),
        ("a_ready_block_is_traced_as_rendered", test_a_ready_block_is_traced_as_rendered),
        ("the_page_embeds_the_graph", test_the_page_embeds_the_graph),
        ("the_shipped_push_button_template_is_traced_per_channel",
         test_the_shipped_push_button_template_is_traced_per_channel),
    ]))

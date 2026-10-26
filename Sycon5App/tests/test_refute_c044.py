"""C-044 refute round 1 (2026-10-26), the Sycon5App side of the production folder: BusField.csv attacked with a
station the project lacks, a device the project records without a GSDML identity, a description with the file's own
delimiter inside, card folders in another case, a card without a project, a project without a controller; the canvas
with empty groups and an XML without a channel. What broke and was fixed: a `;` in a description shifted the IO
driver's columns (replaced by `,` now); a device without identity went into the configuration as node type
0x00000000 (commented out now, `# ... NO DEVICE IDENTITY`); the header's `source` named cards that were skipped
(the written ones only); a project without a controller crashed the writer (skipped with a message). What held: the
master and its own station rows, a missing station commented out, the lowercase folder, the file's header and
encoding, the canvas on empty and channel-less inputs."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
PL5 = os.path.join(os.path.dirname(APP), "Pipeline5App")
sys.path.insert(0, APP)
sys.path.insert(0, PL5)
from sycon5 import canvas  # noqa: E402
from sycon5.handoff import Handoff  # noqa: E402
from sycon5.readback import Device, Project  # noqa: E402
from pipeline5.systems.ipc_based.intervalzero_rtx import sycon_handoff as pl5  # noqa: E402

spec = importlib.util.spec_from_file_location("busfield", os.path.join(APP, "scripts", "busfield.py"))
busfield = importlib.util.module_from_spec(spec)
spec.loader.exec_module(busfield)

XML = ('<?xml version="1.0" encoding="UTF-8"?>\n<Project xmlns:fdt="urn:fdt">\n'
       '<Device deviceNo="controller" progId="Hilscher.PNIOController" fdt:manufacturerId="286" fdt:deviceTypeId="515"/>\n'
       '<Device deviceNo="n0005-a" progId="x.Slave" fdt:manufacturerId="42" fdt:deviceTypeId="787"/>\n'
       '<Device deviceNo="n0006-b" progId="x.Slave"/>\n</Project>\n')
NO_CONTROLLER_XML = XML.replace('progId="Hilscher.PNIOController"', 'progId="x.Slave"')


def station(role, name, ip, **more):
    row = {k: "" for k in pl5.STATIONS_KEYS}
    row.update({"role": role, "station_name": name, "catalog_kind": "master" if role == "controller" else "slave",
                "catalog_item": "CIFX RE/PNM" if role == "controller" else "AL1202", "model_id": "X", "ip_address": ip,
                "subnet_mask": "255.255.255.0", "description": "DESC", "manufacturer": "MAN", "fld": "=TRIB"})
    row.update(more)
    return row


def card_folder(root, n, rows, xml=XML, with_project=True):
    folder = os.path.join(root, "HilscherIOCard%d" % n if n != 2 else "hilscheriocard2")
    handoff = os.path.join(folder, "SyconNetProjectInterface")
    os.makedirs(handoff)
    with open(os.path.join(handoff, "SyconStations.csv"), "w", encoding="utf-8", newline="") as f:
        f.write(pl5._csv(pl5.KIND_STATIONS, pl5.STATIONS_HDR, rows, pl5.STATIONS_KEYS, "test"))
    if with_project:
        os.makedirs(os.path.join(folder, "HilscherPnCard_%d" % n, "_S129"))
        open(os.path.join(folder, "HilscherPnCard_%d.spj" % n), "w").write("spj")
        open(os.path.join(folder, "HilscherPnCard_%d" % n, "_S129", "SYCON_net.xml"), "w", encoding="utf-8").write(xml)
    return folder


def test_rows_of_a_card_with_a_missing_station_a_blank_identity_and_a_hostile_description():
    h = Handoff(folder="", controller=station("controller", "controller", "192.168.1.1"),
                stations=[station("slave", "n0005-a", "192.168.1.5", description="OK; FINE", comment="a;b"),
                          station("slave", "n0006-b", "192.168.1.6"), station("slave", "n0007-c", "192.168.1.300")])
    devices = [Device(device_no="controller", symbolic="", prog_id="Hilscher.PNIOController", gsdml="", manufacturer_id=286, device_type_id=515),
               Device(device_no="N0005-A", symbolic="", prog_id="x.Slave", gsdml="", manufacturer_id=42, device_type_id=787),
               Device(device_no="n0006-b", symbolic="", prog_id="x.Slave", gsdml="")]
    rows = busfield.card_rows(1, h, Project(path="", devices=devices))
    assert rows[0] == "@;1;0;0x011E0203;0;0;0;0;0;0;0;0;#;Hilscher Master Profinet Card 1"
    assert rows[1].startswith("#;1;1;0x011E0203;") and "[controller]" in rows[1], "the master's own station, commented out"
    assert rows[2] == "@;1;5;0x002A0313;0;0;0;0;0;0;0;0;#;[n0005-a] OK, FINE (a,b) =TRIB (192.168.1.5)"
    assert rows[3].startswith("#;1;6;0x00000000;") and rows[3].endswith("NO DEVICE IDENTITY IN THE PROJECT")
    assert rows[4].startswith("#;1;300;0x00000000;") and rows[4].endswith("NOT IN THE PROJECT")
    assert all(r.count(";") == 13 for r in rows), "fourteen columns in every row, whatever the texts hold"


def test_the_file_names_only_the_cards_it_wrote_and_survives_odd_folders(tmp_path):
    root = str(tmp_path)
    card_folder(root, 1, [station("controller", "controller", "192.168.1.1"), station("slave", "n0005-a", "192.168.1.5", description="café")])
    card_folder(root, 2, [station("controller", "controller", "192.168.2.1")])                     # lowercase folder name
    card_folder(root, 3, [station("controller", "controller", "192.168.3.1")], with_project=False)  # no project yet
    card_folder(root, 4, [station("controller", "controller", "192.168.4.1")], xml=NO_CONTROLLER_XML)
    os.makedirs(os.path.join(root, "HilscherIOCard5x"))                                               # not a card
    path = busfield.write_busfield(root)
    raw = open(path, "rb").read()
    assert raw.startswith(b"#!openn\r\n#! kind: hw/iodriver-busfield\r\n") and b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("ascii")
    source = [ln for ln in text.splitlines() if ln.startswith("#! source:")][0]
    assert source == "#! source: HilscherIOCard1/HilscherPnCard_1, HilscherIOCard2/HilscherPnCard_2", source
    body = [ln for ln in text.splitlines() if ln[:1] in "@#" and not ln.startswith("#!") and not ln.startswith("#;Board")]
    assert [ln.split(";")[1] for ln in body] == ["1", "1", "1", "2", "2"], body
    assert "caf?" in text, "ASCII with replacement, as the IO driver reads it"


def test_the_canvas_on_empty_and_channel_less_inputs(tmp_path):
    assert canvas.layout([]) == {}
    assert canvas.group_of("") == "other" and canvas.group_of(None) == "other"
    rects = canvas.layout([{"station_name": "a", "catalog_item": None}, {"station_name": "b", "catalog_item": "SCALANCE XC216"}])
    assert set(rects) == {"a", "b"} and rects["b"][2] - rects["b"][0] == canvas.SIZE["switch"][0]
    path = str(tmp_path / "SYCON_net.xml")
    open(path, "w", encoding="utf-8").write('<?xml version="1.0"?><Project><BusLine><PositionRect top="1" left="2" bottom="3" right="4"/>'
                                            '<Device deviceNo="controller" devicekind="HIL_MASTER" syc:symbolicName="" xmlns:syc="urn:s">'
                                            '<PositionRect top="1" left="1" bottom="2" right="2"/></Device></BusLine></Project>')
    assert canvas.apply(path, {}, {}) == (0, 1), "the controller's box alone, no channel to hang a bus on"
    assert "<BusLines" not in open(path, encoding="utf-8").read()

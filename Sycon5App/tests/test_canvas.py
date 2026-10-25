"""The canvas writer (no GUI): the rule layout of a station list and the in-place edit of a project XML - the
symbolic names and the rectangles written, read back by read_project, the rest of the text untouched."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sycon5 import canvas  # noqa: E402
from sycon5.readback import read_project  # noqa: E402

XML = ('<?xml version="1.0" encoding="UTF-8"?>\n'
       '<Devices xmlns="x-schema:StoreSchema.xml" xmlns:syc="x-schema:SyConDataTypesSchema.xml" '
       'xmlns:fdt="x-schema:FDTDataTypesSchema.xml" syc:deviceName="ProjectName" syc:version="1.1.0.3">\n'
       '\t<BusLines channelPath="/Root">\n'
       '\t\t<BusLine>\n\t\t\t<PositionRect top="50" left="50" bottom="54" right="950"/>\n\t\t</BusLine>\n'
       '\t\t<BusLine>\n\t\t\t<PositionRect top="50" left="414" bottom="72" right="416"/>\n'
       '\t\t\t<Device syc:deviceName="CIFX RE/PNM" syc:symbolicName="CIFX_RE_PNM" syc:progId="Hilscher.PNIOControllerDTM2.1" '
       'syc:devicekind="HIL_MASTER" fdt:manufacturerId="286" fdt:deviceTypeId="515" deviceNo="controller" fdt:deviceTypeInformation="">\n'
       '\t\t\t\t<PositionRect top="72" left="400" bottom="104" right="432"/>\n'
       '\t\t\t\t<BusLines channelPath="/PROFINET_IO">\n'
       '\t\t\t\t\t<BusLine>\n\t\t\t\t\t\t<PositionRect top="72" left="432" bottom="76" right="950"/>\n\t\t\t\t\t</BusLine>\n'
       '\t\t\t\t\t<BusLine>\n\t\t\t\t\t\t<PositionRect top="72" left="546" bottom="92" right="548"/>\n'
       '\t\t\t\t\t\t<Device syc:deviceName="IM 155-6 PN ST V4.2" syc:symbolicName="IM_155-6_PN_ST_V4.2" syc:progId="Hilscher.PNIOGenDevDTM2.1" '
       'syc:devicekind="HIL_SLAVE" fdt:manufacturerId="42" fdt:deviceTypeId="787" deviceNo="n0005-trib-aep01-k35001" '
       'fdt:deviceTypeInformation="C:\\\\GSDML\\\\GSDML-V2.35-Siemens-ET200SP-20210401.xml">\n'
       '\t\t\t\t\t\t\t<PositionRect top="92" left="532" bottom="124" right="564"/>\n'
       '\t\t\t\t\t\t</Device>\n\t\t\t\t\t</BusLine>\n'
       '\t\t\t\t\t<BusLine>\n\t\t\t\t\t\t<PositionRect top="72" left="616" bottom="92" right="618"/>\n'
       '\t\t\t\t\t\t<Device syc:deviceName="PN/PN Coupler X2" syc:symbolicName="PN_PN_Coupler_X2" syc:progId="Hilscher.PNIOGenDevDTM2.1" '
       'syc:devicekind="HIL_SLAVE" fdt:manufacturerId="42" fdt:deviceTypeId="1540" deviceNo="n0006-trib-aec01-k24501" fdt:deviceTypeInformation="">\n'
       '\t\t\t\t\t\t\t<PositionRect top="92" left="602" bottom="124" right="634"/>\n'
       '\t\t\t\t\t\t</Device>\n\t\t\t\t\t</BusLine>\n'
       '\t\t\t\t</BusLines>\n\t\t\t</Device>\n\t\t</BusLine>\n\t</BusLines>\n</Devices>\n')

STATIONS = [
    {"station_name": "n0006-trib-aec01-K24501", "catalog_item": "PN/PN Coupler X2 [DAP X2 V4.2]", "symbolic_name": "SORTER (=TRIB) / INDUCTION <GR1> & \"2\""},
    {"station_name": "n0005-trib-aep01-K35001", "catalog_item": "IM 155-6 PN ST V4.2", "symbolic_name": "=TRIB-AEP01"},
    {"station_name": "n0010-trib-aec01-K26501", "catalog_item": "SCALANCE XC216-4C V4.4", "symbolic_name": "=TRIB-AEC01"},
] + [{"station_name": "drive%02d" % i, "catalog_item": "ServoOne Junior", "symbolic_name": ""} for i in range(10)]


def test_layout_rows_per_group_as_stairs():
    rects = canvas.layout(STATIONS)
    assert len(rects) == 13
    et, coupler, switch = rects["n0005-trib-aep01-K35001"], rects["n0006-trib-aec01-K24501"], rects["n0010-trib-aec01-K26501"]
    assert et == (83, 60, 115, 92), et                                 # the first group's first box
    assert coupler[0] == 83 + 32 + 36 and coupler[1] == 60              # the next group below the last row
    assert switch[2] - switch[0] == 40 and switch[3] - switch[1] == 70  # a switch box
    drives = [rects["drive%02d" % i] for i in range(10)]
    assert drives[1][0] == drives[0][0] + 22 and drives[1][1] == drives[0][1] + 70   # a stair
    assert drives[8][0] == drives[0][0] + 200 and drives[8][1] == 60    # the second row of the group
    assert drives[7][1] == 60 + 7 * 70
    assert canvas.group_of("Anybus Communicator") == "gateway" and canvas.group_of("Whatever") == "other"
    # the rows run in FLD order, not in table or name order
    by_fld = [{"station_name": "n0090-x", "catalog_item": "AL1202", "fld": "=TRIB-SM071-K1"},
              {"station_name": "n0035-x", "catalog_item": "AL1202", "fld": "=TRIB-SM006-K1"},
              {"station_name": "n0087-x", "catalog_item": "AL1202", "fld": "=TRIB-RC01-K1"}]
    r = canvas.layout(by_fld)
    assert r["n0087-x"][1] < r["n0035-x"][1] < r["n0090-x"][1]


def test_apply_writes_labels_and_boxes_in_place():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "SYCON_net.xml")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(XML)
        symbolics = {s["station_name"]: s["symbolic_name"] for s in STATIONS if s["symbolic_name"]}
        rects = canvas.layout(STATIONS)
        n_sym, n_rect = canvas.apply(path, symbolics, rects)
        assert (n_sym, n_rect) == (2, 3)                                # two stations + the controller's box
        p = read_project(path)
        ctrl = p.controller
        assert ctrl.rect == canvas.CONTROLLER_RECT and ctrl.line_rect == (52, 49, 53, 51) and ctrl.symbolic == "CIFX_RE_PNM"
        assert ctrl.node_type == "0x011E0203"
        et = p.device("n0005-trib-aep01-k35001")
        assert et.symbolic == "=TRIB-AEP01" and et.rect == (83, 60, 115, 92) and et.line_rect == (98, 8, 100, 60)
        assert et.node_type == "0x002A0313" and et.gsdml == "GSDML-V2.35-Siemens-ET200SP-20210401.xml"
        coupler = p.device("n0006-trib-aec01-k24501")
        assert coupler.symbolic == 'SORTER (=TRIB) / INDUCTION <GR1> & "2"' and coupler.node_type == "0x002A0604"
        text = open(path, encoding="utf-8").read()
        assert 'syc:symbolicName="SORTER (=TRIB) / INDUCTION &lt;GR1&gt; &amp; &quot;2&quot;"' in text
        assert "channelPath" in text
        # the channel's stub from the bus to the controller, and the vertical bus line past the lowest device
        assert '<PositionRect top="72" left="8" bottom="76" right="34"/>' in text
        lowest = max(rects[k][2] for k in ("n0005-trib-aep01-K35001", "n0006-trib-aec01-K24501"))   # the devices the XML has
        assert text.count("<PositionRect") == XML.count("<PositionRect") + 1
        assert '<PositionRect top="72" left="8" bottom="%d" right="12"/>' % (lowest + canvas.BUS_MARGIN) in text
        assert text.index('right="12"/>') < text.rindex("</BusLines>") and text.index('right="12"/>') > text.index("/PROFINET_IO")
        # idempotent: the vertical bus line is updated, not added again
        assert canvas.apply(path, symbolics, rects) == (0, 3)
        text2 = open(path, encoding="utf-8").read()
        assert text2.count("<PositionRect") == text.count("<PositionRect") and text2.count('right="12"/>') == 1
        p2 = read_project(path)
        assert p2.device("n0006-trib-aec01-k24501").line_rect[1] == 8


if __name__ == "__main__":
    test_layout_rows_per_group_as_stairs()
    test_apply_writes_labels_and_boxes_in_place()
    print("ok")

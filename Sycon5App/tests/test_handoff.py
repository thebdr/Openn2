"""The handoff reader - the `#!openn` header, the column line, the GSDML column present or not (the exports
before 2026-10-23 pm have none) - and the catalog info pane's GSDML citation parser."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sycon5 import handoff  # noqa: E402
from sycon5.catalog import info_files  # noqa: E402

HEAD = "#!openn\r\n#! kind: hw/sycon-stations\r\n#! schema: 1\r\n#!end\r\n"
OLD = (HEAD + "# Role,Station Name,Catalog Kind,Catalog Item,Model Id,IP Address,Subnet Mask,Gateway,Device Number,"
       "Description,Comment\r\n"
       "controller,n0001,master,CIFX RE/PNM,CIFX80-RE/ML,192.168.1.1,255.255.255.0,,1,PC,HILSCHER\r\n"
       "slave,n0006,slave,PN/PN Coupler X2,6ES7158-3AD10-0XA0,192.168.1.6,255.255.255.0,,6,COUPLER,SIEMENS\r\n")
NEW = (HEAD + "# Role,Station Name,Catalog Kind,Catalog Item,Model Id,GSDML (the file of the catalog entry to take),"
       "IP Address,Subnet Mask,Gateway,Device Number,Description,Comment\r\n"
       "controller,n0001,master,CIFX RE/PNM,CIFX80-RE/ML,,192.168.1.1,255.255.255.0,,1,PC,HILSCHER\r\n"
       "slave,n0006,slave,PN/PN Coupler X2,6ES7158-3AD10-0XA0,GSDML-V2.35-Siemens-PNPNIOC-20200924.xml,"
       "192.168.1.6,255.255.255.0,,6,COUPLER,SIEMENS\r\n")


def _load(text):
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, handoff.STATIONS_FILE), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return handoff.load_handoff(d)


def test_stations_without_gsdml_column():
    h = _load(OLD)
    s = h.stations[0]
    assert s["ip_address"] == "192.168.1.6" and s["gsdml"] == "" and s["comment"] == "SIEMENS"
    assert h.controller["ip_address"] == "192.168.1.1" and h.controller["gsdml"] == ""


def test_stations_with_gsdml_column():
    h = _load(NEW)
    s = h.stations[0]
    assert s["gsdml"] == "GSDML-V2.35-Siemens-PNPNIOC-20200924.xml"
    assert s["ip_address"] == "192.168.1.6" and s["device_number"] == "6" and s["comment"] == "SIEMENS"
    assert h.headers["stations"]["columns"].startswith("Role,Station Name,Catalog Kind")


def test_info_files():
    text = ("DTM:\tPROFINET IO Generic Device DTM\r\tInfo:\t\t--\r\rDevice:\tPN/PN Coupler X2\r\tInfo:\t\tCoupler ... "
            "firmware V4.2 [0x00010006] [DAP X2 V4.2] [GSDML-V2.35-Siemens-PNPNIOC-20200924.xml]\r\tVendor:\t\tSIEMENS\r")
    assert info_files(text) == ["GSDML-V2.35-Siemens-PNPNIOC-20200924.xml"]
    assert info_files("") == [] and info_files(None) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

"""The process-data export reader on the FVZ production reference (`HilscherIOCard1\\HilscherIO.xml`): the
controller and the devices by display name, the name of station inside it."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sycon5 import exports  # noqa: E402

FVZ = os.path.join(os.path.dirname(HERE), "spike", "references", "FVZ", "HilscherIO.xml")


def test_process_data_devices_of_the_reference():
    ctrl, devices = exports.process_data_devices(FVZ)
    assert ctrl.startswith("CIFX_RE_PNM[CIFX RE/PNM]<n0001-mc1-cc1-a1001>")
    assert devices and devices[0].startswith("Cell Test[Anybus Communicator]<n0002-ct1-cc1-k63001>")
    names = [exports.station_of(d) for d in devices]
    assert "n0002-ct1-cc1-k63001" in names and "n0005-ms1-cc1-k70001" in names
    assert all("<" not in n for n in names)
    assert exports.station_of("plain") == "plain"
    assert exports.EXPORT_KINDS == {"xml": "XML...", "nxd": "DBM/nxd...", "csv": "CSV..."}


if __name__ == "__main__":
    test_process_data_devices_of_the_reference()
    print("ok")

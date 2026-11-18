"""A station left without its module (2026-10-29, user: "the servo one junior were missing their module on the
sorter"): the GSDML reader on a synthetic file, the verification's new check against it - a DAP that takes modules
and has none plugged FAILs, a DAP that takes none (a switch) is not checked, a missing GSDML is a NOTE - and the
controller's name of station on a saved project (resume names it, an update keeps a named one)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
from sycon5 import consumer, gsdml  # noqa: E402
from sycon5.handoff import Handoff  # noqa: E402
from sycon5.readback import Device, Project  # noqa: E402

GSDML = """<?xml version="1.0" encoding="iso-8859-1"?>
<ISO15745Profile xmlns="http://www.profibus.com/GSDML/2003/11/DeviceProfile"><ProfileBody><ApplicationProcess>
<DeviceAccessPointList>
 <DeviceAccessPointItem ID="DAP 2" FixedInSlots="0"><UseableModules>
  <ModuleItemRef ModuleItemTarget="ID_Mod_07" AllowedInSlots="1..1"/><ModuleItemRef ModuleItemTarget="ID_Mod_08" AllowedInSlots="1"/>
 </UseableModules></DeviceAccessPointItem>
 <DeviceAccessPointItem ID="DIM 1"><UseableModules><ModuleItemRef ModuleItemTarget="P8" FixedInSlots="1"/></UseableModules></DeviceAccessPointItem>
 <DeviceAccessPointItem ID="DAP 5C"/>
 <DeviceAccessPointItem ID="DAP X2 V4.2"><UseableModules><ModuleItemRef ModuleItemTarget="M" AllowedInSlots="1..3 7 9..10"/></UseableModules></DeviceAccessPointItem>
</DeviceAccessPointList></ApplicationProcess></ProfileBody></ISO15745Profile>
"""


def write_gsdml(tmp_path):
    folder = tmp_path / "GSDML"
    folder.mkdir()
    (folder / "GSDML-V2.3-Test-20260101.xml").write_text(GSDML, encoding="iso-8859-1")
    return str(folder), "GSDML-V2.3-Test-20260101.xml"


def test_slot_lists_and_the_daps(tmp_path):
    assert gsdml.slot_list("1..3 7 9..10") == {1, 2, 3, 7, 9, 10}
    assert gsdml.slot_list("") == set() and gsdml.slot_list("x 2") == {2} and gsdml.slot_list("1..99999") == set()
    folder, name = write_gsdml(tmp_path)
    assert gsdml.module_slots(name, "DAP 2", folder) == {1}
    assert gsdml.module_slots(name, "dim 1", folder) == {1}, "a fixed module counts; the DAP id compared in any case"
    assert gsdml.module_slots(name, "DAP 5C", folder) == set(), "a switch's DAP takes no module"
    assert gsdml.module_slots(name, "DAP X2 V4.2", folder) == {1, 2, 3, 7, 9, 10}
    assert gsdml.module_slots(name, "DAP 99", folder) is None and gsdml.module_slots("nope.xml", "DAP 2", folder) is None
    assert gsdml.module_slots("", "DAP 2", folder) is None and gsdml.module_slots(name, "", folder) is None


def station(name, ip):
    return {"role": "slave", "station_name": name, "catalog_kind": "slave", "catalog_item": "T", "model_id": "M",
            "gsdml": "", "ip_address": ip, "subnet_mask": "255.255.255.0", "gateway": "", "update_time_ms": "", "comment": "",
            "symbolic_name": "", "fld": ""}


def device(name, ip, gsdml_file, dap, slots):
    return Device(device_no=name, symbolic="", prog_id="x.PNIOSlave", gsdml=gsdml_file, name=name, ip=ip, type_name="T",
                  dap=dap, slots=dict(slots), manufacturer_id=1, device_type_id=2)


def test_a_station_whose_dap_takes_a_module_fails_without_one(tmp_path):
    folder, name = write_gsdml(tmp_path)
    names = ["n0025-servo", "n0026-servo-ok", "n0010-switch", "n0035-al1202", "n0050-unknown-dap", "n0060-no-gsdml"]
    h = Handoff(folder="", controller={"station_name": "n0001-c", "ip_address": "192.168.1.1"},
                stations=[station(n, "192.168.1.%d" % (i + 2)) for i, n in enumerate(names)])
    devs = [device("n0025-servo", "192.168.1.2", name, "DAP 2", {0: "ServoOne Junior"}),
            device("n0026-servo-ok", "192.168.1.3", name, "DAP 2", {0: "ServoOne Junior", 1: "PPO 3, 4 bytes IO"}),
            device("n0010-switch", "192.168.1.4", name, "DAP 5C", {0: "SCALANCE XC216-4C V4.3"}),
            device("n0035-al1202", "192.168.1.5", name, "DIM 1", {0: "AL1202", 1: "8 Ports"}),
            device("n0050-unknown-dap", "192.168.1.6", name, "DAP 99", {0: "X"}),
            device("n0060-no-gsdml", "192.168.1.7", "", "DAP 1", {0: "X"})]
    ctrl = Device(device_no="n0001-c", symbolic="", prog_id="x.PNIOController", gsdml="", name="n0001-c", ip="192.168.1.1",
                  network=[(d.device_no, d.ip) for d in devs])
    v = consumer.verify(h, Project(path="", devices=[ctrl] + devs), {}, gsdml_dir=folder)
    fails = [ln for ln in v.lines if ln.startswith("FAIL ")]
    assert fails == ["FAIL station n0025-servo: a module plugged (its DAP DAP 2 takes modules in slot 1; the table names none - read 0 ServoOne Junior)"], fails
    assert "PASS station n0026-servo-ok: a module plugged (its DAP DAP 2 takes modules in slot 1; the table names none - read 0 ServoOne Junior, 1 PPO 3, 4 bytes IO)" in v.lines
    assert any(ln.startswith("PASS station n0035-al1202: a module plugged") for ln in v.lines)
    assert not any("n0010-switch: a module" in ln for ln in v.lines), "a switch's DAP takes no module: not checked"
    assert "NOTE station n0050-unknown-dap: GSDML %s / DAP 'DAP 99' not found - its modules not checked" % name in v.lines
    assert not any("n0060-no-gsdml: a module" in ln or "n0060-no-gsdml: GSDML" in ln for ln in v.lines), "no GSDML read back: nothing to say"


def test_the_slot_text():
    assert consumer._slots_text({1}) == "1" and consumer._slots_text({1, 2, 3, 7, 9, 10}) == "1..3, 7, 9..10"


def test_what_a_saved_projects_controller_gets():
    assert consumer.controller_action("resume", "controller", "n0001-c") == "name"
    assert consumer.controller_action("update", "", "n0001-c") == "name"
    assert consumer.controller_action("resume", "N0001-C", "n0001-c") is None, "SYCON.net lower-cases names: the same name"
    assert consumer.controller_action("update", "n0001-c", "n0001-c") is None
    assert consumer.controller_action("resume", "old-name", "n0001-c") == "name", "resume finishes this handoff's own build"
    assert consumer.controller_action("update", "old-name", "n0001-c") == "keep", "an update never changes an existing node"

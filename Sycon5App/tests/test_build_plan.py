"""The build's planning helpers (no GUI): which models are cloned configured, and what the per-station pass does
against a read-back - nothing when everything is there, in-place re-typing of a clone's ports, a parameter whose
record oracle is not met, a full plug when nothing is known."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from sycon5 import consumer  # noqa: E402
from sycon5.handoff import Handoff  # noqa: E402


def _station(name, model, item="AL1202"):
    return {"station_name": name, "model_id": model, "catalog_item": item, "catalog_kind": "slave", "gsdml": "g.xml",
            "ip_address": "192.168.1.5", "role": "slave"}


def _row(station, slot, subslot="", text="", params="", module_id=""):
    return {"station_name": station, "slot": str(slot), "subslot": str(subslot), "module_id": module_id,
            "module_text": text, "parameters": params, "comment": ""}


class _Dev:
    def __init__(self, slots=None, submodules=None, records=None):
        self.slots, self.submodules, self.records = slots or {}, submodules or {}, records or {}


class _Driver:
    def __init__(self):
        self.calls = []

    def plug_modules(self, node, specs):
        self.calls.append(("plug_modules", node, tuple(specs)))
        return [sp.replace("order:", "") for sp in specs]

    def set_module_parameters(self, node, slot, params, subslot=1):
        self.calls.append(("set_module_parameters", node, slot, subslot, tuple(params)))

    def plug_submodules(self, node, slot, wanted):
        self.calls.append(("plug_submodules", node, slot, tuple(wanted)))

    def set_submodules(self, node, slot, wanted):
        self.calls.append(("set_submodules", node, slot, tuple(wanted)))

    def set_dap_submodules(self, node, wanted):
        self.calls.append(("set_dap_submodules", node, tuple(wanted)))


def _handoff(stations, rows):
    modules = {}
    for m in rows:
        modules.setdefault(m["station_name"], []).append(m)
    return Handoff(folder="", controller={"station_name": "ctrl"}, stations=stations, modules=modules)


def test_clone_safety_and_the_al1202_ports():
    a, b = _station("n0035-sm006", "AL1202"), _station("n0036-sm016", "AL1202")
    ports_a = [_row(a["station_name"], 1, 2 + k, "IO-Link In/Out 32/32 Byte + PQI") for k in range(8)]
    ports_b = [_row(b["station_name"], 1, 2 + k, "IO-Link In/Out 32/32 Byte + PQI" if k != 3 else "Digital Input + PQI") for k in range(8)]
    h = _handoff([a, b], ports_a + ports_b)
    assert consumer.clone_safe(h, [a, b]), "the same eight subslots: the types may differ"
    # the head, nothing known: its eight ports plugged
    d = _Driver()
    assert consumer.apply_station(d, h, a["station_name"], None, {}, node="al1202")
    assert d.calls == [("plug_submodules", "al1202", 1, tuple((2 + k, "IO-Link In/Out 32/32 Byte + PQI") for k in range(8)))]
    # a clone carrying the head's ports: only port 5 re-typed, in place
    dev = _Dev(slots={0: "AL1202", 1: "8 Ports"}, submodules={(1, 2 + k): "IO-Link In/Out 32/32 Byte + PQI" for k in range(8)})
    d = _Driver()
    assert consumer.apply_station(d, h, b["station_name"], dev, {})
    assert d.calls == [("set_submodules", b["station_name"], 1, ((5, "Digital Input + PQI"),))]
    # the head itself, read back after the build: nothing to do
    d = _Driver()
    assert not consumer.apply_station(d, h, a["station_name"], dev, {}) and d.calls == []


def test_differing_structures_are_not_cloned_configured():
    a, b = _station("n0005-aep01", "6ES7155-6AU01-0BN0", "IM 155-6 PN ST V4.2"), _station("n0020-ae01", "6ES7155-6AU01-0BN0", "IM 155-6 PN ST V4.2")
    rows = [_row(a["station_name"], 1, module_id="6ES7131-6BH01-0BA0", params="potential_group=Enable new potential group (light BaseUnit)"),
            _row(a["station_name"], 2, module_id="6ES7132-6BH01-0BA0"),
            _row(b["station_name"], 1, module_id="6ES7131-6BH01-0BA0", params="potential_group=Enable new potential group (light BaseUnit)")]
    h = _handoff([a, b], rows)
    assert not consumer.clone_safe(h, [a, b])
    # a station read back with its modules and the potential group record set: nothing to do
    dev = _Dev(slots={0: "IM", 1: "DI", 2: "DQ"}, records={(1, 1, consumer.POTENTIAL_GROUP_RECORD): bytes.fromhex("0100")})
    d = _Driver()
    assert not consumer.apply_station(d, h, a["station_name"], dev, {}) and d.calls == []
    # the record not set: the parameter is applied, the modules left alone
    dev = _Dev(slots={0: "IM", 1: "DI", 2: "DQ"}, records={(1, 1, consumer.POTENTIAL_GROUP_RECORD): bytes.fromhex("0000")})
    d = _Driver()
    assert consumer.apply_station(d, h, a["station_name"], dev, {})
    assert [c[0] for c in d.calls] == ["set_module_parameters"]
    # nothing known: everything plugged, then the parameters
    d = _Driver()
    plugged = {}
    assert consumer.apply_station(d, h, a["station_name"], None, plugged)
    assert [c[0] for c in d.calls] == ["plug_modules", "set_module_parameters"] and plugged[a["station_name"]] == {"1": "6ES7131-6BH01-0BA0", "2": "6ES7132-6BH01-0BA0"}


def test_dap_rows_against_their_record_oracle():
    c = _station("n0006-aec01", "6ES7158-3AD10-0XA0", "PN/PN Coupler X2 [DAP X2 V4.2]")
    rows = [_row(c["station_name"], 0, 1, params="4=0 | record:1=00 0C 00 02 00 00"),
            _row(c["station_name"], 1, text="*OUT 128 Byte"), _row(c["station_name"], 2, text="*IN 128 Byte")]
    h = _handoff([c], rows)
    assert consumer.clone_safe(h, [c])
    dev = _Dev(slots={0: "PN/PN", 1: "*OUT 128 Byte", 2: "*IN 128 Byte"}, records={(0, 1, 1): bytes.fromhex("000c00020000")})
    d = _Driver()
    assert not consumer.apply_station(d, h, c["station_name"], dev, {}) and d.calls == []
    dev.records[(0, 1, 1)] = bytes.fromhex("000e00020000")
    d = _Driver()
    assert consumer.apply_station(d, h, c["station_name"], dev, {})
    assert d.calls == [("set_module_parameters", c["station_name"], 0, 1, (("4", "0"), ("record:1", "00 0C 00 02 00 00")))]
    assert consumer.params_satisfied(dev, 0, 1, "") and not consumer.params_satisfied(dev, 0, 1, "4=0")


if __name__ == "__main__":
    test_clone_safety_and_the_al1202_ports()
    test_differing_structures_are_not_cloned_configured()
    test_dap_rows_against_their_record_oracle()
    print("ok")

"""read_project on the two saved projects of the spike (no GUI): the round-1 build and the round-2 parameters.

Run:  C:\\Source\\Repos\\_Openn5\\.venv\\Scripts\\python -I -m pytest Sycon5App\\tests -q   (or run this file)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
from sycon5.readback import read_project, describe  # noqa: E402

ROUND1 = os.path.join(APP, "spike", "references", "E2E_Round1", "SYCON_net.xml")
ROUND2 = os.path.join(APP, "spike", "references", "E2E_Round2", "SYCON_net.xml")


def test_round1_devices():
    p = read_project(ROUND1)
    assert [d.device_no for d in p.devices] == ["controller", "n0005-ms1-k2501", "sk-cu4-eth"]
    c = p.controller
    assert c.is_controller and c.prog_id == "Hilscher.PNIOControllerDTM2.1"
    assert sorted(c.network) == [("n0005-ms1-k2501", "192.168.2.5"), ("sk-cu4-eth", "192.168.2.2")]
    et = p.device("n0005-ms1-k2501")
    assert et.name == "n0005-ms1-k2501" and et.ip == "192.168.2.5" and et.mask == "255.255.255.0"
    assert et.gsdml == "GSDML-V2.35-Siemens-ET200SP-20210401.xml"
    assert et.slots == {0: "IM 155-6 PN ST V4.2", 1: "DI 8x24VDC HF V2.0"}
    nord = p.device("sk-cu4-eth")
    assert nord.ip == "192.168.2.2" and nord.gsdml == "GSDML-V2.46-NORDDRIVESYSTEMS-PNT-20260803.xml"
    assert nord.slots == {0: "SK CU4-ETH", 2: "Dig-IN (1 word)", 3: "PPO 4 (4 words)"}


def test_round1_ids_and_canvas():
    """The GSDML identity (BusField's node type) and the canvas boxes the Device element carries."""
    p = read_project(ROUND1)
    assert p.controller.node_type == "0x011E0203" and p.controller.manufacturer_id == 286
    et = p.device("n0005-ms1-k2501")
    assert et.node_type == "0x002A0313" and (et.manufacturer_id, et.device_type_id) == (42, 787)
    assert len(et.rect) == 4 and et.rect[2] > et.rect[0] and et.rect[3] > et.rect[1]
    assert len(et.line_rect) == 4 and et.line_rect[2] <= et.rect[0] + 1
    assert "node=0x002A0313" in describe(p)


def test_round1_records():
    et = read_project(ROUND1).device("n0005-ms1-k2501")
    assert (1, 1, 128) in et.records and (1, 1, 243) in et.records and (0, 1, 2) in et.records
    inputs = et.records[(1, 1, 128)]
    assert len(inputs) == 28
    assert inputs[:4] == bytes.fromhex("00 03 00 86")


def test_round2_parameter_edit():
    before = read_project(ROUND1).device("n0005-ms1-k2501").records[(1, 1, 128)]
    after = read_project(ROUND2).device("n0005-ms1-k2501").records[(1, 1, 128)]
    diffs = [(i, before[i], after[i]) for i in range(len(before)) if before[i] != after[i]]
    assert diffs == [(2, 0x00, 0x10), (3, 0x86, 0x83)]      # channel 0: Wire break bit, delay 3.2 ms -> 0.4 ms


def test_describe_runs():
    text = describe(read_project(ROUND2))
    assert "slot 1: DI 8x24VDC HF V2.0" in text and "network: sk-cu4-eth 192.168.2.2" in text


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print(describe(read_project(ROUND2)))

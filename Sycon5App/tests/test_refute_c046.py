"""C-046 refute round 1 (2026-10-26): the read-back oracle attacked with broken projects, the structure laws attacked
on synthetic sources. What broke and was fixed: a DTM blob cut in half read as a device without modules (now
`ReadbackError`: the 4-byte length prefix must equal the body); the construction rule of law L4 skipped a
construction through a module attribute (`driver.SyconDriver()`); a bare `attach_if_running(` call was not a call
to the rule. What held: a truncated XML and a non-hex blob refuse loudly, an intact fixture reads whole, the
import walker sees function-level and relative imports, sideways imports are violations."""
import importlib.util
import os
import re
import shutil
import sys

import pytest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
from sycon5 import readback  # noqa: E402

ROUND1 = os.path.join(APP, "spike", "references", "E2E_Round1", "SYCON_net.xml")
ROUND2 = os.path.join(APP, "spike", "references", "E2E_Round2", "SYCON_net.xml")
BLOB = re.compile(r"<BinData[^>]*>([0-9a-fA-F]+)</BinData>")


def laws():
    spec = importlib.util.spec_from_file_location("laws", os.path.join(HERE, "test_architecture_contracts.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def doctored(tmp_path, replace):
    text = open(ROUND2, encoding="utf-8").read()
    path = str(tmp_path / "SYCON_net.xml")
    open(path, "w", encoding="utf-8").write(replace(text))
    return path


# ---- the oracle ------------------------------------------------------------------------------------------------ #
def test_the_intact_fixtures_read_whole():
    for fixture in (ROUND1, ROUND2):
        text = open(fixture, encoding="utf-8").read()
        for h in BLOB.findall(text):
            raw = bytes.fromhex(h)
            assert int.from_bytes(raw[:4], "little") == len(raw) - 4, "every blob's prefix is its body length"
        p = readback.read_project(fixture)
        assert p.controller is not None and len(p.devices) >= 3
        assert all(d.name and d.ip for d in p.devices if not d.is_controller)


def test_a_blob_cut_in_half_is_refused(tmp_path):
    last = BLOB.findall(open(ROUND2, encoding="utf-8").read())[-1]
    path = doctored(tmp_path, lambda t: t.replace(last, last[: len(last) // 2]))
    with pytest.raises(readback.ReadbackError, match="truncated or corrupt"):
        readback.read_project(path)


def test_a_blob_that_is_not_hex_or_not_ole_is_refused(tmp_path):
    last = BLOB.findall(open(ROUND2, encoding="utf-8").read())[-1]
    with pytest.raises(readback.ReadbackError, match="not hex"):
        readback.read_project(doctored(tmp_path, lambda t: t.replace(last, last[:-1])))
    garbage = (16).to_bytes(4, "little").hex() + "00" * 16              # a true prefix, no OLE behind it
    with pytest.raises(readback.ReadbackError, match="not an OLE"):
        readback.read_project(doctored(tmp_path, lambda t: t.replace(last, garbage)))


def test_a_truncated_xml_is_refused(tmp_path):
    path = doctored(tmp_path, lambda t: t[: len(t) // 2])
    with pytest.raises(ET.ParseError):
        readback.read_project(path)


def test_a_device_without_attributes_or_busline_reads_empty(tmp_path):
    path = str(tmp_path / "SYCON_net.xml")
    open(path, "w", encoding="utf-8").write('<?xml version="1.0"?><Project><Device/><BusLine><PositionRect top="1" left="2" bottom="3" right="4"/></BusLine></Project>')
    p = readback.read_project(path)
    assert len(p.devices) == 1
    d = p.devices[0]
    assert (d.device_no, d.symbolic, d.name, d.ip) == ("", "", "", "") and d.rect == () and d.line_rect == ()
    assert d.manufacturer_id == 0 and d.device_type_id == 0 and not d.slots and not d.records


# ---- the laws -------------------------------------------------------------------------------------------------- #
def test_the_import_walker_sees_every_kind_of_import():
    L = laws()
    text = ("import os\n"
            "from .handoff import natural_key\n"
            "from . import canvas, exports\n"
            "def f():\n"
            "    import sycon5.gui as g\n"
            "    from tkinter import ttk\n"
            "    return g, ttk\n")
    found = set(L.imports_of(text))
    assert found == {"os", "sycon5.handoff", "sycon5.canvas", "sycon5.exports", "sycon5.gui", "tkinter"}


def test_sideways_and_upward_imports_are_violations():
    L = laws()
    edges = [("canvas", "workspace"), ("workspace", "canvas"), ("handoff", "driver"), ("driver", "readback"),
             ("gui", "workspace"), ("consumer", "gui"), ("session", "nowhere")]
    assert L.l1_violations(edges) == [("canvas", "workspace"), ("workspace", "canvas"), ("handoff", "driver"),
                                      ("consumer", "gui"), ("session", "nowhere")]
    assert L.l1_violations(edges, ratchet={("canvas", "workspace"): "quarantined"}) [0] == ("workspace", "canvas")


def test_the_construction_rule_sees_module_attributes_and_skips_definitions():
    L = laws()
    assert L.constructions_in("d = SyconDriver()", "SyconDriver")
    assert L.constructions_in("from . import driver\nd = driver.SyconDriver(project)", "SyconDriver")
    assert L.constructions_in("x = self.session_factory.Session()", "Session")
    assert not L.constructions_in("class SyconDriver(object):\n    pass", "SyconDriver")
    assert not L.constructions_in("def SyconDriver(x):\n    pass", "SyconDriver")
    assert not L.constructions_in("d = MySyconDriver()", "SyconDriver")
    assert L.calls_in("if self.session.attach_if_running():", "attach_if_running")
    assert L.calls_in("from .session import attach_if_running\nattach_if_running()", "attach_if_running")
    assert not L.calls_in("    def attach_if_running(self):", "attach_if_running")


def test_the_drive_rule_sees_calls_not_words():
    L = laws()
    assert L.drives_in("d = SyconDriver()\nd.open(p)\ns = Session()\ns.launch(x)\nd.new_project()") == [
        "SyconDriver(", ".open(", "Session(", ".launch(", ".new_project("]
    assert L.drives_in('x = "SyconDriver("  # a Session( in a comment\nopen(path).read()\nimport SyconDriver') == []


def test_dynamic_imports_are_caught():
    L = laws()
    assert L.DYNAMIC_IMPORT.search("mod = importlib.import_module('.gui', __name__)")
    assert L.DYNAMIC_IMPORT.search("__import__('sycon5.driver')")
    assert not L.DYNAMIC_IMPORT.search("import importlib")


def test_the_real_package_has_no_dynamic_import_outside_init():
    L = laws()
    hits = sorted(m for m, p in L.modules().items() if m != "__init__" and L.DYNAMIC_IMPORT.search(L.source(p)))
    assert hits == []
    shutil.rmtree(os.path.join(APP, "sycon5", "__pycache__"), ignore_errors=True)

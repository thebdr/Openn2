"""M9 gate (data-independent): the phase-800 software-block skeleton.

Covers the Database, the Table, the @builds registry, the engine ($/#/%/@ CreationInfo CSV with an
ABSOLUTE $ template= ref + InstanceDBs + the horizontal ITERATOR), and the 810 shells (the key
inventory: scans the template *.xml for !!key$$ - block_templates.json is deprecated). Shell-
dependent cases point BLOCK_TEMPLATES_DIR at a synthetic template so they stay data-independent.
NOT the per-template builder logic (the user writes that in domain/blocks/builders.py).
"""
import csv
import os
import tempfile
from _harness import run, eq, ok
from openpyxl import load_workbook

from pipeline3.core import config
from pipeline3.domain.blocks.database import Database
from pipeline3.domain.blocks.table import Table
from pipeline3.domain.blocks import registry, engine, shells

_TEMPLATE_XML = (
    "<Document>!!nameOfDB$$ !!02_COM.{db_element}$$ !!NetworkComment$$ "
    "!!instanceOf-FDBACK$$ !!ITERATOR_STRINGS$$</Document>"
)


def _rows():
    return [
        {"script_type": "KQ", "datablocks": "03_FDBACK", "matrix_areas": "AREA 1",
         "name_in_db": "Contactor Feedback Error", "tagtable": "SAFETY_Contactors"},
        {"script_type": "E1/2", "datablocks": "01_Pushbutton", "matrix_areas": "AREA 1|AREA 2",
         "name_in_db": "Emergency PB"},
        {"script_type": "A", "datablocks": "", "matrix_areas": "AREA 2", "name_in_db": ""},
    ]


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def _with_synthetic_templates(fn):
    """Run fn(out_root) with BLOCK_TEMPLATES_DIR pointed at a temp dir holding one synthetic
    template (TEMPLATE--v1.0--T1.xml), and out_root a temp dir. Restores config + registry."""
    saved = config.BLOCK_TEMPLATES_DIR
    registry.clear()
    with tempfile.TemporaryDirectory() as tdir, tempfile.TemporaryDirectory() as out:
        with open(os.path.join(tdir, "TEMPLATE--v1.0--T1.xml"), "w", encoding="utf-8") as f:
            f.write(_TEMPLATE_XML)
        config.BLOCK_TEMPLATES_DIR = tdir
        try:
            fn(out)
        finally:
            config.BLOCK_TEMPLATES_DIR = saved
            registry.clear()


def test_database_queries():
    db = Database(_rows())
    eq(len(db.by_type("kq", "e1/2")), 2)
    eq(len(db.by_db("03_FDBACK")), 1)
    eq(len(db.by_area("AREA 1")), 2)
    eq(db.areas(), ["AREA 1", "AREA 2"])


def test_table_add():
    t = Table("X")
    t.add(template_type="01", NetworkComment="hi", **{"02_COM.{db_element}": "v"})
    eq(t.columns, ["TemplateType", "NetworkComment", "02_COM.{db_element}"])
    eq(t.rows[0]["NetworkComment"], "hi")


def test_engine_absolute_ref_and_instances():
    registry.clear()

    @registry.builds("TestBlock")
    def _b(db):
        t = Table("TestBlock")
        for area in db.areas():
            t.add(template_type="02", NetworkComment=area,
                  **{"instanceOf-FDBACK": f"INST_{area}"},
                  ITERATOR_STRINGS=[r["name_in_db"] for r in db.by_area(area) if r.get("name_in_db")])
        return t

    try:
        with tempfile.TemporaryDirectory() as d:
            res = engine.generate_blocks(_rows(), d, emit=lambda *_: None)
            grid = _read(os.path.join(res["dir"], "TestBlock.csv"))
            eq(grid[0][0], "$")
            ref = grid[0][1].split("=", 1)[1]
            ok(os.path.isabs(ref) and ref.endswith("TestBlock.xml"), f"absolute $ ref: {ref}")
            eq(grid[2][0], "%")
            eq(grid[2][-1], "!!ITERATOR_STRINGS$$", "iterator column last")
            eq(len([r for r in grid if r[0] == "@"]), 2)
            inst = _read(os.path.join(res["dir"], "InstanceDBs.csv"))
            ok(any(r[0] == "@" and r[2] == "FDBACK" for r in inst))
    finally:
        registry.clear()


def test_shells_scan_and_inventory():
    def check(out):
        res = shells.generate_shells(out, emit=lambda *_: None)
        eq(res["created"], ["T1"], "one shell per scanned template")
        info = shells.read_shells(out)["T1"]
        eq(info["mode"], "fill")
        ok(os.path.isabs(info["ref"]) and info["ref"].endswith("T1.xml"), info["ref"])
        # the % header is the FULL key set scanned from the .xml (block_templates.json NOT used)
        eq(info["keys"], ["TemplateType", "nameOfDB", "02_COM.{db_element}",
                          "NetworkComment", "instanceOf-FDBACK", "ITERATOR_STRINGS"])
        # additive: a 2nd run keeps it
        eq(shells.generate_shells(out, emit=lambda *_: None)["created"], [])
    _with_synthetic_templates(check)


def test_output_header_is_full_shell_keyset():
    def check(out):
        shells.generate_shells(out, emit=lambda *_: None)

        @registry.builds("T1")
        def _b(db):
            t = Table("T1")
            t.add(template_type="01", NetworkComment="only this one set")   # builder fills 1 of 5 keys
            return t

        res = engine.generate_blocks(_rows(), out, emit=lambda *_: None)
        grid = _read(os.path.join(res["dir"], "T1.csv"))
        header = grid[2]
        for k in ("TemplateType", "!!nameOfDB$$", "!!02_COM.{db_element}$$",
                  "!!NetworkComment$$", "!!instanceOf-FDBACK$$", "!!ITERATOR_STRINGS$$"):
            ok(k in header, f"% header carries the full shell key set: missing {k}")
    _with_synthetic_templates(check)


def test_override_uses_shell_rows():
    def check(out):
        shells.generate_shells(out, emit=lambda *_: None)
        path = shells._shell_path(out)
        wb = load_workbook(path)
        ws = wb["T1"]
        ws["B2"] = "override"
        ws["A4"] = "@"; ws["B4"] = "01"; ws["C4"] = "MY_DB"     # B4=TemplateType, C4=nameOfDB
        wb.save(path)
        res = engine.generate_blocks([], out, emit=lambda *_: None)   # no builder -> override drives it
        grid = _read(os.path.join(res["dir"], "T1.csv"))
        ok(any(r[0] == "@" and "MY_DB" in r for r in grid), "override @ row carried through")
    _with_synthetic_templates(check)


if __name__ == "__main__":
    raise SystemExit(run("blocks", [
        ("database_queries", test_database_queries),
        ("table_add", test_table_add),
        ("engine_absolute_ref_and_instances", test_engine_absolute_ref_and_instances),
        ("shells_scan_and_inventory", test_shells_scan_and_inventory),
        ("output_header_is_full_shell_keyset", test_output_header_is_full_shell_keyset),
        ("override_uses_shell_rows", test_override_uses_shell_rows),
    ]))

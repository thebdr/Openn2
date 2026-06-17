#!/usr/bin/env python3
"""Tests for the SoftwareBlocks generator (softwareblocks.py + block_builders.py).

Synthetic checks of the CSV layout engine (no I/O List needed) — META columns from the
sidecar shape, zero-padded TemplateType, the 00 vertical iterator, capacity padding, the
Always FALSE pad override, and the ESTOP doors sidecar (door-count -> TemplateType) — plus
an integration check against the real I/O List when params.yaml points to one (every
generated header's !!key$$ set is a subset of the template scan, and carries no memberOf).

Run: python test_softwareblocks.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pipeline2.blocks import block_builders
from pipeline2.blocks import block_templates
from pipeline2.blocks import softwareblocks as sb

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def _header(grid):
    return next(r for r in grid if r and r[0] == "%")


def header_keys(grid):
    """The !!key$$ names from a grid's % header."""
    return [c[2:-2] for c in _header(grid)
            if isinstance(c, str) and c.startswith("!!") and c.endswith("$$")]


def data_rows(grid):
    return [r for r in grid if r and r[0] == "@"]


# template stems (match block_builders.BUILDERS / the .xml files)
S00 = "TEMPLATE--v1.1--00_Only for Commissioning"
S02 = "TEMPLATE--v1.1--02_EM Push Button"
S04 = "TEMPLATE--v1.0--04_ESTOP"
S05 = "TEMPLATE--v1.1--05_Output Feedback"
S06 = "TEMPLATE--v1.0--06_Feedback Error"
S08 = "TEMPLATE--v1.0--08_Gate Manager"


def main():
    # --- ESTOP door-count -> TemplateType (doors sidecar selection) ----------
    check("estop 2 doors -> index 1", block_builders.estop_template_type(2) == 1)
    check("estop 4 doors -> index 1", block_builders.estop_template_type(4) == 1)
    check("estop 5 doors -> index 2", block_builders.estop_template_type(5) == 2)
    check("estop 0 doors -> ResetRequired 6", block_builders.estop_template_type(0) == 6)
    check("estop 999 doors -> largest tier 5", block_builders.estop_template_type(999) == 5)

    # --- output filename drops the TEMPLATE--vX.Y-- prefix -------------------
    check("out name drops v1.0 prefix",
          sb._out_name("TEMPLATE--v1.0--07_Speed Control") == "07_Speed Control.csv")
    check("out name drops v1.1 prefix",
          sb._out_name(S00) == "00_Only for Commissioning.csv")

    # --- sidecar kinds -------------------------------------------------------
    check("00 no sidecar -> none", sb._load_sidecar(S00)["kind"] == "none")
    check("02 capacity sidecar", sb._load_sidecar(S02)["kind"] == "capacity")
    check("04 doors sidecar", sb._load_sidecar(S04)["kind"] == "doors")
    check("05 multi sidecar", sb._load_sidecar(S05)["kind"] == "multi")
    check("08 purpose sidecar", sb._load_sidecar(S08)["kind"] == "purpose")

    # --- vertical (no-capacity list template) --------------------------------
    grid, _ = sb.build_template_csv(
        S00, lambda _db: [{"00_Commissioning.{db_element}": ["a", "b", "c"]}], [])
    check("00 vertical: only TemplateType meta",
          _header(grid)[1] == "TemplateType" and header_keys(grid) == ["00_Commissioning.{db_element}"])
    body = [r for r in grid if r and r[0] in ("@", "") and len(r) > 1 and r[1] == "01"]
    check("00 vertical: one row per element", len(body) == 3, str(len(body)))
    check("00 vertical: @ on first row only",
          body[0][0] == "@" and all(b[0] == "" for b in body[1:]))
    check("00 vertical: TemplateType zero-padded 01", all(b[1] == "01" for b in body))

    # --- capacity padding + zero-pad TT (02 sidecar now loads after vfix) ----
    grid, _ = sb.build_template_csv(
        S02, lambda _db: [{"instanceOf:00_Push-Button_Input": "X", "NetworkComment": "c",
                           "00_Commissioning.{db_element}": "byp", "ITERATOR_STRINGS": ["e1"]}], [])
    dr = data_rows(grid)[0]
    check("02 TemplateType zero-padded 01", dr[1] == "01")
    check("02 capacity 4 / index 1 ride", dr[2] == "4" and dr[3] == "1")
    check("02 #Elements Needed = 1", dr[4] == "1")
    check("02 iterator padded to capacity 4 with 'Always TRUE'", dr.count("Always TRUE") == 3)

    # --- pad override (Always FALSE) ----------------------------------------
    grid, _ = sb.build_template_csv(
        S06, lambda _db: [{"instanceOf:03_FDBACK error": "X", "NetworkComment": "c",
                           "00_Commissioning.{db_element}": "byp", "ITERATOR_STRINGS": ["k1"],
                           "_pad": "Always FALSE"}], [])
    row = data_rows(grid)[0]
    check("06 pad override -> Always FALSE", "Always FALSE" in row and "Always TRUE" not in row)

    # --- doors sidecar: META + ride + door-count TT + no padding -------------
    grid, _ = sb.build_template_csv(
        S04, lambda _db: [{"_template_type": block_builders.estop_template_type(2),
                           "instanceOf:ESTOP1": "E1", "ITERATOR_STRINGS": ["d1", "d2"]},
                          {"_template_type": block_builders.estop_template_type(0),
                           "instanceOf:ESTOP1": "E2", "ITERATOR_STRINGS": []}], [])
    hdr = _header(grid)
    check("04 doors META columns",
          hdr[1:5] == ["TemplateType", "#Templates Machine Type",
                       "#Templates Capacity Doors", "#Templates Index"])
    check("04 no #Elements Needed", "#Elements Needed" not in hdr)
    dr = data_rows(grid)
    check("04 area with 2 doors -> TT 01", dr[0][1] == "01")
    check("04 area with 0 doors -> TT 06", dr[1][1] == "06")
    check("04 all 7 sidecar rows ride",
          sum(1 for r in grid if len(r) > 2 and r[2] and ("SORTER" in r[2] or "GENERIC" in r[2])) == 7)
    check("04 doors iterator NOT padded",
          dr[0].count("Always TRUE") == 0 and "d1" in dr[0] and "d2" in dr[0])

    # --- instance-DB list extraction: skip empty instanceOf-, FB = the suffix -----------
    grid, _ = sb.build_template_csv(
        S08, lambda _db: [{"_template_type": 1, "instanceOf-02_Safety_Door": "",
                           "tagName:SorterRunningIOC": "x"},
                          {"_template_type": 2, "instanceOf-02_Safety_Door": "DOOR_A",
                           "tagName:DoorClosedCh1": "y"}], [])
    check("instance-db rows: skip empty, FB = instanceOf- suffix",
          sb._instance_db_rows(grid) == [("DOOR_A", "02_Safety_Door")],
          str(sb._instance_db_rows(grid)))

    # --- integration: real I/O List (skipped if not present) ----------------
    try:
        from pipeline2.core import config, staging
        params = config.load_params()
        db, _w = staging.load_io_list(params, config.load_signal_types())
    except Exception as e:
        print(f"SKIP  real I/O List integration ({type(e).__name__}: {e})")
        db = None
    if db is not None:
        scanned = block_templates.scan_template_keys()
        for stem, builder in block_builders.BUILDERS.items():
            grid, _n = sb.build_template_csv(stem, builder, db)
            want = set(scanned.get(stem, []))
            got = set(header_keys(grid))
            label = sb._out_name(stem)[:-4]
            check(f"[{label}] header keys subset of template scan", got <= want,
                  f"unknown={sorted(got - want)}")
            check(f"[{label}] no memberOf in header", not any("memberOf" in k for k in got))

        # the CreateInstanceDB list is written and well-formed
        import tempfile
        written = sb.generate(out_dir=tempfile.mkdtemp(prefix="sblk_"))
        check("InstanceDBs in generate() output",
              "InstanceDBs" in written and os.path.exists(written["InstanceDBs"][0]))
        with open(written["InstanceDBs"][0], encoding="utf-8-sig") as f:
            lines = [ln.rstrip("\n") for ln in f]
        check("InstanceDBs header",
              lines[0].startswith("#,Instance DBs created directly via CreateInstanceDB")
              and lines[1] == "%,Name,InstanceOf,Number,Folder")
        data = [ln.split(",") for ln in lines[2:] if ln.startswith("@")]
        check("InstanceDBs: every row has a non-empty Name + InstanceOf",
              data and all(r[1].strip() and r[2].strip() for r in data))
        check("InstanceDBs: Number blank, Folder = InstanceOf",
              all(r[3] == "" and r[4] == r[2] for r in data))

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()

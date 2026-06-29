"""ph200 integrated fill (domain/fillout/fill.fill_out) - the in-memory re-typing after 210, the
AD/AE/AF write-back cells, the DiagnosisBlocks append + derived recompute, and the no-op backup drop.

Hermetic: a tiny synthetic raw I/O List via openpyxl + a real staging read (the config CSVs ship with
the package), so the whole stage->fill->re-read flow exercises the integration without the real docs.
"""
import os
import tempfile

from openpyxl import Workbook, load_workbook

from _harness import run, eq, ok
from pipeline4.domain.fillout import fill, diag_blocks, diag_alloc

_SHEET = "NETSAFETY"


def _raw_iolist(path):
    """A raw I/O List with the columns staging reads by position (per column_map): F=ID, G=Bit, K/L=desc,
    O/P/Q = FU/Location/Device, R=Type, X=Mnemonic. AA..AG (the fill output columns) left BLANK."""
    wb = Workbook()
    ws = wb.active
    ws.title = _SHEET
    # a node head + two door channels on the same FLD (an indexable family that also diagnoses)
    ws["F2"] = "5"; ws["R2"] = "PLC"; ws["K2"] = "MAIN PLC NODE"; ws["O2"] = "=S1"
    ws["G3"] = "I0.0"; ws["K3"] = "DOOR OPEN"; ws["L3"] = "CH1"
    ws["O3"] = "=S1"; ws["P3"] = "+Z1"; ws["Q3"] = "-D9"; ws["AB3"] = "DI1/2"
    ws["G4"] = "I0.1"; ws["K4"] = "DOOR CLOSED"; ws["L4"] = "CH2"
    ws["O4"] = "=S1"; ws["P4"] = "+Z1"; ws["Q4"] = "-D9"; ws["AB4"] = "DD"
    wb.save(path)


def _params(path):
    return {"iolist_path": path,
            "iolist_params": {"sheets": _SHEET, "header_row": 1, "diag_bits_range": [0, 62]}}


def test_full_fill_writes_index_and_diag_cells():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        _raw_iolist(p)
        res = fill.fill_out(_params(p))
        wb = load_workbook(p)
        ws = wb[_SHEET]
        # 220 wrote AD (index) for the door anchor; the door member inherits the same index by FLD
        ok(str(ws["AD3"].value or "").strip(), "AD index written for the DI1/2 anchor")
        ok(str(ws["AD4"].value or "").strip(), "AD index written for the DD member (inherited)")
        eq(ws["AD3"].value, ws["AD4"].value, "the door pair shares one index")
        # 230/240 wrote AE/AF (diag cabinet/bit) for the in-diag door rows
        ok(str(ws["AE3"].value or "").strip(), "AE diag_cabinet written")
        ok(str(ws["AF3"].value or "").strip(), "AF diag_bit written")
        eq(res["findings"] and [f.type for f in res["findings"] if f.severity == "FAIL"], [],
           "no blocking findings on a clean doc")


def test_diagnosisblocks_sheet_created_with_derived():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        _raw_iolist(p)
        fill.fill_out(_params(p))
        wb = load_workbook(p)
        ok("DiagnosisBlocks" in wb.sheetnames, "a fresh DiagnosisBlocks sheet was created")
        ws = wb["DiagnosisBlocks"]
        header = [c.value for c in next(ws.iter_rows())]
        eq(header, diag_blocks.HEADERS, "the 10-column DiagnosisBlocks header")
        # at least one cabinet row with the derived Count/unused_bits columns populated
        body = list(ws.iter_rows(min_row=2, values_only=True))
        ok(body, "at least one cabinet row appended")
        ok(any(r[7] not in (None, "") for r in body), "Count (derived) populated")


def test_noop_drops_backup_on_prefilled_doc():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        _raw_iolist(p)
        fill.fill_out(_params(p))                              # first run fills everything
        res2 = fill.fill_out(_params(p))                       # second run changes nothing
        eq(res2["backup"], "", "value-identical re-run drops its backup (no-op)")
        eq((res2["filled"], res2["index"], res2["diag"]), (0, 0, 0),
           "nothing re-filled (AB/AD/AE/AF already present)")


def test_retyping_after_210_feeds_220_230():
    # a row whose AB is BLANK gets Mode-1 classified, re-resolved to a `type`, and that type drives the
    # 220/230 legs - so a blank-AB diagnosable signal still receives an index + a diag slot.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        wb = Workbook()
        ws = wb.active
        ws.title = _SHEET
        ws["F2"] = "5"; ws["R2"] = "PLC"; ws["K2"] = "MAIN PLC NODE"; ws["O2"] = "=S1"
        # a blank-AB safety door input the rules classify to DI1/2
        ws["G3"] = "I0.0"; ws["K3"] = "SAFETY DOOR OPEN"; ws["L3"] = "CH1"
        ws["O3"] = "=S1"; ws["P3"] = "+Z1"; ws["Q3"] = "-D9"
        wb.save(p)
        fill.fill_out(_params(p))
        ws2 = load_workbook(p)[_SHEET]
        ab = str(ws2["AB3"].value or "").strip()
        ok(ab and ab != "<input required>", f"AB classified from the rules (got {ab!r})")
        ok(str(ws2["AC3"].value or "").strip(), "AC suggested written (always)")


def test_only_arg_restricts_writeback():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        _raw_iolist(p)
        # only=210 writes AB/AC but NOT AD/AE/AF
        fill.fill_out(_params(p), only=210)
        ws = load_workbook(p)[_SHEET]
        eq(str(ws["AD3"].value or "").strip(), "", "only=210 leaves AD (index) blank")
        eq(str(ws["AE3"].value or "").strip(), "", "only=210 leaves AE (diag_cabinet) blank")
        # now only=220 fills AD but still not the diag cells
        fill.fill_out(_params(p), only=220)
        ws = load_workbook(p)[_SHEET]
        ok(str(ws["AD3"].value or "").strip(), "only=220 fills AD (index)")
        eq(str(ws["AE3"].value or "").strip(), "", "only=220 still leaves AE blank")


def test_index_unresolved_is_reported():
    # a door-lamp DL is a MANUAL door member (no DI anchor): 220 cannot auto-group it -> <input required>,
    # which MUST be reported (the unresolved count + a fill_unresolved FAIL + a _UnresolvedIndex row pointing
    # at the AD column). Regression: the report was 210-only and silently dropped 220's index-unresolved rows.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        wb = Workbook()
        ws = wb.active
        ws.title = _SHEET
        ws["F2"] = "5"; ws["R2"] = "PLC"; ws["K2"] = "MAIN PLC NODE"; ws["O2"] = "=S1"
        # a door-open lamp output, AB pre-set to DL (a manual door member), blank index
        ws["G3"] = "Q0.0"; ws["K3"] = "DOOR OPEN LAMP"
        ws["O3"] = "=S1"; ws["P3"] = "+Z1"; ws["Q3"] = "-D9"; ws["AB3"] = "DL"
        wb.save(p)
        res = fill.fill_out(_params(p), only=220)
        ok(res["unresolved"] >= 1, f"the ungroupable DL index is reported unresolved (got {res['unresolved']})")
        ok(any(f.type == "fill_unresolved" for f in res["findings"]), "a fill_unresolved FAIL finding is emitted")
        ws2 = load_workbook(p)["_UnresolvedIndex"]
        body = list(ws2.iter_rows(min_row=2, values_only=True))
        ok(body, "_UnresolvedIndex lists the unresolved index row (not just the header)")
        ok(any(r[1] == "AD" for r in body), "the unresolved entry points at the AD (index) column")


def test_range_component_suffix_and_shared_index():
    # a 2-channel contactor: the KQ output is the RANGE device -K66701..2; its feedbacks are INDEPENDENT rows
    # -K66701/-K66702. The fill suffixes the feedbacks KI -> KI1/2 / KI2/2 (the channel from the range) and
    # groups all three under ONE index (the independent components inherit the range anchor's index).
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "io.xlsx")
        wb = Workbook()
        ws = wb.active
        ws.title = _SHEET
        ws["F2"] = "5"; ws["R2"] = "PLC"; ws["K2"] = "MAIN PLC NODE"; ws["O2"] = "=S1"
        # KQ output, range device, Out gate (Q address)
        ws["G3"] = "Q0.0"; ws["K3"] = "SAFETY RELAY ENABLE DRIVE"
        ws["O3"] = "=S1"; ws["P3"] = "+DL1.CC1"; ws["Q3"] = "-K66701..2"
        # two KI feedbacks, independent component devices, In gate (I address), consecutive rows
        ws["G4"] = "I0.0"; ws["K4"] = "FEEDBACK OF SAFETY RELAY"
        ws["O4"] = "=S1"; ws["P4"] = "+DL1.CC1"; ws["Q4"] = "-K66701"
        ws["G5"] = "I0.1"; ws["K5"] = "FEEDBACK OF SAFETY RELAY"
        ws["O5"] = "=S1"; ws["P5"] = "+DL1.CC1"; ws["Q5"] = "-K66702"
        wb.save(p)
        fill.fill_out(_params(p))
        ws2 = load_workbook(p)[_SHEET]
        eq(str(ws2["AB3"].value or "").strip(), "KQ", "the range KQ output keeps its base type")
        eq(str(ws2["AB4"].value or "").strip(), "KI1/2", "independent component 1 -> KI1/2")
        eq(str(ws2["AB5"].value or "").strip(), "KI2/2", "independent component 2 -> KI2/2")
        ad3 = str(ws2["AD3"].value or "").strip()
        ok(ad3, "the KQ anchor got an index")
        eq(str(ws2["AD4"].value or "").strip(), ad3, "KI1/2 shares the KQ index (one object)")
        eq(str(ws2["AD5"].value or "").strip(), ad3, "KI2/2 shares the KQ index")


def test_risky_assignments_by_node_type_and_row_order():
    # the manual "risky index fill" heuristic: per (node, family, script_type), the i-th <input required>
    # (row order) takes the i-th existing object index in that node/family; leftover stays unresolved.
    from pipeline4.domain.fillout import fill
    from pipeline4.domain.fillout.families import ObjectFamily, LINK_FLD
    door = ObjectFamily(family="door", key="D", member_types=("DI", "DD", "DL", "DR"), anchor="DI1/2",
                        link=LINK_FLD, index_stride=1, bits=2, diag_block="+SafetyDoors")

    def r(uid, st, idx, row):
        return {"uid": uid, "script_type": st, "index": idx, "functional_unit": "=S1", "location": "+L",
                "device": "-X" + str(row), "desc_l1": "d", "source_sheet": "S", "source_row": row}

    # node N1: 2 door objects (0001, 0002) + 2 DL + 1 DR unresolved; one stray row in NO node (skipped)
    rows = [r("a", "DI1/2", "0001", 1), r("b", "DD", "0001", 2), r("c", "DI1/2", "0002", 3),
            r("d", "DD", "0002", 4), r("e", "DL", "<input required>", 5), r("f", "DL", "<input required>", 6),
            r("g", "DR", "<input required>", 7), r("h", "DL", "<input required>", 8)]
    node_key = {u: "N1" for u in "abcdefg"}
    node_key["h"] = None                                          # not in any node -> never filled
    assigns, leftover = fill.risky_assignments(rows, [door], node_key)
    got = {row["uid"]: idx for row, idx in assigns}
    eq(got.get("e"), "0001", "1st DL (row order) -> the 1st object index 0001")
    eq(got.get("f"), "0002", "2nd DL -> the 2nd object index 0002")
    eq(got.get("g"), "0001", "1st DR -> object 0001 (matched per script_type, independently of the DLs)")
    ok("h" not in got, "a row in no IO node is never risky-filled")
    eq(leftover, 0, "every in-node unresolved member lined up with an object")


def test_risky_assignments_leftover_when_more_than_objects():
    from pipeline4.domain.fillout import fill
    from pipeline4.domain.fillout.families import ObjectFamily, LINK_FLD
    door = ObjectFamily(family="door", key="D", member_types=("DI", "DL"), anchor="DI1/2", link=LINK_FLD,
                        index_stride=1, bits=2, diag_block="+SafetyDoors")

    def r(uid, st, idx, row):
        return {"uid": uid, "script_type": st, "index": idx, "functional_unit": "=S1", "location": "+L",
                "device": "-X" + str(row), "desc_l1": "d", "source_sheet": "S", "source_row": row}

    # ONE object (0001) but THREE DL unresolved -> only the 1st lines up, two stay unresolved
    rows = [r("a", "DI1/2", "0001", 1), r("e", "DL", "<input required>", 2),
            r("f", "DL", "<input required>", 3), r("g", "DL", "<input required>", 4)]
    node_key = {u: "N1" for u in "aefg"}
    assigns, leftover = fill.risky_assignments(rows, [door], node_key)
    eq([row["uid"] for row, _ in assigns], ["e"], "only the 1st DL lines up with the single object")
    eq(leftover, 2, "the extra two DL stay unresolved (never invents an index)")


def test_diag_blocks_append_only_reuses_existing_id():
    # diag_blocks.read_existing reuses a present cabinet's ID_Local; block_rows appends only new cabinets.
    wb = Workbook()
    ws = wb.active
    ws.title = "DiagnosisBlocks"
    ws.append(diag_blocks.HEADERS)
    ws.append([5, 5, "=S1", "+OLD", "=S1+OLD", 1, "", 0, "", ""])
    ids, rows, header = diag_blocks.read_existing(wb)
    eq(ids, {"=S1+OLD": 5}, "existing FullName -> ID_Local reused")
    eq(rows, {5: 2}, "the existing cabinet's worksheet row")
    blocks = [diag_alloc.DiagBlock(id_local=5, fu="=S1", location="+OLD", full_name="=S1+OLD", template_type=1),
              diag_alloc.DiagBlock(id_local=6, fu="=S1", location="+NEW", full_name="=S1+NEW", template_type=1)]
    new = [b for b in blocks if b.full_name not in ids]
    appended = diag_blocks.block_rows(new, {}, (0, "", ""))
    eq(len(appended), 1, "only the NEW cabinet is appended")
    eq(appended[0][4], "=S1+NEW", "the appended row is the new FullName")


if __name__ == "__main__":
    import sys
    sys.exit(run("fillout_integration", [
        ("full_fill_writes_index_and_diag_cells", test_full_fill_writes_index_and_diag_cells),
        ("diagnosisblocks_sheet_created_with_derived", test_diagnosisblocks_sheet_created_with_derived),
        ("noop_drops_backup_on_prefilled_doc", test_noop_drops_backup_on_prefilled_doc),
        ("retyping_after_210_feeds_220_230", test_retyping_after_210_feeds_220_230),
        ("only_arg_restricts_writeback", test_only_arg_restricts_writeback),
        ("index_unresolved_is_reported", test_index_unresolved_is_reported),
        ("range_component_suffix_and_shared_index", test_range_component_suffix_and_shared_index),
        ("risky_assignments_by_node_type_and_row_order", test_risky_assignments_by_node_type_and_row_order),
        ("risky_assignments_leftover_when_more_than_objects", test_risky_assignments_leftover_when_more_than_objects),
        ("diag_blocks_append_only_reuses_existing_id", test_diag_blocks_append_only_reuses_existing_id),
    ]))

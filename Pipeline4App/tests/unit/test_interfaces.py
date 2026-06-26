"""Phase 400 (Interfaces). 400a: the per-signal interface_tagname (identity + annotate). Data-independent."""
from _harness import run, eq
from pipeline4.core.database import Database
from pipeline4.domain import identity, interfaces
from pipeline4.domain.signals import signals_table


def test_interp_keep_keeps_unknown_tokens():
    eq(identity.interp_keep("a {x} {y} b", {"x": "1"}), "a 1 {y} b", "a missing key's token is kept literal")
    eq(identity.interp_keep("{x}", {"x": None}), "", "a present-but-None key substitutes to ''")


def test_interface_tagname_tag_name_and_kept_tokens():
    # {tag_name} resolves to name_in_tagtable; {interface_name}/{interface_id} are KEPT for the generator
    row = {"name_in_tagtable": "Safety Breaker [ S1-B1 ]"}
    out = identity.interface_tagname(row, "PNC_Q_{interface_name}-{interface_id}_{tag_name}")
    eq(out, "PNC_Q_{interface_name}-{interface_id}_Safety Breaker [ S1-B1 ]")


def test_interface_tagname_db_element_from_name_in_db():
    # the door types template uses {db_element}, which in PL4 is the 520-written name_in_db
    row = {"name_in_db": "Door Closed SAFE_STATE [ =S1+SG1-B1 ]"}
    out = identity.interface_tagname(row, "PNC_Q_{interface_name}-{interface_id}_{db_element}")
    eq(out, "PNC_Q_{interface_name}-{interface_id}_Door Closed SAFE_STATE [ =S1+SG1-B1 ]")


def test_interface_tagname_row_tokens_and_empty_template():
    row = {"desc_l1": "EMERGENCY", "desc_l1b": "PUSH BUTTON", "iol_FLD": "S1-E1"}
    out = identity.interface_tagname(row, "PNC_Q_{interface_name}-{interface_id}_{desc_l1} {desc_l1b} [ {iol_FLD} ]")
    eq(out, "PNC_Q_{interface_name}-{interface_id}_EMERGENCY PUSH BUTTON [ S1-E1 ]")
    eq(identity.interface_tagname(row, ""), "", "no template -> ''")


def test_annotate_writes_per_type_from_config():
    tagnames = {"E1/2": "PNC_Q_{interface_name}-{interface_id}_{tag_name}",
                "DI1/2": "PNC_Q_{interface_name}-{interface_id}_{db_element}",
                "IOC": ""}
    table = signals_table(["script_type"])
    table.add(script_type="E1/2", type={"type_id": "E1/2"}, name_in_tagtable="Emergency Push Button [ X ]")
    table.add(script_type="DI1/2", type={"type_id": "DI1/2"}, name_in_db="Door Closed SAFE_STATE [ Y ]")
    table.add(script_type="IOC", type={"type_id": "IOC"})
    db = Database([table])
    interfaces.annotate_interface_tagnames(db, tagnames)
    rows = list(db["signals"])
    eq(rows[0]["interface_tagname"], "PNC_Q_{interface_name}-{interface_id}_Emergency Push Button [ X ]")
    eq(rows[1]["interface_tagname"], "PNC_Q_{interface_name}-{interface_id}_Door Closed SAFE_STATE [ Y ]")
    eq(rows[2]["interface_tagname"], "", "an IOC (no template) gets ''")


if __name__ == "__main__":
    import sys
    sys.exit(run("interfaces", [
        ("interp_keep_keeps_unknown_tokens", test_interp_keep_keeps_unknown_tokens),
        ("interface_tagname_tag_name_and_kept_tokens", test_interface_tagname_tag_name_and_kept_tokens),
        ("interface_tagname_db_element_from_name_in_db", test_interface_tagname_db_element_from_name_in_db),
        ("interface_tagname_row_tokens_and_empty_template", test_interface_tagname_row_tokens_and_empty_template),
        ("annotate_writes_per_type_from_config", test_annotate_writes_per_type_from_config),
    ]))

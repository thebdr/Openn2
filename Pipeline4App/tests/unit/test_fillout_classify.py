"""ph200 / 210 - script-type classification over the SHIPPED rule CSVs (gate_rules + script_type_rules),
evaluated by the UNIFIED engine `core.expr` over a STAGED signals row.

A `row` is a signals dict carrying the canonical columns the `$`-rules reference directly
(`desc_l1`/`desc_l1b`/`bit`/`id_node`/`type_hw`/...); the rules clean/join those themselves.
"""
from _harness import run, eq
from pipeline4.core import config
from pipeline4.domain.fillout import classify

_GATE = config.load_gate_rules()
_TYPE = config.load_script_type_rules()


def _t(bit="", id_node="", desc_l1="", desc_l1b="", type_hw=""):
    """Classify a STAGED signals row (canonical columns) via the engine-evaluated CSV rules."""
    row = {"bit": bit, "id_node": id_node, "desc_l1": desc_l1, "desc_l1b": desc_l1b, "type_hw": type_hw}
    return classify.classify(row, _GATE, _TYPE)


def test_node_passthrough():
    eq(_t(id_node="3", type_hw="PLC"), "PLC", "node -> Type col verbatim")


def test_in_ladder():
    eq(_t(bit="I0.0", desc_l1="EMERGENCY PUSH-BUTTON PRESSED", desc_l1b="CH1"), "E1/2", "emergency push-button")
    eq(_t(bit="I0.1", desc_l1="FEEDBACK SAFETY RELAY"), "KI", "safety relay feedback")
    eq(_t(bit="I0.2", desc_l1="DOOR OPEN", desc_l1b="CH2"), "DI2/2", "door channel input")
    eq(_t(bit="I0.3", desc_l1="DOOR OPEN", desc_l1b="RESET"), "DR", "door reset")
    eq(_t(bit="I0.4", desc_l1="DOOR OPEN"), "DD", "door open plain")
    eq(_t(bit="I0.5", desc_l1="SAFETY ENCODER PHOTOCELL", desc_l1b="CELL 3"), "N3/2", "encoder photocell")
    eq(_t(bit="I0.6", desc_l1="SWITCH DISCONNECTOR OPEN", desc_l1b="CH1"), "B1/2", "switch-disconnector")
    eq(_t(bit="I0.7", desc_l1="FIRE ALARM", desc_l1b="CH2"), "F2/2", "fire alarm")
    eq(_t(bit="I1.0", desc_l1="EMERGENCY RESET", desc_l1b="AREA 4"), "R4", "emergency reset, numbered area")
    eq(_t(bit="I1.1", desc_l1="EMERGENCY RESET", desc_l1b="GENERAL"), "R*", "emergency reset, no area -> R*")


def test_in_catch_alls():
    eq(_t(bit="I2.0", desc_l1="SOME UNRECOGNISED DESCRIPTION", type_hw="ZZ"), "ZZ", "IN catch-all -> Type col")
    eq(_t(bit="I2.1", desc_l1="SOME UNRECOGNISED DESCRIPTION"), "<input required>", "IN catch-all -> sentinel")
    eq(_t(bit="I2.2", desc_l1="AB"), "", "too-short description -> unclassified blank")
    # type_hw is rendered through clean() -> a whitespace-laden Type cell collapses
    eq(_t(bit="I2.3", desc_l1="ANOTHER UNRECOGNISED ROW", type_hw="  R5  "), "R5", "IN catch-all clean(type_hw)")


def test_out_ladder():
    eq(_t(bit="Q0.0", desc_l1="SAFETY RELAY"), "KQ", "safety relay output (desc1)")
    eq(_t(bit="Q0.1", desc_l1="DOOR OPEN"), "DQ", "door open output")
    eq(_t(bit="Q0.2", desc_l1="DOOR", desc_l1b="LAMP"), "DL", "door lamp")
    eq(_t(bit="Q0.3", desc_l1="OUTPUT", desc_l1b="EMERGENCY AREA 2"), "Z2", "emergency-area output")
    eq(_t(bit="Q0.4", desc_l1="SOME UNRECOGNISED OUTPUT"), "<input required>", "OUT catch-all -> sentinel")


def test_node_passthrough_cleaned():
    eq(_t(id_node="7", type_hw="  PlcCardCm  "), "PlcCardCm", "node -> clean(Type col) verbatim")


def test_no_gate():
    eq(_t(desc_l1="A STRUCTURAL ROW"), "", "no I/O address and no node -> no gate -> unclassified")


if __name__ == "__main__":
    import sys
    sys.exit(run("fillout_classify", [
        ("node_passthrough", test_node_passthrough),
        ("in_ladder", test_in_ladder),
        ("in_catch_alls", test_in_catch_alls),
        ("out_ladder", test_out_ladder),
        ("node_passthrough_cleaned", test_node_passthrough_cleaned),
        ("no_gate", test_no_gate),
    ]))

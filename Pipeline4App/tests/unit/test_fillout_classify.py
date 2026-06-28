"""ph200 / 210 - script-type classification over the SHIPPED rule CSVs (gate_rules + script_type_rules)."""
from _harness import run, eq
from pipeline4.core import config
from pipeline4.domain.fillout import classify

_GATE = config.load_gate_rules()
_TYPE = config.load_script_type_rules()


def _t(addr="", id_node="", d1="", d2="", type_hw=""):
    raw = {"bit": addr, "id_node": id_node, "desc_l1": d1, "desc_l1b": d2, "type_hw": type_hw}
    return classify.classify(raw, _GATE, _TYPE)


def test_node_passthrough():
    eq(_t(id_node="3", type_hw="PLC"), "PLC", "node -> Type col verbatim")


def test_in_ladder():
    eq(_t(addr="I0.0", d1="EMERGENCY PUSH-BUTTON PRESSED", d2="CH1"), "E1/2", "emergency push-button")
    eq(_t(addr="I0.1", d1="FEEDBACK SAFETY RELAY"), "KI", "safety relay feedback")
    eq(_t(addr="I0.2", d1="DOOR OPEN", d2="CH2"), "DI2/2", "door channel input")
    eq(_t(addr="I0.3", d1="DOOR OPEN", d2="RESET"), "DR", "door reset")
    eq(_t(addr="I0.4", d1="DOOR OPEN"), "DD", "door open plain")
    eq(_t(addr="I0.5", d1="SAFETY ENCODER PHOTOCELL", d2="CELL 3"), "N3/2", "encoder photocell")
    eq(_t(addr="I0.6", d1="SWITCH DISCONNECTOR OPEN", d2="CH1"), "B1/2", "switch-disconnector")
    eq(_t(addr="I0.7", d1="FIRE ALARM", d2="CH2"), "F2/2", "fire alarm")
    eq(_t(addr="I1.0", d1="EMERGENCY RESET", d2="AREA 4"), "R4", "emergency reset, numbered area")
    eq(_t(addr="I1.1", d1="EMERGENCY RESET", d2="GENERAL"), "R*", "emergency reset, no area -> R*")


def test_in_catch_alls():
    eq(_t(addr="I2.0", d1="SOME UNRECOGNISED DESCRIPTION", type_hw="ZZ"), "ZZ", "IN catch-all -> Type col")
    eq(_t(addr="I2.1", d1="SOME UNRECOGNISED DESCRIPTION"), "<input required>", "IN catch-all -> sentinel")
    eq(_t(addr="I2.2", d1="AB"), "", "too-short description -> unclassified blank")


def test_out_ladder():
    eq(_t(addr="Q0.0", d1="SAFETY RELAY"), "KQ", "safety relay output (desc1)")
    eq(_t(addr="Q0.1", d1="DOOR OPEN"), "DQ", "door open output")
    eq(_t(addr="Q0.2", d1="DOOR", d2="LAMP"), "DL", "door lamp")
    eq(_t(addr="Q0.3", d1="OUTPUT", d2="EMERGENCY AREA 2"), "Z2", "emergency-area output")
    eq(_t(addr="Q0.4", d1="SOME UNRECOGNISED OUTPUT"), "<input required>", "OUT catch-all -> sentinel")


def test_no_gate():
    eq(_t(d1="A STRUCTURAL ROW"), "", "no I/O address and no node -> no gate -> unclassified")


if __name__ == "__main__":
    import sys
    sys.exit(run("fillout_classify", [
        ("node_passthrough", test_node_passthrough),
        ("in_ladder", test_in_ladder),
        ("in_catch_alls", test_in_catch_alls),
        ("out_ladder", test_out_ladder),
        ("no_gate", test_no_gate),
    ]))

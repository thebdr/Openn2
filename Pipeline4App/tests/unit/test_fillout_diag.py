"""ph200 / 230 + 240 - DIAGNOSIS cabinet/bit allocation (`domain/fillout/diag_alloc.py`) over hermetic
synthetic staged rows. A `row` is a signals dict; `type` is the resolved type object (in_diag/type_id/
channel); `family` is resolved from `script_type` against the shipped object_families.

Covers: a node cabinet (non-P bits up from min / P down from max), the lone-PA/PW -> +FieldIODevices
inference, the Type-2 family `_family_offset` (door DI base+1 / DD base+2, encoder ch1 vs ch2, Z = area
number), an idempotent preserve of a pre-filled diag_bit, and stable-cabinet-id reuse via `existing`.
"""
from _harness import run, eq, ok
from pipeline4.domain.fillout import diag_alloc
from pipeline4.domain.fillout.families import ObjectFamily

_PARAMS = {"iolist_params": {"diag_bit_min": 0, "diag_bit_max": 62}}

# the shipped object_families (the subset the tests exercise)
_FAMS = [
    ObjectFamily("door", "D", ("DI", "DD", "DR", "DL", "DQ", "DO"), "DI1/2", "fld", 1, 2, "+SafetyDoors"),
    ObjectFamily("contactor", "K", ("KI", "KQ"), "KQ", "series", 1, 1, ""),
    ObjectFamily("emergency_pb", "E", ("E1/2", "E2/2"), "E1/2", "channel", 1, 1, "+EmergencyPushButtons"),
    ObjectFamily("breaker", "B", ("B1/2", "B2/2"), "B1/2", "channel", 1, 1, "+SafetyBreakers"),
    ObjectFamily("encoder", "N", ("N1/2", "N2/2"), "N1/2", "channel", 1, 2, "+SafetyEncoders"),
    ObjectFamily("reset", "R", ("R*", "R#"), "R*", "none", 1, 0, ""),
    ObjectFamily("emergency_area", "Z", ("Z#",), "Z#", "pattern", 1, 1, "+EmergencyAreas"),
    ObjectFamily("fire_alarm", "F", ("F1/2", "F2/2"), "F1/2", "channel", 1, 1, "+FireAlarm"),
]

_seq = [0]


def _row(script_type, type_id="", channel="", in_diag=True, index="", fu="=S1", loc="+X1", dev="",
         sheet="S", row=None, diag_cabinet="", diag_bit=""):
    _seq[0] += 1
    return {
        "uid": f"u{_seq[0]}",
        "script_type": script_type,
        "type": {"type_id": type_id or script_type, "channel": channel, "in_diag": in_diag},
        "index": index,
        "functional_unit": fu, "location": loc, "device": dev,
        "source_sheet": sheet, "source_row": row if row is not None else _seq[0],
        "diag_cabinet": diag_cabinet, "diag_bit": diag_bit,
    }


def test_node_cabinet_non_p_up_p_down():
    # two non-P (A) + one P (PA) on the same node FL -> one Type-1 cabinet; non-P up from 0, P down from 62.
    rows = [
        _row("A", "A", fu="=S1", loc="+N1", row=10),
        _row("A", "A", fu="=S1", loc="+N1", row=11),
        _row("PA", "PA", fu="=S1", loc="+N1", row=12),
    ]
    blocks, plac = diag_alloc.allocate(rows, _FAMS, _PARAMS)
    eq(len(blocks), 1, "one node cabinet")
    eq(blocks[0].template_type, 1, "Type-1")
    eq(blocks[0].full_name, "=S1+N1")
    cab = f"{blocks[0].id_local:03d}"
    eq(plac[rows[0]["uid"]], (cab, "00"), "first non-P at min")
    eq(plac[rows[1]["uid"]], (cab, "01"), "second non-P next up")
    eq(plac[rows[2]["uid"]], (cab, "62"), "P down from max")


def test_lone_pa_pw_field_inference():
    # a LONE PA on a node -> +FieldIODevices (Type-2), filled DOWNWARD from max; no dedicated cabinet.
    rows = [_row("PW", "PW", fu="=S1", loc="+SW1")]
    blocks, plac = diag_alloc.allocate(rows, _FAMS, _PARAMS)
    eq(len(blocks), 1, "only the +FieldIODevices block")
    eq(blocks[0].family, "+FieldIODevices")
    eq(blocks[0].template_type, 2)
    cab = f"{blocks[0].id_local:03d}"
    eq(plac[rows[0]["uid"]], (cab, "62"), "lone PW poured DOWN from max into the field block")


def test_type2_door_offset():
    # door family: DI at base+1, DD at base+2 (index 1 -> base 0 -> DI bit 1, DD bit 2).
    rows = [
        _row("DI1/2", "DI1/2", channel="1", index="1", dev="-D1"),
        _row("DD", "DD", index="1", dev="-D1"),
    ]
    blocks, plac = diag_alloc.allocate(rows, _FAMS, _PARAMS)
    door = next(b for b in blocks if b.family == "+SafetyDoors")
    cab = f"{door.id_local:03d}"
    eq(plac[rows[0]["uid"]], (cab, "01"), "DI -> base+1")
    eq(plac[rows[1]["uid"]], (cab, "02"), "DD -> base+2")


def test_type2_encoder_channels():
    # encoder family: two channels per index. index 1 -> ch1 bit 0, ch2 bit 1.
    rows = [
        _row("N1/2", "N1/2", channel="1", index="1", dev="-E1"),
        _row("N2/2", "N2/2", channel="2", index="1", dev="-E1"),
    ]
    blocks, plac = diag_alloc.allocate(rows, _FAMS, _PARAMS)
    enc = next(b for b in blocks if b.family == "+SafetyEncoders")
    cab = f"{enc.id_local:03d}"
    eq(plac[rows[0]["uid"]], (cab, "00"), "encoder ch1 -> bit 0")
    eq(plac[rows[1]["uid"]], (cab, "01"), "encoder ch2 -> bit 1")


def test_type2_emergency_area_number():
    # Z family: bit = the area number embedded in the script_type (Z3 -> bit 3).
    rows = [_row("Z3", "Z3", index="1", dev="-Z3")]
    blocks, plac = diag_alloc.allocate(rows, _FAMS, _PARAMS)
    area = next(b for b in blocks if b.family == "+EmergencyAreas")
    cab = f"{area.id_local:03d}"
    eq(plac[rows[0]["uid"]], (cab, "03"), "Z3 -> bit 3 (the area number)")


def test_idempotent_preserve_ex_bit():
    # a row carrying a pre-filled diag_bit keeps it; a blank sibling CONTINUES PAST the used bit.
    rows = [
        _row("A", "A", fu="=S1", loc="+N2", row=5, diag_bit="07"),   # pre-filled at 7
        _row("A", "A", fu="=S1", loc="+N2", row=6),                  # blank -> first free non-P
    ]
    blocks, plac = diag_alloc.allocate(rows, _FAMS, _PARAMS)
    cab = f"{blocks[0].id_local:03d}"
    eq(plac[rows[0]["uid"]], (cab, "07"), "kept the pre-filled bit")
    eq(plac[rows[1]["uid"]], (cab, "00"), "blank takes min (0 not yet used)")


def test_stable_cabinet_id_reuse_via_existing():
    # an existing full_name -> id 5 is reused (no renumber); a new cabinet gets the next free id above it.
    rows = [
        _row("A", "A", fu="=S1", loc="+OLD", row=1),
        _row("A", "A", fu="=S1", loc="+NEW", row=2),
    ]
    existing = {"=S1+OLD": 5}
    blocks, plac = diag_alloc.allocate(rows, _FAMS, _PARAMS, existing=existing)
    by_fn = {b.full_name: b.id_local for b in blocks}
    eq(by_fn["=S1+OLD"], 5, "reused the existing id")
    ok(by_fn["=S1+NEW"] > 5, "new cabinet id above every existing")
    eq(plac[rows[0]["uid"]][0], "005", "old row -> cabinet 005")


def test_no_collisions_mixed():
    rows = [
        _row("A", "A", fu="=S1", loc="+N9", row=1),
        _row("PA", "PA", fu="=S1", loc="+N9", row=2),
        _row("DI1/2", "DI1/2", channel="1", index="1", dev="-D9"),
        _row("DD", "DD", index="1", dev="-D9"),
        _row("Z2", "Z2", index="1", dev="-Z2"),
    ]
    blocks, plac = diag_alloc.allocate(rows, _FAMS, _PARAMS)
    seen = {}
    for uid, slot in plac.items():
        ok(slot not in seen, f"collision {slot}")
        seen[slot] = uid


TESTS = [
    ("node_cabinet_non_p_up_p_down", test_node_cabinet_non_p_up_p_down),
    ("lone_pa_pw_field_inference", test_lone_pa_pw_field_inference),
    ("type2_door_offset", test_type2_door_offset),
    ("type2_encoder_channels", test_type2_encoder_channels),
    ("type2_emergency_area_number", test_type2_emergency_area_number),
    ("idempotent_preserve_ex_bit", test_idempotent_preserve_ex_bit),
    ("stable_cabinet_id_reuse_via_existing", test_stable_cabinet_id_reuse_via_existing),
    ("no_collisions_mixed", test_no_collisions_mixed),
]

if __name__ == "__main__":
    raise SystemExit(run("fillout diag_alloc", TESTS))

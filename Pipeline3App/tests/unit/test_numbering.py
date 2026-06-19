"""M1 gate: the sparse hierarchical numbering convention."""
from _harness import run, eq, raises
from pipeline3.core import numbering as n


def test_phase_of():
    eq(n.phase_of(100), 100)
    eq(n.phase_of(130), 100)
    eq(n.phase_of(150), 100)
    eq(n.phase_of(620), 600)
    eq(n.phase_of(900), 900)


def test_slot_of():
    eq(n.slot_of(100), 0)
    eq(n.slot_of(130), 30)
    eq(n.slot_of(850), 50)


def test_sub():
    eq(n.sub(100, 10), 110)
    eq(n.sub(800, 50), 850)


def test_between():
    eq(n.between(110, 120), 115)
    eq(n.between(120, 110), 115)   # order-independent
    eq(n.between(100, 200), 150)


def test_between_no_gap():
    raises(ValueError, lambda: n.between(110, 111))
    raises(ValueError, lambda: n.between(110, 110))


if __name__ == "__main__":
    raise SystemExit(run("numbering", [
        ("phase_of", test_phase_of),
        ("slot_of", test_slot_of),
        ("sub", test_sub),
        ("between", test_between),
        ("between_no_gap", test_between_no_gap),
    ]))

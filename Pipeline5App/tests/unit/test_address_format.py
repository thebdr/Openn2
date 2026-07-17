"""The configurable I/O address notation (P-010) - truth.addresses under per-system formats.

The Siemens pattern must parse byte/bit-EXACTLY like PL4's literal parser; a synthetic alternate
notation (German-style E/A directions, dash separator) must work with ZERO code change - only
config - and map to the kernel's CANONICAL I/Q directions.
"""
from _harness import run, eq, ok

from pipeline5.truth import addresses


def _restore():
    addresses.configure_address_format(None, None)


def test_siemens_default_matches_pl4_literal_parser():
    """The shipped TIA pattern == the PL4 `_addr_byte` literal, case by case."""
    _restore()
    cases = {
        "I100.3": ("I", 100), "Q1.0": ("Q", 1), "i5.7": ("I", 5), "q10000.0": ("Q", 10000),
        " I12.3 ": ("I", 12),
        "I100": None,          # no bit -> not a full address
        "PEW 100": None, "": None, None: None, "M10.1": None, "I.3": None, "Ix.3": None,
    }
    for raw, want in cases.items():
        eq(addresses.addr_byte(raw), want, f"addr_byte({raw!r})")
    ok(addresses.has_io_prefix("I100"), "prefix predicate stays LOOSER than the full parse")
    ok(addresses.has_io_prefix("q"), "a bare direction letter still prefixes")
    ok(not addresses.has_io_prefix("M10.1"), "a non-direction letter does not")


def test_alternate_notation_is_config_only():
    """A German-style notation (E/A, dash separator) parses with no code change and maps to the
    kernel's canonical I/Q - the whole point of P-010."""
    addresses.configure_address_format(
        r"%(?P<direction>[EA])(?P<byte>\d+)-(?P<bit>\d+)",
        {"input": ["E"], "output": ["A"]})
    try:
        eq(addresses.addr_byte("%E10-1"), ("I", 10), "E maps to the canonical input direction")
        eq(addresses.addr_byte("%A2-0"), ("Q", 2), "A maps to the canonical output direction")
        eq(addresses.addr_byte("I100.3"), None, "the TIA spelling no longer matches")
        ok(addresses.has_io_prefix("%") is False and addresses.has_io_prefix("E77"),
           "the prefix predicate follows the configured tokens")
    finally:
        _restore()


def test_refresh_injects_from_the_tiers():
    """config.use_system re-resolves address_format.yaml through the 4-tier walk and injects it -
    the Siemens system ships the TIA pattern, so the default behavior is unchanged end to end."""
    from pipeline5 import config
    from pipeline5.systems import catalog
    config.use_system(catalog.by_id("siemens_s7_safety"))   # re-inject (the harness already did once)
    eq(addresses.addr_byte("Q88.4"), ("Q", 88), "the shipped Siemens format is active")


def test_node_of_uses_the_canonical_direction():
    """node_of keys the positional range columns on the CANONICAL direction, whatever the spelling."""
    addresses.configure_address_format(
        r"(?P<direction>[EA])(?P<byte>\d+)\.(?P<bit>\d+)", {"input": ["E"], "output": ["A"]})
    try:
        rows = [{"profinet_name": "N1", "I_startByte": 0, "I_endByte": 99, "uid": "n1"},
                {"bit": "E50.1", "uid": "s"}]
        node = addresses.node_of(rows, rows[1])
        ok(node is not None and node["uid"] == "n1", "E-address lands in the I_ range")
    finally:
        _restore()


if __name__ == "__main__":
    import sys
    sys.exit(run("address_format", [
        ("siemens_default_matches_pl4_literal_parser", test_siemens_default_matches_pl4_literal_parser),
        ("alternate_notation_is_config_only", test_alternate_notation_is_config_only),
        ("refresh_injects_from_the_tiers", test_refresh_injects_from_the_tiers),
        ("node_of_uses_the_canonical_direction", test_node_of_uses_the_canonical_direction),
    ]))

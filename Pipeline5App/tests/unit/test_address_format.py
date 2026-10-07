"""The configurable I/O address notation (P-010) - truth.addresses under per-system formats.

The Siemens pattern must parse byte/bit-EXACTLY like PL4's literal parser; a synthetic alternate
notation (German-style E/A directions, dash separator) must work with ZERO code change - only
config - and map to the kernel's CANONICAL I/Q directions.
"""
import os

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
        eq(addresses.addr_byte("I100.3"), ("I", 100),
           "the TIA spelling is the CANONICAL one staging stores - it reads under any notation (C-022)")
        eq(addresses.addr_byte("E100.3"), None, "a spelling of neither form is no address")
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


_DOTTED = r"(?P<direction>[IQ])\.?(?P<byte>\d+)\.(?P<bit>\d+)"


def test_canonical_spelling_default_unchanged():
    """C-022 completion: under the TIA default the canonical spelling is the address itself (its direction
    letter upper-cased); a value that is no address comes back unchanged; format_ok keeps its verdicts."""
    _restore()
    eq(addresses.canonical("I10.3"), "I10.3")
    eq(addresses.canonical("q1484.0"), "Q1484.0", "the canonical direction letter is upper-case")
    for v in ("", None, "PA", "I100", "I.645.1", "I:0.0", "M10.1"):
        eq(addresses.canonical(v), v, f"{v!r} is no address in the TIA notation -> unchanged")
    ok(addresses.format_ok("I10.3") and not addresses.format_ok("I.645.1") and not addresses.format_ok("I:0.0"),
       "the default verdicts: a dot after the direction is malformed under TIA")
    eq(addresses.key(" I 10.3 "), "I10.3", "the key strips whitespace")


def test_dotted_project_notation():
    """C-022 completion (FVT LaPoste): a project notation with a dot after the direction (`I.645.1`). The
    canonical spelling is `I645.1`; both spellings parse, key alike and pass the format check; a malformed
    dotted value still fails."""
    addresses.configure_address_format(_DOTTED, None)
    try:
        eq(addresses.canonical("I.645.1"), "I645.1")
        eq(addresses.canonical("Q.1484.0"), "Q1484.0")
        eq(addresses.canonical("I645.1"), "I645.1", "the canonical spelling itself is accepted")
        eq(addresses.key("I.645.1"), addresses.key("I645.1"), "I/O List and C&E match whatever spelling")
        eq(addresses.addr_byte("I.645.1"), ("I", 645))
        eq(addresses.parse("Q.1484.7"), ("Q", 1484, 7))
        ok(addresses.format_ok("I.645.1") and addresses.format_ok("Q.1484.0"), "the notation's addresses are well formed")
        ok(not addresses.format_ok("I.645") and not addresses.format_ok("I.645.x"), "a malformed dotted value still fails")
        ok(addresses.is_input(addresses.key("I.645.1")) and addresses.is_output(addresses.key("Q.1484.0")),
           "the kind is read on the canonical key")
    finally:
        _restore()


def test_canonical_spelling_reads_under_any_notation():
    """What staging STORES (the canonical spelling) reads back under ANY notation - the node ranges,
    diagnosis, coverage and the tag predicate read the stored address; a spelling of neither form does not."""
    addresses.configure_address_format(r"%(?P<direction>[EA])(?P<byte>\d+)-(?P<bit>\d+)",
                                       {"input": ["E"], "output": ["A"]})
    try:
        eq(addresses.canonical("%E10-1"), "I10.1", "the German spelling stored canonical")
        eq(addresses.addr_byte("I10.1"), ("I", 10), "the stored spelling reads back")
        ok(addresses.has_io_prefix("I10.1"), "a stored address keeps its tag")
        eq(addresses.addr_byte("E10.1"), None, "a spelling of neither form is no address")
    finally:
        _restore()


def test_whitespace_inside_a_cell():
    """C-022 completion (refute round 1): whitespace inside an address cell is tolerated the same way by the
    canonical spelling, the key and the node-range reader - `I 12.3` is stored `I12.3`, so its tag is `%I12.3`
    and its node range covers byte 12."""
    _restore()
    eq(addresses.canonical("I 12.3"), "I12.3")
    eq(addresses.addr_byte("I 12.3"), ("I", 12))
    eq(addresses.canonical(" PA "), " PA ", "a non-address stays as written")
    addresses.configure_address_format(_DOTTED, None)
    try:
        eq(addresses.key("I. 645.1"), addresses.key("I.645.1"), "a stray space keys like the clean dotted spelling")
        eq(addresses.canonical("I. 645.1"), "I645.1")
    finally:
        _restore()


def test_project_tier_overrides_the_notation():
    """C-022: a project's tier-1 `config_project/systems/<sid>/address_format.yaml` installs its notation on
    use_project (the FVT project's route); closing the project restores the system default."""
    import tempfile
    from pipeline5.config import paths
    from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM
    paths.use_system(SYSTEM)
    with tempfile.TemporaryDirectory() as d:
        sysdir = os.path.join(d, "config_project", "systems", SYSTEM.id)
        os.makedirs(sysdir)
        with open(os.path.join(sysdir, "address_format.yaml"), "w", encoding="utf-8") as f:
            f.write("pattern: '(?P<direction>[IQ])\\.?(?P<byte>\\d+)\\.(?P<bit>\\d+)'\n")
        paths.use_project(d)
        try:
            ok(addresses.format_ok("I.645.1"), "the project notation is active")
            eq(addresses.canonical("I.645.1"), "I645.1")
        finally:
            paths.use_project(None)
    ok(not addresses.format_ok("I.645.1"), "closing the project restores the TIA default")
    _restore()


def test_optional_group_notation_never_crashes():
    """C-022 (refute round 2): a notation whose bit group is OPTIONAL (word addresses `IW256` match) treats a
    match without a bit as no address - staging and validation never crash on it."""
    addresses.configure_address_format(r"(?P<direction>[IQ])W?(?P<byte>\d+)(?:\.(?P<bit>\d+))?", None)
    try:
        eq(addresses.parse("IW256"), None, "no bit -> no address")
        eq(addresses.canonical("IW256"), "IW256", "left as written")
        eq(addresses.addr_byte("IW256"), None)
        addresses.format_ok("IW256")                  # no exception
        eq(addresses.canonical("I10.3"), "I10.3", "a full address still parses")
    finally:
        _restore()


def test_notation_without_a_named_group_is_refused():
    """C-022 (refute round 2): a notation that names no direction / byte / bit group is a config error at load,
    never a silent no-address for every cell; the active notation is left as it was."""
    try:
        addresses.configure_address_format(r"(?P<direction>[IQ])(\d+)\.(?P<bit>\d+)", None)
        ok(False, "a pattern without (?P<byte>...) must be refused")
    except ValueError as e:
        ok("byte" in str(e), str(e))
    eq(addresses.canonical("I10.3"), "I10.3", "the previous notation still active")
    _restore()


def test_broad_direction_class_reads_the_stored_canonical():
    """C-022 (refute round 2): a notation whose direction class also matches the canonical letters (here any
    letter, tokens E/A) still reads the STORED canonical `I10.1` - an unmapped token falls through to the
    canonical spelling - while a letter of neither is no address."""
    addresses.configure_address_format(r"(?P<direction>[A-Z])(?P<byte>\d+)\.(?P<bit>\d+)",
                                       {"input": ["E"], "output": ["A"]})
    try:
        eq(addresses.canonical("E10.1"), "I10.1", "the notation's input token")
        eq(addresses.addr_byte("I10.1"), ("I", 10), "the stored canonical spelling")
        eq(addresses.addr_byte("M10.1"), None, "a letter of neither form")
    finally:
        _restore()


def _tier1(project, text):
    from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM
    d = os.path.join(project, "config_project", "systems", SYSTEM.id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "address_format.yaml"), "w", encoding="utf-8") as f:
        f.write(text)


def test_unusable_project_notation_never_raises():
    """C-022 refute round 3: a project notation that will not load (a group named wrong, a bad regex, not a
    mapping) NEVER raises out of the project switch - the switch completes, the TIA default is installed, the
    problem is kept - and staging turns it into the blocking `stg_address_format` FAIL; fixed, the next read
    clears it."""
    import tempfile
    from pipeline5 import config
    from pipeline5.config import paths
    from pipeline5.phases.staging import iolist as staging
    from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM
    paths.use_system(SYSTEM)
    previous = paths.active_project()
    try:
        for bad in ("pattern: '(?P<direction>[IQ])(\\d+)\\.(?P<bit>\\d+)'\n",     # (?P<byte>...) missing
                    "pattern: '(?P<direction>[IQ]'\n",                               # not a regex
                    "- just a list\n"):                                              # not a mapping
            with tempfile.TemporaryDirectory() as project:
                _tier1(project, bad)
                paths.use_project(project)                    # must not raise
                eq(paths.active_project(), project, "the switch completed")
                ok(config.address_format_problem(), "the problem is kept")
                eq(addresses.canonical("I10.3"), "I10.3", "the TIA default installed meanwhile")
                found = staging.notation_findings()
                eq([(f.type, f.severity) for f in found], [("stg_address_format", "FAIL")], bad)
                _tier1(project, "pattern: '(?P<direction>[IQ])\\.?(?P<byte>\\d+)\\.(?P<bit>\\d+)'\n")
                eq(staging.notation_findings(), [], "fixed: the next read clears it")
                eq(addresses.canonical("I.645.1"), "I645.1", "and installs the edited notation")
                paths.use_project(previous)
    finally:
        paths.use_project(previous)
        _restore()


def test_launch_order_installs_the_project_notation():
    """C-022 refute round 3: at launch the project opens BEFORE a system is active (auto-reopen); the system
    switch that follows installs the project's tier-1 notation."""
    import tempfile
    from pipeline5.config import paths
    from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM
    previous_project, previous_system = paths.active_project(), paths.active_system()
    with tempfile.TemporaryDirectory() as project:
        _tier1(project, "pattern: '(?P<direction>[IQ])\\.?(?P<byte>\\d+)\\.(?P<bit>\\d+)'\n")
        try:
            paths.use_system(None)
            paths.use_project(project)
            ok(not addresses.format_ok("I.645.1"), "no system yet: the tier-1 system notation is not visible")
            paths.use_system(SYSTEM)
            eq(addresses.canonical("I.645.1"), "I645.1", "the system switch installs it")
        finally:
            paths.use_project(previous_project)
            paths.use_system(SYSTEM if previous_system else None)
            _restore()


if __name__ == "__main__":
    import sys
    sys.exit(run("address_format", [
        ("siemens_default_matches_pl4_literal_parser", test_siemens_default_matches_pl4_literal_parser),
        ("alternate_notation_is_config_only", test_alternate_notation_is_config_only),
        ("refresh_injects_from_the_tiers", test_refresh_injects_from_the_tiers),
        ("node_of_uses_the_canonical_direction", test_node_of_uses_the_canonical_direction),
        ("canonical_spelling_default_unchanged", test_canonical_spelling_default_unchanged),
        ("dotted_project_notation", test_dotted_project_notation),
        ("canonical_spelling_reads_under_any_notation", test_canonical_spelling_reads_under_any_notation),
        ("whitespace_inside_a_cell", test_whitespace_inside_a_cell),
        ("project_tier_overrides_the_notation", test_project_tier_overrides_the_notation),
        ("optional_group_notation_never_crashes", test_optional_group_notation_never_crashes),
        ("notation_without_a_named_group_is_refused", test_notation_without_a_named_group_is_refused),
        ("broad_direction_class_reads_the_stored_canonical", test_broad_direction_class_reads_the_stored_canonical),
        ("unusable_project_notation_never_raises", test_unusable_project_notation_never_raises),
        ("launch_order_installs_the_project_notation", test_launch_order_installs_the_project_notation),
    ]))

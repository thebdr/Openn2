"""Address parsing/format for phase-100 validation. Verbatim clean-room port of PL3's
`domain/validation/address.py` (pure, data-independent).

PLC addresses are dotted I/Q/O addresses: 2-part `<letter><byte>.<bit>` (e.g. I20.0, Q0.1) or 4-part
`<letter><byte>.<n>.<n>.<n>`. Rockwell colon addresses (`I:0.0`) are NOT supported. A bare number
("2", "2.0") is a value, not an address attempt, and is not flagged.
"""
from __future__ import annotations

import re

_NUMERIC = re.compile(r"\d+(?:\.\d+)*$")


def norm(value) -> str:
    """Address key: all whitespace removed, upper-cased."""
    return "".join(str(value if value is not None else "").split()).upper()


def kind(value) -> str:
    """Leading address kind: 'I', 'Q', 'O', or '' when the value is not an I/Q/O address."""
    lead = norm(value)[:1]
    return lead if lead in ("I", "Q", "O") else ""


def is_input(value) -> bool:
    return kind(value) == "I"


def is_output(value) -> bool:
    return kind(value) in ("Q", "O")


def format_ok(value) -> bool:
    """True when `value` is an acceptable address (or not an address attempt at all). False only for a
    malformed dotted/colon address: a Rockwell colon, a bad leading letter, a non-numeric byte/segment,
    or a dot-count other than 2 or 4. Judged on the CANONICAL spelling ([[C-022]]): an address written in
    the active notation (a project's `I.645.1`) is a well-formed address; under the TIA default the
    canonical spelling is the value itself, so the verdict is unchanged."""
    a = norm(canonical(value))
    if not a:
        return True                       # empty: nothing to validate
    if ":" in a:
        return False                      # Rockwell colon form not supported
    if "." not in a:
        return True                       # no dot: an ID / non-dotted token, not validated here
    if _NUMERIC.match(a):
        return True                       # a bare number (e.g. "2.0"), not an address attempt
    parts = a.split(".")
    head = parts[0]
    if head[:1] not in ("I", "Q", "O") or not head[1:].isdigit():
        return False
    if len(parts) == 2:
        return parts[1].isdigit()
    if len(parts) == 4:
        return all(p.isdigit() for p in parts[1:])
    return False


# --- the configurable I/O address NOTATION (P-010) ------------------------------------------------ #
# Every system spells addresses its own way; the KERNEL only ever sees the canonical direction
# ('I' input / 'Q' output) + byte. The active system's `address_format.yaml` is INJECTED here by
# `config.use_project/use_system` (config imports truth, never the reverse - the L1 law). The
# default is the TIA notation, byte/bit-exact with the PL4 literal parser.
_DEFAULT_PATTERN = r"(?P<direction>[IQ])(?P<byte>\d+)\.(?P<bit>\d+)"
_DEFAULT_TOKENS = {"input": ("I",), "output": ("Q",)}
_format = {"rx": re.compile(_DEFAULT_PATTERN, re.IGNORECASE), "tokens": dict(_DEFAULT_TOKENS)}


def configure_address_format(pattern: str | None, direction_tokens: dict | None) -> None:
    """Install the ACTIVE system's notation (None/None reverts to the TIA default). Called by
    config.use_project/use_system after resolving `address_format.yaml` through the 4-tier walk."""
    if not pattern:
        _format["rx"] = re.compile(_DEFAULT_PATTERN, re.IGNORECASE)
        _format["tokens"] = dict(_DEFAULT_TOKENS)
        return
    _format["rx"] = re.compile(pattern, re.IGNORECASE)
    tokens = direction_tokens or {}
    _format["tokens"] = {
        "input": tuple(str(x).upper() for x in (tokens.get("input") or ("I",))),
        "output": tuple(str(x).upper() for x in (tokens.get("output") or ("Q",))),
    }


def _canonical(direction: str):
    d = str(direction or "").upper()
    if d in _format["tokens"]["input"]:
        return "I"
    if d in _format["tokens"]["output"]:
        return "Q"
    return None


# --- the CANONICAL spelling ([[C-022]] completion) ------------------------------------------------- #
# The notation is INPUT-only: a document cell is parsed through it, and what the pipeline stores and emits
# is the canonical spelling `<I|Q><byte>.<bit>` (the TIA form - tags prefix '%'). Staging stores it in the
# signals table, so every later phase sees one spelling whatever the documents write.
_CANONICAL_RX = re.compile(r"(?P<direction>[IQ])(?P<byte>\d+)\.(?P<bit>\d+)", re.IGNORECASE)


def parse(value):
    """(canonical 'I'|'Q', byte, bit) of an address written in the ACTIVE notation - or already in the
    canonical spelling (what staging stores, so a stored address parses under any notation); None when
    the cell is not an address. Whitespace inside the cell is tolerated (`I 12.3`, `I. 645.1`) - the
    tolerance the matching key and the hardware / block address readers already have: the cell is
    tried as written (trimmed - a notation may spell a space), then with all whitespace removed."""
    s = str(value if value is not None else "").strip()
    compact = "".join(s.split())
    for cell in dict.fromkeys((s, compact)):
        m = _format["rx"].fullmatch(cell)
        if m:
            d = _canonical(m.group("direction"))
            if d is not None:
                try:
                    return d, int(m.group("byte")), int(m.group("bit"))
                except (ValueError, IndexError):
                    pass
    m = _CANONICAL_RX.fullmatch(compact)
    if m:
        return m.group("direction").upper(), int(m.group("byte")), int(m.group("bit"))
    return None


def canonical(value):
    """The canonical spelling of an address cell (`I.645.1` under a dotted notation -> `I645.1`); any value
    that is not an address in the active notation comes back UNCHANGED (an ID, a blank, a typo - left for
    the format check to judge)."""
    p = parse(value)
    if p is None:
        return value
    d, byte, bit = p
    return f"{d}{byte}.{bit}"


def key(value) -> str:
    """Address KEY for matching across documents: the canonical spelling, whitespace removed, upper-cased -
    so the I/O List and the C&E match whatever notation each writes."""
    return norm(canonical(value))


def has_io_prefix(bit) -> bool:
    """True when the cell STARTS with one of the notation's direction tokens - the taggable-I/O
    predicate (`identity.is_io_signal`), deliberately looser than a full address parse. The canonical
    letters I / Q count under any notation - staging stores the canonical spelling ([[C-022]])."""
    first = str(bit or "").strip().upper()[:1]
    return (first in _format["tokens"]["input"] or first in _format["tokens"]["output"]
            or first in ("I", "Q"))


# --- positional Profinet-node lookup (moved from the diagnosis chapter - coupling truths #2/#g) --- #
def addr_byte(bit):
    """(canonical 'I'|'Q', byte) parsed from the ACTIVE notation's full address (`I100.3` ->
    ('I', 100) under the TIA default); None when the cell is not an address. The kernel's node
    ranges (I_/Q_ startByte/endByte) key on the CANONICAL direction, whatever the system spells. The
    canonical spelling staging stores ([[C-022]]) is read too, under any notation - ONE parser, `parse`."""
    p = parse(bit)
    return (p[0], p[1]) if p else None


def node_of(rows, row):
    """The Profinet node whose POSITIONAL I/Q byte range (staging `I_/Q_startByte/endByte`) contains
    this signal's address; None otherwise. Shared vocabulary: diagnosis allocates by it, coverage
    traces by it, the risky-index fill matches by it."""
    ab = addr_byte(row.get("bit"))
    if not ab:
        return None
    kind_, byte = ab
    sk, ek = f"{kind_}_startByte", f"{kind_}_endByte"
    for n in (r for r in rows or [] if r.get("profinet_name")):
        s, e = n.get(sk, ""), n.get(ek, "")
        if str(s) != "" and int(s) <= byte <= int(e):
            return n
    return None

"""Address parsing/format for phase-100 validation. Verbatim clean-room port of PL3's
`domain/validation/address.py` (pure, data-independent).

PLC addresses are dotted I/Q/O addresses: 2-part `<letter><byte>.<bit>` (e.g. I20.0, Q0.1) or 4-part
`<letter><byte>.<n>.<n>.<n>`. Rockwell colon addresses (`I:0.0`) are NOT supported. A bare number
("2", "2.0") is a value, not an address attempt, and is not flagged.
"""
from __future__ import annotations

import re

_NUMERIC = re.compile(r"\d+(?:\.\d+)*$")
_DOTTED_AREA = re.compile(r"^(\s*[IQOiqo])\.(?=\s*\d+\s*\.\s*\d)")


def normalize_dotted(value):
    """A project convention writes a dot after the area letter ('I.645.1', 'Q.1484.0'). Drop that one dot
    -> the standard form ('I645.1', 'Q1484.0'); anything else (already standard, blank, a non-address)
    is returned unchanged. Applied where the documents are READ when the project turns on
    `iolist_params` / `matrix_params` `normalize_dotted_address`."""
    if not isinstance(value, str):
        return value
    return _DOTTED_AREA.sub(r"\1", value, count=1)


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
    or a dot-count other than 2 or 4."""
    a = norm(value)
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

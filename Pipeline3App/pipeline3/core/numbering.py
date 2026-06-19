"""Sparse hierarchical numbering for every ordered enumeration (plan, Context + §4).

Pipeline phases are **hundreds** (100, 200, ... 900). Sub-phases/steps within a phase are the
parent phase **plus tens** (110, 120, ...). The **ones digit is reserved** for finer insertions
(e.g. 115 between 110 and 120). A number is just an int; presentation sorts ascending. New steps
slot in on the gaps, so existing numbers never need renumbering.

This matches assets/ButtonsLayout.xlsx, where row 1 carries the phase id (100..900) and column A
carries the slot id (10..50): a button's number == phase id + slot id.
"""
from __future__ import annotations

PHASE_STEP = 100   # spacing between top-level pipeline phases
SUB_STEP = 10      # spacing between sub-phases / steps within a phase


def phase_of(number: int) -> int:
    """The owning pipeline phase (hundreds) of any number.  phase_of(130) -> 100."""
    return (number // PHASE_STEP) * PHASE_STEP


def slot_of(number: int) -> int:
    """The within-phase slot of a number.  slot_of(130) -> 30; slot_of(100) -> 0."""
    return number - phase_of(number)


def sub(phase: int, slot: int) -> int:
    """Compose a sub-phase number from a phase + slot.  sub(100, 30) -> 130."""
    return phase + slot


def between(a: int, b: int) -> int:
    """A number strictly between two adjacent ones, for inserting a step later.
    between(110, 120) -> 115.  Raises ValueError when there is no integer gap."""
    lo, hi = (a, b) if a <= b else (b, a)
    if hi - lo < 2:
        raise ValueError(f"no integer gap between {a} and {b}")
    return (lo + hi) // 2

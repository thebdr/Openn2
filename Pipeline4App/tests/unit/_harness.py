"""Tiny test harness for the plain-python unit tests (no pytest).

Each test module builds a list of (name, fn) and calls run(...). Importing this module also bootstraps
the Pipeline4App root onto sys.path so `from pipeline4.core import ...` works when a test is launched
directly (python tests/unit/test_x.py).
"""
from __future__ import annotations
import os
import sys
import traceback

# tests/unit/_harness.py -> unit -> tests -> Pipeline4App
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)


def run(title: str, tests) -> int:
    print(f"== {title} ==")
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {e}")
            traceback.print_exc()
    total = len(tests)
    print(f"  -> {total - failed}/{total} passed\n")
    return 1 if failed else 0


def eq(a, b, msg=""):
    if a != b:
        raise AssertionError(f"{msg} expected {b!r}, got {a!r}")


def ok(cond, msg=""):
    if not cond:
        raise AssertionError(msg or "expected truthy")


def raises(exc, fn):
    try:
        fn()
    except exc:
        return
    raise AssertionError(f"expected {exc.__name__}")

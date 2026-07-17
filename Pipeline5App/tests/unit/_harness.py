"""Tiny test harness for the plain-python unit tests (no pytest) - the PL4 harness carried forward.

Each test module builds a list of (name, fn) and calls run(...). Importing this module also bootstraps
the Pipeline5App root onto sys.path so `from pipeline5.truth import ...` works when a test is launched
directly (python tests/unit/test_x.py).
"""
from __future__ import annotations
import os
import sys
import traceback

# tests/unit/_harness.py -> unit -> tests -> Pipeline5App
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

# The 4-tier config resolver needs an ACTIVE SYSTEM for the system-tier files (signal_types, the
# rule CSVs, generation params). Tests exercise the Siemens data flows, so the harness activates
# the one registered system app-wide - exactly what app startup does.
from pipeline5 import config as _config             # noqa: E402
from pipeline5.systems import catalog as _catalog   # noqa: E402
_config.use_system(_catalog.by_id("siemens_s7_safety"))


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

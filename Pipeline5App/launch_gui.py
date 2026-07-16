"""Pipeline5App entry point - `python launch_gui.py` (mirrors PL4's launcher).

Until migration step 2 lands the GUI kernel, this exits with a pointed message instead of a
traceback - the scaffold is importable, not yet runnable.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    try:
        from pipeline5.gui import app_main  # noqa: F401
    except ImportError:
        print("Pipeline5App: the GUI kernel is not ported yet (migration step 2 of the PL5 plan).")
        print("The systems scaffold is importable: python -c \"from pipeline5.systems import catalog\"")
        return 2
    return app_main.main()


if __name__ == "__main__":
    sys.exit(main())

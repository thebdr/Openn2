"""Entrypoint: hand over to the workbench window (the run-plan registry lands here at step 5)."""
from __future__ import annotations


def main() -> int:
    from pipeline5.workbench import app_main
    return app_main.main() or 0

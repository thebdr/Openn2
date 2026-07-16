"""List the guide sections declared in docs/guide/index.yaml that have no .md page yet - the visible
authoring TODO (those ids currently render the missing-section fallback page).
    py scripts/list_guide_stubs.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline5.workbench import guide_window as helpwin  # noqa: E402

missing = helpwin.missing_sections()
print("\n".join(missing) if missing else "every indexed guide section has a page")

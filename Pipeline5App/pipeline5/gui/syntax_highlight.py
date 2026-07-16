"""Syntax highlighting - the EMBEDDING SHIM over `filexy.highlight` (the extracted FileXY package;
the logic moved there with the file-editor consolidation). Keeps the historical
`pipeline5.gui.syntax_highlight` surface so files_panel/db_explorer and the tests are untouched, and adds
what moved in: the data-driven Notepad++-UDL-style languages (`langs.json`: scl/sql/ini shipped;
`available_kinds()` feeds the Files tab's language picker; `object_kind_of` routes the
Object-explorer view)."""
from __future__ import annotations

from pipeline5.gui import filexy_shim  # noqa: F401  (sys.path + theme binding - must run first)

from filexy.highlight import (  # noqa: E402,F401
    COLORS, LANGS, OBJECT_KINDS, apply, available_kinds, configure_tags, kind_of,
    load_languages, object_kind_of, spans,
)

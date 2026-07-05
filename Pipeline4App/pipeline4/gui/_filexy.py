"""The ONE FileXY embedding bootstrap (the extracted viewer/editor package at ../../FileXYApp -
formerly TableViewerApp/tableviewer). Every PL4 shim (datagrid, highlight, object_editor) imports
this FIRST: it puts the sibling package on sys.path and binds `filexy.theme` to PL4's OWN tokens +
bundled fonts BEFORE any widget exists - so the embedded widgets are pixel-identical to PL4's look
and follow its theme toggle, import order be damned."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "FileXYApp"))
if os.path.isdir(_ROOT) and _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pipeline4.gui import theme as _pl4_theme     # noqa: E402
from filexy import theme as _fx_theme             # noqa: E402

_fx_theme.TOKENS = _pl4_theme.TOKENS
_fx_theme.mono_family = lambda _widget: _pl4_theme.MONO_FONT[0]
_fx_theme.narrow_family = _pl4_theme.narrow_family

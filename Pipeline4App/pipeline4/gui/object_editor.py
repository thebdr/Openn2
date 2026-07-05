"""The Object explorer/editor - the EMBEDDING SHIM over `filexy.objectview` (the extracted FileXY
package; the logic moved there with the file-editor consolidation). Keeps the historical
`pipeline4.gui.object_editor` surface (files_panel + the tests are untouched)."""
from __future__ import annotations

from pipeline4.gui import _filexy  # noqa: F401  (sys.path + theme binding - must run first)

from filexy.objectview import (  # noqa: E402,F401
    ObjectEditor, _is_element, add_dict_neighbor, add_list_neighbor, coerce, dump_document,
    get_at, is_scalar, load_document, path_role, picked_value, set_at, xml_items,
)

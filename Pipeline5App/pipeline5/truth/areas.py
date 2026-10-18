"""The C&E area hierarchy SSOT table definition ([[C-040]]) - the table DEF only (like `diagnosis.py`).

- `areas` - one row per C&E area, in the matrix's column order (then any area only an AREA sheet names), staged
  by the C&E pass (320): its `number` (a plain area its own, `AREA 3` -> 3; a sub-area its parent's x 1000 + its
  ordinal among that parent's sub-areas, `AREA 1_TRIB` -> 1001), its `parent` / `part` (a sub-area only, with
  `matrix_params.sub_areas` on), its CONCEPT `description` (matched by name; a sub-area inherits its parent's)
  and its kind - `sorter` = "yes" when `matrix_params.sorter_areas` lists its number. The builders read it for
  the sorter areas, their encoder number and the network titles.
"""
from __future__ import annotations

from pipeline5.truth.table import Table


def areas_table() -> Table:
    """One row per C&E area: the declared hierarchy, numbers, descriptions and kinds."""
    return Table(
        "areas",
        columns=["uid", "name", "number", "parent", "part", "order", "description", "sorter"],
        json_columns=[],
        key_columns=["name"],
    )

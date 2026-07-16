"""The `signals` table - PL4's fact table, successor of PL3's flat `IODatabase.csv`.

One row per kept I/O-List row (signals + node/metadata). Columns = the raw IoList canonical columns,
kept VERBATIM (DESIGN 10.5), followed by the staging-enriched fields. The difference from PL3 is the
representation, and it is the whole point of PL4:

  - the multi-valued fields are REAL JSON list cells, not '|'-joined strings - so no split-on-read, no
    "leftmost db name" hack: `datablocks` is `["07_DOOR"]`, `datablocks[0]` is the leftmost, typed;
  - the resolved type is STORED as one `type` object cell (replacing PL3's flattened
    `type_id_resolved`/`type_category`), so a reader never has to re-attach it from `signal_types`;
  - `plc_binding` is STORED, not re-derived on every call.

The staging logic that POPULATES this table (reads the documents, enriches, computes the identity
fields) is ported separately; this module only DEFINES the table so the schema is one fixed thing the
populate, the projections, and the GUI all share.
"""
from __future__ import annotations

from pipeline5.truth.table import Table

# The multi-valued / object columns - stored as JSON, never '|'-joined or re-derived. `interface_mapping`
# is a raw IoList column (the AH '|'-list); the rest are enriched.
SIGNAL_JSON_COLUMNS = ["matrix_areas", "areas_description", "datablocks", "interface_mapping", "type"]

# A signal's stable identity -> its content-hash uid (core.keys + DESIGN 10.1). `combined_FLD` +
# `script_type` is the stable content identity (it survives a row move); `source_cell` disambiguates the
# node/metadata rows that carry neither. To be validated on real data with `Table.duplicate_uids()` and
# refined when the staging read is ported (e.g. a node uses its profinet name/ip instead of source_cell).
SIGNAL_KEY_COLUMNS = ["combined_FLD", "script_type", "source_cell"]

# The staging-enriched columns appended to the raw IoList columns. This mirrors PL3 staging._EXTRA, with
# two deliberate changes: the flattened `type_id_resolved`/`type_category` are replaced by the whole
# `type` object, and `plc_binding` is added (stored, not re-derived). `_source_sheet`/`_source_row` lose
# their PL3 underscore prefix (verbose/clean naming, DESIGN 10.7).
ENRICHED_COLUMNS = [
    "matrix_areas", "areas_description",
    "ce_functional_unit", "ce_location", "ce_device", "numerazione_linea",
    "iol_FLD", "ce_FLD", "combined_FLD",
    "IsSorterArea", "name_in_db", "name_in_tagtable", "tagtable", "datablocks", "plc_binding", "diag_desc",
    "interface_tagname", "diag_block_name", "diag_block_template", "swp_cabinet", "subnet_name",
    "I_startByte", "I_endByte", "Q_startByte", "Q_endByte",
    "source_cell", "source_sheet", "source_row", "type",
]


def signals_table(iolist_columns) -> Table:
    """Build the empty `signals` Table: `uid`, then the raw IoList canonical columns VERBATIM (in their
    given order), then the enriched columns (those not already a raw column). `iolist_columns` is the
    canonical IoList column-name list (from the column map). The JSON + key columns are applied from the
    module constants, restricted to columns that actually exist in this schema."""
    iolist = list(iolist_columns)
    columns = ["uid"] + iolist + [column for column in ENRICHED_COLUMNS if column not in iolist]
    present = set(columns)
    return Table(
        "signals",
        columns=columns,
        json_columns=[column for column in SIGNAL_JSON_COLUMNS if column in present],
        key_columns=SIGNAL_KEY_COLUMNS,
    )

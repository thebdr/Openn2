"""Phase 400 (Interfaces) - clean-room port of PL3's interfaces.

Builds one `IF_<instance>.xlsx` per IOC signal from the MachineInterfaces template, mirrors flagged
signals into a custom byte-packed block, and (optionally) inserts each interface as an `IF_` sheet into
the I/O List. The mirrored signals + their byte layout land in the **`interfaces`** SSOT table; the
`IF_*.xlsx` are its projection.

This first cut (400a) is the per-signal **`interface_tagname`** (the Signal Name Side 1 base): the
type's template (the relocated `chain_reactions/interface_tagnames.csv`) resolved against the signal,
keeping `{interface_name}`/`{interface_id}` for the generator. It runs AFTER 520 (it reads the written
`name_in_db` for the door types' `{db_element}`), matching DESIGN section 9's `… 520 → 600 → 400` order.
"""
from __future__ import annotations

from pipeline4.core import config
from pipeline4.core.database import Database
from pipeline4.domain import identity
from pipeline4.domain.signals import signals_table


def annotate_interface_tagnames(database: Database, tagnames: dict | None = None) -> None:
    """Write `interface_tagname` onto every signal from its resolved type's template (keyed by `type_id`).
    Needs the 520 write-back (`name_in_db`) + the staged `name_in_tagtable`."""
    tagnames = tagnames if tagnames is not None else config.load_interface_tagnames()
    for row in database["signals"]:
        type_id = ((row.get("type") or {}).get("type_id") or "").strip().upper()
        row["interface_tagname"] = identity.interface_tagname(row, tagnames.get(type_id, ""))


def build_tagnames(database: Database | None = None) -> Database:
    """400a entry: load the (post-520) Database, annotate `interface_tagname`, save. Returns the Database."""
    if database is None:
        colmap = config.load_column_map("IoList")
        database = Database([signals_table([m["canonical"] for m in colmap])]).load(config.database_dir())
    annotate_interface_tagnames(database)
    database.save(config.database_dir())
    return database

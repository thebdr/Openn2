"""The truth - the SSOT data dictionary. Everything the pipeline knows is a row in here.

Phases never talk to each other; they meet in these tables (pipes-and-filters). This part owns the
table PRIMITIVES and every table SCHEMA, so reading it end-to-end tells you exactly what data exists.

WHERE TO LOOK:
  table.py          the CSV-with-JSON-cells Table primitive (deterministic codec, uid stamping)
  database.py       named tables + save/load - THE single source of truth on disk
  content_hash.py   uid(*parts) - how every entity gets its stable name
  signals.py        the signals fact table (one row per I/O signal)
  diagnosis.py      diagnosis_entries + diagnosis_cabinets schemas
  datablocks.py     db_blocks / db_members / instance_dbs schemas
  identity.py       FLD / tag-name identity derivation (the vocabulary of signal naming)
  addresses.py      I/O address parsing helpers (becomes config-regex-driven per P-010)
"""

# The Database Explorer

A read-only SQL console over the SSOT: every `Database/*.csv` table loads into an in-memory SQLite
copy, so cross-table JOINs, GROUP BY, and `json_extract()` over the JSON cells all work. The on-disk
CSVs are never touched - even a `DELETE` only hits the throwaway copy.

## Using it

- The database loads on the first visit, in the background; re-visiting the tab reloads it only when
  the `Database/` folder actually changed (a phase run does that). **Refresh** forces a reload.
- Write SQL in the editor, run with **Ctrl+Enter**; results land in the grid in slices, capped at
  2000 rows.
- Double-click a table in the sidebar for a `SELECT * … LIMIT 100`.
- The **Samples** box holds ready-made queries - JOINs on the `uid` foreign keys, findings by
  severity, coverage ORPHANs.

## The JSON cells

Object/list cells are stored as their JSON text. Query them with SQLite's JSON functions:

```
SELECT json_extract(type, '$.type_id') AS t, COUNT(*) FROM signals GROUP BY t
```

The engine lives in [pipeline5/gui/database_query.py](src://pipeline5/gui/database_query.py) (Tk-free, tested).

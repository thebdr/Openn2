"""The phase-520 block tables - PL4's SSOT for generated data blocks (DESIGN section 2):

  - `db_members`  - one row per generated Global-DB member (the seeds, the per-signal members, the
    `unique` aggregate tags). It is what the `<DB>.xml` projection (520c) is built FROM, grouped by
    `db_name`, in row order. Each member carries `source` = the producing signal's `uid` (a `row`-kind
    element), the bound value (a `unique` element, e.g. a cabinet number), or `"seed"`.
  - `instance_dbs` - one row per FB instance-DB family member -> `InstanceDBs.csv`.

The boolean member attributes (`retain` + the three `ext_*` + `setpoint`) are JSON cells so they
round-trip as real `True`/`False` (not the lossy `"True"`/`"False"` text a plain column would store).
"""
from __future__ import annotations

from pipeline4.core.table import Table

# The boolean member columns - JSON so a saved/loaded db_members.csv round-trips them as real bools.
DB_MEMBERS_BOOL_COLUMNS = ["retain", "ext_accessible", "ext_visible", "ext_writable", "setpoint"]


def db_members_table() -> Table:
    """The empty `db_members` table: `uid`, the member's DB + name + type + attributes, and `source`
    (the FK to what produced it). `uid` = content hash of (`db_name`, `member`) - unique, since 520
    dedups a member name within its DB."""
    return Table(
        "db_members",
        columns=["uid", "db_name", "member", "datatype", "start_value", "comment",
                 "retain", "ext_accessible", "ext_visible", "ext_writable", "setpoint", "source"],
        json_columns=DB_MEMBERS_BOOL_COLUMNS,
        key_columns=["db_name", "member"],
    )


def instance_dbs_table() -> Table:
    """The empty `instance_dbs` table: `uid`, the instance DB `instance_name`, and the `fb` it instantiates.
    `uid` = content hash of `instance_name` (unique - 520 dedups instance names)."""
    return Table(
        "instance_dbs",
        columns=["uid", "instance_name", "fb"],
        json_columns=[],
        key_columns=["instance_name"],
    )

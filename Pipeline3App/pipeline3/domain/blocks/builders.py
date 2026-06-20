"""USER-EDITABLE software-block builders (phase 800 / 820).

This is the file you edit. One function per template, registered with `@builds("<output name>")`.
Each builder receives the `Database` (the single source = the staged IODatabase / ctx.rows) and
returns a `Table`. There are NO rules and NO sidecars - your Python does whatever the template needs;
the engine just serializes your Table into the `$/#/%/@` CreationInfo CSV.

The Database (domain/blocks/database.py) gives you the rows + helpers:
    db.rows                      every staged row (dict: IoList columns + name_in_db, name_in_tagtable,
                                 tagtable, datablocks, matrix_areas, areas_description, diag_*, ...)
    db.by_type("KQ", "KI")       rows by Script Type
    db.by_db("03_FDBACK")        rows that are members of a data block
    db.by_area("AREA 1")         rows in a C&E area
    db.by_tagtable("SAFETY_Contactors")
    db.where(lambda r: ...)      arbitrary predicate
    db.areas()                   distinct C&E areas, in order

The Table (domain/blocks/table.py): t.add(template_type="01", <key>=<value>, ...) per @ row.
- a key matching a template placeholder is emitted as `!!<key>$$` (use the bare block_templates.json
  names, e.g. "02_COM.{db_element}", "NetworkComment", "instanceOf-ESTOP1");
- a list value is the horizontal ITERATOR (written across cells, placed last);
- `template_type` -> the TemplateType column (you decide it; default "01").

--------------------------------------------------------------------------------------------------
EXAMPLE (illustrative - adapt to the real template):

    @builds("02_EM Push Button")
    def build_em_push_button(db: Database) -> Table:
        t = Table("02_EM Push Button")
        for area in db.areas():
            pbs = [r["name_in_db"] for r in db.by_area(area) if r.get("script_type") == "E1/2"]
            t.add(
                template_type="01",
                NetworkComment=f"{area} Emergency Push Buttons",
                **{"00_Commissioning.{db_element}": area},
                **{"instanceOf-00_Push-Button_Input": f"EMPB_{area}"},
                ITERATOR_STRINGS=pbs,                      # horizontal iterator
            )
        return t
--------------------------------------------------------------------------------------------------
"""
from __future__ import annotations

from pipeline3.domain.blocks.database import Database
from pipeline3.domain.blocks.table import Table
from pipeline3.domain.blocks.registry import builds


@builds("00_Only for Commissioning")
def build_00_commissioning(db: Database) -> Table:
    t = Table("00_Only for Commissioning")
    # TODO: your logic
    return t


@builds("02_EM Push Button")
def build_02_em_push_button(db: Database) -> Table:
    t = Table("02_EM Push Button")
    # TODO: your logic
    return t


@builds("03_Zone Cumulative")
def build_03_zone_cumulative(db: Database) -> Table:
    t = Table("03_Zone Cumulative")
    # TODO: your logic
    return t


@builds("04_ESTOP")
def build_04_estop(db: Database) -> Table:
    t = Table("04_ESTOP")
    # TODO: your logic
    return t


@builds("05_Output Feedback")
def build_05_output_feedback(db: Database) -> Table:
    t = Table("05_Output Feedback")
    # TODO: your logic
    return t


@builds("06_Feedback Error")
def build_06_feedback_error(db: Database) -> Table:
    t = Table("06_Feedback Error")
    # TODO: your logic
    return t


@builds("07_Speed Control")
def build_07_speed_control(db: Database) -> Table:
    t = Table("07_Speed Control")
    # TODO: your logic
    return t


@builds("08_Gate Manager")
def build_08_gate_manager(db: Database) -> Table:
    t = Table("08_Gate Manager")
    # TODO: your logic
    return t

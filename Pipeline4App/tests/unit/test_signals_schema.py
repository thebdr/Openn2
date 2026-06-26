"""The signals table schema (domain.signals): shape + a representative signal round-trip."""
import os
import tempfile

from _harness import run, eq, ok
from pipeline4.core.keys import uid
from pipeline4.domain.signals import signals_table

# a small representative slice of the IoList canonical columns (interface_mapping is the AH '|'-list)
_IOLIST = ["functional_unit", "location", "device", "script_type", "bit", "interface_mapping"]


def test_schema_shape():
    t = signals_table(_IOLIST)
    eq(t.columns[0], "uid", "uid is the first column")
    eq(t.columns[1:1 + len(_IOLIST)], _IOLIST, "the raw IoList columns come next, verbatim + in order")
    for json_col in ("type", "datablocks", "matrix_areas", "areas_description", "interface_mapping"):
        ok(json_col in t.json_columns, f"{json_col} is a JSON cell")
    ok("functional_unit" in t.columns and "name_in_db" in t.columns and "plc_binding" in t.columns,
       "raw IoList + enriched (incl. stored plc_binding) columns are all present")
    ok("type_id_resolved" not in t.columns and "type_category" not in t.columns,
       "the flattened type fields are gone - the whole `type` object replaces them")


def test_representative_signal_round_trips():
    t = signals_table(_IOLIST)
    row = t.add(
        functional_unit="=S1", location="+SG1", device="-B1", script_type="DI1/2", bit="I0.0",
        combined_FLD="=S1+SG1-B1", source_cell="NS50!O12",
        interface_mapping=["01", "02"],
        matrix_areas=["AREA 1", "AREA 2"], areas_description=["zone one", "zone two"],
        datablocks=["07_DOOR"], name_in_db="Door Closed SAFE_STATE [ =S1+SG1-B1 ]",
        plc_binding='"07_DOOR"."Door Closed SAFE_STATE [ =S1+SG1-B1 ]"',
        type={"type_id": "DI1/2", "category": "Safety", "channel": "1",
              "db_names": ["07_DOOR"], "in_diagnosis": True},
    )
    eq(row["uid"], uid("=S1+SG1-B1", "DI1/2", "NS50!O12"),
       "uid = content hash of combined_FLD + script_type + source_cell")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "signals.csv")
        t.write_csv(path)
        loaded = signals_table(_IOLIST).read_csv(path)
    r = loaded.rows[0]
    eq(r["datablocks"], ["07_DOOR"], "datablocks is a real list (datablocks[0] is the leftmost db, typed)")
    eq(r["interface_mapping"], ["01", "02"], "the AH interface_mapping is a real list, not a '|' string")
    eq(r["matrix_areas"], ["AREA 1", "AREA 2"], "matrix_areas list round-trips")
    eq(r["areas_description"], ["zone one", "zone two"], "areas_description list (parallel to matrix_areas)")
    eq(r["type"]["in_diagnosis"], True, "the resolved type object is stored + keeps its types")
    eq(r["type"]["db_names"], ["07_DOOR"], "type.db_names round-trips (no re-attach from signal_types)")
    eq(r["plc_binding"], '"07_DOOR"."Door Closed SAFE_STATE [ =S1+SG1-B1 ]"', "plc_binding stored verbatim")
    eq(t.duplicate_uids(), set(), "no duplicate uid")


if __name__ == "__main__":
    import sys
    sys.exit(run("signals_schema", [
        ("schema_shape", test_schema_shape),
        ("representative_signal_round_trips", test_representative_signal_round_trips),
    ]))

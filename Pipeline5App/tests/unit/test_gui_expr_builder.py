"""The ƒx Expression Builder's Tk-free half (gui/expr_builder.py): the SSOT table loader with decoded
JSON cells, the eval-ctx builder (row + _db), the word-before-cursor scan, and the completion pools.
The dialog itself (highlight/lint/preview/popup) is checked scripted + manually."""
import csv
import os
import tempfile

from _harness import run, eq, ok
from pipeline5.gui import expr_builder as eb


def _fixture(d):
    with open(os.path.join(d, "signals.csv"), "w", newline="", encoding="utf-8") as h:
        w = csv.writer(h)
        w.writerow(["uid", "combined_FLD", "type", "datablocks"])
        w.writerow(["u1", "S1", '{"type_id":"KQ","in_diag":"x"}', '["03_FDBACK"]'])
        w.writerow(["u2", "S2", '{"type_id":"KI"}', "[]"])
    with open(os.path.join(d, "db_members.csv"), "w", newline="", encoding="utf-8") as h:
        w = csv.writer(h)
        w.writerow(["uid", "db_name"])
        w.writerow(["m1", "03_FDBACK"])


def test_load_tables_decodes_cells():
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        tables = eb.load_tables(d)
        eq(set(tables), {"signals", "db_members"})
        cols, rows = tables["signals"]
        eq(cols, ["uid", "combined_FLD", "type", "datablocks"])
        eq(rows[0]["type"], {"type_id": "KQ", "in_diag": "x"}, "a JSON object cell decodes")
        eq(rows[0]["datablocks"], ["03_FDBACK"], "a JSON list cell decodes")
        eq(rows[1]["datablocks"], [], "the empty list decodes")
        eq(eb.decode_cell("plain"), "plain", "a plain cell stays a string")
        eq(eb.decode_cell("{broken"), "{broken", "broken JSON stays the raw string")


def test_build_ctx_row_plus_db():
    with tempfile.TemporaryDirectory() as d:
        _fixture(d)
        tables = eb.load_tables(d)
        ctx = eb.build_ctx(tables, "signals", 1)
        eq(ctx["combined_FLD"], "S2", "the chosen row's fields are top-level")
        ok("_db" in ctx and "db_members" in ctx["_db"], "_db carries every table for the data funcs")
        from pipeline5.core import expr
        eq(expr.evaluate("$type.type_id", ctx), "KI", "dotted drill works on the decoded cell")
        eq(expr.evaluate("count(db_members)", ctx), 1, "data funcs see _db")


def test_word_before_and_completions():
    text = "present($com"
    word, start = eb.word_before(text, len(text))
    eq((word, start), ("$com", 8), "the $stem before the cursor")
    cands = eb.completions("$com", ["combined_FLD", "uid"], {})
    eq(cands, ["$combined_FLD"], "column completion")
    cands2 = eb.completions("ext", [], {})
    ok("extract" in cands2, "function completion")
    cands3 = eb.completions("sig", [], {"signals": ([], [])})
    ok("signals" in cands3, "table-name completion")
    eq(eb.completions("", [], {}), [], "no stem, no popup")
    word2, _ = eb.word_before("$a = 3 ", 7)
    eq(word2, "", "cursor after whitespace -> no stem")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_expr_builder", [
        ("load_tables_decodes_cells", test_load_tables_decodes_cells),
        ("build_ctx_row_plus_db", test_build_ctx_row_plus_db),
        ("word_before_and_completions", test_word_before_and_completions),
    ]))

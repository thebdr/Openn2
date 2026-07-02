"""The in-app guide's Tk-free half (gui/helpwin.py): the Markdown-subset parser, the TOC index, the
missing-section machinery, and the help-id ancestor walk. The window/tooltip rendering is a manual +
scripted check."""
from _harness import run, eq, ok
from pipeline4.gui import helpwin


def test_parse_markdown_blocks():
    md = ("# Title\n"
          "\n"
          "A **bold** word and `code` here.\n"
          "## Sub\n"
          "- item one\n"
          "- see [the guide](guide://expressions)\n"
          "```\n"
          "SELECT 1\n"
          "```\n")
    ops = helpwin.parse_markdown(md)
    eq(ops[0], ("h1", "Title"), "the h1")
    eq(ops[1], ("blank", ""), "blank lines survive as spacing")
    kinds = [k for k, _p in ops]
    ok("h2" in kinds and "code_block" in kinds, "h2 + fenced block parsed")
    para = ops[2][1]
    eq(para[1], ("bold", "bold", ""), "inline bold span")
    ok(("code", "code", "") in para, "inline code span")
    bullets = [p for k, p in ops if k == "bullet"]
    eq(len(bullets), 2, "two bullets")
    ok(("link", "the guide", "guide://expressions") in bullets[1], "a link span carries its target")
    code = next(p for k, p in ops if k == "code_block")
    eq(code, "SELECT 1", "the fenced content, verbatim")


def test_parse_markdown_unclosed_fence():
    ops = helpwin.parse_markdown("```\nabc")
    eq(ops, [("code_block", "abc")], "an unclosed fence still renders")


def test_index_and_sections_complete():
    index = helpwin.load_index()
    ok(len(index) >= 6, "the shipped TOC has the six sections")
    ids = [sid for sid, _t in index]
    for sid in ("getting-started", "phase-bar", "files-tab", "database-explorer",
                "expressions", "treatments"):
        ok(sid in ids, f"{sid} indexed")
        ok(helpwin.has_section(sid), f"{sid}.md shipped")
    eq(helpwin.missing_sections(), [], "no authoring TODOs in the shipped guide")


def test_missing_page_names_source():
    page = helpwin.missing_page("no-such-feature", source_hint="pipeline4/gui/phasebar.py")
    ok("No instructions provided" in page, "the user's fallback wording")
    ok("src://pipeline4/gui/phasebar.py" in page, "the source hint becomes the link")
    page2 = helpwin.missing_page("thing")
    ok("src://pipeline4" in page2, "no hint -> the package folder")


def test_help_id_walks_ancestors():
    class Node:
        def __init__(self, master=None):
            self.master = master
    root = Node()
    mid = Node(root)
    leaf = Node(mid)
    eq(helpwin.help_id_of(leaf), None, "nothing attached -> None")
    helpwin.attach(root, "getting-started")
    eq(helpwin.help_id_of(leaf), "getting-started", "the walk reaches the attached ancestor")
    helpwin.attach(mid, "files-tab")
    eq(helpwin.help_id_of(leaf), "files-tab", "the NEAREST attachment wins")
    eq(helpwin.help_id_of(None), None, "no widget -> None")


if __name__ == "__main__":
    import sys
    sys.exit(run("gui_helpwin", [
        ("parse_markdown_blocks", test_parse_markdown_blocks),
        ("parse_markdown_unclosed_fence", test_parse_markdown_unclosed_fence),
        ("index_and_sections_complete", test_index_and_sections_complete),
        ("missing_page_names_source", test_missing_page_names_source),
        ("help_id_walks_ancestors", test_help_id_walks_ancestors),
    ]))

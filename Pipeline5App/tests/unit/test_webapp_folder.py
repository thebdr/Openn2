"""The web application folder writer (phase 650, C-050, contract v1 kind `web/app`): the manifest's header round
trip through the OP5 rules, the resources written byte for byte without a header, the size + SHA-256 binding,
the writer's refusals (all before anything is written), and the never-sweep rule (a leftover stays, listed)."""
import hashlib
import os
import tempfile

from _harness import run, eq, ok, raises
from pipeline5.systems.plc_based.siemens_s7 import openn_header as header
from pipeline5.systems.plc_based.siemens_s7 import webapp_folder as webapp

_FILES = [("index.html", b"<!doctype html><title>safety</title>\n"),
          ("app.js", "console.log('é');\n".encode("utf-8")),
          ("plant.json", b'{"schema": 1}'),
          ("img/plant.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"/>')]


def _app_dir(root, app="safety"):
    return os.path.join(root, "n1", header.WEB_APPS, app)


def test_manifest_header_round_trip():
    header.begin_run("20261028-150000-c050")
    with tempfile.TemporaryDirectory() as root:
        res = webapp.write_web_app(_app_dir(root), "safety", _FILES, plc="n1", default_page="index.html",
                                   source="plant model + Shared template")
        h = header.read_header(res["manifest"])
        eq((h.status, h.get("kind"), h.get("schema"), h.get("producer"), h.get("run"), h.get("plc"),
            h.get("target"), h.get("name")),
           ("ok", "web/app", "1", "Pipeline5 5.0 (phase 650)", "20261028-150000-c050", "n1",
            "Web applications/safety", "safety"), f"the manifest header: {h.problems}")
        text = open(res["manifest"], encoding="utf-8", newline="").read()
        ok(text.startswith("#!openn\r\n") and "\r\nname,media_type,size,sha256,visibility,default_page\r\n" in text,
           "header first, then the column row (CRLF)")
        rows = webapp.read_manifest(res["manifest"])
        eq([(r["name"], r["media_type"], r["visibility"], r["default_page"]) for r in rows],
           [("index.html", "text/html", "public", "yes"), ("app.js", "application/javascript", "public", ""),
            ("plant.json", "application/json", "public", ""), ("img/plant.svg", "image/svg+xml", "public", "")],
           "one row per resource, in order, one default page")
        eq(rows[1]["size"], str(len(_FILES[1][1])), "size = the byte count (UTF-8, not characters)")
        eq(rows[1]["sha256"], hashlib.sha256(_FILES[1][1]).hexdigest())


def test_resources_are_byte_for_byte_and_header_free():
    with tempfile.TemporaryDirectory() as root:
        res = webapp.write_web_app(_app_dir(root), "safety", _FILES, plc="n1", default_page="index.html")
        for name, data in _FILES:
            path = os.path.join(res["dir"], *name.split("/"))
            eq(open(path, "rb").read(), data, f"{name} byte for byte")
            ok(b"#!openn" not in open(path, "rb").read(), f"{name} carries no header")
        eq(webapp.verify(res["dir"]), [], "the folder is what its manifest says")
        with open(os.path.join(res["dir"], "app.js"), "r+b") as handle:   # same size, other bytes
            handle.write(b"C")
        problems = webapp.verify(res["dir"])
        ok(len(problems) == 1 and problems[0].startswith("app.js:"), problems)
        os.remove(os.path.join(res["dir"], "plant.json"))
        ok("plant.json: missing" in webapp.verify(res["dir"]), "a missing resource is reported")


def test_refusals_write_nothing():
    with tempfile.TemporaryDirectory() as root:
        target = _app_dir(root)
        raises(ValueError, lambda: webapp.write_web_app(target, "safety", _FILES, plc="n1", default_page="nope.html"))
        raises(ValueError, lambda: webapp.write_web_app(target, "safety", _FILES + [("x.exe", b"")], plc="n1",
                                                        default_page="index.html"))
        raises(ValueError, lambda: webapp.write_web_app(target, "safety", _FILES + [("../up.js", b"")], plc="n1",
                                                        default_page="index.html"))
        raises(ValueError, lambda: webapp.write_web_app(target, "safety", _FILES + [("APP.JS", b"")], plc="n1",
                                                        default_page="index.html"))
        raises(ValueError, lambda: webapp.write_web_app(target, "safety", [("webapp.manifest.csv", b"")]
                                                        + _FILES, plc="n1", default_page="index.html"))
        raises(ValueError, lambda: webapp.write_web_app(target, "safety", _FILES, plc="n1", default_page="index.html",
                                                        visibility="secret"))
        raises(ValueError, lambda: webapp.write_web_app(_app_dir(root, "my app"), "my app", _FILES, plc="n1",
                                                        default_page="index.html"))
        raises(ValueError, lambda: webapp.write_web_app(target, "other", _FILES, plc="n1", default_page="index.html"))
        ok(not os.path.exists(target), "every refusal comes before the first write")


def test_leftovers_are_kept_and_listed():
    with tempfile.TemporaryDirectory() as root:
        target = _app_dir(root)
        webapp.write_web_app(target, "safety", _FILES, plc="n1", default_page="index.html")
        res = webapp.write_web_app(target, "safety", _FILES[:2], plc="n1", default_page="index.html")
        eq(res["leftovers"], ["img/plant.svg", "plant.json"], "an older run's files stay on disk, listed")
        eq([r["name"] for r in webapp.read_manifest(res["manifest"])], ["index.html", "app.js"],
           "the manifest lists only this generation's resources")
        eq(webapp.verify(target), [], "and they verify")


if __name__ == "__main__":
    import sys
    sys.exit(run("webapp_folder", [
        ("manifest_header_round_trip", test_manifest_header_round_trip),
        ("resources_are_byte_for_byte_and_header_free", test_resources_are_byte_for_byte_and_header_free),
        ("refusals_write_nothing", test_refusals_write_nothing),
        ("leftovers_are_kept_and_listed", test_leftovers_are_kept_and_listed),
    ]))

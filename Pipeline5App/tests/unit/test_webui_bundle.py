"""The shipped web diagnosis page (C-050 M3, Shared/Templates/WebServer/SafetyDiagnosis) as phase 650 bundles it:
the files it ships, no external URL (the CPU serves everything), the Web API methods it can send (read-only: the
anonymous login, PlcProgram.Read / Browse - never a write), every text set as text (no HTML sink), the size budget,
the mock simulator loaded only on a local host, the plant.json keys it reads all present in build_plant's
output, and the drawing's positions export read back by the loader (M5). The page's behaviour itself is checked in a browser against the mock (evidence C-050 M3)."""
import json
import os
import re

from _harness import run, eq, ok
from pipeline5 import config
from pipeline5.systems.plc_based.siemens_s7.safety import webui_model as model
from pipeline5.systems.plc_based.siemens_s7.safety import webui_project as project
import test_webui_model as fixture

PAGE = ("index.html", "app.js", "app.css", "icons.svg")
PAGE_BUDGET = 120 * 1024          # the plan's budget for what every browser loads
MOCK_BUDGET = 24 * 1024           # the dev preview's simulator, loaded only on a local host
READ_ONLY = {"Api.Login", "Api.Logout", "PlcProgram.Read", "PlcProgram.Browse"}
NAMESPACES = {"http://www.w3.org/2000/svg"}


def _files():
    return dict(project.bundle(config.WEBAPP_TEMPLATE_DIR))


def _text(files, name):
    return files[name].decode("utf-8")


def test_the_files_it_ships():
    files = _files()
    eq(sorted(files), ["app.css", "app.js", "icons.svg", "index.html", "mock.js"], "the page + the dev simulator")
    js = _text(files, "app.js")
    parts = re.findall(r"^// --- (js/[^ ]+) ---$", js, re.M)
    eq(parts, sorted(parts), "app.js = js/*.js in name order")
    ok(parts[0] == "js/00_util.js" and parts[-1] == "js/99_boot.js", "the helpers first, the boot last")
    html = _text(files, "index.html")
    eq(re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', html), ["app.js"], "index.html loads app.js only")
    eq(re.findall(r'<link\b[^>]*\bhref="([^"]+)"', html), ["app.css"], "and app.css only")
    ok("Read-only diagnostic display, not a safety function." in html, "the footer says what the page is not")
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html)
    ok(csp and "connect-src 'self'" in csp.group(1) and "script-src 'self'" in csp.group(1), "same-origin only")


def test_no_external_url():
    files = _files()
    for name, data in files.items():
        text = data.decode("utf-8")
        urls = set(re.findall(r"(?i)\b(?:https?:)?//[a-z0-9-]+(?:\.[a-z0-9-]+)+[^\s\"'<>)]*", text)) - NAMESPACES
        eq(sorted(urls), [], f"{name}: no URL leaves the CPU")
        ok(not re.search(r"@import|url\(\s*['\"]?(?:https?:)?//", text), f"{name}: no remote CSS resource")


def test_read_only_web_api_methods():
    files = _files()
    for name in ("app.js", "mock.js"):
        text = _text(files, name)
        methods = set(re.findall(r"\b(?:Api|PlcProgram|Plc|WebApp|Files|DataLogs|Alarms|Project|Modules|Syslog|"
                                 r"Redundancy|Failsafe|DiagnosticBuffer)\.[A-Z][A-Za-z]+\b", text))
        ok(methods <= READ_ONLY, f"{name} names only {sorted(READ_ONLY)}: {sorted(methods - READ_ONLY)}")
    allow = re.search(r"var READ_ONLY = \{([^}]*)\}", _text(files, "app.js"))
    ok(allow, "the client's method allowlist")
    eq(set(re.findall(r'"([A-Za-z]+\.[A-Za-z]+)": true', allow.group(1))), READ_ONLY, "the allowlist is the read set")
    ok('password: ""' in _text(files, "app.js"), "the anonymous login's empty password - no secret in the page")


def test_texts_are_text():
    files = _files()
    sinks = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function",
             "setAttribute(\"style\"", ".style.", "javascript:")
    for name in ("app.js", "mock.js", "index.html"):
        text = _text(files, name)
        eq([s for s in sinks if s in text], [], f"{name}: no HTML or code sink")


def test_size_budget():
    files = _files()
    page = sum(len(files[name]) for name in PAGE)
    ok(page <= PAGE_BUDGET, f"the page is {page} bytes (budget {PAGE_BUDGET})")
    ok(len(files["mock.js"]) <= MOCK_BUDGET, f"mock.js is {len(files['mock.js'])} bytes (budget {MOCK_BUDGET})")


def test_the_mock_only_on_a_local_host():
    files = _files()
    js, html = _text(files, "app.js"), _text(files, "index.html")
    ok("mock.js" not in html, "index.html never loads the simulator")
    eq(js.count('loadScript("mock.js")'), 1, "one place loads it")
    guard = re.search(r"var LOCAL = \[(.*?)\];", js)
    ok(guard, "the local-host list")
    eq(sorted(re.findall(r'"([^"]+)"', guard.group(1))), sorted(["localhost", "127.0.0.1", "[::1]", "::1"]),
       "loopback names only - never a CPU address")
    ok("SD.mockWanted() ? loadScript" in js and "LOCAL.indexOf(location.hostname) >= 0" in js, "gated on the host")
    ok("SIMULATED DATA" in js, "a mock page says so")


def _part(js, name):
    """One js/ file's text inside app.js (between its `// --- js/... ---` line and the next)."""
    return re.search(r"^// --- %s ---$(.*?)(?=^// --- js/|\Z)" % re.escape(name), js, re.M | re.S).group(1)


def test_the_plant_keys_it_reads_exist():
    plant, _findings = fixture._build()
    plant = json.loads(model.to_json(plant))
    js = _text(_files(), "app.js")
    top = set(re.findall(r"\bplant\.([a-z_]+)\b", js)) - {"json"}
    eq(sorted(top - set(plant)), [], "every plant.<key> the page reads is in plant.json")
    for key, rx, text in (("polling", r"\bpolling\.([a-z_]+)\b", js), ("diag", r"\b(?:plant|this)\.diag\.([a-z_]+)\b", js),
                          ("layout", r"\blayout\.([a-z_]+)\b", js),
                          ("custom_data", r"\bcfg\.([a-z_]+)\b", _part(js, "js/66_custom.js"))):
        used = set(re.findall(rx, text))
        ok(used, f"the page reads {key}")
        eq(sorted(used - set(plant[key])), [], f"every {key}.<key> the page reads is in plant.json")
    for kind in plant["kinds"]:
        ok(re.search(r'<symbol id="%s"' % re.escape(kind["icon"]), _text(_files(), "icons.svg")),
           f"icons.svg has the {kind['kind']} icon {kind['icon']!r}")


def test_the_positions_round_trip():
    """[[C-050]] M5: the drawing's edit mode exports webui_positions.csv (SD.positionsCsv) - its header is the
    loader's columns, CRLF, csv quoting - and such a file loads back through config.load_webui_positions exactly.
    The browser side (the export of the unedited positions byte-identical to the file 650 read) is evidence."""
    import tempfile
    from pipeline5.config import loaders
    js = _part(_text(_files(), "app.js"), "js/55_drawing.js")
    head = re.search(r'var rows = \[\[([^\]]*)\]\];', js)
    ok(head, "the exporter's header row")
    eq(tuple(re.findall(r'"([a-z]+)"', head.group(1))), loaders.WEBUI_POSITION_COLUMNS, "the loader's columns")
    ok('.join("\\r\\n")' in js and "toFixed(1)" in js, "CRLF rows, one decimal")
    text = ('kind,fld,x,y\r\ncontactor,=LB-AE01-Q32001/Q32002,1205.6,405.2\r\n'
            'estop,"=ES-0040, moved",1080.4,2280.4\r\n')
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "webui_positions.csv")
        open(path, "w", newline="", encoding="utf-8").write(text)
        rows = config.load_webui_positions("webui/webui_positions.csv", path=path)
    eq(rows, [{"kind": "contactor", "fld": "=LB-AE01-Q32001/Q32002", "x": 1205.6, "y": 405.2},
              {"kind": "estop", "fld": "=ES-0040, moved", "x": 1080.4, "y": 2280.4}], "read back as written")
    image = set(re.findall(r"\bimage\.([a-z_]+)\b", js))
    ok(image, "the drawing reads plant.layout.image")
    eq(sorted(image - {"file", "width", "height", "view_box"}), [], "only what 650 measures (webui_project.measure)")


def test_every_kind_icon_is_drawn():
    svg = _text(_files(), "icons.svg")
    for kind in config.load_webui_kinds():
        ok(f'<symbol id="{kind["icon"]}"' in svg, f"device_kinds.csv {kind['kind']}: icons.svg#{kind['icon']}")


if __name__ == "__main__":
    import sys
    sys.exit(run("webui_bundle", [
        ("the_files_it_ships", test_the_files_it_ships),
        ("no_external_url", test_no_external_url),
        ("read_only_web_api_methods", test_read_only_web_api_methods),
        ("texts_are_text", test_texts_are_text),
        ("size_budget", test_size_budget),
        ("the_mock_only_on_a_local_host", test_the_mock_only_on_a_local_host),
        ("the_plant_keys_it_reads_exist", test_the_plant_keys_it_reads_exist),
        ("the_positions_round_trip", test_the_positions_round_trip),
        ("every_kind_icon_is_drawn", test_every_kind_icon_is_drawn),
    ]))

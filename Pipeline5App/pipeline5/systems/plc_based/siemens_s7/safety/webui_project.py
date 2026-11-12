"""Phase 650 - generate the safety web diagnosis app into the OP5 workspace (C-050):
`<PLC>/Web applications/<app>/` = the fixed app (`Shared/Templates/WebServer/SafetyDiagnosis`, the same on every
project) + the project's `plant.json` (+ the plant drawing when the project has one) + `webapp.manifest.csv`.

- **The fixed app.** The template folder's `js/**/*.js` are joined into ONE `app.js` and its `css/**/*.css` into
  ONE `app.css`, in path order (name the files to order them - `00_rpc.js` before `10_poller.js`); every other
  file is copied as it is (`*.md` notes excepted). No build tool, no CDN: what the template holds is what the CPU
  serves.
- **The project's data.** `plant.json` = `webui_model.build_plant` over the Database and the webui config
  (device_kinds.csv, member_states.csv, webui_params.yaml, the positions file); the drawing (`layout.drawing`, an
  optional .svg / .png / .jpg in the config tiers) ships as `plant.<ext>` with its size measured here (SVG
  viewBox / width / height, the PNG IHDR, the JPEG SOF - stdlib only).
- **The folder.** `webapp_folder.write_web_app` writes the resources byte for byte and the headered manifest; it
  never sweeps (an older run's file stays, listed in the result and noted by OP5).

A config file that does not load, or a template folder without its default page, is a FAIL and nothing is
written. Called by phase 650 (`run_diagnosis` in src://pipeline5/systems/plc_based/siemens_s7/safety/main.py)
after the 600 build.
"""
from __future__ import annotations

import os
import re
import struct

from pipeline5 import config
from pipeline5.findings.finding import Finding
from pipeline5.systems.plc_based.siemens_s7 import openn_header as header
from pipeline5.systems.plc_based.siemens_s7 import webapp_folder
from pipeline5.systems.plc_based.siemens_s7.output_layout import LAYOUT
from pipeline5.systems.plc_based.siemens_s7.safety import webui_model

PHASE = 650
PLANT_FILE = "plant.json"
APP_JS, APP_CSS = "app.js", "app.css"
_SVG_ROOT = re.compile(rb"<svg\b[^>]*>", re.S)
_ATTR = r'\b{}\s*=\s*["\']([^"\']*)["\']'


def _f(type: str, severity: str, detail: str, location: str = "") -> Finding:
    return Finding(phase=PHASE, type=type, severity=severity, detail=detail, location=location)


# --- the fixed app ------------------------------------------------------------------------------------------ #
def bundle(template_dir: str) -> list:
    """The fixed app's resources [(name, bytes)]: every template file except js/ and css/ as it is (`*.md`
    and dot-files skipped), then `app.css` and `app.js` = the css/ and js/ files joined in path order, each
    after a one-line comment naming it."""
    plain, joined = [], {"css": [], "js": []}
    for dirpath, dirs, files in os.walk(template_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith(".") or name.lower().endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, template_dir).replace(os.sep, "/")
            top = rel.split("/")[0]
            if top in joined and "/" in rel and name.lower().endswith("." + top):
                joined[top].append((rel, path))
            else:
                plain.append((rel, open(path, "rb").read()))
    out = list(plain)
    for kind, target, note in (("css", APP_CSS, "/* --- {} --- */"), ("js", APP_JS, "// --- {} ---")):
        if joined[kind]:
            parts = [note.format(rel) + "\n" + open(path, encoding="utf-8-sig").read().rstrip("\n") + "\n"
                     for rel, path in sorted(joined[kind])]
            out.append((target, "\n".join(parts).encode("utf-8")))
    names = [name.lower() for name, _ in out]
    if PLANT_FILE in names or len(names) != len(set(names)):
        raise ValueError(f"the web app template {template_dir} holds {PLANT_FILE} or a file the bundle writes "
                         f"({APP_CSS} / {APP_JS}) - they are generated")
    return out


# --- the drawing -------------------------------------------------------------------------------------------- #
def _number(text):
    match = re.match(r"^\s*([0-9]*\.?[0-9]+)\s*(px)?\s*$", text or "")
    return float(match.group(1)) if match else None


def measure(path: str) -> dict:
    """{width, height, view_box} of an SVG (viewBox, else width/height), a PNG or a JPEG; ValueError when the
    file's size cannot be read."""
    data = open(path, "rb").read()
    extension = os.path.splitext(path)[1].lower()
    if extension == ".svg":
        root = _SVG_ROOT.search(data)
        if not root:
            raise ValueError("no <svg> root element")
        tag = root.group(0).decode("utf-8", "replace")
        box = re.search(_ATTR.format("viewBox"), tag)
        width = _number((re.search(_ATTR.format("width"), tag) or [None, ""])[1])
        height = _number((re.search(_ATTR.format("height"), tag) or [None, ""])[1])
        if box:
            values = [float(v) for v in re.split(r"[\s,]+", box.group(1).strip()) if v]
            if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
                raise ValueError(f"viewBox {box.group(1)!r} is not four numbers with a positive size")
            return {"width": width or values[2], "height": height or values[3], "view_box": values}
        if width and height:
            return {"width": width, "height": height, "view_box": [0, 0, width, height]}
        raise ValueError("neither a viewBox nor a width and height")
    if extension == ".png":
        if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            raise ValueError("not a PNG file")
        width, height = struct.unpack(">II", data[16:24])
    elif extension in (".jpg", ".jpeg"):
        if data[:2] != b"\xff\xd8":
            raise ValueError("not a JPEG file")
        pos, width, height = 2, None, None
        while pos + 9 < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
                pos += 1 if marker == 0xFF else 2
                continue
            length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
                break
            pos += 2 + length
        if not width or not height:
            raise ValueError("no JPEG frame header")
    else:
        raise ValueError(f"unsupported drawing type {extension!r} (svg, png, jpg)")
    return {"width": float(width), "height": float(height), "view_box": [0, 0, float(width), float(height)]}


# --- the generation ----------------------------------------------------------------------------------------- #
def _plc_ip(database, plc: str) -> str:
    for row in (database["signals"] if "signals" in database else []):
        if str(row.get("profinet_name") or "").strip() == plc and str(row.get("profinet_ip") or "").strip():
            return str(row["profinet_ip"]).strip()
    return ""


def project(database, out_dir: str | None = None, template_dir: str | None = None) -> dict:
    """Write the app folder from the built `database`. Returns {'dir', 'manifest', 'resources', 'leftovers',
    'counts', 'bytes', 'findings'}; 'dir' is None when a FAIL stopped it (nothing written)."""
    result = {"dir": None, "manifest": None, "resources": [], "leftovers": [], "counts": {}, "bytes": 0,
              "findings": []}
    findings = result["findings"]
    try:
        kinds = config.load_webui_kinds()
        member_states = config.load_webui_member_states()
        params = config.load_webui_params()
        positions = config.load_webui_positions(params["layout"]["positions"])
    except (OSError, ValueError) as error:
        findings.append(_f("webui_config_invalid", "FAIL", f"the web app config does not load: {error}",
                           "webui/"))
        return result
    template_dir = template_dir or config.WEBAPP_TEMPLATE_DIR
    default_page = str(params["app"]["default_page"])
    if not os.path.isfile(os.path.join(template_dir, *default_page.split("/"))):
        findings.append(_f("webui_template_missing", "FAIL",
                           f"the web app template has no {default_page}: {template_dir}", template_dir))
        return result
    try:
        files = bundle(template_dir)
    except (OSError, ValueError, UnicodeDecodeError) as error:
        findings.append(_f("webui_template_invalid", "FAIL", f"the web app template cannot be bundled: {error}",
                           template_dir))
        return result

    drawing, drawing_file = None, None
    drawing_path = config.find_webui_drawing(str(params["layout"]["drawing"]))
    if drawing_path:
        extension = os.path.splitext(drawing_path)[1].lower()
        try:
            drawing = {"file": "plant" + extension, **measure(drawing_path)}
            drawing_file = ("plant" + extension, open(drawing_path, "rb").read())
        except (OSError, ValueError) as error:
            findings.append(_f("webui_drawing_unreadable", "WARN",
                               f"the plant drawing {drawing_path} is not used - its size cannot be read: {error}",
                               drawing_path))

    plc = LAYOUT.plc_folder(database, required=out_dir is None) or ""
    app = str(params["app"]["name"])
    meta = {"run": header.current_run(), "producer": header.producer(PHASE), "project": header.project_code(),
            "generated": header.generated_now()}
    plant, model_findings = webui_model.build_plant(
        database, kinds, member_states, params, positions=positions, drawing=drawing, meta=meta,
        plc={"station": plc, "ip": _plc_ip(database, plc)})
    findings += model_findings
    files.append((PLANT_FILE, webui_model.to_json(plant)))
    if drawing_file:
        files.append(drawing_file)
    first = [f for f in files if f[0] == default_page]
    files = first + [f for f in files if f[0] != default_page]
    out_dir = out_dir or LAYOUT.web_app_dir(plc, app)
    written = webapp_folder.write_web_app(
        out_dir, app, files, plc=plc, default_page=default_page, visibility=str(params["app"]["visibility"]),
        phase=PHASE, source=f"plant model + {os.path.basename(template_dir)} template")
    if written["leftovers"]:
        findings.append(_f("webui_leftovers", "INFO",
                           f"{len(written['leftovers'])} file(s) of an older run stay in the app folder - not in the "
                           f"manifest, never uploaded: {', '.join(written['leftovers'][:5])}", out_dir))
    result.update(dir=written["dir"], manifest=written["manifest"], resources=written["resources"],
                  leftovers=written["leftovers"], counts=plant["counts"],
                  bytes=sum(int(r["size"]) for r in written["resources"]))
    return result

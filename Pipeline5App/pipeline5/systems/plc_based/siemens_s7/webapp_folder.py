"""Phase 650 - write ONE CPU web application folder of the OP5 workspace (C-050, contract v1 kind `web/app`).

`<PLC>/Web applications/<app>/` holds the app's resources BYTE FOR BYTE - a browser is served exactly what is
written, so no resource carries a `#!openn` header - and `webapp.manifest.csv`, the folder's one headered file:
the header (`kind: web/app`, `target: Web applications/<app>`, `name: <app>`), then one row per resource -
`name, media_type, size, sha256, visibility, default_page` - which binds each resource to this generation by its
size and SHA-256 (OP5's `WebAppManifest.VerifyResources` refuses a missing or changed one, its catalog lists the
resources Ignored and a file the manifest does not list as "never uploaded").

The folder is never swept: a file an older run left beside the manifest stays on disk (OP5 notes it, nothing
uploads it) - the generation's rule for every workspace folder. Pure file writing: what the app contains is the
caller's (src://pipeline5/systems/plc_based/siemens_s7/safety/webui_project.py).
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re

from pipeline5.systems.plc_based.siemens_s7 import openn_header as header

PHASE = 650
MANIFEST_COLUMNS = ("name", "media_type", "size", "sha256", "visibility", "default_page")
VISIBILITIES = ("public", "protected")
# the Web API resource media types by extension - a resource of another extension is refused (the CPU serves
# the type the manifest names, so a guess would be served wrong)
MEDIA_TYPES = {".html": "text/html", ".htm": "text/html", ".js": "application/javascript", ".css": "text/css",
               ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
               ".jpeg": "image/jpeg", ".ico": "image/x-icon", ".txt": "text/plain", ".woff2": "font/woff2"}
_APP_NAME_RX = re.compile(r"^[A-Za-z0-9_-]+$")


def media_type(name: str) -> str:
    """The media type of a resource name, from its extension (MEDIA_TYPES); an unknown one is an error."""
    extension = os.path.splitext(name)[1].lower()
    if extension not in MEDIA_TYPES:
        raise ValueError(f"web application resource {name!r}: no media type for {extension or 'no extension'!r} "
                         f"(known: {', '.join(sorted(MEDIA_TYPES))})")
    return MEDIA_TYPES[extension]


def _check_name(name: str) -> str:
    clean = str(name or "").replace("\\", "/")
    parts = clean.split("/")
    if not clean or clean.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"web application resource {name!r}: a plain path inside the app folder is needed")
    if clean.lower() == header.WEBAPP_MANIFEST:
        raise ValueError(f"web application resource {name!r}: the manifest's own name")
    return clean


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_rows(files, default_page: str, visibility: str) -> list:
    """The manifest's data rows for `files` = [(name, bytes)] in order: [{name, media_type, size, sha256,
    visibility, default_page}] ('yes' on the one default page). Every check the writer applies: plain unique
    names, a known media type, a known visibility, the default page among the files."""
    if visibility not in VISIBILITIES:
        raise ValueError(f"web application visibility {visibility!r} (expected {' or '.join(VISIBILITIES)})")
    rows, seen = [], set()
    for name, data in files:
        clean = _check_name(name)
        if clean.lower() in seen:
            raise ValueError(f"web application resource {clean!r} given twice")
        seen.add(clean.lower())
        rows.append({"name": clean, "media_type": media_type(clean), "size": str(len(data)), "sha256": sha256(data),
                     "visibility": visibility, "default_page": "yes" if clean == default_page else ""})
    if default_page not in {row["name"] for row in rows}:
        raise ValueError(f"web application default page {default_page!r} is not one of its resources")
    return rows


def render_manifest(rows: list, values: dict) -> str:
    """The manifest text: the `#!openn` header, the column row, the data rows (csv, CRLF)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(MANIFEST_COLUMNS)
    for row in rows:
        writer.writerow([row[c] for c in MANIFEST_COLUMNS])
    return header.stamp_csv(buffer.getvalue(), values)


def write_web_app(out_dir: str, app_name: str, files, *, plc: str, default_page: str, visibility: str = "public",
                  phase: int = PHASE, source: str | None = None) -> dict:
    """Write the app folder `out_dir` (= `<PLC>/Web applications/<app_name>`): every resource of `files` =
    [(name, bytes)] byte for byte (sub-folders created), then `webapp.manifest.csv` with its header. All checks
    run before anything is written. Returns {'dir', 'manifest', 'resources': the manifest rows, 'leftovers':
    files on disk the manifest does not list (kept - never swept)}."""
    if not _APP_NAME_RX.match(str(app_name or "")):
        raise ValueError(f"web application name {app_name!r}: letters, digits, '_' or '-' only")
    if os.path.basename(os.path.normpath(out_dir)) != app_name:
        raise ValueError(f"web application folder {out_dir!r} is not named after the app {app_name!r}")
    files = list(files)
    rows = manifest_rows(files, default_page, visibility)
    values = header.fields("web/app", phase, plc=plc, target=f"{header.WEB_APPS}/{app_name}", name=app_name,
                           source=source)
    text = render_manifest(rows, values)
    os.makedirs(out_dir, exist_ok=True)
    for (_name, data), row in zip(files, rows):
        path = os.path.join(out_dir, *row["name"].split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)
    manifest = os.path.join(out_dir, header.WEBAPP_MANIFEST)
    with open(manifest, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    listed = {row["name"].lower() for row in rows} | {header.WEBAPP_MANIFEST}
    leftovers = sorted(os.path.relpath(os.path.join(dp, f), out_dir).replace(os.sep, "/")
                       for dp, _dirs, names in os.walk(out_dir) for f in names
                       if os.path.relpath(os.path.join(dp, f), out_dir).replace(os.sep, "/").lower() not in listed)
    return {"dir": out_dir, "manifest": manifest, "resources": rows, "leftovers": leftovers}


def read_manifest(path: str) -> list:
    """The data rows of a written manifest (the header skipped) - [{column: value}]; for checks and tests."""
    with open(path, encoding="utf-8", newline="") as handle:
        text = header.strip_header(handle.read())
    return list(csv.DictReader(io.StringIO(text)))


def verify(app_dir: str) -> list:
    """The OP5 check, PL5-side: every manifest row's file exists with its size and SHA-256. Returns the problems
    ([] = the folder is what its manifest says)."""
    problems = []
    for row in read_manifest(os.path.join(app_dir, header.WEBAPP_MANIFEST)):
        path = os.path.join(app_dir, *row["name"].split("/"))
        if not os.path.isfile(path):
            problems.append(f"{row['name']}: missing")
            continue
        data = open(path, "rb").read()
        if str(len(data)) != row["size"] or sha256(data) != row["sha256"]:
            problems.append(f"{row['name']}: {len(data)} bytes, sha256 {sha256(data)[:12]}... - not the manifest's "
                            f"{row['size']} bytes, {row['sha256'][:12]}...")
    return problems

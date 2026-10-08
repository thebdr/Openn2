"""The `#!openn … #!end` header - what every file PL5 hands to OP5 opens with (contract v1 §3), and the
run id + workspace config that go with it (§3.4, §6.2).

Chapter: how a BuilderData file says what it is. OP5 never guesses a kind from a file name, an extension or
a folder when a header is present: the header declares the `kind` (the §2 taxonomy id), the per-kind
`schema` (hardware csvs continue the format-2 numbering, everything else starts at 1), the `producer`
(`Pipeline5 <version> (phase NNN)`), the `generated` time (UTC, ISO 8601), the `run` id of the generation
that wrote the file, the `project` code, and - for a file under a PLC - the `plc` and the `target` TIA
folder, which MUST agree with where the file sits (a mismatch is an error on the OP5 side, not a hint).

One block, three wrappings (§3.3): csv lines as they are (`#` is the csv comment char; OP5 undoes Excel's
trailing-delimiter padding and line quoting, so a value must not END with the delimiter), XML as the first
comment after the declaration (`--` is illegal inside an XML comment - written `- -`), text sources with
every line prefixed `//`; a binary file (PLCTags.xlsx) carries the csv form in a `<file>.openn` sidecar.
The workspace itself has a header too - `.openn/workspace.openn.config` (`contract`, `project`, `producer`,
`generated`, `run`, `plcs`, `templates`; no kind).

THE RUN ID (§6.2, user decision 2026-10-08): one fresh id per GENERATION = one button press - Run-all is
one id for every phase of its chain, a single phase button mints its own. The host mints it and hands it
in through `PhaseContext.run`; the Siemens run-plan adopts it (`begin_run`) before the first write, every
writer stamps it (`current_run`), and the workspace config carries it. A file whose run differs from the
workspace's is a leftover of an older generation: OP5 lists it as Stale and never imports it - this
replaces a sweep. So after a lone phase button the other phases' files are Stale until regenerated; a
headless caller (the parity oracle, a test) gets a lazily minted id.

Place in the flow: every BuilderData writer of this package renders its header here
(src://pipeline5/systems/plc_based/siemens_s7/hardware_csv_export.py, globaldb_xml_emitter.py,
fc_xml_emitter.py, scl_emitter.py, interface_scl_emitter.py, creation_info_csv.py, plctags_xlsx_writer.py,
safety/opc_diagnosis_scl.py); the workspace config is written by the layout at the start of a generation
(src://pipeline5/systems/plc_based/siemens_s7/output_layout.py `begin_generation`, called from the
run-plan handlers in src://pipeline5/systems/plc_based/siemens_s7/safety/main.py). The parser half
(`parse_directives`, `read_header`) mirrors OP5's reference implementation
(`Openn5App/00_Contract/OpennHeader.cs`) for the round-trip tests and the parity oracle - the spec
(Shared/PL5_OP5_contract.md §3) and the two implementations change together.
"""
from __future__ import annotations

import datetime
import os
import re
import secrets
from dataclasses import dataclass, field

from pipeline5 import __version__

CONTRACT = 1                      # the contract version this producer writes against
MARKER = "#!"
OPEN = "#!openn"
END = "#!end"
LEGACY_FORMAT = "format"          # the retired `#!format=N` tag (OP5 reads it as Legacy)
SIDECAR_SUFFIX = ".openn"

# The workspace shape vocabulary (contract §4) - the TIA folder names a header's `target` names.
HARDWARE_FOLDER = "Devices & networks"
TEMPLATES_FOLDER = "Templates"
PROGRAM_BLOCKS = "Program blocks"
PLC_TAGS = "PLC tags"
PLC_DATA_TYPES = "PLC data types"
CONFIG_FOLDER = ".openn"
CONFIG_FILE = "workspace.openn.config"
RESERVED_ROOT_FOLDERS = frozenset({CONFIG_FOLDER, ".vci", HARDWARE_FOLDER, TEMPLATES_FOLDER})

# kind id -> the schema this producer writes (§2): the hardware csvs continue the format-2 numbering.
SCHEMAS = {
    "hw/device-types": 1, "hw/stations": 2, "hw/modules": 2,
    "sw/udt": 1, "sw/tag-table": 1, "sw/data-block": 1, "sw/instance-db": 1, "sw/block-gen": 1,
    "sw/code-block": 1, "sw/source": 1, "sw/block-template": 1,
    "doc/plc-tags-workbook": 1, "doc/other": 1,
}
REQUIRED = ("kind", "schema", "producer", "generated")
WORKSPACE_REQUIRED = ("contract", "producer", "generated")
KNOWN_KEYS = ("kind", "schema", "producer", "generated", "run", "project", "plc", "target", "name",
              "source", "id", "depends", "comment", "contract", "plcs", "templates")
# the key order a rendered header uses (file keys first, then the workspace-config keys)
KEY_ORDER = ("kind", "contract", "schema", "producer", "generated", "run", "project", "plcs", "templates",
             "plc", "target", "name", "source", "id", "depends", "comment")
_KEY_RX = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_EOL = "\r\n"


# --- the clock + the run id ---------------------------------------------------------------------- #
def clock() -> datetime.datetime:
    """Now, UTC - a module attribute so a test can pin it."""
    return datetime.datetime.now(datetime.timezone.utc)


def generated_now() -> str:
    """The `generated` value: ISO 8601, UTC `Z`, whole seconds (what OP5's writer renders too)."""
    return clock().strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id(now: datetime.datetime | None = None) -> str:
    """A fresh run id: `YYYYMMDD-HHMMSS-xxxx` (UTC time + 4 hex digits - readable, unique enough)."""
    now = now or clock()
    return f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


_RUN: str | None = None            # the id of the generation this process is writing (None: not begun)


def begin_run(run_id: str | None = None) -> str:
    """Begin a generation: adopt the host's id (one per button press) or mint one. Returns the run id."""
    global _RUN
    _RUN = str(run_id).strip() if run_id else new_run_id()
    return _RUN


def current_run() -> str:
    """The run id every writer stamps - begun by the run-plan, or minted lazily for a headless caller."""
    return _RUN or begin_run()


def producer(phase: int | None = None) -> str:
    """`Pipeline5 <version> (phase NNN)` - the tool, its version, the phase that wrote the file."""
    return f"Pipeline5 {__version__}" + (f" (phase {phase})" if phase else "")


def project_code() -> str:
    """The active project's `project_code` ('' when the params carry none - the key is then omitted)."""
    from pipeline5 import config
    try:
        return str((config.load_params() or {}).get("project_code") or "").strip()
    except Exception:  # noqa: BLE001 - no params file / unreadable: a recommended key, never a crash
        return ""


# --- the fields ---------------------------------------------------------------------------------- #
def fields(kind: str, phase: int | None = None, *, run: str | None = None, project: str | None = None,
           plc: str | None = None, target: str | None = None, name: str | None = None,
           source: str | None = None, comment: str | None = None, generated: str | None = None) -> dict:
    """The header of ONE file: the required keys from the kind + phase, `run`/`project` from the process
    state unless given, the optional keys only when given. An unknown kind is a programming error."""
    if kind not in SCHEMAS:
        raise ValueError(f"unknown kind {kind!r} (contract v1 kinds: {', '.join(SCHEMAS)})")
    out = {"kind": kind, "schema": str(SCHEMAS[kind]), "producer": producer(phase),
           "generated": generated or generated_now(), "run": run or current_run(),
           "project": project if project is not None else project_code(),
           "plc": plc, "target": target, "name": name, "source": source, "comment": comment}
    return {k: str(v) for k, v in out.items() if v is not None and str(v) != ""}


def workspace_fields(*, run: str | None = None, project: str | None = None, plcs=(),
                     templates: str = TEMPLATES_FOLDER, generated: str | None = None) -> dict:
    """The workspace config header (§3.4): the contract version, the project, the producer, the run, the
    PLC folders and the templates folder."""
    out = {"contract": str(CONTRACT), "project": project if project is not None else project_code(),
           "producer": producer(), "generated": generated or generated_now(), "run": run or current_run(),
           "plcs": ", ".join(p for p in plcs if p), "templates": templates}
    return {k: str(v) for k, v in out.items() if v is not None and str(v) != ""}


# --- rendering ----------------------------------------------------------------------------------- #
def _clean(value) -> str:
    return re.sub(r"[\r\n]+", " ", str(value)).strip()


def directive_lines(values: dict) -> list:
    """`#!openn`, one `#! key: value` per key (KEY_ORDER first, then the rest as given), `#!end`."""
    keys = [k for k in KEY_ORDER if k in values] + [k for k in values if k not in KEY_ORDER]
    lines = [OPEN]
    for key in keys:
        if not _KEY_RX.match(key):
            raise ValueError(f"invalid header key {key!r} (lower-case letters, digits and '-')")
        lines.append(f"{MARKER} {key}: {_clean(values[key])}")
    lines.append(END)
    return lines


def render_csv(values: dict, delimiter: str = ",") -> str:
    """The csv wrapping: the lines as they are, CRLF. A value ending with the delimiter is refused - OP5
    strips Excel's trailing-delimiter padding, which would eat it."""
    for key, value in values.items():
        if _clean(value).endswith(delimiter):
            raise ValueError(f"header value of {key!r} must not end with the csv delimiter {delimiter!r}: {value!r}")
    return _EOL.join(directive_lines(values)) + _EOL


def render_xml(values: dict) -> str:
    """The XML wrapping: the block inside one comment (`--` in a value becomes `- -`), CRLF."""
    safe = {k: _clean(v).replace("--", "- -") for k, v in values.items()}
    return "<!--" + _EOL + _EOL.join(directive_lines(safe)) + _EOL + "-->" + _EOL


def render_source(values: dict) -> str:
    """The text-source wrapping (.scl .awl .db .udt .st): every line prefixed `//`, CRLF."""
    return _EOL.join("//" + line for line in directive_lines(values)) + _EOL


_XML_DECL_RX = re.compile(r"^(﻿?)(<\?xml[^>]*\?>)(\r\n|\n|\r|)")
_XML_HEADER_RX = re.compile(r"^[ \t]*<!--[ \t]*(?:\r\n|\n|\r)?[ \t]*#!openn\b.*?-->(?:\r\n|\n|\r)?", re.S)
_SOURCE_HEADER_RX = re.compile(r"^(﻿?)//[ \t]*#!openn[^\r\n]*(?:\r\n|\n|\r)(?:[^\r\n]*(?:\r\n|\n|\r))*?//[ \t]*#!end[^\r\n]*(?:\r\n|\n|\r)?")
_CSV_HEADER_RX = re.compile(r"^(﻿?)#!openn[^\r\n]*(?:\r\n|\n|\r)(?:[^\r\n]*(?:\r\n|\n|\r))*?#!end[^\r\n]*(?:\r\n|\n|\r)?")
_LEGACY_TAG_RX = re.compile(r"^(﻿?)#!format=\d+[^\r\n]*(?:\r\n|\n|\r)?")


def stamp_xml(text: str, values: dict) -> str:
    """`text` (an XML document, BOM-less or not) with the header as the FIRST comment after the
    declaration - an existing `#!openn` comment there is replaced (a stamped template copy, a re-stamp)."""
    m = _XML_DECL_RX.match(text)
    if not m:                                  # no declaration: the comment opens the document
        bom = "﻿" if text.startswith("﻿") else ""
        return bom + render_xml(values) + _XML_HEADER_RX.sub("", text[len(bom):], count=1)
    bom, decl, eol = m.group(1), m.group(2), m.group(3) or _EOL
    rest = _XML_HEADER_RX.sub("", text[m.end():], count=1)
    return bom + decl + eol + render_xml(values) + rest


def stamp_source(text: str, values: dict) -> str:
    """`text` (a text source) with the header as its first lines; an existing leading block is replaced."""
    m = _SOURCE_HEADER_RX.match(text)
    if m:
        return m.group(1) + render_source(values) + text[m.end():]
    bom = "﻿" if text.startswith("﻿") else ""
    return bom + render_source(values) + text[len(bom):]


def stamp_csv(text: str, values: dict, delimiter: str = ",") -> str:
    """`text` (csv) with the header as its first lines; an existing leading block or a legacy
    `#!format=N` tag line is replaced."""
    m = _CSV_HEADER_RX.match(text) or _LEGACY_TAG_RX.match(text)
    if m:
        return m.group(1) + render_csv(values, delimiter) + text[m.end():]
    bom = "﻿" if text.startswith("﻿") else ""
    return bom + render_csv(values, delimiter) + text[len(bom):]


def strip_header(text: str) -> str:
    """`text` without its leading header block (any wrapping) and without a legacy `#!format=N` tag line
    - the parity oracle's normalization. Everything else stays byte-identical."""
    m = _XML_DECL_RX.match(text)
    if m:
        return text[:m.end()] + _XML_HEADER_RX.sub("", text[m.end():], count=1)
    for rx in (_SOURCE_HEADER_RX, _CSV_HEADER_RX, _LEGACY_TAG_RX):
        m = rx.match(text)
        if m:
            return m.group(1) + text[m.end():]
    return text


def sidecar_path(path: str) -> str:
    return path + SIDECAR_SUFFIX


def write_sidecar(path: str, values: dict) -> str:
    """The header of a binary / foreign file, as `<file>.openn` beside it (csv form, UTF-8, CRLF)."""
    side = sidecar_path(path)
    with open(side, "w", encoding="utf-8", newline="") as handle:
        handle.write(render_csv(values))
    return side


def write_workspace_config(path: str, values: dict) -> str:
    """`.openn/workspace.openn.config` - the workspace header (csv form); the folder is created."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(render_csv(values))
    return path


# --- parsing (the OP5 rules, mirrored for the round-trip tests and the oracle) ------------------- #
@dataclass
class Header:
    """A parsed header: `status` ok / legacy / missing / invalid, the values (keys lower-case, file order),
    the hard problems (any one = invalid), the soft remarks (unknown keys), the legacy format number."""
    status: str = "missing"
    values: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    remarks: list = field(default_factory=list)
    legacy_format: int | None = None

    def get(self, key: str, default=None):
        return self.values.get(key.lower(), default)


def normalize_csv_line(raw: str) -> str:
    """Undo what Excel does to a csv comment line when it saves the file: the trailing delimiter
    padding (`,,,,`), and the quoting of a line that contained the delimiter (`"..."` with `""` escapes)."""
    line = (raw or "").rstrip("\r\n").strip()
    if not line:
        return line
    if line[0] == '"':
        close = line.find('"', 1)
        while close >= 0 and close + 1 < len(line) and line[close + 1] == '"':
            close = line.find('"', close + 2)
        if close > 0:
            line = line[1:close].replace('""', '"')
    return line.rstrip(",;\t ")


def parse_directives(lines, required=REQUIRED) -> Header:
    """Build a Header from directive lines (each starting with `#!`, comment prefixes and Excel padding
    already removed): keys case-insensitive, the first `:` splits, duplicates are an error, unknown keys a
    remark, a bare `#!format=N` outside the block = legacy, nothing = missing."""
    h = Header()
    is_open = closed = False
    for raw in lines or ():
        line = (raw or "").strip()
        if not line.startswith(MARKER):
            continue
        body = line[len(MARKER):].strip()
        if not is_open:
            if body.lower() == OPEN[len(MARKER):]:
                if closed:
                    h.problems.append("second #!openn block")
                is_open = True
                continue
            if "=" in body and body.split("=", 1)[0].strip().lower() == LEGACY_FORMAT:
                try:
                    h.legacy_format = int(body.split("=", 1)[1].strip())
                    continue
                except ValueError:
                    pass
            h.remarks.append(f"directive outside the header ignored: {line}")
            continue
        if body.lower() == END[len(MARKER):]:
            is_open, closed = False, True
            continue
        if ":" not in body or body.index(":") == 0:
            h.problems.append(f"header line is not 'key: value': {line}")
            continue
        key, value = body.split(":", 1)
        key, value = key.strip().lower(), value.strip()
        if not _KEY_RX.match(key):
            h.problems.append(f"invalid header key '{key}' (lower-case letters, digits and '-')")
            continue
        if key in h.values:
            h.problems.append(f"duplicate header key: {key}")
            continue
        h.values[key] = value
        if key not in KNOWN_KEYS:
            h.remarks.append(f"unknown header key: {key}")
    if is_open:
        h.problems.append("#!openn block not closed with #!end")
    if not is_open and not closed:
        h.status = "legacy" if h.legacy_format is not None else "missing"
        return h
    for key in required:
        if not h.values.get(key):
            h.problems.append(f"missing required header key: {key}")
    if "schema" in h.values and not h.values["schema"].isdigit():
        h.problems.append(f"schema is not an integer: {h.values['schema']}")
    if "contract" in h.values and not h.values["contract"].isdigit():
        h.problems.append(f"contract is not an integer: {h.values['contract']}")
    if "kind" in h.values and h.values["kind"] not in SCHEMAS:
        h.problems.append(f"unknown kind: {h.values['kind']}")
    if "generated" in h.values and not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$",
                                               h.values["generated"]):
        h.problems.append(f"generated is not an ISO 8601 date-time: {h.values['generated']}")
    h.status = "ok" if not h.problems else "invalid"
    return h


def syntax_for(path: str) -> str:
    """The wrapping a file uses, from its extension: csv / xml / source / sidecar."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt", ".md", ".config", ".openn"):
        return "csv"
    if ext in (".xml", ".aml", ".xsd"):
        return "xml"
    if ext in (".scl", ".awl", ".db", ".udt", ".st", ".src"):
        return "source"
    return "sidecar"


def directive_lines_of(text: str, syntax: str) -> list:
    """The `#!` directive lines at the top of `text` in the given wrapping, prefixes and Excel padding
    removed - stops at the first line that is neither blank, a comment nor a directive."""
    text = text[1:] if text.startswith("﻿") else text
    out = []
    if syntax == "xml":
        pos = 0
        while True:
            while pos < len(text) and text[pos].isspace():
                pos += 1
            if text.startswith("<?", pos):
                end = text.find("?>", pos)
                if end < 0:
                    return []
                pos = end + 2
                continue
            if text.startswith("<!--", pos):
                end = text.find("-->", pos + 4)
                if end < 0:
                    return []
                return [ln.strip() for ln in text[pos + 4:end].split("\n") if ln.strip().startswith(MARKER)]
            return []
    for raw in text.splitlines()[:200]:
        if syntax == "source":
            t = raw.strip()
            if not t:
                continue
            if not t.startswith("//"):
                break
            line = t[2:].strip()
            if line.startswith(MARKER):
                out.append(line)
            continue
        line = normalize_csv_line(raw)
        if not line:
            continue
        if line.startswith(MARKER):
            out.append(line)
            continue
        if line[0] == "#":
            continue
        break
    return out


def read_header(path: str, required=REQUIRED) -> Header:
    """The header of a file: in-file for a text wrapping, else (or when the file has none) from its
    `<file>.openn` sidecar - an in-file header wins. Never raises: an unreadable file is invalid."""
    try:
        syntax = syntax_for(path)
        in_file = []
        if syntax != "sidecar":
            with open(path, encoding="utf-8", errors="replace", newline="") as handle:
                in_file = directive_lines_of(handle.read(64 * 1024), syntax)
        side = sidecar_path(path)
        if in_file or not os.path.isfile(side):
            h = parse_directives(in_file, required)
            if os.path.isfile(side):
                h.remarks.append(f"sidecar {os.path.basename(side)} ignored - the in-file header wins")
            return h
        with open(side, encoding="utf-8", errors="replace", newline="") as handle:
            h = parse_directives(directive_lines_of(handle.read(), "csv"), required)
        h.remarks.append(f"header read from sidecar {os.path.basename(side)}")
        return h
    except OSError as error:
        h = Header(status="invalid")
        h.problems.append(f"cannot read header: {error}")
        return h

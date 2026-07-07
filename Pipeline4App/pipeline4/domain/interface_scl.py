"""Phase 400 - project the `interface_elements` SSOT table to **`10_Machine Interfaces.scl`** (the
configured `interfaces.scl_file`; the TIA import surface, beside the diagnosis SCL in ImportReady):
ONE ASSIGNMENT PER INTERFACED SIGNAL, grouped in a REGION per interface, the line per DIRECTION
(the template sheet's `Direction </>` column - `>` = Q, out toward the partner; `<` = I, in from
the partner; the SSOT stores I/Q):

    >:  <signal name side 1> := <expression side 1>;
    <:  <expression side 1> := <signal name side 1>;

Within a region, a BLANK LINE opens each new I/O BYTE (the `io_address_side1` up to the `.bit`) -
the assignments read grouped by byte, like the IF_ sheet lays them out (user spec 2026-07-07).

The line templates live in generation_params.yaml (`interfaces.scl_line_templates`), rendered
through the ONE expression engine against each element row. The ctx carries the raw SSOT columns
($signal_name / $expression == the sheet's 'Signal Name Side 1' / 'Expression Side 1') plus their
TIA-QUOTED variants ($signal_name_q / $expression_q - quoted unless the value already starts with a
quote, e.g. a stored `"db"."member"` binding or the template's `"Clock 1Hz"`). The FUNCTION is
named after the configured file's stem, so the config rename drives both.

UTF-8 BOM + CRLF like every SCL surface. A pure projection - returns findings, records nothing.
"""
from __future__ import annotations

import os

from pipeline4.core import config, expr
from pipeline4.core.database import Database
from pipeline4.core.finding import Finding

_IO_TO_DIR = {"Q": ">", "I": "<"}      # the SSOT direction -> the sheet's `Direction </>` glyph


def _f(type: str, severity: str, detail: str, location: str = "") -> Finding:
    """A phase-400 Finding - the MachineInterfaces-SCL projection report container (WARN-only)."""
    return Finding(phase=400, type=type, severity=severity, detail=detail, location=location)


def _scl_params() -> dict:
    """The projection knobs from user_input/generation_params.yaml (UI_REFRESH_PLAN F style) -
    STRICT: a missing key is a located error, never an in-code default."""
    section = (config.load_generation_params() or {}).get("interfaces") or {}
    try:
        templates = section["scl_line_templates"]
        return {"file": str(section["scl_file"]),
                "templates": {str(k): str(v) for k, v in dict(templates).items()}}
    except (KeyError, TypeError):
        raise RuntimeError("generation_params.yaml: interfaces.scl_file / interfaces.scl_line_templates"
                           " is missing/malformed") from None


def _quoted(text: str) -> str:
    """The TIA-quoted form: as-is when the value already starts with a quote (a stored
    `"db"."member"` binding / an already-quoted tag), else wrapped."""
    text = str(text or "").strip()
    if not text or text.startswith('"'):
        return text
    return f'"{text}"'


def render_lines(elements, templates: dict) -> tuple:
    """`(lines, findings)` - the SCL body: a REGION per interface (first-seen order), one rendered
    assignment per element, a BLANK line before each NEW I/O byte (the address up to `.bit` - the
    byte grouping the IF_ sheet also shows; skipped elements don't break a byte group). An element
    with a blank signal/expression or an unmapped direction is SKIPPED with a WARN (the rest of the
    file still ships)."""
    lines, findings = [], []
    by_interface: dict = {}
    for e in elements:
        by_interface.setdefault(str(e.get("interface") or ""), []).append(e)
    for instance, rows in by_interface.items():
        lines.append(f"REGION {instance}")
        last_byte = None
        for e in rows:
            signal = str(e.get("signal_name") or "").strip()
            expression = str(e.get("expression") or "").strip()
            where = f"interface {instance}  {signal or e.get('description', '')}"
            if not signal or not expression:
                findings.append(_f("if_scl_blank_element", "WARN",
                                   "blank signal/expression - assignment skipped", where))
                continue
            glyph = _IO_TO_DIR.get(str(e.get("direction") or "").strip().upper())
            template = templates.get(glyph or "")
            if template is None:
                findings.append(_f("if_scl_no_direction_template", "WARN",
                                   f"no scl_line_template for direction {e.get('direction')!r}", where))
                continue
            byte = str(e.get("io_address_side1") or "").strip().split(".", 1)[0]
            if last_byte is not None and byte != last_byte:
                lines.append("")                     # a blank line opens each new I/O byte (user spec)
            last_byte = byte
            ctx = {"signal_name": signal, "expression": expression,
                   "signal_name_q": _quoted(signal), "expression_q": _quoted(expression),
                   "direction": glyph, "interface": instance}
            lines.append(expr.render(template, ctx, mode="strict"))
        lines.append("END_REGION")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines, findings


def project(database: Database | None = None, out_dir: str | None = None) -> dict:
    """Write the configured `interfaces.scl_file` (default `10_Machine Interfaces.scl`) from the
    `interface_elements` table into `out_dir` (defaults to `config.blocks_import_dir()`). The
    FUNCTION is named after the file's stem. Returns {path, assignments, interfaces, findings};
    no elements -> nothing written (path '')."""
    if database is None:
        from pipeline4.domain.interfaces import interface_elements_table, interfaces_table
        database = Database([interfaces_table(), interface_elements_table()]).load(config.database_dir())
    elements = list(database["interface_elements"]) if "interface_elements" in database else []
    params = _scl_params()
    if not elements:
        return {"path": "", "assignments": 0, "interfaces": 0, "findings": []}
    body, findings = render_lines(elements, params["templates"])
    n_regions = sum(1 for line in body if line.startswith("REGION "))
    n_assign = sum(1 for line in body if line.strip().endswith(";"))
    function_name = os.path.splitext(os.path.basename(params["file"]))[0]
    text_lines = [f'FUNCTION "{function_name}" : Void',
                  "{ S7_Optimized_Access := 'TRUE' }",
                  "VERSION : 0.1",
                  "BEGIN",
                  *body,
                  "END_FUNCTION"]
    out_dir = out_dir or config.blocks_import_dir()
    os.makedirs(out_dir, exist_ok=True)
    legacy = os.path.join(out_dir, "MachineInterfaces.scl")   # the pre-rename output (2026-07-07):
    if params["file"] != "MachineInterfaces.scl" and os.path.exists(legacy):
        os.remove(legacy)                                     # it must not survive as a 2nd import
    path = os.path.join(out_dir, params["file"])
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write("\r\n".join(text_lines) + "\r\n")
    return {"path": path, "assignments": n_assign, "interfaces": n_regions, "findings": findings}

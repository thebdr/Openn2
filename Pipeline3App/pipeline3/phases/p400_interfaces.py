"""Phase 400 - Interfaces Generation.

410 Generate Interfaces: one IF_<instance>.xlsx per IOC row of the staged database, into
interfaces_dir (ProjectDocumentation/.../Interfaces - NOT the Open2App BuilderData import surface).
420 Open Interfaces Folder and 430 Generate Custom Interface... are GUI-era (M11); 430's underlying
single-interface primitive (interfaces.generate_one) is built and unit-tested now. Depends on
Staging (300), which fills ctx.rows.
"""
from __future__ import annotations

from pipeline3.phase import (Phase, SubPhase, PhaseResult, Button,
                             KIND_ACTION, KIND_OPEN, KIND_SPECIAL)
from pipeline3.registry import register
from pipeline3.core import config
from pipeline3.domain import interfaces


def _generate(ctx) -> PhaseResult:
    template = ctx.params.get("interface_template") or config.INTERFACE_TEMPLATE_DEFAULT
    out_dir = config.out_path(ctx.out_root, "interfaces_dir")
    # insert_interface_sheets: overwrite existing outputs AND insert each interface as a sheet into
    # the I/O List (if not already present). Off by default -> the preserve-only behavior.
    insert = config.as_bool(ctx.params.get("insert_interface_sheets"))
    iolist_path = ctx.io_list_path() if insert else None
    res = interfaces.generate(ctx.rows, out_dir, template, overwrite=insert, iolist_path=iolist_path)
    for e in res.get("errors", []):
        ctx.emit(f"  ERROR {e}")
    for w in res["warnings"]:
        ctx.emit(f"  WARN {w}")
    for inst in res["fallback"]:
        ctx.emit(f"  {inst}: no machine-type sheet -> {interfaces.GENERIC_SHEET}")
    for line in res.get("iolist", []):
        ctx.emit(f"  iolist: {line}")
    created, preserved = len(res["created"]), len(res["preserved"])
    ctx.emit(f"interfaces: {created} created, {preserved} preserved -> {out_dir}")
    ok = not res.get("errors") and not any("template not found" in w for w in res["warnings"])
    return PhaseResult(ok=ok, artifacts={"interfaces_dir": out_dir},
                       summary=f"{created} interface(s) created, {preserved} preserved")


def run(ctx) -> PhaseResult:
    return _generate(ctx)


SUB_PHASES = [
    SubPhase(410, "gen_interfaces", "pb_gen_interfaces", _generate),
]

BUTTONS = [
    Button("pb_gen_interfaces", KIND_ACTION, 410, "410"),
    Button("pb_open_interfaces", KIND_OPEN, 420, "open:interfaces_dir"),
    Button("pb_gen_custom_iface", KIND_SPECIAL, 430, "special:custom_interface"),
]

register(Phase(
    number=400, key="interfaces", name_key="ph_interfaces", run=run, requires=(300,),
    buttons=BUTTONS, sub_phases=SUB_PHASES,
    inputs=("io_database", "interface_template"),
    outputs=("interfaces_dir",),
))

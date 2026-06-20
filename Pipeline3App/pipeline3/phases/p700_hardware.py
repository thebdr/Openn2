"""Phase 700 - Hardware Generation.

710 Generate Stations + 720 Generate Modules: a single extract over the staged database produces both
format-2 CSVs -> hardware_dir (the Open2App BuilderData surface). See domain/hardware.py. A head whose
model isn't in the DeviceTypesDatabase is an ERROR (WARNING for switches) and is skipped. 730 (Open
Hardware Data Folder) is GUI-era (M11). Depends on Staging (300).
"""
from __future__ import annotations

from pipeline3.phase import Phase, SubPhase, PhaseResult, Button, KIND_ACTION, KIND_OPEN
from pipeline3.registry import register
from pipeline3.core import config
from pipeline3.domain import hardware


def _generate(ctx) -> dict:
    dtd = ctx.device_db or config.load_device_types_db(ctx.params)
    ctx.device_db = dtd
    res = hardware.generate(ctx.rows, ctx.out_root, dtd)
    for level, text in res["messages"]:
        ctx.emit(f"  {level} {text}")
    ctx.emit(f"hardware: {res['stations']} station(s), {res['modules']} module(s) -> {res['dir']}")
    return res


def _stations(ctx) -> PhaseResult:
    res = _generate(ctx)
    return PhaseResult(ok=not res["errors"], artifacts={"hardware_dir": res["dir"]},
                       summary=f"{res['stations']} station(s)")


def _modules(ctx) -> PhaseResult:
    res = _generate(ctx)
    return PhaseResult(ok=not res["errors"], artifacts={"hardware_dir": res["dir"]},
                       summary=f"{res['modules']} module(s)")


def run(ctx) -> PhaseResult:
    res = _generate(ctx)
    return PhaseResult(ok=not res["errors"], artifacts={"hardware_dir": res["dir"]},
                       summary=f"{res['stations']} station(s), {res['modules']} module(s)")


SUB_PHASES = [
    SubPhase(710, "gen_stations", "pb_gen_stations", _stations),
    SubPhase(720, "gen_modules", "pb_gen_modules", _modules),
]

BUTTONS = [
    Button("pb_gen_stations", KIND_ACTION, 710, "710"),
    Button("pb_gen_modules", KIND_ACTION, 720, "720"),
    Button("pb_open_hardware", KIND_OPEN, 730, "open:hardware_dir"),
]

register(Phase(
    number=700, key="hardware", name_key="ph_hardware", run=run, requires=(300,),
    buttons=BUTTONS, sub_phases=SUB_PHASES,
    inputs=("io_database", "device_types_db"),
    outputs=("hardware_dir",),
))

"""Phase 800 - Software Generation (rebuilt clean).

810 Generate Empty Shells .xlsm (one sheet per template, `$ <mode>` keep/fill/override in B2) FIRST,
so 820 can read the modes. 820 Generate Blocks runs the user-editable Python builders
(domain/blocks/builders.py) over the single Database (ctx.rows) and writes the kept `$/#/%/@`
CreationInfo CSVs; an `override` shell sheet supplies the table directly instead. 830 Generate
Instances writes InstanceDBs.csv from the built tables. 840/850 (Open …) are GUI-era (M11).

No rules, no sidecars - each builder owns its template's logic; the engine just serializes the Table.
Depends on Staging (300) for ctx.rows.
"""
from __future__ import annotations

from pipeline3.phase import Phase, SubPhase, PhaseResult, Button, KIND_ACTION, KIND_OPEN
from pipeline3.registry import register
from pipeline3.core import config
from pipeline3.domain.blocks import engine, shells
import pipeline3.domain.blocks.builders  # noqa: F401  (importing registers the @builds builders)


def _shells(ctx) -> PhaseResult:
    res = shells.generate_shells(ctx.out_root, emit=ctx.emit)
    return PhaseResult(ok=True, artifacts={"blocks_creation_dir": config.out_path(ctx.out_root, "blocks_creation_dir")},
                       summary=f"shells: {len(res['created'])} new / {len(res['kept'])} kept")


def _blocks(ctx) -> PhaseResult:
    res = engine.generate_blocks(ctx.rows, ctx.out_root, emit=ctx.emit, write_instances=False)
    return PhaseResult(ok=True, artifacts={"blocks_creation_dir": res["dir"]},
                       summary=f"{res['count']} block CSV(s)")


def _instances(ctx) -> PhaseResult:
    res = engine.generate_blocks(ctx.rows, ctx.out_root, emit=ctx.emit, write_instances=True)
    return PhaseResult(ok=True, artifacts={"blocks_creation_dir": res["dir"]},
                       summary=f"{res['instances']} instance(s)")


def run(ctx) -> PhaseResult:
    _shells(ctx)
    res = engine.generate_blocks(ctx.rows, ctx.out_root, emit=ctx.emit, write_instances=True)
    return PhaseResult(ok=True, artifacts={"blocks_creation_dir": res["dir"]},
                       summary=f"{res['count']} block CSV(s) + {res['instances']} instance(s)")


SUB_PHASES = [
    SubPhase(810, "gen_shells", "pb_gen_shells", _shells),
    SubPhase(820, "gen_blocks", "pb_gen_blocks", _blocks),
    SubPhase(830, "gen_instances", "pb_gen_instances", _instances),
]

BUTTONS = [
    Button("pb_gen_shells", KIND_ACTION, 810, "810"),
    Button("pb_gen_blocks", KIND_ACTION, 820, "820"),
    Button("pb_gen_instances", KIND_ACTION, 830, "830"),
    Button("pb_open_shells", KIND_OPEN, 840, "open:shell_xlsm"),
    Button("pb_open_blocks_folder", KIND_OPEN, 850, "open:blocks_creation_dir"),
]

register(Phase(
    number=800, key="software", name_key="ph_software", run=run, requires=(300,),
    buttons=BUTTONS, sub_phases=SUB_PHASES,
    inputs=("io_database", "block_templates.json", "Tia Portal Software Blocks/*"),
    outputs=("blocks_creation_dir",),
))

"""Phase 500 - Signals Mapping.

510 Generate I/O Tags: one TIA "PLC Tags" workbook (io_tags_dir/PLCTags.xlsx) = the resolved I/O
signals of the staged database PLUS the interface tags read from the IF_ sheets phase 400 inserted
into the I/O List (see domain/signals.py). 520 Generate Data Blocks follows. 530/540 (Open IO Tags /
Open Data Blocks Folder) are GUI-era (M11). Depends on Staging (300); interface tags additionally
need phase 400 to have run with insert_interface_sheets (absent IF_ sheets simply yield none).
"""
from __future__ import annotations

from pipeline3.phase import Phase, SubPhase, PhaseResult, Button, KIND_ACTION, KIND_OPEN
from pipeline3.registry import register
from pipeline3.core import config
from pipeline3.domain import signals


def _io_tags(ctx) -> PhaseResult:
    res = signals.generate_io_tags(ctx.rows, ctx.out_root, iolist_path=ctx.io_list_path())
    for w in res["warnings"]:
        ctx.emit(f"  WARN {w}")
    ctx.emit(f"i/o tags: {res['total']} tag(s) "
             f"({res['io_count']} I/O + {res['iface_count']} interface) "
             f"in {len(res['tables'])} table(s) -> {res['path']}")
    return PhaseResult(ok=True, artifacts={"io_tags_dir": config.out_path(ctx.out_root, "io_tags_dir")},
                       summary=f"{res['total']} tag(s) -> PLCTags.xlsx")


def _data_blocks(ctx) -> PhaseResult:
    res = signals.generate_data_blocks(ctx.rows, ctx.out_root)
    for w in res["warnings"]:
        ctx.emit(f"  WARN {w}")
    ctx.emit(f"data blocks: {res['count']} DB(s) -> .xml "
             f"({len(res['safe'])} F_DB + {len(res['normal'])} DB) -> {res['dir']}")
    return PhaseResult(ok=True, artifacts={"blocks_import_dir": res["dir"]},
                       summary=f"{res['count']} data block(s)")


def run(ctx) -> PhaseResult:
    r1 = _io_tags(ctx)
    r2 = _data_blocks(ctx)
    artifacts = dict(r1.artifacts)
    artifacts.update(r2.artifacts)
    return PhaseResult(ok=r1.ok and r2.ok, artifacts=artifacts,
                       summary=f"{r1.summary}; {r2.summary}")


SUB_PHASES = [
    SubPhase(510, "gen_io_tags", "pb_gen_io_tags", _io_tags),
    SubPhase(520, "gen_data_blocks", "pb_gen_data_blocks", _data_blocks),
]

BUTTONS = [
    Button("pb_gen_io_tags", KIND_ACTION, 510, "510"),
    Button("pb_gen_data_blocks", KIND_ACTION, 520, "520"),
    Button("pb_open_io_tags", KIND_OPEN, 530, "open:io_tags_dir"),
    Button("pb_open_data_blocks", KIND_OPEN, 540, "open:blocks_import_dir"),
]

register(Phase(
    number=500, key="signals", name_key="ph_signals", run=run, requires=(300,),
    buttons=BUTTONS, sub_phases=SUB_PHASES,
    inputs=("io_database", "signal_types.csv", "datablock_elements_rules.csv"),
    outputs=("io_tags_dir", "blocks_import_dir"),
))

"""Where Siemens deliveries land - the OP5 handoff WORKSPACE, as the system's OutputLayout (coupling #3).

Chapter: the folder shape of what TIA receives. The workspace (`<output root>/TiaPortalProjectInterface/
BuilderData`) is shaped like a TIA Version Control Interface (VCI) workspace (contract v1 §4):

    BuilderData/
      .openn/workspace.openn.config      the workspace header (contract, project, producer, run, plcs)
      Devices & networks/                hw/stations + hw/modules (project-level hardware)
      Templates/                         the block-template copies the block-gen csvs reference
      <PLC>/Program blocks/              data-block + code-block XML, block-gen csvs, InstanceDBs.csv, sources
      <PLC>/PLC tags/                    PLCTags.xlsx (+ its .openn sidecar)
      <PLC>/PLC data types/              (sw/udt - not emitted yet)

Location says where a file lands in TIA: the PLC folder IS the Plc station's name (what Stations.csv
calls it), the folder under it is the TIA tree folder's name. Reserved root folders: `.openn`, `.vci`,
`Devices & networks`, `Templates` - every other root folder is a PLC. The legacy layout
(HardwareConfiguration/, SoftwareBlocks/CreationInfo|ImportReady/, PlcTags/) is not written any more
(user decision 2026-10-08: the VCI shape only; OP5 v1 still reads old trees with warnings).

Place in the flow: constructed once as `LAYOUT` and carried as `SYSTEM.output_layout`
(src://pipeline5/systems/plc_based/siemens_s7/safety/system.py). `delivery_dirs(database)` is what the
writers and the 800 engine resolve their default folders through (the PLC name comes from the staged
facts: the `hardware_stations` Plc row, else the PLC head of `signals`); `begin_generation` opens a
generation - the run id and the workspace config (src://pipeline5/systems/plc_based/siemens_s7/
openn_header.py) - called by the run-plan handlers before their first write
(src://pipeline5/systems/plc_based/siemens_s7/safety/main.py); `dirs()` answers the phase bar's
`kind="open"` buttons from what is on disk (src://pipeline5/workbench/app_main.py). It writes no table.
"""
from __future__ import annotations

import os

from pipeline5 import config
from pipeline5.systems.plc_based.siemens_s7 import openn_header as header
from pipeline5.systems.plc_based.siemens_s7 import profinet_hardware as hardware
from pipeline5.systems.system_contract import OutputLayout

WORKSPACE_PARTS = ("TiaPortalProjectInterface", "BuilderData")


class TiaOutputLayout(OutputLayout):
    """The Siemens delivery dirs - the VCI-shaped OP5 workspace under the active output root."""

    def __init__(self) -> None:
        self._begun: set = set()          # (workspace root, run) pairs whose config this process wrote

    # --- the shape ------------------------------------------------------------------------------- #
    def workspace_root(self) -> str:
        return os.path.join(config.output_root(), *WORKSPACE_PARTS)

    def config_path(self) -> str:
        return os.path.join(self.workspace_root(), header.CONFIG_FOLDER, header.CONFIG_FILE)

    def hardware_dir(self) -> str:
        return os.path.join(self.workspace_root(), header.HARDWARE_FOLDER)

    def templates_dir(self) -> str:
        return os.path.join(self.workspace_root(), header.TEMPLATES_FOLDER)

    def plc_dir(self, plc: str) -> str:
        return os.path.join(self.workspace_root(), plc)

    def program_blocks_dir(self, plc: str) -> str:
        return os.path.join(self.plc_dir(plc), header.PROGRAM_BLOCKS)

    def plc_tags_dir(self, plc: str) -> str:
        return os.path.join(self.plc_dir(plc), header.PLC_TAGS)

    def plc_data_types_dir(self, plc: str) -> str:
        return os.path.join(self.plc_dir(plc), header.PLC_DATA_TYPES)

    # --- the PLC --------------------------------------------------------------------------------- #
    @staticmethod
    def plc_folder(database, required: bool = True):
        """The PLC folder name = the Plc station name (contract §4): the `hardware_stations` Plc row when
        the table is there, else the PLC head of the staged `signals` (the rule phase 700 applies). None -
        or, `required`, a pointed error - when the I/O List names no PLC: software has no home then."""
        if database is not None:
            if "hardware_stations" in database:
                for row in database["hardware_stations"]:
                    if str(row.get("role") or "") == "Plc" and str(row.get("station_name") or "").strip():
                        return str(row["station_name"]).strip()
            if "signals" in database:
                name = hardware.plc_station_name(database["signals"])
                if name:
                    return name
        if required:
            raise RuntimeError("no Plc station in the I/O List (a PLC head row with a PROFINET name) - the "
                               "OP5 workspace needs the PLC folder name (contract v1 §4)")
        return None

    def plc_folders_on_disk(self) -> list:
        """The PLC folders the workspace holds right now (every root folder that is not reserved)."""
        root = self.workspace_root()
        if not os.path.isdir(root):
            return []
        return sorted(d for d in os.listdir(root)
                      if os.path.isdir(os.path.join(root, d)) and d not in header.RESERVED_ROOT_FOLDERS)

    # --- the two resolutions --------------------------------------------------------------------- #
    def delivery_dirs(self, database) -> dict:
        """The folders ONE generation writes into, from the staged facts (the PLC folder): `hardware`,
        `templates`, `blocks_import` + `blocks_creation` (both `<PLC>/Program blocks` - the VCI shape has
        one program-blocks folder), `io_tags` (`<PLC>/PLC tags`), `workspace`, and the `plc` name."""
        plc = self.plc_folder(database)
        blocks = self.program_blocks_dir(plc)
        return {"plc": plc, "workspace": self.workspace_root(), "hardware": self.hardware_dir(),
                "templates": self.templates_dir(), "blocks_import": blocks, "blocks_creation": blocks,
                "io_tags": self.plc_tags_dir(plc)}

    def dirs(self) -> dict:
        """The GUI's open targets, from what is ON DISK: the first PLC folder's `Program blocks` /
        `PLC tags` (the workspace root until a generation created one), the hardware folder, the
        workspace itself."""
        root = self.workspace_root()
        plcs = self.plc_folders_on_disk()
        plc = plcs[0] if plcs else None
        blocks = self.program_blocks_dir(plc) if plc else root
        return {"blocks_import": blocks, "blocks_creation": blocks,
                "io_tags": self.plc_tags_dir(plc) if plc else root,
                "hardware": self.hardware_dir(), "workspace": root}

    # --- the generation -------------------------------------------------------------------------- #
    def begin_generation(self, database, run: str = "") -> tuple:
        """Open a generation before its first write (contract §6.2): adopt the host's run id
        (`PhaseContext.run` - one per button press, Run-all included) or mint one, and write
        `.openn/workspace.openn.config` for it ONCE per (workspace, run) in this process - the later
        phases of a Run-all join it. Returns (run id, whether the config was written now)."""
        run = header.begin_run(run or None)
        key = (os.path.normcase(os.path.abspath(self.workspace_root())), run)
        if key in self._begun:
            return run, False
        plcs = [self.plc_folder(database)]
        header.write_workspace_config(self.config_path(), header.workspace_fields(run=run, plcs=plcs))
        self._begun.add(key)
        return run, True


LAYOUT = TiaOutputLayout()

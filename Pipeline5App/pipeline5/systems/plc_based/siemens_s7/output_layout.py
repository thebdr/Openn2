"""Where Siemens deliveries land - the TiaPortalProjectInterface/BuilderData tree, as an OutputLayout.

The BuilderData tree is the OP4 (C# TIA-Openness importer) contract: what these dirs contain is what
TIA receives. TRANSITIONAL: the dir functions still live in `pipeline5.config.paths` (the kernel);
this layout object is the system-owned handle the migration-step-4 extraction moves them behind -
consumers switch from `config.blocks_import_dir()` to `system.output_layout` as step 4 lands.
"""
from __future__ import annotations

from pipeline5 import config
from pipeline5.systems.system_contract import OutputLayout


class TiaOutputLayout(OutputLayout):
    """The Siemens delivery dirs, keyed by the GUI's open-target names."""

    def dirs(self) -> dict:
        return {
            "blocks_import": config.blocks_import_dir(),      # <DB>.xml + ready SCL/FC-XML (ImportReady)
            "blocks_creation": config.blocks_creation_dir(),  # $/#/%/@ CreationInfo CSVs + InstanceDBs.csv
            "io_tags": config.io_tags_dir(),                  # PLCTags.xlsx
            "hardware": config.hardware_dir(),                # Stations.csv + Modules.csv (format-2)
        }


LAYOUT = TiaOutputLayout()

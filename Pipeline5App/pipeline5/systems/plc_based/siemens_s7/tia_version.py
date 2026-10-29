"""The TIA Portal version a Siemens generation targets - one project setting ([[C-049]]).

The user, 2026-10-27: "we should be able to set the tia version in PL5". Every SimaticML document PL5 writes
opens with `<Engineering version="V..">` - the Global DBs (520), the tag tables (510), the FC XMLs built from
the block templates (800) - and a TIA Portal refuses a document newer than itself. The version is the
`tia_version` key of the project's project_params.yaml (the Output parameters block, beside output_dir);
blank or absent means the BUILTIN project_params.yaml's value - config, never an in-code default - so a
project made before the key existed still generates. The New-project dialog offers it as a dropdown
(`OPTION`, the System descriptor's `project_options` - the kernel dialog never names Siemens).

The resolved version also rides in `.openn/workspace.openn.config` (`tia`), where OP5 compares it with the
Portal it attaches to: a workspace newer than the Portal is refused, an older one imports with a warning
(Shared/PL5_OP5_contract.md §3.4, §7).

`SUPPORTED` mirrors OP5's Openness range (`OpennessSetup.MinimumPortalMajorVersion` ..
`MaximumPortalMajorVersion`, Openn5App/03_ApiManager/OpennessSetup.cs): a version OP5 cannot attach to is
not offered. The block templates in Shared/Templates keep the stamp they were exported with - OP5's
BlockXmlGenerator re-stamps a generated block with the attached Portal's version anyway.

Place in the flow: no phase button runs THIS module - the emitters (globaldb_xml_emitter, plctags_xml_emitter,
fc_xml_emitter) and the workspace header (output_layout.begin_generation) call `active()` /
`stamp()` whenever they write. It reads project_params.yaml and writes nothing.
"""
from __future__ import annotations

import os
import re

from pipeline5 import config
from pipeline5.systems.system_contract import ProjectOption

PARAM = "tia_version"
SUPPORTED = ("V18", "V19", "V20")
OPTION = ProjectOption(PARAM, "np_tia_version", SUPPORTED)

_ENGINEERING = re.compile(r'<Engineering version="[^"]*"')
_SPELLING = re.compile(r"^[Vv]?\s*(\d+)$")


def normalize(value) -> str:
    """`20`, `v20`, ` V20 ` -> `V20`; anything that is not a supported version raises ValueError."""
    text = str(value if value is not None else "").strip()
    m = _SPELLING.match(text)
    version = f"V{int(m.group(1))}" if m else text
    if version not in SUPPORTED:
        raise ValueError(f"{PARAM} {text!r} is not a supported TIA Portal version ({', '.join(SUPPORTED)})")
    return version


def builtin() -> str:
    """The builtin project_params.yaml's version (what a project without the key gets)."""
    path = os.path.join(config.builtin_shared_config_dir(), "project_params.yaml")
    return normalize(config.load_params(path).get(PARAM))


def active(params: dict | None = None) -> str:
    """The version the active project targets: its own `tia_version`, else the builtin one."""
    params = config.load_params() if params is None else params
    value = params.get(PARAM)
    return normalize(value) if str(value if value is not None else "").strip() else builtin()


def engineering_line(version: str | None = None) -> str:
    """The SimaticML version line, indented as TIA exports it."""
    return f'  <Engineering version="{version or active()}" />'


def stamp(xml: str, version: str | None = None) -> str:
    """`xml` with its (first) `<Engineering version=..>` set to the target version - a template's own stamp
    replaced; a document without one is returned unchanged."""
    return _ENGINEERING.sub(f'<Engineering version="{version or active()}"', xml, count=1)

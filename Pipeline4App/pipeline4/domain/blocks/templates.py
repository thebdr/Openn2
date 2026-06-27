"""The block-template KEY INVENTORY scan (phase 800) - the source of the CreationInfo CSV `%` header.

Clean-room port of the template-scanning half of PL3's `domain/blocks/shells.py` (the editable `.xlsm`
shell - an operator surface, NOT part of the OP4 import contract - is deferred). Scanning the shipped
template `*.xml` for `!!key$$` placeholders gives each block's full ordered key set; the engine uses it as
the `%` header so the CSV carries the template's full placeholder inventory (matching PL3's shipped output),
not just the columns a builder happened to fill.
"""
from __future__ import annotations

import os
import re

from pipeline4.core import config

_PLACEHOLDER = re.compile(r"!!(.+?)\$\$")
_PREFIX_RE = re.compile(r"^TEMPLATE--v\d+\.\d+--")

# Blocks whose shell sheet is the COIL-COLUMNS layout (the cause->effect linking) rather than the standard
# %/@ key inventory. Kept for parity with PL3's engine (the 03 block emits direct FC XML in 800c).
COIL_COLUMN_BLOCKS = {"03_Zone Cumulative"}


def short_name(stem: str) -> str:
    """The OUTPUT block name = the template stem with the `TEMPLATE--vX.Y--` prefix dropped."""
    return _PREFIX_RE.sub("", stem)


def template_ref(stem: str) -> str:
    """Absolute path to a template's .xml (the `$ template=` reference written into the CSV)."""
    return os.path.join(config.BLOCK_TEMPLATES_DIR, f"{stem}.xml")


def scan_templates() -> dict:
    """{stem: [keys...]} by scanning the block-template `*.xml` for `!!key$$` (distinct, first-seen order).
    The template XML is the source of truth (PL3's block_templates.json is deprecated)."""
    out = {}
    d = config.BLOCK_TEMPLATES_DIR
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.lower().endswith(".xml"):
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        keys = []
        for k in _PLACEHOLDER.findall(text):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
        out[fn[:-4]] = keys
    return out


def template_keys() -> dict:
    """{short_name: [keys...]} - the key inventory keyed by the OUTPUT block name (the builder's name)."""
    return {short_name(stem): keys for stem, keys in scan_templates().items()}


def stem_ref_by_name() -> dict:
    """{short_name: (stem, template_ref)} for every shipped template - the engine resolves a builder's
    template + the `$ template=` path from its name."""
    return {short_name(stem): (stem, template_ref(stem)) for stem in scan_templates()}

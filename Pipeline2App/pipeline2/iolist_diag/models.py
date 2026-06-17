"""Typed models, enums and constants for the I/O-list diagnosis populator.

Frozen dataclasses for the records that flow through the stage (`SignalTypeDef`,
`ObjectFamily`, `IoRow`, `DiagBlock`) plus a small mutable `RowResult` that accumulates the
computed AB/AC/AD/AE/AF for one row. `enum` + structural `match` drive the category and
block-kind decisions; the sentinels (`<input required>`, the suggested-type `???` marker, the
`"-"` mnemonic) and the generated sheet names live here so nothing downstream hardcodes a
magic string.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

# --- sentinels / magic strings (one place) --------------------------------- #
INPUT_REQUIRED = "<input required>"   # written into an index cell we can't auto-resolve
SUGGEST_UNMATCHED = "???"             # the suggested-type formula's "looks real but unmatched" marker
DASH = "-"                            # mnemonic value that marks a deleted/skipped row
DIAGBLOCKS_SHEET = "DiagnosisBlocks"
UNRESOLVED_SHEET = "_UnresolvedIndex"

_P_TYPES = {"PA", "PW"}               # diagnosed from the TOP of the block (diag_bit_max down)


class Category(str, Enum):
    SAFETY = "Safety"
    DIAG = "Diag"
    STD = "Std"
    INTERFACE = "Interface"
    OTHER = ""


class BlockKind(Enum):
    TYPE1_FL = 1          # physical-node cabinet; FullName = FU+location, no _n suffix
    TYPE2_GENERATED = 2   # generated function block (+SafetyDoors_n, +EmergencyPushButtons_n, ...)


class LinkKind(str, Enum):
    CHANNEL = "channel"   # the two channels of one device share a FLD (strict; mismatch = error)
    SERIES = "series"     # K: a KQ output + its series-wired KI feedbacks (FLDs may legitimately differ)
    FLD = "fld"           # siblings inherit the anchor's device FLD (door sensor: DI/DD)
    PATTERN = "pattern"   # one shared index for the whole family (emergency areas; bit = area number)
    NONE = "none"         # no grouping - every row consumes the counter (reset; and A/W/PA/PW non-families)
    MANUAL = "manual"     # can't be auto-linked -> <input required> (door relay/PLC inputs DR/DL/DQ)


@dataclass(frozen=True)
class SignalTypeDef:
    """One row of signal_types.csv, only the fields the populator needs."""
    type_id: str
    desc: str
    category: Category
    pair_key: str
    channel: str               # "1" / "2" / ""
    is_pattern: bool
    in_diag: bool
    diag_container_check: str

    @classmethod
    def from_record(cls, rec: dict) -> "SignalTypeDef":
        try:
            cat = Category(rec.get("category", ""))
        except ValueError:
            cat = Category.OTHER
        return cls(
            type_id=rec["type_id"],
            desc=rec.get("type_id_desc", ""),
            category=cat,
            pair_key=rec.get("pair_key", ""),
            channel=str(rec.get("channel", "") or ""),
            is_pattern=bool(rec.get("is_pattern")),
            in_diag=bool(rec.get("in_diagnosis")),
            diag_container_check=rec.get("diag_container_check", ""),
        )

    @property
    def is_p_type(self) -> bool:
        return self.type_id.upper() in _P_TYPES


@dataclass(frozen=True)
class ObjectFamily:
    """One row of object_families.csv - a multi-signal object grouping (spec §7.1)."""
    family: str
    key: str                       # leading letter(s) of the script_type (D, K, E, ...)
    member_types: tuple[str, ...]
    anchor: str                    # canonical anchor type id (DI1/2, KQ, E1/2, ...)
    link: LinkKind
    index_stride: int
    bits: int                      # diag bits one object consumes (0 = not diagnosed)
    diag_block: str                # destination Type-2 block FullName stem; '' = node cabinet (Type-1)


@dataclass(frozen=True)
class IoRow:
    """One data row of the I/O List, as read (raw, stripped). Immutable identity + inputs."""
    sheet: str
    row: int                       # 1-based source row (for cell links)
    functional_unit: str
    location: str
    device: str
    desc_l1: str
    desc_l1b: str
    id_node: str
    addr: str                      # the I/O address (col G "bit"): I20.0 / Q130.1 / ''
    type_hw: str                   # col R "Type"
    mnemonic: str
    skip_reason: str
    struck: bool
    ex_script_type: str            # AB as found (Mode-2 preserve)
    ex_suggested: object           # AC as found
    ex_index: str                  # AD as found
    ex_diag_cabinet: str           # AE as found
    ex_diag_bit: str               # AF as found

    @property
    def fld(self) -> str:
        """FUNCTIONAL UNIT + LOCATION + DEVICE, as written (matches outputs.fld)."""
        return self.functional_unit + self.location + self.device

    @property
    def node_fl(self) -> str:
        """The node-cabinet key: FUNCTIONAL UNIT + LOCATION (no device)."""
        return self.functional_unit + self.location

    @property
    def description(self) -> str:
        return f"{self.desc_l1} {self.desc_l1b}".strip()

    @property
    def has_device(self) -> bool:
        return bool(self.device.strip())


@dataclass(frozen=True)
class DiagBlock:
    """One generated DiagnosisBlocks row. `id_local == id_swp` (kept equal so both the spec's
    join (AE = ID_Local) and the existing reader (key = ID_SWP) agree)."""
    id_local: int
    fu: str
    location: str
    full_name: str
    template_type: int             # 1 (FL node) or 2 (generated)
    kind: BlockKind
    family: str = ""               # family stem for Type-2 ('' for Type-1)
    instance: int = 0              # the _n suffix for Type-2 (0 for Type-1)

    @property
    def cabinet_text(self) -> str:
        """The 3-digit cabinet string written into diag_cabinet (AE)."""
        return f"{self.id_local:03d}"


@dataclass
class RowResult:
    """Mutable per-row accumulation of the computed columns + bookkeeping for the report."""
    iorow: IoRow
    type_def: SignalTypeDef | None = None
    family: ObjectFamily | None = None
    script_type: str = ""          # AB to write
    suggested_type: object = ""    # AC to write (str, or bool False for the formula's dangling case)
    index: str = ""                # AD
    diag_cabinet: str = ""         # AE
    diag_bit: str = ""             # AF
    skipped: bool = False
    skip_reason: str = ""
    unresolved: bool = False       # index could not be auto-resolved -> <input required>
    unresolved_reason: str = ""
    unknown_type: bool = False     # script_type not in the catalogue
    error: str = ""                # a hard data-entry defect (channel FLD mismatch / orphan)
    prefilled: bool = False        # AB was non-empty on input (Mode-2 preserve + audit)
    audit_mismatch: bool = False   # prefilled AB differs from the computed value
    computed_script_type: str = "" # what Mode-1 would have written (for the audit line)

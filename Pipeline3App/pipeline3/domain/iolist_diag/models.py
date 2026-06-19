"""Data model for the I/O-List populator (phase 200).

A faithful clean-room re-model of Pipeline2's iolist_diag. IoRow is the immutable row as read;
RowResult is the mutable per-row accumulation (the computed AB/AC/AD/AE/AF + bookkeeping);
ObjectFamily / DiagBlock support index assignment + diagnosis allocation.
"""
from __future__ import annotations
from dataclasses import dataclass, field

# --- sentinels + sheet names (the exact strings staging/validation also recognize) --- #
INPUT_REQUIRED = "<input required>"     # written into a cell that can't be auto-resolved (halts)
DASH = "-"                              # mnemonic value marking a deleted/spare row
DIAGBLOCKS_SHEET = "DiagnosisBlocks"    # generated sheet (also accept legacy "DiagnosticBlocks")
DIAGBLOCKS_LEGACY = "DiagnosticBlocks"
UNRESOLVED_SHEET = "_UnresolvedIndex"   # the audit/report sheet

# --- link kinds (object grouping strategy, from object_families.csv 'link') --- #
LINK_CHANNEL = "channel"
LINK_SERIES = "series"
LINK_FLD = "fld"
LINK_PATTERN = "pattern"
LINK_NONE = "none"

P_TYPES = {"PA", "PW"}                  # field/node "P" types (allocate downward)


@dataclass(frozen=True)
class ObjectFamily:
    family: str                  # human name, e.g. "door"
    key: str                     # leading letter(s) matched against script_type, e.g. "D"
    member_types: tuple          # canonical members, e.g. ("DI","DD","DR","DL","DQ")
    anchor: str                  # the type that consumes the index, e.g. "DI1/2"
    link: str                    # LINK_* grouping strategy
    index_stride: int            # index slots per family member (currently 1)
    bits: int                    # diag bits one object consumes (0 = not diagnosed)
    diag_block: str              # Type-2 destination block stem ("" = node cabinet / Type-1)


@dataclass(frozen=True)
class IoRow:
    sheet: str
    row: int                     # 1-based row number (for cell links)
    functional_unit: str = ""
    location: str = ""
    device: str = ""
    desc_l1: str = ""
    desc_l1b: str = ""
    id_node: str = ""
    addr: str = ""               # the Bit cell (col G)
    type_hw: str = ""            # col R
    mnemonic: str = ""           # col X
    skip_reason_cell: str = ""   # col AA (cached value)
    struck: bool = False
    # existing (pre-filled) output columns - for idempotency / Mode-2 preserve
    ex_script_type: str = ""
    ex_suggested: object = None
    ex_index: str = ""
    ex_diag_cabinet: str = ""
    ex_diag_bit: str = ""

    @property
    def fld(self) -> str:
        return f"{self.functional_unit}{self.location}{self.device}"

    @property
    def node_fl(self) -> str:
        return f"{self.functional_unit}{self.location}"

    @property
    def description(self) -> str:
        return f"{self.desc_l1} {self.desc_l1b}".strip()

    @property
    def has_device(self) -> bool:
        return bool(self.device.strip())


@dataclass
class RowResult:
    iorow: IoRow
    type_def: dict | None = None        # signal_types record (config.load_signal_types) or None
    family: ObjectFamily | None = None
    script_type: str = ""               # AB (computed Mode-1 or preserved Mode-2)
    index: str = ""                      # AD
    diag_cabinet: str = ""               # AE
    diag_bit: str = ""                   # AF
    skipped: bool = False
    skip_reason: str = ""
    unresolved: bool = False
    unresolved_reason: str = ""
    unknown_type: bool = False
    error: str = ""
    prefilled: bool = False              # AB was non-empty on input (Mode-2)
    audit_mismatch: bool = False
    computed_script_type: str = ""       # what Mode-1 would have written (for the audit)


@dataclass(frozen=True)
class DiagBlock:
    id_local: int
    fu: str
    location: str
    full_name: str
    template_type: int                   # 1 = node FL; 2 = generated
    family: str = ""
    instance: int = 0

    @property
    def cabinet_text(self) -> str:
        return f"{self.id_local:03d}"


# --- signal-type record helpers (over config.load_signal_types() dicts) --- #
def td_channel(rec: dict | None) -> str:
    return (rec or {}).get("channel", "")


def td_in_diag(rec: dict | None) -> bool:
    return bool((rec or {}).get("in_diagnosis"))


def td_category(rec: dict | None) -> str:
    return (rec or {}).get("category", "")


def td_is_interface(rec: dict | None) -> bool:
    return td_category(rec).lower() == "interface"


def td_is_p(rec: dict | None) -> bool:
    return (rec or {}).get("type_id", "").upper() in P_TYPES

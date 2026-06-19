"""Core data model: the single LogEntry every check emits (plan §4.1).

ONE log structure for every phase; only the right-hand `detail` varies. The rendered line
(produced by io.render in M3) is:

    [LEVEL] <id>  <location>  |  bit | FLD | desc_l1 | desc_l1b | drawing | type-index  ::  <detail>

- `id`  is the human ordinal "<phase>-<NNN>" (phase/sub-phase number + 0-padded incremental).
- `uid` is the STABLE identity hash used for cross-run error-management treatments: it depends
  on the *finding* (phase, type, location, normalized detail), never on the volatile seq/id or
  the level (a treatment changes the level, so hashing it would break the match next run).
"""
from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass, field

# Severity levels.  PHASE is a banner (a section header), not a finding.
LEVELS = ("PHASE", "INFO", "PASS", "SKIP", "WARN", "FAIL")
# The error-only report keeps phase headers + INFO + WARN + FAIL (drops only PASS/SKIP).
ERROR_REPORT_LEVELS = ("PHASE", "INFO", "WARN", "FAIL")


def norm(s) -> str:
    """Whitespace-collapsed, lower-cased identity normalization (uid + comparisons)."""
    return re.sub(r"\s+", " ", str(s if s is not None else "").strip()).lower()


@dataclass
class InfoBlock:
    """The fixed middle of every log line; blank fields render empty."""
    bit: str = ""
    fld: str = ""
    desc_l1: str = ""
    desc_l1b: str = ""
    drawing: str = ""
    type_index: str = ""

    def cells(self) -> list:
        return [self.bit, self.fld, self.desc_l1, self.desc_l1b, self.drawing, self.type_index]


@dataclass
class LogEntry:
    level: str                                   # one of LEVELS
    phase: int                                   # phase/sub-phase number this entry belongs to (e.g. 130)
    detail: str = ""                             # the variable RIGHT part (message / cross-check payload)
    type: str = ""                               # error-type slug; gates treatments (e.g. "addr_match_dev_mismatch")
    location: str = ""                           # clickable Doc!Sheet!Cell (primary)
    location2: str = ""                          # second-workbook link (cross-checks); "" otherwise
    info: InfoBlock = field(default_factory=InfoBlock)
    seq: int = 0                                 # 1-based incremental within its phase (assigned by number_entries)

    @property
    def id(self) -> str:
        """Human ordinal, '<phase>-<NNN>' e.g. '130-007'."""
        return f"{self.phase}-{self.seq:03d}"

    @property
    def uid(self) -> str:
        """Stable identity hash for cross-run treatments (see module docstring)."""
        basis = "|".join((str(self.phase), norm(self.type), norm(self.location), norm(self.detail)))
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:10]


def number_entries(entries) -> list:
    """Assign each non-banner entry its 1-based `seq` within its phase, in list order.
    Idempotent for a given ordering. Returns the same list for chaining."""
    counters: dict = {}
    for e in entries:
        if e.level == "PHASE":
            continue
        counters[e.phase] = counters.get(e.phase, 0) + 1
        e.seq = counters[e.phase]
    return entries


def banner(phase: int, text: str) -> LogEntry:
    """A PHASE section-header entry."""
    return LogEntry(level="PHASE", phase=phase, detail=text)

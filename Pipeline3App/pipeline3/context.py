"""The PipelineContext threaded through every phase (plan §4).

Separates in-memory state (recomputed) from artifacts (paths on disk under the output root - the
Open2App handoff). The single database is the CSV `IODatabase.csv`; `rows` is just that database
loaded. `populated_path` carries phase 200's output to phase 300, keeping `params` immutable.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional

from pipeline3.core.model import LogEntry, split_level


@dataclass
class PipelineContext:
    params: dict
    out_root: str
    lang: str = "en"
    profile: str = "main"

    # loaded-once config (cached on first use by phases)
    signal_types: Optional[dict] = None
    device_db: Optional[dict] = None

    # in-memory pipeline state, filled as phases run
    populated_path: str = ""           # phase 200 output; phase 300 reads THIS (or the raw io_list)
    rows: Optional[list] = None         # the staged CentralDatabase (IODatabase.csv loaded)
    diag_blocks: Optional[dict] = None  # cabinet -> block info (from the DiagnosisBlocks sheet)

    # accumulated across phases
    log: list = field(default_factory=list)        # LogEntry objects - the ONE log for every phase
    artifacts: dict = field(default_factory=dict)   # OUTPUT_PATHS key -> written path
    completed: set = field(default_factory=set)     # phase numbers already run (memoization)

    # the unified log engine (§4.1): emit() appends a LogEntry tagged with the phase the engine runs.
    _current_phase: int = 0             # set by the engine (app._run_one / run_subphase) before a phase runs
    _phase_start: int = 0               # index in `log` where the current phase's entries begin
    on_progress: Optional[Callable] = None   # live hook for the raw emit text (GUI status bar / CLI print)
    on_phase_log: Optional[Callable] = None  # fired with a phase's LogEntry slice when it completes (GUI render)

    def emit(self, *args) -> None:
        """The progress sink, now part of the ONE log engine: every emit becomes a LogEntry under the
        current phase's banner (level inferred + token stripped by model.split_level), and the raw text
        is forwarded to the live hook (status bar / console)."""
        msg = " ".join(str(a) for a in args)
        level, detail = split_level(msg)
        self.log.append(LogEntry(level=level, phase=self._current_phase, detail=detail))
        if self.on_progress is not None:
            self.on_progress(msg)

    def absorb(self, result) -> None:
        """Merge a PhaseResult's artifacts (and any log it still returns) into the context. Phases now
        append their LogEntries to ctx.log directly (via emit()/ctx.log); `result.log` is kept only as
        an incremental-safety path for a phase that still returns one."""
        if result is None:
            return
        if result.log:
            self.log.extend(result.log)
        self.artifacts.update(result.artifacts)

    def io_list_path(self) -> str:
        """The workbook staging/validation should read: the populated copy if phase 200 produced
        one, otherwise the raw input doc (the validation-only profile path)."""
        return self.populated_path or self.params["io_list"]["path"]

    @classmethod
    def create(cls, params: dict | None = None, profile: str = "main",
               lang: str | None = None, emit: Callable | None = None) -> "PipelineContext":
        from pipeline3.core import config
        params = params if params is not None else config.load_params()
        ctx = cls(
            params=params,
            out_root=config.output_root(params),
            lang=lang or params.get("language") or "en",
            profile=profile,
        )
        if emit is not None and emit is not print:   # back-compat: `emit=` now drives the live hook
            ctx.on_progress = emit
        return ctx

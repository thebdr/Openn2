"""The PipelineContext threaded through every phase (plan §4).

Separates in-memory state (recomputed) from artifacts (paths on disk under the output root - the
Open2App handoff). The single database is the CSV `IODatabase.csv`; `rows` is just that database
loaded. `populated_path` carries phase 200's output to phase 300, keeping `params` immutable.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional


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
    log: list = field(default_factory=list)        # LogEntry objects
    artifacts: dict = field(default_factory=dict)   # OUTPUT_PATHS key -> written path
    completed: set = field(default_factory=set)     # phase numbers already run (memoization)

    emit: Callable = print              # progress sink: emit(message) - CLI prints / GUI queues / tests collect

    def absorb(self, result) -> None:
        """Merge a PhaseResult's log + artifacts into the context."""
        if result is None:
            return
        self.log.extend(result.log)
        self.artifacts.update(result.artifacts)

    def io_list_path(self) -> str:
        """The workbook staging/validation should read: the populated copy if phase 200 produced
        one, otherwise the raw input doc (the validation-only profile path)."""
        return self.populated_path or self.params["io_list"]["path"]

    @classmethod
    def create(cls, params: dict | None = None, profile: str = "main",
               lang: str | None = None, emit: Callable = print) -> "PipelineContext":
        from pipeline3.core import config
        params = params if params is not None else config.load_params()
        return cls(
            params=params,
            out_root=config.output_root(params),
            lang=lang or params.get("language") or "en",
            profile=profile,
            emit=emit,
        )

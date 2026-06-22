"""app_main.py - the Pipeline3 operator window (the interactive twin of the CLI).

A dark-by-default window (dark title bar too) whose top **phase bar is generated from the phase
registry** (`phasebar.build_spec` over `registry().presentation_order()`), with the pink Run-Pipeline
master on the left. A phase header runs the whole phase; its chevron dropdown lists that phase's
buttons (action steps / opens / specials). The pipeline runs on a worker thread; its `emit` output is
queued and drained into the `LogView` on the Tk main thread. Font: bundled Monaspace Neon.

First GUI slice (M11): the registry-driven bar + dark theme/title + Monaspace + worker-run wiring +
log view. The YAML-explorer config, Files tab, Project Manager, designer GUI, and Excel-cell links
land in later slices.
"""
from __future__ import annotations
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

from pipeline3 import app
import pipeline3.phases  # noqa: F401  (side-effect: registers every phase into the registry)
from pipeline3.context import PipelineContext
from pipeline3.core import config
from pipeline3.registry import registry
from pipeline3.gui import fonts, theme, darktitle, phasebar, logview

_ICON = os.path.join(config.APP_ROOT, "assets", "Pipeline3.png")


class App:
    def __init__(self, root: tk.Tk, profile: str = "main"):
        self.root = root
        self.profile = profile
        self.reg = registry()
        self.q: queue.Queue = queue.Queue()
        self._run_buttons: list = []
        self._busy = False
        self._ctx: PipelineContext | None = None

        fonts.register()
        self.font_family = fonts.family(root)
        self.dark = True
        self.pal = theme.apply_base(root, self.font_family, self.dark)   # sv-ttk + Monaspace default

        root.title("Pipeline3")
        root.configure(bg=self.pal["bg"])
        root.geometry("1180x740")
        root.minsize(900, 560)
        try:
            self._icon = tk.PhotoImage(file=_ICON)
            root.iconphoto(True, self._icon)
        except Exception:  # noqa: BLE001
            pass

        self._build()
        darktitle.apply(root)
        root.after(60, self._drain)

    # ---- layout ---------------------------------------------------------- #
    def _build(self):
        top = ttk.Frame(self.root, padding=(8, 6, 8, 2))
        top.pack(side="top", fill="x")
        ttk.Label(top, text="PIPELINE3", font=(self.font_family, 13, "bold")).pack(side="left")
        ttk.Button(top, text="Clear Log", command=self._clear).pack(side="right")
        ttk.Button(top, text="Open Output", command=lambda: self._startfile(self._out_root())).pack(side="right", padx=6)

        run, phases = phasebar.build_spec(
            self.reg, "en",
            run_cb=lambda: self._start_all,
            phase_cb=lambda ph: (lambda n=ph.number: self._start(n)),
            button_cb=self._button_cb,
            include_run=(self.profile == "main"))
        self.bar = phasebar.PhaseBar(self.root, run, phases, self._run_buttons,
                                     dark=self.dark, bg=self.pal["bg"], font=self.font_family, padding=(6, 2))
        self.bar.pack(side="top", fill="x", padx=4)
        ttk.Separator(self.root, orient="horizontal").pack(side="top", fill="x", pady=(4, 0))

        self.log = logview.LogView(self.root, self.pal, self.font_family)
        self.log.pack(side="top", fill="both", expand=True, padx=4, pady=4)

        bottom = ttk.Frame(self.root, padding=(8, 2))
        bottom.pack(side="bottom", fill="x")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(bottom, textvariable=self.status).pack(side="left")
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=160)
        self.progress.pack(side="right")

        self.log.append("Pipeline3 - operator GUI", "SECTION")
        self.log.append(f"font: {self.font_family}   profile: {self.profile}   "
                        f"phases: {', '.join(str(p.number) for p in self.reg.presentation_order())}")

    # ---- button wiring (from the registry) ------------------------------- #
    def _button_cb(self, button, phase):
        if button.kind == "disabled":
            return None
        if button.kind == "open":
            key = button.command_key.split(":", 1)[1] if ":" in button.command_key else ""
            return lambda k=key: self._open_artifact(k)
        if button.kind == "special":
            return lambda b=button: self.status.set(f"{button.command_key}: not wired yet")
        if button.number is not None:                  # action -> run the (sub-)phase number
            return lambda n=button.number: self._start(n)
        return None

    # ---- worker run ------------------------------------------------------ #
    def _ensure_ctx(self) -> PipelineContext:
        if self._ctx is None:
            self._ctx = PipelineContext.create(profile=self.profile, emit=self._emit)
        return self._ctx

    def _out_root(self) -> str:
        try:
            return self._ensure_ctx().out_root
        except Exception:  # noqa: BLE001
            return config.output_root(config.load_params())

    def _emit(self, *args):                            # the ctx.emit sink (called on the worker thread)
        self.q.put(("log", " ".join(str(a) for a in args)))

    def _start(self, number: int):
        self._run(lambda ctx: self._run_number(ctx, number), f"running {number} ...")

    def _start_all(self):
        self._run(app.run_all, "running the whole pipeline ...")

    def _run(self, work, status: str):
        if self._busy:
            return
        self.q.put(("busy", True))
        self.q.put(("status", status))

        def job():
            try:
                ctx = self._ensure_ctx()
                work(ctx)
                self.q.put(("status", "Ready"))
            except Exception as e:  # noqa: BLE001
                self.q.put(("log", f"[ERROR] {type(e).__name__}: {e}"))
                self.q.put(("status", "error - see the log"))
            finally:
                self.q.put(("busy", False))
        threading.Thread(target=job, daemon=True).start()

    def _run_number(self, ctx, number: int):
        """Run a whole phase (hundreds) or one sub-phase (its prerequisites first)."""
        if number % 100 == 0:
            app.run_phase(ctx, number)
            return
        parent = (number // 100) * 100
        ph = self.reg.get(parent)
        for req in ph.requires:
            app.run_phase(ctx, req)
        sub = next((s for s in (ph.sub_phases or []) if s.number == number), None)
        if sub is None or sub.run is None:
            self._emit(f"{number}: not implemented")
            return
        ctx.absorb(sub.run(ctx))

    # ---- queue drain (main thread) --------------------------------------- #
    def _drain(self):
        try:
            while True:
                ev = self.q.get_nowait()
                if ev[0] == "log":
                    self.log.append(ev[1])
                elif ev[0] == "busy":
                    self._set_busy(ev[1])
                elif ev[0] == "status":
                    self.status.set(ev[1])
        except queue.Empty:
            pass
        self.root.after(60, self._drain)

    def _set_busy(self, busy: bool):
        self._busy = busy
        for b in self._run_buttons:
            try:
                b.configure(state="disabled" if busy else "normal")
            except tk.TclError:
                pass
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    # ---- opens / utilities ----------------------------------------------- #
    def _clear(self):
        self.log.clear()

    def _startfile(self, path: str):
        if path and os.path.exists(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
                self.status.set(f"opened {os.path.basename(path) or path}")
                return
            except Exception as e:  # noqa: BLE001
                self.status.set(str(e))
                return
        self.status.set("not found (run the phase first)" if path else "nothing to open")

    def _open_artifact(self, key: str):
        params = config.load_params()
        if key == "io_list":
            return self._startfile((params.get("io_list") or {}).get("path", ""))
        if key == "ce":
            return self._startfile((params.get("ce") or {}).get("path", ""))
        if key in config.OUTPUT_PATHS:
            base = config.out_path(self._out_root(), key)
            for cand in (base, base + ".txt", base + ".csv"):     # report bases carry an extension
                if os.path.exists(cand):
                    return self._startfile(cand)
            return self._startfile(base)
        self.status.set(f"open '{key}': not wired yet")


def main(profile: str = "main"):
    root = tk.Tk()
    App(root, profile=profile)
    root.mainloop()


if __name__ == "__main__":
    main()

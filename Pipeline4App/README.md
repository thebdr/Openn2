# Pipeline4App (PL4)

The Python pipeline that turns a hand-authored **I/O List** (+ Cause&Effect matrix) into the TIA
Portal import surface (`BuilderData/`): PLC tags, data blocks, diagnosis lists, hardware stations,
software blocks, SCL sources. Built around a **single-source-of-truth database** (CSV-with-JSON-cells
tables under `Database/`); every export is a byte-stable projection of those tables. The C# importer
(**Openn3App / OP4**, in this same repo) reads `BuilderData/` into a TIA project.

## Quickstart

1. **Python 3.10+** (3.12–3.14 tested) from [python.org](https://www.python.org/downloads/) —
   keep the default options; tkinter is included.
2. Install the dependencies:

   ```
   cd Pipeline4App
   pip install -r requirements.txt
   ```

3. Run the operator GUI:

   ```
   python launch_gui.py
   ```

   Use **Project ▾** to create/open a project, pick the I/O List on the **Documents** tab, then run
   the phases from the phase bar (the pink **Run** button runs the whole chain).

## Optional extras

- **FileXY native engine** — a Rust speedup for the built-in table viewer (~19× faster xlsx loads).
  Not required: without it a pure-Python fallback is used automatically. To build it: install
  [rustup](https://rustup.rs/), then `py rust/install_native.py` from `../FileXYApp`.
  `FILEXY_RUST=0` opts out at runtime.
- **Excel** (or LibreOffice) — for the clickable `Sheet!Cell` log links and the
  "Open externally" buttons.

## Tests

Plain-python suites, no framework:

```
cd Pipeline4App
python tests/unit/test_staging.py        # one suite
for %f in (tests\unit\test_*.py) do @python %f   # all of them (cmd)
```

## Deeper documentation

- `DESIGN.md` — the architecture rationale (the SSOT thesis).
- `CLAUDE.md` — the live architecture + per-phase state (the most detailed reference).
- `HANDOFF.md` — the point-in-time "what's next".
- `Shared/PL4_OP4_coordination.md` (repo root) — the PL⇄OP `BuilderData/` contract + its change log.

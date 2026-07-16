# The phase bar

One button per phase, in pipeline order, each showing its icon, number, and name. The pink
**Run Pipeline** master on the left runs every runnable phase in dependency order and halts the chain
on a blocking FAIL.

## Buttons

- **Click a phase header** to run that whole phase (its prerequisites are rebuilt first).
- **Click the thin ▾ strip** under a phase to open its sub-steps:
  - white = run just that sub-step,
  - blue = open a produced file/folder,
  - orange = a special manual action (e.g. *245 Risky Index Fill* - deliberately not in the pipeline),
  - grey = a step that exists in the operator oracle but is not available yet.
- A dropdown taller than the window clamps at the app border and scrolls (mouse wheel works).

## Icons

The icons live in [assets/icons/](src://assets/icons) with a `phase_icons.yaml` registry mapping each
phase to its PNG - a new phase needs one row and one 72x72 image, no code. Official art is Twemoji
(see the NOTICE file); the custom ones are drawn by
[scripts/gen_custom_icons.py](src://scripts/gen_custom_icons.py).

Phase 200 (Documents Fill Out) writes back into the source document, so it is kept OUT of Run
Pipeline by design - run it deliberately.

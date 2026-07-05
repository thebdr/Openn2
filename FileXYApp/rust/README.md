# filexy-core (Rust)

The Rust port of FileXY's pure grid engine. `filexy/core.py` is the executable **spec**: every
Rust test vector mirrors a Python golden test, so the two engines stay behaviour-identical while
the port grows. The Python engine keeps running the app today; this crate replaces it piece by
piece once the bindings land.

## Port map

| core.py | Rust module | Notes |
|---|---|---|
| `natural_key`, `cycle_sort`, `sorted_view` | `src/sort.rs` | derive-`Ord` on `Part`/`NaturalKey` replaces Python's tuple trick: variant order gives Num < Text, field order puts blanks last |
| `filter_passes`, `apply_filters`, `distinct_values` | `src/filter.rs` | `col: None` = the global quick search; a broken regex matches nothing |
| `updated_selection` | `src/select.rs` | plain / Ctrl-toggle / Shift-range with a sticky anchor |
| `cell_kind`, `compute_col_widths`, `fit_text`, `sanitize`, `cell_at`, `boundary_at`, `fit_col_width`, `frozen_width`, `hit_x` | `src/layout.rs` | pixel-measure functions injected as closures, same as Python |
| `to_tsv`, `column_stats`, `stats_text` | `src/export.rs` | `num()` ≈ Python's `%g` (integral values drop the `.0`) |

## Build + test

```sh
export PATH="$PATH:$HOME/.cargo/bin"   # Git Bash; PowerShell has it on PATH already
cd FileXYApp/rust/filexy-core
cargo test
```

## Next steps (the learning roadmap)

1. **PyO3 bindings** — add `pyo3` (feature `extension-module`) + [maturin](https://www.maturin.rs)
   and expose the engine as a Python module, so `filexy/grid.py` can swap
   `from filexy import core` for the compiled engine behind a flag. The Python golden tests then
   run against BOTH engines.
2. **calamine loader** — read `.xlsx` natively (the current Python path is the slow part on big
   workbooks); return rows as display strings ready for the grid.
3. **egui shell** — only if the standalone FileXY exe ever needs to drop Tk entirely.

Rust nuggets encountered so far:

- Deriving `Ord` compares enum variants by declaration order and struct fields top-to-bottom —
  which encodes Python's `(0, int) < (1, str)` key trick *in the type* (`src/sort.rs`).
- `impl Fn(&str) -> i32` parameters are the closure-injection pattern: the layout maths stays
  display-free and testable with fake per-char measures, exactly like the Python design.
- `f64` has no `Ord` (NaN), so min/max fold through `reduce(f64::min)` instead of `.min()`.
- Labeled loops (`'rows: for … continue 'rows`) are the clean port of Python's for/else-style
  filter cascade.

# filexy-core (Rust)

The Rust port of FileXY's pure grid engine. `filexy/core.py` is the executable **spec**: every
Rust test vector mirrors a Python golden test, so the two engines stay behaviour-identical while
the port grows.

**The engine is live.** Build it once with

```sh
py rust/install_native.py        # from FileXYApp/ - maturin build + drops filexy_core.pyd here
```

and `filexy.core` swaps its data-sized functions (filtering, sorting, export, bulk sanitize) plus
the whole xlsx loader for the compiled ones at import - transparently for the standalone viewer
AND PL4's embedding. `filexy.core.ENGINE` reports which engine is active (the standalone window
title shows it), `FILEXY_RUST=0` is the no-rebuild escape hatch back to pure Python. Parity is
gated by `tests/test_native.py`: shared golden vectors through both engines plus a CELL-BY-CELL
comparison of the calamine loader against the openpyxl loader on the repo's real workbooks
(first benchmark: DeviceTypesDatabase.xlsx, 28 sheets / ~7k rows - openpyxl ~300 ms, calamine
~15-20 ms, **~17-19x**).

## Port map

| core.py | Rust module | Notes |
|---|---|---|
| `natural_key`, `cycle_sort`, `sorted_view` | `src/sort.rs` | derive-`Ord` on `Part`/`NaturalKey` replaces Python's tuple trick: variant order gives Num < Text, field order puts blanks last |
| `filter_passes`, `apply_filters`, `distinct_values` | `src/filter.rs` | `col: None` = the global quick search; a broken regex matches nothing |
| `updated_selection` | `src/select.rs` | plain / Ctrl-toggle / Shift-range with a sticky anchor |
| `cell_kind`, `compute_col_widths`, `fit_text`, `sanitize`, `cell_at`, `boundary_at`, `fit_col_width`, `frozen_width`, `hit_x` | `src/layout.rs` | pixel-measure functions injected as closures, same as Python |
| `to_tsv`, `column_stats`, `stats_text` | `src/export.rs` | `num()` ≈ Python's `%g` (integral values drop the `.0`) |
| files.py `read_xlsx`, `xlsx_sheets` | `src/xlsx.rs` | calamine; `py_float_str` renders numbers the way Python `str()`s openpyxl values, XML newline normalization |
| — | `src/python.rs` | the PyO3 bindings (`filexy_core` module, feature `python`, abi3 ≥ 3.10) |

## Build + test

```sh
export PATH="$PATH:$HOME/.cargo/bin"   # Git Bash; PowerShell has it on PATH already
cd FileXYApp/rust/filexy-core
cargo test
```

## Next steps (the learning roadmap)

1. ~~**PyO3 bindings**~~ DONE — `src/python.rs` + maturin (`rust/install_native.py`); the swap
   lives at the end of `filexy/core.py` and `filexy/files.py`.
2. ~~**calamine loader**~~ DONE — `src/xlsx.rs`, cell-identical to openpyxl (one accepted
   difference: trailing formatting-only rows are dropped instead of rendered blank).
3. **A resident `Table` handle** (`#[pyclass]`) — today every call converts `list[list[str]]`
   both ways; keeping the loaded table IN Rust and passing only views/indices would cut the
   remaining FFI cost. Worth it once the grid feels slow on 50k+ rows, not before.
4. **egui shell** — only if the standalone FileXY exe ever needs to drop Tk entirely.

Rust nuggets encountered so far:

- Deriving `Ord` compares enum variants by declaration order and struct fields top-to-bottom —
  which encodes Python's `(0, int) < (1, str)` key trick *in the type* (`src/sort.rs`).
- `impl Fn(&str) -> i32` parameters are the closure-injection pattern: the layout maths stays
  display-free and testable with fake per-char measures, exactly like the Python design.
- `f64` has no `Ord` (NaN), so min/max fold through `reduce(f64::min)` instead of `.min()`.
- Labeled loops (`'rows: for … continue 'rows`) are the clean port of Python's for/else-style
  filter cascade.
- `sort_by_key` + `reverse()` is NOT Python's `sorted(reverse=True)`: reversing flips ties too.
  A reversed **comparator** (`b.cmp(&a)`) keeps equal keys in original order - the stable-desc
  contract the grid relies on (`src/sort.rs`).
- Feature-gated deps (`pyo3 = { optional = true }` + `[features] python = ["dep:pyo3"]`) let
  `cargo test` run without linking Python while maturin builds the extension with it.
- Rust's `regex` crate has no lookarounds/backreferences (by design - guaranteed linear time), so
  the Python wrapper routes such patterns back to `re` (`core.py::_needs_python_regex`).
- XML parsers must normalize `\r\n` to `\n` in character content (XML 1.0 §2.11) - openpyxl's
  does, quick-xml under calamine doesn't, hence `normalize_newlines` in `src/xlsx.rs`.
- `to_lowercase()` is SIMPLE case folding; Python's `str.casefold()` is FULL folding (ß -> ss,
  µ -> μ). The `caseless` crate provides the full fold - without it, filtering "ss" misses
  "straße" (`src/filter.rs`, `src/sort.rs`).
- Compile the regex ONCE per filter, not per cell: Python's `re` module caches compiled patterns
  behind `re.search(pattern, ...)`, so a naive line-for-line port silently recompiles 20k times
  per keystroke (`Matcher` in `src/filter.rs`).
- Two regex engines can't be reconciled by syntax lists. The exact fix: ask each engine.
  `re.compile` failing -> the pattern must "match nothing" (run it on Python); the native
  `regex_ok()` failing -> Python-only syntax (run it on Python). See `core.py::_install_native`.

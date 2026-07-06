//! filexy-core - the Rust port of FileXY's pure grid engine (`filexy/core.py` is the executable
//! spec; every test vector here mirrors the Python golden tests, so the two engines stay
//! behaviour-identical while the port grows).
//!
//! Port map (core.py -> module):
//!   natural_key / cycle_sort / sorted_view      -> sort
//!   filter_passes / apply_filters / distinct    -> filter   (col: None = the quick search)
//!   updated_selection                           -> select
//!   cell_kind / widths / fit / hit tests        -> layout   (pixel-measure closures injected)
//!   to_tsv / column_stats / stats_text          -> export
//!   files.py read_xlsx / xlsx_sheets            -> xlsx     (calamine - the performance goal)
//!
//! With feature "python" (how maturin builds it), `python.rs` exposes the data-sized functions
//! as the `filexy_core` extension module that filexy/core.py + files.py swap in at import.

pub mod export;
pub mod filter;
pub mod layout;
#[cfg(feature = "python")]
mod python;
pub mod select;
pub mod sort;
pub mod xlsx;

pub use export::{column_stats, stats_text, to_tsv, ColumnStats};
pub use filter::{apply_filters, distinct_values, filter_passes, FilterSpec};
pub use layout::{
    boundary_at, cell_at, cell_kind, compute_col_widths, fit_col_width, fit_text, frozen_width,
    hit_x, sanitize, CellKind, FIT_MAX_W, LONG_CELL_CHARS, MAX_COL_W, MIN_COL_W, MIN_DRAG_W,
    PAD_X, RESIZE_TOL,
};
pub use select::updated_selection;
pub use sort::{cycle_sort, natural_key, sorted_view, Dir, NaturalKey, Part, SortState};
pub use xlsx::{load_xlsx, py_float_str, sheet_names};

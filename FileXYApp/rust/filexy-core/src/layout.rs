//! Layout + hit-testing - the port of core.py's measure-injected pixel maths. The pixel-measure
//! functions are CLOSURES (`Fn(&str) -> i32`), exactly like the Python design: the engine stays
//! display-free and unit-testable with fake measures.

pub const LONG_CELL_CHARS: usize = 64;
pub const MIN_COL_W: i32 = 60;
pub const MAX_COL_W: i32 = 420;
pub const MIN_DRAG_W: i32 = 30;
pub const FIT_MAX_W: i32 = 1200;
pub const RESIZE_TOL: f64 = 5.0;
pub const PAD_X: i32 = 6;
const SAMPLE_ROWS: usize = 200;
const ELLIPSIS: char = '…';

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CellKind {
    Normal,
    Small,
}

/// Small (the narrow font) when the cell exceeds LONG_CELL_CHARS.
pub fn cell_kind(text: &str) -> CellKind {
    if text.chars().count() > LONG_CELL_CHARS { CellKind::Small } else { CellKind::Normal }
}

fn char_prefix(text: &str, chars: usize) -> &str {
    match text.char_indices().nth(chars) {
        Some((i, _)) => &text[..i],
        None => text,
    }
}

/// Per-column pixel widths adapted to the data: the widest of the header and the sampled cells
/// (each measured in ITS OWN rendering font), clamped to [MIN_COL_W, MAX_COL_W].
pub fn compute_col_widths(
    columns: &[String],
    rows: &[Vec<String>],
    measure_normal: impl Fn(&str) -> i32,
    measure_small: impl Fn(&str) -> i32,
    measure_header: impl Fn(&str) -> i32,
) -> Vec<i32> {
    columns
        .iter()
        .enumerate()
        .map(|(c, column)| {
            let mut width = measure_header(column) + 2 * PAD_X;
            for row in rows.iter().take(SAMPLE_ROWS) {
                let cell = row.get(c).map(String::as_str).unwrap_or("");
                let w = match cell_kind(cell) {
                    CellKind::Small => measure_small(char_prefix(cell, LONG_CELL_CHARS)),
                    CellKind::Normal => measure_normal(cell),
                };
                width = width.max(w + 2 * PAD_X);
            }
            width.clamp(MIN_COL_W, MAX_COL_W)
        })
        .collect()
}

/// `text` truncated with an ellipsis to fit `avail_px` (binary search over the cut point).
pub fn fit_text(text: &str, avail_px: i32, measure: impl Fn(&str) -> i32) -> String {
    if measure(text) <= avail_px {
        return text.to_string();
    }
    let chars = text.chars().count();
    let (mut lo, mut hi) = (0usize, chars);
    while lo < hi {
        let mid = (lo + hi + 1) / 2;
        let candidate = format!("{}{}", char_prefix(text, mid), ELLIPSIS);
        if measure(&candidate) <= avail_px { lo = mid } else { hi = mid - 1 }
    }
    format!("{}{}", char_prefix(text, lo), ELLIPSIS)
}

/// One display line per cell: the first line of a multi-line value + an ellipsis marker.
pub fn sanitize(cell: &str) -> String {
    match cell.split_once('\n') {
        Some((first, _)) => format!("{first}{ELLIPSIS}"),
        None => cell.to_string(),
    }
}

/// The `(row, col, cell_x0)` under canvas point (x, y), or None outside the data.
pub fn cell_at(widths: &[i32], row_h: i32, n_rows: usize, x: f64, y: f64) -> Option<(usize, usize, i32)> {
    if y < 0.0 || row_h <= 0 {
        return None;
    }
    let row = (y / row_h as f64) as usize;
    if row >= n_rows {
        return None;
    }
    let mut x0 = 0i32;
    for (col, &width) in widths.iter().enumerate() {
        if (x0 as f64) <= x && x < (x0 + width) as f64 {
            return Some((row, col, x0));
        }
        x0 += width;
    }
    None
}

/// The column whose RIGHT edge sits within `tol` px of canvas-x `x` (the resize grab zone).
pub fn boundary_at(widths: &[i32], x: f64, tol: f64) -> Option<usize> {
    let mut edge = 0i32;
    for (i, &width) in widths.iter().enumerate() {
        edge += width;
        if (x - edge as f64).abs() <= tol {
            return Some(i);
        }
    }
    None
}

/// The double-click auto-fit width: the widest of the header + EVERY row's cell, clamped
/// [MIN_DRAG_W, FIT_MAX_W] - no MAX_COL_W cap, no sampling (a fit means the content fits).
pub fn fit_col_width(
    columns: &[String],
    rows: &[Vec<String>],
    c: usize,
    measure_normal: impl Fn(&str) -> i32,
    measure_small: impl Fn(&str) -> i32,
    measure_header: impl Fn(&str) -> i32,
) -> i32 {
    let mut width = measure_header(columns.get(c).map(String::as_str).unwrap_or("")) + 2 * PAD_X;
    for row in rows {
        let cell = row.get(c).map(String::as_str).unwrap_or("");
        let w = match cell_kind(cell) {
            CellKind::Small => measure_small(cell),
            CellKind::Normal => measure_normal(cell),
        };
        width = width.max(w + 2 * PAD_X);
    }
    width.clamp(MIN_DRAG_W, FIT_MAX_W)
}

/// The pixel width of the pinned strip: the first `frozen` columns.
pub fn frozen_width(widths: &[i32], frozen: usize) -> i32 {
    widths.iter().take(frozen).sum()
}

/// Map a WIDGET-space x to the NATURAL canvas x under pinned columns: inside the strip the widget
/// coords ARE the pinned columns' natural [0, frozen_w) coords; past it, normal scrolling applies.
pub fn hit_x(widget_x: f64, x_left: f64, frozen_w: f64) -> f64 {
    if widget_x < frozen_w { widget_x } else { x_left + widget_x }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn measure(px_per_char: i32) -> impl Fn(&str) -> i32 {
        move |s: &str| px_per_char * s.chars().count() as i32
    }

    fn strs(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn kind_boundary_matches_python() {
        assert_eq!(cell_kind(&"x".repeat(64)), CellKind::Normal);
        assert_eq!(cell_kind(&"x".repeat(65)), CellKind::Small);
        assert_eq!(cell_kind(""), CellKind::Normal);
    }

    #[test]
    fn widths_adapt_and_clamp() {
        let cols = strs(&["c"]);
        let rows = vec![strs(&[&"x".repeat(30)])];
        let w = compute_col_widths(&cols, &rows, measure(10), measure(4), measure(10));
        assert_eq!(w, vec![300 + 12]);
        let long = vec![strs(&[&"y".repeat(100)])];
        let w = compute_col_widths(&cols, &long, measure(10), measure(4), measure(10));
        assert_eq!(w, vec![4 * 64 + 12], "a long cell measures in the SMALL font, 64-char capped");
        let long2 = vec![strs(&[&"z".repeat(500)])];
        let w2 = compute_col_widths(&cols, &long2, measure(10), measure(4), measure(10));
        assert_eq!(w, w2, "the small-font measure caps at 64 chars - longer changes nothing");
        let wide = vec![strs(&[&"w".repeat(60)])]; // 60 chars, NORMAL font: 612px
        let w = compute_col_widths(&cols, &wide, measure(10), measure(4), measure(10));
        assert_eq!(w, vec![MAX_COL_W], "clamped at MAX_COL_W");
        let w = compute_col_widths(&cols, &[], measure(10), measure(4), measure(10));
        assert_eq!(w, vec![MIN_COL_W], "empty data clamps up to MIN_COL_W");
    }

    #[test]
    fn fit_and_hit_tests() {
        assert_eq!(fit_text("abcdef", 30, measure(10)), "ab…", "ellipsis fit");
        assert_eq!(sanitize("one\ntwo"), "one…", "multi-line collapses to line 1 + marker");
        assert_eq!(sanitize("plain"), "plain");
        assert_eq!(cell_at(&[100, 80], 20, 3, 150.0, 45.0), Some((2, 1, 100)));
        assert_eq!(cell_at(&[100], 20, 3, 50.0, 100.0), None, "past the last row");
        assert_eq!(boundary_at(&[100, 80], 102.0, RESIZE_TOL), Some(0));
        assert_eq!(boundary_at(&[100, 80], 120.0, RESIZE_TOL), None);
        let w = fit_col_width(&strs(&["c"]), &[strs(&[&"x".repeat(60)])], 0,
                              measure(10), measure(4), measure(10));
        assert_eq!(w, 600 + 12, "the auto-fit ignores MAX_COL_W");
    }

    #[test]
    fn pinned_mapping_matches_python() {
        assert_eq!(frozen_width(&[100, 80, 200], 2), 180);
        assert_eq!(frozen_width(&[100, 80], 0), 0);
        assert_eq!(hit_x(50.0, 300.0, 180.0), 50.0, "inside the strip = natural coords");
        assert_eq!(hit_x(200.0, 300.0, 180.0), 500.0, "past the strip = canvasx");
        assert_eq!(hit_x(50.0, 300.0, 0.0), 350.0, "no strip = plain canvasx");
        assert!(hit_x(180.0, 300.0, 180.0) >= 480.0, "the covered zone is unreachable");
    }
}

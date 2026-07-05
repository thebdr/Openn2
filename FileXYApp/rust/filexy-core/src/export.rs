//! Clipboard/export helpers - the port of core.py's to_tsv / column_stats / stats_text.

/// The view as clipboard-ready TSV (Excel pastes it into cells). Cells are display strings
/// already; embedded tabs collapse to spaces so the column structure survives.
pub fn to_tsv(columns: &[String], rows: &[Vec<String>], view: &[usize], header: bool) -> String {
    let line = |cells: &[String]| {
        cells.iter().map(|c| c.replace('\t', " ")).collect::<Vec<_>>().join("\t")
    };
    let mut out = if header { vec![line(columns)] } else { Vec::new() };
    out.extend(view.iter().map(|&i| line(&rows[i])));
    out.join("\n")
}

/// One column's stats over the VISIBLE rows - the filter popup's footer. Blank means exactly ""
/// (a whitespace-only cell is non-blank); distinct counts non-blank values; sum/min/max exist only
/// when at least one cell parses as a number.
#[derive(Debug, Clone, PartialEq)]
pub struct ColumnStats {
    pub rows: usize,
    pub blank: usize,
    pub distinct: usize,
    pub numeric: usize,
    pub sum: Option<f64>,
    pub min: Option<f64>,
    pub max: Option<f64>,
}

pub fn column_stats(rows: &[Vec<String>], view: &[usize], col: usize) -> ColumnStats {
    let mut blank = 0usize;
    let mut distinct = std::collections::HashSet::new();
    let mut numbers = Vec::new();
    for &i in view {
        let cell = rows[i].get(col).map(String::as_str).unwrap_or("");
        if cell.is_empty() {
            blank += 1;
            continue;
        }
        distinct.insert(cell.to_string());
        if let Ok(n) = cell.trim().parse::<f64>() {
            // trim: Python's float() ignores surrounding whitespace
            numbers.push(n);
        }
    }
    ColumnStats {
        rows: view.len(),
        blank,
        distinct: distinct.len(),
        numeric: numbers.len(),
        sum: (!numbers.is_empty()).then(|| numbers.iter().sum()),
        min: numbers.iter().copied().reduce(f64::min),
        max: numbers.iter().copied().reduce(f64::max),
    }
}

/// Like Python's %g for the common cases: an integral value prints without the trailing ".0"
/// ("Σ 4", not "Σ 4.0"). (Full precision for non-integral values, where %g rounds to 6 sig digits.)
fn num(n: f64) -> String {
    if n == n.trunc() && n.abs() < 1e15 {
        format!("{}", n as i64)
    } else {
        format!("{n}")
    }
}

/// The one-line status text: "N rows · N distinct[ · N blank][ · Σ S · min m · max M]".
pub fn stats_text(s: &ColumnStats) -> String {
    let mut parts = vec![format!("{} rows", s.rows), format!("{} distinct", s.distinct)];
    if s.blank > 0 {
        parts.push(format!("{} blank", s.blank));
    }
    if let (Some(sum), Some(min), Some(max)) = (s.sum, s.min, s.max) {
        parts.push(format!("Σ {}", num(sum)));
        parts.push(format!("min {}", num(min)));
        parts.push(format!("max {}", num(max)));
    }
    parts.join(" · ")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn strs(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn tsv_matches_python() {
        let cols = strs(&["A", "B"]);
        let rows = vec![strs(&["1.5", "x\ty"]), strs(&["2.5", "z"])];
        assert_eq!(to_tsv(&cols, &rows, &[1, 0], true), "A\tB\n2.5\tz\n1.5\tx y",
                   "view order + tab collapse");
        assert_eq!(to_tsv(&cols, &rows, &[], true), "A\tB", "empty selection = header only");
        assert_eq!(to_tsv(&cols, &rows, &[1], false), "2.5\tz", "no-header variant");
    }

    #[test]
    fn stats_match_python() {
        let rows = vec![strs(&["1.5"]), strs(&[""]), strs(&["2.5"]), strs(&["1.5"])];
        let s = column_stats(&rows, &[0, 1, 2, 3], 0);
        assert_eq!(s, ColumnStats { rows: 4, blank: 1, distinct: 2, numeric: 3,
                                    sum: Some(5.5), min: Some(1.5), max: Some(2.5) });
        assert_eq!(stats_text(&s), "4 rows · 2 distinct · 1 blank · Σ 5.5 · min 1.5 · max 2.5");

        let s = column_stats(&rows, &[0, 2], 0);
        assert_eq!((s.rows, s.blank, s.numeric, s.sum), (2, 0, 2, Some(4.0)),
                   "stats follow the VISIBLE view");
        assert_eq!(stats_text(&s), "2 rows · 2 distinct · Σ 4 · min 1.5 · max 2.5",
                   "no blank part; integral sum prints without .0");

        let text_rows = vec![strs(&["door"]), strs(&["estop"]), strs(&[" "])];
        let s = column_stats(&text_rows, &[0, 1, 2], 0);
        assert_eq!((s.rows, s.blank, s.distinct), (3, 0, 3),
                   "a whitespace-only cell is NON-blank (the Python contract)");
        assert_eq!((s.numeric, s.sum, s.min, s.max), (0, None, None, None));
        assert_eq!(stats_text(&s), "3 rows · 3 distinct", "text column = counts only");
    }
}

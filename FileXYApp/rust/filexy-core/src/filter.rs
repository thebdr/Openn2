//! Cascade filters + the global quick search - the port of core.py's filter_passes /
//! apply_filters / distinct_values.

use std::collections::HashSet;

use regex::{Regex, RegexBuilder};

use crate::sort::natural_key;

/// One filter spec. `col: None` = the GLOBAL quick search (any cell may match). A `values` set is
/// the Excel-style pick list; else `text` matches as a regex (`regex: true`; a broken pattern
/// matches nothing) or a case-insensitive substring. An empty spec passes everything.
#[derive(Debug, Clone, Default)]
pub struct FilterSpec {
    pub col: Option<usize>,
    pub text: String,
    pub regex: bool,
    pub values: Option<HashSet<String>>,
}

/// Python's str.casefold - FULL case folding ("SS" finds "ß"), which to_lowercase is not.
fn fold(s: &str) -> String {
    caseless::default_case_fold_str(s)
}

/// The spec compiled ONCE, applied per cell. Python's `re` caches compiled patterns internally;
/// without this, apply_filters would recompile the regex for EVERY cell of a 20k-row table.
enum Matcher<'a> {
    Values(&'a HashSet<String>),
    All,
    Regex(Option<Regex>), // None = the pattern didn't compile -> matches nothing (the contract)
    Substr(String),
}

impl<'a> Matcher<'a> {
    fn new(spec: &'a FilterSpec) -> Self {
        if let Some(values) = &spec.values {
            return Matcher::Values(values);
        }
        if spec.text.is_empty() {
            return Matcher::All;
        }
        if spec.regex {
            return Matcher::Regex(
                RegexBuilder::new(&spec.text).case_insensitive(true).build().ok(),
            );
        }
        Matcher::Substr(fold(&spec.text))
    }

    fn passes(&self, cell: &str) -> bool {
        match self {
            Matcher::Values(values) => values.contains(cell),
            Matcher::All => true,
            Matcher::Regex(Some(re)) => re.is_match(cell),
            Matcher::Regex(None) => false,
            Matcher::Substr(text) => fold(cell).contains(text.as_str()),
        }
    }
}

pub fn filter_passes(cell: &str, spec: &FilterSpec) -> bool {
    Matcher::new(spec).passes(cell)
}

/// The visible SOURCE row indices: the rows passing EVERY filter (cascade = AND; each filter was
/// added over the then-visible rows, and the conjunction reproduces that narrowing exactly).
pub fn apply_filters(rows: &[Vec<String>], filters: &[FilterSpec]) -> Vec<usize> {
    let matchers: Vec<(Option<usize>, Matcher)> =
        filters.iter().map(|spec| (spec.col, Matcher::new(spec))).collect();
    let mut view = Vec::new();
    'rows: for (i, row) in rows.iter().enumerate() {
        for (col, matcher) in &matchers {
            let passes = match col {
                None => row.iter().any(|cell| matcher.passes(cell)), // quick search
                Some(c) => matcher.passes(row.get(*c).map(String::as_str).unwrap_or("")),
            };
            if !passes {
                continue 'rows;
            }
        }
        view.push(i);
    }
    view
}

/// The column's distinct values among the VISIBLE rows, natural-sorted, capped - the cascade rule:
/// the filter popup offers only what the previous filters left on screen.
pub fn distinct_values(rows: &[Vec<String>], view: &[usize], col: usize, cap: usize) -> Vec<String> {
    let mut seen: Vec<String> = view
        .iter()
        .map(|&i| rows[i].get(col).cloned().unwrap_or_default())
        .collect::<HashSet<_>>()
        .into_iter()
        .collect();
    seen.sort_by_key(|s| natural_key(s));
    seen.truncate(cap);
    seen
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rows() -> Vec<Vec<String>> {
        [["S1", "I2.0", "door"], ["S1", "I10.1", "estop"], ["S2", "I2.2", "door open"]]
            .iter().map(|r| r.iter().map(|s| s.to_string()).collect()).collect()
    }

    fn text_spec(col: Option<usize>, text: &str) -> FilterSpec {
        FilterSpec { col, text: text.into(), ..Default::default() }
    }

    #[test]
    fn passes_modes_match_python() {
        assert!(filter_passes("NET SAFETY 50", &text_spec(Some(0), "safety")), "substring, ci");
        assert!(!filter_passes("NET SAFETY 50", &text_spec(Some(0), "sorter")));
        let re = FilterSpec { col: Some(0), text: r"^I\d+\.0$".into(), regex: true, ..Default::default() };
        assert!(filter_passes("I110.0", &re));
        let broken = FilterSpec { col: Some(0), text: "([".into(), regex: true, ..Default::default() };
        assert!(!filter_passes("x", &broken), "a broken regex matches nothing");
        let values = FilterSpec {
            col: Some(0),
            values: Some(["A".to_string(), "B".to_string()].into_iter().collect()),
            ..Default::default()
        };
        assert!(filter_passes("A", &values) && !filter_passes("C", &values));
        assert!(filter_passes("anything", &text_spec(Some(0), "")), "empty spec passes all");
    }

    #[test]
    fn substring_uses_full_case_folding() {
        // Python: pattern.casefold() in cell.casefold() - "ss" finds "ß" and vice versa
        assert!(filter_passes("straße", &text_spec(Some(0), "ss")), "ss finds ß");
        assert!(filter_passes("PRESS", &text_spec(Some(0), "ß")), "ß finds SS");
        assert!(filter_passes("µm", &text_spec(Some(0), "μ")), "micro sign folds to Greek mu");
    }

    #[test]
    fn cascade_and_quick_search() {
        let r = rows();
        assert_eq!(apply_filters(&r, &[text_spec(Some(0), "S1")]), vec![0, 1]);
        let two = [text_spec(Some(0), "S1"),
                   FilterSpec { col: Some(1), text: "^I".into(), regex: true, ..Default::default() }];
        assert_eq!(apply_filters(&r, &two), vec![0, 1], "cascade = AND");
        assert_eq!(apply_filters(&r, &[text_spec(None, "estop")]), vec![1], "quick search: any cell");
        let combo = [text_spec(None, "door"), text_spec(Some(0), "S2")];
        assert_eq!(apply_filters(&r, &combo), vec![2], "quick search cascades with column filters");
        assert_eq!(apply_filters(&r, &[text_spec(None, "")]), vec![0, 1, 2]);
    }

    #[test]
    fn distinct_of_visible() {
        let r = rows();
        assert_eq!(distinct_values(&r, &[0, 1], 2, 1000), vec!["door", "estop"]);
        assert_eq!(distinct_values(&r, &[0, 1, 2], 0, 1000), vec!["S1", "S2"]);
        assert_eq!(distinct_values(&r, &[0, 1, 2], 0, 1).len(), 1, "capped");
    }
}

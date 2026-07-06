//! Natural tri-state sorting - the port of core.py's natural_key / cycle_sort / sorted_view.

/// One chunk of a natural key. Variant ORDER is the comparison rule: any number sorts before any
/// text at the same position - exactly Python's `(0, int)` vs `(1, str)` tuple trick.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub enum Part {
    Num(i128),
    Text(String),
}

/// The comparable natural key. Field order drives the derived Ord: `blank` first, so an empty
/// cell (blank = true) sorts AFTER every non-blank one - Python's `((2, ""),)` marker.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct NaturalKey {
    blank: bool,
    parts: Vec<Part>,
}

/// Numeric-aware sort key: `I10.1` sorts after `I2.0` and `10` after `9` (a digit run compares as
/// its number, the rest case-insensitively). Blank cells sort LAST.
pub fn natural_key(text: &str) -> NaturalKey {
    if text.is_empty() {
        return NaturalKey { blank: true, parts: Vec::new() };
    }
    let mut parts = Vec::new();
    let mut run = String::new();
    let mut run_is_digit = None::<bool>;
    for ch in text.chars() {
        let is_digit = ch.is_ascii_digit();
        if run_is_digit != Some(is_digit) && !run.is_empty() {
            parts.push(finish(&run, run_is_digit == Some(true)));
            run.clear();
        }
        run_is_digit = Some(is_digit);
        run.push(ch);
    }
    if !run.is_empty() {
        parts.push(finish(&run, run_is_digit == Some(true)));
    }
    NaturalKey { blank: false, parts }
}

fn finish(run: &str, is_digit: bool) -> Part {
    if is_digit {
        if let Ok(n) = run.parse::<i128>() {
            return Part::Num(n);
        }
    }
    // FULL case folding = Python's str.casefold ("straße" sorts as "strasse"); to_lowercase isn't
    Part::Text(caseless::default_case_fold_str(run))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Dir {
    Asc,
    Desc,
}

pub type SortState = Option<(usize, Dir)>;

/// The header-click tri-state: unsorted -> (col, Asc) -> (col, Desc) -> released (None).
/// A click on a DIFFERENT column starts fresh at Asc.
pub fn cycle_sort(state: SortState, col: usize) -> SortState {
    match state {
        Some((c, Dir::Asc)) if c == col => Some((col, Dir::Desc)),
        Some((c, Dir::Desc)) if c == col => None,
        _ => Some((col, Dir::Asc)),
    }
}

/// `view` (source indices) ordered by the sort state - NON-destructive: the source rows never
/// move, only the view permutes; None returns the original document order. Stable + natural,
/// with Python's `reverse=True` semantics: equal keys keep their ORIGINAL order in BOTH
/// directions - so Desc is a reversed comparator, NOT a sort-then-reverse (that would flip ties).
pub fn sorted_view(rows: &[Vec<String>], view: &[usize], sort: SortState) -> Vec<usize> {
    let Some((col, dir)) = sort else {
        return view.to_vec();
    };
    let mut keyed: Vec<(NaturalKey, usize)> = view
        .iter()
        .map(|&i| (natural_key(rows[i].get(col).map(String::as_str).unwrap_or("")), i))
        .collect();
    match dir {
        Dir::Asc => keyed.sort_by(|a, b| a.0.cmp(&b.0)),
        Dir::Desc => keyed.sort_by(|a, b| b.0.cmp(&a.0)),
    }
    keyed.into_iter().map(|(_, i)| i).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sorted_strs(items: &[&str]) -> Vec<String> {
        let mut v: Vec<String> = items.iter().map(|s| s.to_string()).collect();
        v.sort_by_key(|s| natural_key(s));
        v
    }

    #[test]
    fn natural_order_matches_python() {
        assert_eq!(sorted_strs(&["I10.1", "I2.0", "I2.10", "I2.2"]),
                   vec!["I2.0", "I2.2", "I2.10", "I10.1"]);
        assert_eq!(sorted_strs(&["10", "9", "100"]), vec!["9", "10", "100"]);
        assert_eq!(sorted_strs(&["b", "", "a"]), vec!["a", "b", ""], "blanks sort LAST");
        assert_eq!(sorted_strs(&["Beta", "alpha"]), vec!["alpha", "Beta"], "case-insensitive");
        assert_eq!(sorted_strs(&["strassf", "straße"]), vec!["straße", "strassf"],
                   "full case folding: ß sorts as ss (Python casefold)");
    }

    #[test]
    fn tri_state_cycle() {
        let s1 = cycle_sort(None, 2);
        assert_eq!(s1, Some((2, Dir::Asc)));
        let s2 = cycle_sort(s1, 2);
        assert_eq!(s2, Some((2, Dir::Desc)));
        assert_eq!(cycle_sort(s2, 2), None, "third click releases");
        assert_eq!(cycle_sort(s2, 0), Some((0, Dir::Asc)), "a different column starts fresh");
    }

    #[test]
    fn view_sorting() {
        let rows: Vec<Vec<String>> = [["S1", "I2.0"], ["S1", "I10.1"], ["S2", "I2.2"]]
            .iter().map(|r| r.iter().map(|s| s.to_string()).collect()).collect();
        assert_eq!(sorted_view(&rows, &[0, 1, 2], Some((1, Dir::Asc))), vec![0, 2, 1]);
        assert_eq!(sorted_view(&rows, &[0, 1], Some((1, Dir::Desc))), vec![1, 0]);
        assert_eq!(sorted_view(&rows, &[0, 1], None), vec![0, 1], "released = document order");
        // Python's reverse=True stability: ties keep their ORIGINAL order in Desc too
        assert_eq!(sorted_view(&rows, &[0, 1, 2], Some((0, Dir::Desc))), vec![2, 0, 1],
                   "Desc ties stay in view order (sorted(reverse=True) semantics)");
    }
}

//! The row multi-selection model - the port of core.py's updated_selection.

use std::collections::HashSet;

/// The next `(selected_set, anchor)` after a click on `row` (the standard list-selection model):
/// a plain click selects just that row; Ctrl toggles it; Shift extends from the anchor
/// (inclusive). The anchor moves on plain/Ctrl clicks and stays put across Shift extensions.
pub fn updated_selection(
    selected: &HashSet<usize>,
    anchor: Option<usize>,
    row: usize,
    ctrl: bool,
    shift: bool,
) -> (HashSet<usize>, Option<usize>) {
    if shift {
        if let Some(a) = anchor {
            let (lo, hi) = if a <= row { (a, row) } else { (row, a) };
            return ((lo..=hi).collect(), Some(a));
        }
    }
    if ctrl {
        let mut next = selected.clone();
        if !next.remove(&row) {
            next.insert(row);
        }
        return (next, Some(row));
    }
    ([row].into_iter().collect(), Some(row))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn set(items: &[usize]) -> HashSet<usize> {
        items.iter().copied().collect()
    }

    #[test]
    fn selection_model_matches_python() {
        let (sel, anchor) = updated_selection(&set(&[]), None, 3, false, false);
        assert_eq!((sel.clone(), anchor), (set(&[3]), Some(3)), "plain click selects just it");
        let (sel, anchor) = updated_selection(&sel, anchor, 5, true, false);
        assert_eq!((sel.clone(), anchor), (set(&[3, 5]), Some(5)), "Ctrl adds + moves the anchor");
        let (sel, anchor) = updated_selection(&sel, anchor, 5, true, false);
        assert_eq!((sel.clone(), anchor), (set(&[3]), Some(5)), "Ctrl toggles OFF");
        let (sel, anchor) = updated_selection(&sel, anchor, 1, false, true);
        assert_eq!((sel.clone(), anchor), (set(&[1, 2, 3, 4, 5]), Some(5)), "Shift ranges");
        let (sel, anchor) = updated_selection(&sel, anchor, 7, false, true);
        assert_eq!((sel, anchor), (set(&[5, 6, 7]), Some(5)), "re-range from the SAME anchor");
        let (sel, anchor) = updated_selection(&set(&[9]), None, 2, false, true);
        assert_eq!((sel, anchor), (set(&[2]), Some(2)), "Shift with no anchor = plain click");
        let (sel, anchor) = updated_selection(&set(&[1, 2, 9]), Some(9), 4, false, false);
        assert_eq!((sel, anchor), (set(&[4]), Some(4)), "plain click REPLACES a multi-selection");
    }
}

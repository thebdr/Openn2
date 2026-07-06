//! The calamine xlsx loader - the port of files.py's `read_xlsx`/`xlsx_sheets` (openpyxl), and the
//! actual performance goal of the Rust engine: openpyxl re-parses the workbook XML in Python,
//! calamine does it natively. The output contract is files.py's exactly - (columns, rows) of
//! DISPLAY strings, first row = header, None/Empty cells become "" - and every value renders the
//! way Python's `str()` renders what openpyxl yields (gated by tests/test_native.py, which
//! compares both loaders cell-by-cell on the repo's real workbooks).

use std::fs::File;
use std::io::BufReader;

use calamine::{open_workbook, Data, Reader, Xlsx};

type Workbook = Xlsx<BufReader<File>>;

// files.py's caps: guard against runaway sheets, not real data.
pub const MAX_ROWS: usize = 200_000;
pub const MAX_COLS: usize = 256;

/// The workbook's sheet names (files.py's `xlsx_sheets`).
pub fn sheet_names(path: &str) -> Result<Vec<String>, String> {
    let book = open_workbook::<Workbook, _>(path).map_err(|e| e.to_string())?;
    Ok(book.sheet_names().to_vec())
}

/// (columns, rows) from one xlsx sheet (`sheet` None = the first). The first row is the header;
/// empty cells become "".
///
/// KNOWN divergences from the openpyxl loader (accepted - files.py falls back to openpyxl when
/// this loader ERRORS, so none of these makes a file unopenable):
/// - openpyxl iterates the sheet's declared DIMENSION, calamine the cells with VALUES: rows or
///   leading rows/columns that hold only FORMATTING come back blank from openpyxl and are absent
///   here (tests/test_native.py compares trailing-trimmed).
/// - openpyxl decides int-vs-float from the raw `<v>` TEXT (only Excel-unusual writers emit
///   "4.0"/"1E+2"; both Excel and openpyxl write "4"), we decide from the parsed f64 - so such
///   files show "4" here vs "4.0" there; plain-digit integers >= 1e16 (programmatic ID columns)
///   pass through f64 and lose exact digits.
/// - regex/substring case-insensitivity inside the GRID is full-fold now, but the regex crate's
///   own (?i) uses simple folding (İ vs i) - a residual, documented in filter.rs.
pub fn load_xlsx(path: &str, sheet: Option<&str>) -> Result<(Vec<String>, Vec<Vec<String>>), String> {
    let mut book = open_workbook::<Workbook, _>(path).map_err(|e| e.to_string())?;
    let name = match sheet {
        Some(s) => s.to_string(),
        None => book.sheet_names().first().cloned().ok_or("workbook has no sheets")?,
    };
    let range = book.worksheet_range(&name).map_err(|e| e.to_string())?;
    let mut table: Vec<Vec<String>> = range
        .rows()
        .take(MAX_ROWS + 1) // the header + MAX_ROWS data rows, like files.py
        .map(|row| row.iter().take(MAX_COLS).map(cell_to_string).collect())
        .collect();
    if table.is_empty() {
        return Ok((Vec::new(), Vec::new()));
    }
    let columns = table.remove(0);
    Ok((columns, table))
}

/// XML 1.0 line-ending normalization (CRLF and lone CR -> LF). XML parsers MUST do this to
/// character content; openpyxl's does, quick-xml (under calamine) does not - so a multi-line
/// cell stored with CRLF reads "a\r\nb" from calamine but "a\nb" from openpyxl. Normalizing
/// here keeps the loaders cell-identical (and is the spec-correct reading).
fn normalize_newlines(s: &str) -> String {
    if !s.contains('\r') {
        return s.to_string();
    }
    s.replace("\r\n", "\n").replace('\r', "\n")
}

/// One cell as the display string Python's `str()` would produce for the openpyxl value.
fn cell_to_string(cell: &Data) -> String {
    match cell {
        Data::Empty => String::new(),
        Data::String(s) => normalize_newlines(s),
        // openpyxl int-parses Excel's decimal-free numbers ("4" -> int 4 -> "4"), floats keep
        // their decimals; py_float_str reproduces both plus Python's scientific-notation rules.
        Data::Float(f) => py_float_str(*f),
        Data::Int(i) => i.to_string(),
        Data::Bool(b) => if *b { "True".into() } else { "False".into() },
        Data::DateTime(dt) => {
            let serial = dt.as_f64();
            if dt.is_duration() {
                // a duration format ([h]:mm:ss family): openpyxl yields datetime.timedelta
                return py_timedelta_str(serial);
            }
            match dt.as_datetime() {
                // serial < 1.0 is a pure time-of-day: openpyxl yields datetime.time
                Some(ndt) if serial < 1.0 => fmt_hms(&ndt),
                // else datetime.datetime - str() always includes the time part. Python's datetime
                // stops at year 9999 (chrono goes much further): openpyxl substitutes "#VALUE!"
                // for serials outside it (e.g. a yyyymmdd number sitting in a date column).
                Some(ndt) => {
                    use chrono::Datelike;
                    if ndt.year() < 1 || ndt.year() > 9999 {
                        "#VALUE!".into()
                    } else {
                        format!("{} {}", ndt.format("%Y-%m-%d"), fmt_hms(&ndt))
                    }
                }
                None => "#VALUE!".into(), // beyond even chrono's range - beyond Python's too
            }
        }
        // ods-style ISO cells: already strings
        Data::DateTimeIso(s) | Data::DurationIso(s) => s.clone(),
        // with data_only, openpyxl yields the cached error text ("#DIV/0!", ...)
        Data::Error(e) => e.to_string(),
    }
}

/// "HH:MM:SS[.ffffff]" - Python's str(time)/str(datetime) time part (microseconds only if nonzero).
fn fmt_hms(ndt: &chrono::NaiveDateTime) -> String {
    use chrono::Timelike;
    let base = ndt.format("%H:%M:%S").to_string();
    let micros = ndt.time().nanosecond() / 1_000;
    if micros > 0 { format!("{base}.{micros:06}") } else { base }
}

/// A duration serial (days) exactly as Python renders openpyxl's timedelta:
/// "[D day(s), ]H:MM:SS[.ffffff]" - hours NOT zero-padded, the days part only when nonzero,
/// negatives normalized Python-style (-0.5 days -> "-1 day, 12:00:00").
fn py_timedelta_str(days: f64) -> String {
    // timedelta rounds the fractional carry to microseconds with round-HALF-EVEN
    let micros_f = days * 86_400_000_000.0;
    let micros = if (micros_f - micros_f.trunc()).abs() == 0.5 {
        ((micros_f / 2.0).round() * 2.0) as i128
    } else {
        micros_f.round() as i128
    };
    let (d, rem) = (micros.div_euclid(86_400_000_000), micros.rem_euclid(86_400_000_000));
    let (h, m) = (rem / 3_600_000_000, (rem / 60_000_000) % 60);
    let (s, us) = ((rem / 1_000_000) % 60, rem % 1_000_000);
    let mut out = String::new();
    if d != 0 {
        out += &format!("{} day{}, ", d, if d == 1 || d == -1 { "" } else { "s" });
    }
    out += &format!("{h}:{m:02}:{s:02}");
    if us != 0 {
        out += &format!(".{us:06}");
    }
    out
}

/// A float exactly as Python renders openpyxl's parse of it:
/// - Excel writes integral numbers without decimals, openpyxl int-parses them -> "4"
/// - non-integral values: both Python's repr and Rust's Display print the SHORTEST decimal that
///   round-trips, so the digits agree; only the scientific-notation rules differ. Python switches
///   to scientific at >= 1e16 or < 1e-4 and pads the exponent ("1.5e-07", "2.5e+16").
pub fn py_float_str(x: f64) -> String {
    let a = x.abs();
    if x.fract() == 0.0 && a < 1e16 {
        return format!("{}", x as i64);
    }
    if a >= 1e16 || (a > 0.0 && a < 1e-4) {
        let s = format!("{x:e}"); // "1.5e-7" / "2.5e16"
        if let Some((mantissa, exp)) = s.split_once('e') {
            if let Ok(exp) = exp.parse::<i32>() {
                let sign = if exp < 0 { '-' } else { '+' };
                return format!("{mantissa}e{sign}{:02}", exp.abs());
            }
        }
        return s; // unreachable for finite values; NaN/inf can't come from Excel
    }
    format!("{x}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn timedelta_strings_match_python_str() {
        assert_eq!(py_timedelta_str(1.5), "1 day, 12:00:00", "singular day");
        assert_eq!(py_timedelta_str(2.0), "2 days, 0:00:00");
        assert_eq!(py_timedelta_str(0.10416666666666667), "2:30:00", "hours NOT zero-padded");
        assert_eq!(py_timedelta_str(-0.5), "-1 day, 12:00:00", "Python-normalized negative");
        assert_eq!(py_timedelta_str(0.0), "0:00:00");
        let micro = 0.5 + 0.123456 / 86_400.0;
        assert_eq!(py_timedelta_str(micro), "12:00:00.123456", "microseconds when nonzero");
    }

    #[test]
    fn newline_normalization_matches_xml_spec() {
        assert_eq!(normalize_newlines("a\r\nb"), "a\nb");
        assert_eq!(normalize_newlines("a\rb"), "a\nb", "lone CR normalizes too");
        assert_eq!(normalize_newlines("a\nb"), "a\nb");
        assert_eq!(cell_to_string(&Data::String("x\r\ny".into())), "x\ny");
    }

    #[test]
    fn float_strings_match_python_str() {
        assert_eq!(py_float_str(4.0), "4", "integral = openpyxl's int parse");
        assert_eq!(py_float_str(-12.0), "-12");
        assert_eq!(py_float_str(0.0), "0");
        assert_eq!(py_float_str(4.5), "4.5");
        assert_eq!(py_float_str(0.1), "0.1", "shortest round-trip, like Python repr");
        assert_eq!(py_float_str(0.0001), "0.0001", "1e-4 is still positional in Python");
        assert_eq!(py_float_str(9.999e-5), "9.999e-05", "below 1e-4 goes scientific, padded");
        assert_eq!(py_float_str(1.5e-7), "1.5e-07");
        assert_eq!(py_float_str(1e16), "1e+16", ">= 1e16 goes scientific even when integral");
        assert_eq!(py_float_str(2.5e16), "2.5e+16");
        assert_eq!(py_float_str(-1.5e-7), "-1.5e-07");
        assert_eq!(py_float_str(1234567890123456.0), "1234567890123456", "just under 1e16");
    }
}

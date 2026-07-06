//! The PyO3 bindings - the `filexy_core` Python extension module (built by maturin via
//! rust/install_native.py, feature "python"). Only the DATA-SIZED core functions cross the FFI:
//! filtering/sorting/export over whole tables plus the xlsx loader. The measure-injected layout
//! maths and the per-event hit tests stay in filexy/core.py - calling Tk font closures through
//! the FFI would cost more than it saves.
//!
//! The Python-side contract (what core.py passes verbatim):
//! - rows: list[list[str]], view: list[int]
//! - sort: None | (col, "asc"|"desc")
//! - a filter spec: a dict with optional keys col (None = the quick search), text, regex, values

use std::collections::HashSet;

use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::{export, filter, layout, sort, xlsx};

fn spec_from(any: &Bound<'_, PyAny>) -> PyResult<filter::FilterSpec> {
    let d = any.downcast::<PyDict>().map_err(|_| PyValueError::new_err("filter spec: dict expected"))?;
    let get = |k: &str| d.get_item(k);
    let col = match get("col")? {
        Some(v) if !v.is_none() => Some(v.extract::<usize>()?),
        _ => None,
    };
    let text = match get("text")? {
        Some(v) if !v.is_none() => v.extract::<String>()?,
        _ => String::new(),
    };
    let regex = match get("regex")? {
        Some(v) if !v.is_none() => v.extract::<bool>()?,
        _ => false,
    };
    let values = match get("values")? {
        Some(v) if !v.is_none() => Some(v.extract::<HashSet<String>>()?),
        _ => None,
    };
    Ok(filter::FilterSpec { col, text, regex, values })
}

fn sort_from(sort: Option<(usize, String)>) -> PyResult<sort::SortState> {
    match sort {
        None => Ok(None),
        Some((col, dir)) => match dir.as_str() {
            "asc" => Ok(Some((col, sort::Dir::Asc))),
            "desc" => Ok(Some((col, sort::Dir::Desc))),
            other => Err(PyValueError::new_err(format!("sort direction: {other:?}"))),
        },
    }
}

#[pyfunction]
fn apply_filters(rows: Vec<Vec<String>>, filters: Vec<Bound<'_, PyAny>>) -> PyResult<Vec<usize>> {
    let specs = filters.iter().map(spec_from).collect::<PyResult<Vec<_>>>()?;
    Ok(filter::apply_filters(&rows, &specs))
}

#[pyfunction]
fn sorted_view(rows: Vec<Vec<String>>, view: Vec<usize>, sort: Option<(usize, String)>) -> PyResult<Vec<usize>> {
    Ok(sort::sorted_view(&rows, &view, sort_from(sort)?))
}

#[pyfunction]
#[pyo3(signature = (rows, view, col, cap = 1000))]
fn distinct_values(rows: Vec<Vec<String>>, view: Vec<usize>, col: usize, cap: usize) -> Vec<String> {
    filter::distinct_values(&rows, &view, col, cap)
}

#[pyfunction]
#[pyo3(signature = (columns, rows, view, header = true))]
fn to_tsv(columns: Vec<String>, rows: Vec<Vec<String>>, view: Vec<usize>, header: bool) -> String {
    export::to_tsv(&columns, &rows, &view, header)
}

#[pyfunction]
fn column_stats<'py>(py: Python<'py>, rows: Vec<Vec<String>>, view: Vec<usize>, col: usize) -> PyResult<Bound<'py, PyDict>> {
    let s = export::column_stats(&rows, &view, col);
    let d = PyDict::new(py);
    d.set_item("rows", s.rows)?;
    d.set_item("blank", s.blank)?;
    d.set_item("distinct", s.distinct)?;
    d.set_item("numeric", s.numeric)?;
    if let (Some(sum), Some(min), Some(max)) = (s.sum, s.min, s.max) {
        // like the Python dict: sum/min/max keys exist only when something parsed as a number
        d.set_item("sum", sum)?;
        d.set_item("min", min)?;
        d.set_item("max", max)?;
    }
    Ok(d)
}

#[pyfunction]
fn sanitize_rows(rows: Vec<Vec<String>>) -> Vec<Vec<String>> {
    rows.iter().map(|row| row.iter().map(|c| layout::sanitize(c)).collect()).collect()
}

#[pyfunction]
#[pyo3(signature = (path, sheet = None))]
fn read_xlsx(path: String, sheet: Option<String>) -> PyResult<(Vec<String>, Vec<Vec<String>>)> {
    xlsx::load_xlsx(&path, sheet.as_deref()).map_err(PyIOError::new_err)
}

#[pyfunction]
fn xlsx_sheets(path: String) -> PyResult<Vec<String>> {
    xlsx::sheet_names(&path).map_err(PyIOError::new_err)
}

/// True when the pattern compiles under THIS engine's regex crate. The Python side routes any
/// regex filter failing this (lookarounds, backrefs, \Z, conditionals - Python-only syntax) to
/// the Python engine, instead of the native path silently matching nothing.
#[pyfunction]
fn regex_ok(pattern: String) -> bool {
    regex::RegexBuilder::new(&pattern).case_insensitive(true).build().is_ok()
}

#[pymodule]
fn filexy_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__engine__", "rust")?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(apply_filters, m)?)?;
    m.add_function(wrap_pyfunction!(sorted_view, m)?)?;
    m.add_function(wrap_pyfunction!(distinct_values, m)?)?;
    m.add_function(wrap_pyfunction!(to_tsv, m)?)?;
    m.add_function(wrap_pyfunction!(column_stats, m)?)?;
    m.add_function(wrap_pyfunction!(sanitize_rows, m)?)?;
    m.add_function(wrap_pyfunction!(read_xlsx, m)?)?;
    m.add_function(wrap_pyfunction!(xlsx_sheets, m)?)?;
    m.add_function(wrap_pyfunction!(regex_ok, m)?)?;
    Ok(())
}

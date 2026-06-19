"""CSV read/write: comma on the way OUT, delimiter-sniffed on the way IN (plan: Delimiters).

All CSVs Pipeline3 writes are comma-delimited (QUOTE_MINIMAL); readers sniff ',' vs ';' so older
';' files still load. Custom parameters use '|' internally, so they never need quoting.
"""
from __future__ import annotations
import csv
import os


def _sniff_delim(text: str) -> str:
    first = next((ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")), "")
    return ";" if first.count(";") > first.count(",") else ","


def read_rows(path: str) -> list:
    """Read a CSV as a list of dicts (DictReader), delimiter-sniffed, BOM-tolerant."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        text = f.read()
    return list(csv.DictReader(text.splitlines(), delimiter=_sniff_delim(text)))


def write_rows(path: str, fieldnames, rows) -> str:
    """Write dict rows as a comma-delimited CSV (QUOTE_MINIMAL). Creates parent dirs. Returns path."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore", quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def write_table(path: str, header, rows) -> str:
    """Write a positional table (header list + list-of-lists rows) as comma-delimited CSV."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        if header is not None:
            w.writerow(list(header))
        for r in rows:
            w.writerow(list(r))
    return path

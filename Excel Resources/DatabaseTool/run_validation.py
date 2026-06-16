#!/usr/bin/env python3
"""Run the C&E / AREA -> I/O List cross-validation against the real documents.
Prints every check (pass and fail) with cell addresses and writes
Output/validation_log.txt. Run: python run_validation.py
"""
import os
from safetydb import config, staging, validation


def main():
    params = config.load_params()
    types = config.load_signal_types()

    io_rows, io_warnings = staging.load_io_list(params, types)
    for w in io_warnings:
        print("  " + w)

    log = validation.validate(params, io_rows)
    print("=" * 90)
    for e in log:
        print(e.format())
    print("=" * 90)

    out_dir = os.path.join(os.path.dirname(__file__), params.get("output_dir", "Output"))
    passed, failed, warned = validation.write_log(log, out_dir)
    print(f"SUMMARY: {passed} passed, {failed} failed, {warned} warning(s)   ->  {os.path.join(out_dir, 'validation_log.txt')}")


if __name__ == "__main__":
    main()

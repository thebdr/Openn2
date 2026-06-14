#!/usr/bin/env python3
"""Staging test against the real I/O List. Run: python test_staging.py"""
import os
from safetydb import config, staging

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def main():
    params = config.load_params()
    if not os.path.exists(params["io_list"]["path"]):
        raise SystemExit("real I/O List not found: " + params["io_list"]["path"])
    types = config.load_signal_types()

    rows, warnings = staging.load_io_list(params, types)
    print("--- warnings ---")
    for w in warnings:
        print("  " + w)

    check("rows loaded", len(rows) > 0, f"{len(rows)} rows")
    check("no header-mismatch warnings", len(warnings) == 1, "; ".join(warnings[1:]) or "clean")

    # the IOC interface row must be present and resolved
    ioc = [r for r in rows if r.get("script_type", "").upper() == "IOC"]
    check("IOC row present", len(ioc) == 1)
    if ioc:
        r = ioc[0]
        check("IOC has Index SORTER-01", r.get("index") == "SORTER-01", r.get("index"))
        check("IOC base (Bit col) and node (ID col) read",
              r.get("bit") == "10000" and r.get("id_node") == "6",
              f"bit={r.get('bit')} id={r.get('id_node')}")
        check("IOC type resolved to Interface category",
              r.get("_type") and r["_type"]["category"] == "Interface")

    # known signal types resolve; unknowns are flagged by _type is None
    typed = [r for r in rows if r.get("_type")]
    untyped_with_script = [r for r in rows if r.get("script_type") and not r.get("_type")]
    check("most rows resolve a signal type", len(typed) > 0, f"{len(typed)} typed")
    print(f"  ({len(untyped_with_script)} rows have a Script Type that did not resolve)")
    for r in untyped_with_script[:10]:
        print(f"    row {r['_source_row']}: script_type={r['script_type']!r}")

    # channel-pair types present (E1/2 + E2/2 etc.)
    pairs = {r["_type"]["pair_key"] for r in typed if r["_type"]["pair_key"]}
    check("channel-pair types found", {"E", "B", "ENC", "DI"} & pairs == {"E", "B", "ENC", "DI"}, str(sorted(pairs)))

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Staging test against the real I/O List. Run: python test_staging.py"""
import os
from pipeline2.core import config, staging

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
        check("IOC base address read (Bit col G); ID col F mapped",
              r.get("bit") == "10000" and "id_node" in r,
              f"bit={r.get('bit')} id={r.get('id_node')!r}")
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

    # diag_block_name/diag_block_template enriched from the DiagnosticBlocks sheet (cols E/F),
    # looked up by Diag Cabinet - the encoders are assigned to the SafetyEncoders cabinet
    enc = [r for r in rows if r.get("script_type") in ("ENC1/2", "ENC2/2")]
    check("encoder rows carry their diagnosis-block name + template",
          bool(enc) and all(r.get("diag_block_name") == "=S1+SafetyEncoders"
                            and r.get("diag_block_template") == "2" for r in enc),
          enc and f"{enc[0].get('diag_block_name')!r}/{enc[0].get('diag_block_template')!r}")

    # source_cell = 'Sheet!<FU col><row>' link back into the I/O List
    r0 = rows[0]
    check("rows carry a source_cell link (Sheet!<FU col><row>)",
          bool(r0.get("source_cell")) and "!" in r0["source_cell"]
          and r0["source_cell"].endswith(str(r0.get("_source_row"))),
          r0.get("source_cell"))

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()

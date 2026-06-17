#!/usr/bin/env python3
"""Tests for pipeline2/core/i18n.py: every key is bilingual, tr() formats + falls back cleanly.

Run: python test_i18n.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pipeline2.core import i18n

failures = 0


def check(name, ok, detail=""):
    global failures
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures += 1


def main():
    missing = [k for k, v in i18n.STRINGS.items()
               if not (v.get("en", "").strip() and v.get("it", "").strip())]
    check("every key has non-empty en + it", not missing, ", ".join(missing))

    # placeholder formatting works in both languages
    en = i18n.tr("col_wrong", "en", actual="Devvice", n=17, expected="Device")
    it = i18n.tr("col_wrong", "it", actual="Devvice", n=17, expected="Device")
    check("EN formats placeholders", "Devvice" in en and "17" in en and "Device" in en)
    check("IT formats placeholders", "Devvice" in it and "17" in it and "Device" in it)
    check("EN and IT differ", en != it)

    # keys that take placeholders must reference them in BOTH languages (catch drift)
    import re
    bad = []
    for k, v in i18n.STRINGS.items():
        toks_en = set(re.findall(r"{(\w+)}", v["en"]))
        toks_it = set(re.findall(r"{(\w+)}", v["it"]))
        if toks_en != toks_it:
            bad.append(k)
    check("placeholder tokens match across languages", not bad, ", ".join(bad))

    # unknown key -> the key itself (visible, no crash)
    check("unknown key falls back to the key", i18n.tr("nope_missing", "en") == "nope_missing")
    # unknown language -> default (en)
    check("unknown language falls back to en",
          i18n.tr("btn_run_all", "de") == i18n.tr("btn_run_all", "en"))
    # missing format kwargs -> raw string, not an exception
    check("missing format args don't raise", isinstance(i18n.tr("col_wrong", "en"), str))

    print("ALL CHECKS PASS" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()

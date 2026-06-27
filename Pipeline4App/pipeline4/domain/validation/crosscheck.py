"""130/140 - the two cross-checks. Clean-room port of PL3's `domain/validation/crosscheck.py`, over PL4's
SSOT `signals` rows + the `ce_refs` reader, emitting Findings (with the rich Cmp + dual-workbook links).

130 forward (CEM->IOL): every C&E reference must be declared in the I/O List (device + address).
140 reverse (IOL->CEM): every mandatory/safety I/O signal must be present in the C&E.
Both link the matched cell in the *other* workbook via `location2`/`doc2`. C&E absent -> one SKIP, never raises.
PL4: takes `(database, params)` (the staged `signals` table + the resolved params); reads the `type` object
cell (PL3's `_type`) + the nested `validation_params.crosscheck.*` config.
"""
from __future__ import annotations

import os

from pipeline4.core import config
from pipeline4.core.model import InfoBlock
from pipeline4.io.workbook import FileLockedError
from pipeline4.domain.validation import ce_refs, model as vm

_DEFAULT_WORDS = ("emergency", "safety", "relay", "contactor", "enable")
# The "<caller> vs <other>" link text when there is NO matched cell in the other workbook (a miss):
# location2 carries this label (no "!"), doc2 the workbook -> the GUI opens that file (no cell).
_IO_LABEL, _CE_LABEL = "I/O List", "C&E Matrix"


def _ce_present(params) -> bool:
    p = params.get("matrix_path") or ""
    return bool(p and os.path.exists(p))


def _signals(database) -> list:
    return list(database["signals"]) if (database is not None and "signals" in database) else []


# --- 130 forward: CEM -> IOL ------------------------------------------------ #
def run_xcheck_cem_iol(database, params) -> list:
    if not _ce_present(params):
        return [vm.entry("SKIP", 130, "ce_absent")]
    try:
        refs, _ = ce_refs.read_ce_refs(params)
    except FileLockedError:
        return [vm.entry("FAIL", 130, "ce_locked")]

    rows = _signals(database)
    io_fld = ce_refs.build_io_index(rows)          # FLD -> {addrs, raw_addr, raw_fld, source_cell}
    io_addr = ce_refs.build_io_addr_index(rows)    # address -> {keys, raw_fld, source_cell}
    ce_doc, io_doc = os.path.basename(params.get("matrix_path") or ""), os.path.basename(params.get("iolist_path") or "")
    out, checked = [], 0
    for ref in refs:
        if not ref["addr"]:
            continue
        checked += 1
        info = InfoBlock(bit=ref["raw_addr"], fld=ref["raw_fld"])
        if not ref["key"]:
            out.append(vm.entry("FAIL", 130, "cem_ref_empty", location=ref["loc"], doc=ce_doc, info=info))
            continue

        # SEARCH BY I/O ADDRESS: PASS if the address is in the I/O List under a MATCHING FLD; FAIL if it's
        # there under a DIFFERENT FLD; FAIL if the address isn't there at all.
        ah = io_addr.get(ref["addr"])
        if ah is None:
            out.append(vm.entry("FAIL", 130, "cem_addr_none", location=ref["loc"], doc=ce_doc,
                                location2=_IO_LABEL, doc2=io_doc, info=info))
        elif ref["key"] in ah["keys"]:
            out.append(vm.entry("PASS", 130, "cem_addr_ok", location=ref["loc"], doc=ce_doc,
                                location2=ah["source_cell"], doc2=io_doc, info=info))
        else:
            io_flds = ", ".join(sorted(ah["raw_fld"].values())) or "(none)"
            cmp = vm.cmp_detail(ref["raw_addr"], ref["raw_addr"], ref["raw_fld"], io_flds, addr_eq=True, fld_eq=False)
            out.append(vm.entry("FAIL", 130, "cem_addr_fld", location=ref["loc"], doc=ce_doc,
                                location2=ah["source_cell"], doc2=io_doc, info=info, cmp=cmp))

        # SEARCH BY FLD: PASS if the FLD is in the I/O List at a MATCHING address; FAIL if it's there at a
        # DIFFERENT address; FAIL if the FLD isn't there at all.
        fh = io_fld.get(ref["key"])
        if fh is None:
            out.append(vm.entry("FAIL", 130, "cem_fld_none", location=ref["loc"], doc=ce_doc,
                                location2=_IO_LABEL, doc2=io_doc, info=info))
        elif ref["addr"] in fh["addrs"]:
            out.append(vm.entry("PASS", 130, "cem_fld_ok", location=ref["loc"], doc=ce_doc,
                                location2=fh["source_cell"], doc2=io_doc, info=info))
        else:
            io_addrs = ", ".join(sorted(fh["raw_addr"].values())) or "(none)"
            cmp = vm.cmp_detail(ref["raw_addr"], io_addrs, ref["raw_fld"], fh["raw_fld"], addr_eq=False, fld_eq=True)
            out.append(vm.entry("FAIL", 130, "cem_fld_addr", location=ref["loc"], doc=ce_doc,
                                location2=fh["source_cell"], doc2=io_doc, info=info, cmp=cmp))

    out.append(vm.entry("INFO", 130, "cem_summary", refs=checked))
    return out


# --- 140 reverse: IOL -> CEM ------------------------------------------------ #
def _ce_match(k, a, idx) -> str:
    ce_addrs = idx["by_key"].get(k)
    if ce_addrs is not None and (not a or a in ce_addrs or "" in ce_addrs):
        return "full"
    if ce_addrs is not None:
        return "fld_only"
    if a and a in idx["by_addr"]:
        return "addr_only"
    return "missing"


def _row_text(row) -> str:
    return " ".join(vm.raw(row.get(k)) for k in ("desc_l1", "desc_l1b", "desc_l2", "desc_l2b", "mnemonic"))


def run_xcheck_iol_cem(database, params) -> list:
    if not _ce_present(params):
        return [vm.entry("SKIP", 140, "ce_absent")]
    try:
        refs, _ = ce_refs.read_ce_refs(params)
    except FileLockedError:
        return [vm.entry("FAIL", 140, "ce_locked")]
    idx = ce_refs.build_ce_index(refs)

    rows = _signals(database)
    io_doc, ce_doc = os.path.basename(params.get("iolist_path") or ""), os.path.basename(params.get("matrix_path") or "")
    xc = "validation_params.crosscheck.iol_in_matrix."
    words = config.get_param(params, xc + "mandatory_words") or _DEFAULT_WORDS
    excluded = config.get_param(params, xc + "excluded_words") or []
    always = config.get_param(params, xc + "bypass_words") or []
    fuzzy = int(config.get_param(params, xc + "levenshtein_deviation", 2) or 0)
    full_check = bool(config.get_param(params, "validation_params.crosscheck.global.full_check", False))

    out, checked, skipped = [], 0, 0
    for row in rows:
        k = vm.key(row.get("functional_unit"), row.get("location"), row.get("device"))
        if not k:
            continue
        a = vm.addr(row.get("bit"))
        t = row.get("type") or {}
        info, loc = vm.info_for_row(row), row.get("source_cell", "")
        # Whether to cross-check this row (per the configured decision tree):
        #   typed & ce_mandatory yes/warn -> CHECK   (yes -> FAIL severity, warn -> WARN)
        #   typed & ce_mandatory no/unset -> NO_CHECK   ("no" is a skip trigger)
        #   untyped & bypass(always-excluded) -> NO_CHECK
        #   untyped & (full_check|safety) -> CHECK
        #   untyped & (excluded | plain)  -> NO_CHECK   (only when full_check is false)
        mand = ""
        if t:
            mand = (t.get("ce_mandatory") or "").lower()
            if mand not in ("yes", "warn"):       # "no"/unset -> not required in the C&E -> NO_CHECK
                skipped += 1
                out.append(vm.entry("SKIP", 140, "iol_cem_not_required", location=loc, doc=io_doc, info=info))
                continue
            is_fail = (mand == "yes")
        else:
            if not a:
                continue
            text = _row_text(row)
            aw = vm.first_match(text, always, 0)
            if aw:
                skipped += 1
                out.append(vm.entry("SKIP", 140, "iol_cem_skipped", word=str(aw), location=loc, doc=io_doc, info=info))
                continue
            is_safety = vm.matches_words(text, words, fuzzy)
            if not full_check and not is_safety:
                skipped += 1
                ew = vm.first_match(text, excluded, fuzzy)
                if ew:
                    out.append(vm.entry("SKIP", 140, "iol_cem_skipped", word=str(ew), location=loc, doc=io_doc, info=info))
                else:
                    out.append(vm.entry("SKIP", 140, "iol_cem_unclassified", location=loc, doc=io_doc, info=info))
                continue
            is_fail = is_safety

        checked += 1
        status = _ce_match(k, a, idx)
        if status == "full":
            out.append(vm.entry("PASS", 140, "iol_cem_match", location=loc, doc=io_doc,
                                location2=idx["loc_by_key"].get(k, ""), doc2=ce_doc, info=info))
            continue
        if status == "missing":
            if t and mand == "yes":
                lvl, typ = "FAIL", "iol_cem_missing_mandatory"
            elif (not t) and is_fail:
                lvl, typ = "FAIL", "iol_cem_missing_safety"
            else:
                lvl, typ = "WARN", "iol_cem_missing_plain"
            out.append(vm.entry(lvl, 140, typ, location=loc, doc=io_doc,
                                location2=_CE_LABEL, doc2=ce_doc, info=info))
            continue

        lvl = "FAIL" if is_fail else "WARN"
        caller_fld = vm.fld_text(row.get("functional_unit"), row.get("location"), row.get("device"))
        if status == "fld_only":
            ce_addrs = ", ".join(sorted(idx["raw_addr_by_key"].get(k, {}).values())) or "(none)"
            cmp = vm.cmp_detail(vm.raw(row.get("bit")), ce_addrs, caller_fld,
                                idx["raw_fld_by_key"].get(k, ""), addr_eq=False, fld_eq=True)
            out.append(vm.entry(lvl, 140, "iol_cem_fld_only", location=loc, doc=io_doc,
                                location2=idx["loc_by_key"].get(k, ""), doc2=ce_doc, info=info, cmp=cmp))
        else:  # addr_only
            other = ", ".join(sorted(idx["by_addr"].get(a, set()))) or "(none)"
            cmp = vm.cmp_detail(vm.raw(row.get("bit")), vm.raw(row.get("bit")), caller_fld, other,
                                addr_eq=True, fld_eq=False)
            out.append(vm.entry(lvl, 140, "iol_cem_addr_only", location=loc, doc=io_doc,
                                location2=idx["loc_by_addr"].get(a, ""), doc2=ce_doc, info=info, cmp=cmp))

    out.append(vm.entry("INFO", 140, "iol_cem_summary", checked=checked))
    if skipped:
        out.append(vm.entry("INFO", 140, "iol_cem_skip_summary", skipped=skipped))
    return out

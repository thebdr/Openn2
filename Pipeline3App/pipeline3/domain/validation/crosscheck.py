"""130/140 - the two cross-checks (built from scratch; P2 `validation/checks.py` for intent only).

130 forward (CEM->IOL): every C&E reference must be declared in the I/O List (device + address).
140 reverse (IOL->CEM): every mandatory/safety I/O signal must be present in the C&E.
Both link the matched cell in the *other* workbook via `location2`/`doc2`; the visible link is
`sheet!cell` only. C&E absent -> the sub-phase is skipped (one SKIP), never raises.
"""
from __future__ import annotations
import os

from pipeline3.core import config
from pipeline3.core.model import InfoBlock
from pipeline3.io.workbook import FileLockedError
from pipeline3.domain.validation import model as vm, indexes

_DEFAULT_WORDS = ("emergency", "safety", "relay", "contactor", "enable")
# The "<caller> vs <other>" link text when there is NO matched cell in the other workbook (a miss):
# location2 carries this label (no "!"), doc2 the workbook -> the GUI opens that file (no cell).
_IO_LABEL, _CE_LABEL = "I/O List", "C&E Matrix"


def _ce_present(ce) -> bool:
    return bool(ce.get("path") and os.path.exists(ce["path"]))


# --- 130 forward: CEM -> IOL ------------------------------------------------ #
def run_xcheck_cem_iol(ctx) -> list:
    ce = ctx.params.get("ce") or {}
    if not _ce_present(ce):
        return [vm.entry("SKIP", 130, "ce_absent", ctx.lang)]
    try:
        refs, _ = indexes.read_ce_refs(ctx.params)
    except FileLockedError:
        return [vm.entry("FAIL", 130, "ce_locked", ctx.lang)]

    io_index = indexes.build_io_index(ctx.rows or [])
    ce_doc, io_doc = os.path.basename(ce["path"]), os.path.basename(ctx.io_list_path())
    out, checked = [], 0
    for ref in refs:
        if not ref["addr"]:
            continue
        checked += 1
        info = InfoBlock(bit=ref["raw_addr"], fld=ref["raw_fld"])
        if not ref["key"]:
            out.append(vm.entry("FAIL", 130, "cem_ref_empty", ctx.lang, location=ref["loc"], doc=ce_doc, info=info))
            continue
        hit = io_index.get(ref["key"])
        if hit is None:
            # no I/O List cell to point at -> link the I/O List FILE (open it) as the second link
            out.append(vm.entry("FAIL", 130, "cem_dev_missing", ctx.lang, location=ref["loc"], doc=ce_doc,
                                location2=_IO_LABEL, doc2=io_doc, info=info))
            continue
        if ref["addr"] in hit["addrs"]:
            # full match: link BOTH workbooks - the C&E ref cell (primary) AND the matched I/O List cell
            out.append(vm.entry("PASS", 130, "cem_match", ctx.lang, location=ref["loc"], doc=ce_doc,
                                location2=hit.get("source_cell", ""), doc2=io_doc, info=info))
            continue
        io_addrs = ", ".join(sorted(hit["raw_addr"].values())) or "(none)"
        cmp = vm.cmp_detail(ref["raw_addr"], io_addrs, ref["raw_fld"], hit["raw_fld"], addr_eq=False, fld_eq=True)
        out.append(vm.entry("FAIL", 130, "cem_fld_addr_mismatch", ctx.lang, location=ref["loc"], doc=ce_doc,
                            location2=hit["source_cell"], doc2=io_doc, info=info, cmp=cmp))
    out.append(vm.entry("INFO", 130, "cem_summary", ctx.lang, refs=checked))
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


def run_xcheck_iol_cem(ctx) -> list:
    ce = ctx.params.get("ce") or {}
    if not _ce_present(ce):
        return [vm.entry("SKIP", 140, "ce_absent", ctx.lang)]
    try:
        refs, _ = indexes.read_ce_refs(ctx.params)
    except FileLockedError:
        return [vm.entry("FAIL", 140, "ce_locked", ctx.lang)]
    idx = indexes.build_ce_index(refs)

    io_doc, ce_doc = os.path.basename(ctx.io_list_path()), os.path.basename(ce["path"])
    words = ctx.params.get("ce_mandatory_words") or _DEFAULT_WORDS
    excluded = ctx.params.get("ce_excluded_words") or []
    always = ctx.params.get("ce_always_excluded_words") or []
    fuzzy = int(ctx.params.get("ce_fuzzy_chars", 2) or 0)
    full_check = config.as_bool(ctx.params.get("ce_full_check"))

    out, checked, skipped = [], 0, 0
    for row in ctx.rows or []:
        k = vm.key(row.get("functional_unit"), row.get("location"), row.get("device"))
        if not k:
            continue
        a = vm.addr(row.get("bit"))
        t = row.get("_type") or {}
        info, loc = vm.info_for_row(row), row.get("source_cell", "")
        # Whether to cross-check this row (per the configured decision tree):
        #   typed & ce_mandatory yes/warn -> CHECK   (yes -> FAIL severity, warn -> WARN)
        #   typed & ce_mandatory no/unset -> NO_CHECK   ("no" is a skip trigger)
        #   untyped & always_excluded     -> NO_CHECK
        #   untyped & (full_check|safety) -> CHECK
        #   untyped & (excluded | plain)  -> NO_CHECK   (only when ce_full_check is false)
        mand = ""
        if t:
            mand = (t.get("ce_mandatory") or "").lower()
            if mand not in ("yes", "warn"):       # "no"/unset -> not required in the C&E -> NO_CHECK
                skipped += 1
                out.append(vm.entry("SKIP", 140, "iol_cem_not_required", ctx.lang, location=loc, doc=io_doc, info=info))
                continue
            is_fail = (mand == "yes")
        else:
            if not a:
                continue
            text = _row_text(row)
            aw = vm.first_match(text, always, 0)
            if aw:
                skipped += 1
                out.append(vm.entry("SKIP", 140, "iol_cem_skipped", ctx.lang, word=str(aw), location=loc, doc=io_doc, info=info))
                continue
            is_safety = vm.matches_words(text, words, fuzzy)
            if not full_check and not is_safety:
                skipped += 1
                ew = vm.first_match(text, excluded, fuzzy)
                if ew:
                    out.append(vm.entry("SKIP", 140, "iol_cem_skipped", ctx.lang, word=str(ew), location=loc, doc=io_doc, info=info))
                else:
                    out.append(vm.entry("SKIP", 140, "iol_cem_unclassified", ctx.lang, location=loc, doc=io_doc, info=info))
                continue
            is_fail = is_safety

        checked += 1
        status = _ce_match(k, a, idx)
        if status == "full":
            # full match: link BOTH workbooks - the I/O List cell (primary) AND the matched C&E cell
            out.append(vm.entry("PASS", 140, "iol_cem_match", ctx.lang, location=loc, doc=io_doc,
                                location2=idx["loc_by_key"].get(k, ""), doc2=ce_doc, info=info))
            continue
        if status == "missing":
            if t and mand == "yes":
                lvl, typ = "FAIL", "iol_cem_missing_mandatory"
            elif (not t) and is_fail:
                lvl, typ = "FAIL", "iol_cem_missing_safety"
            else:
                lvl, typ = "WARN", "iol_cem_missing_plain"
            # no C&E cell to point at -> link the C&E FILE (open it) as the second link
            out.append(vm.entry(lvl, 140, typ, ctx.lang, location=loc, doc=io_doc,
                                location2=_CE_LABEL, doc2=ce_doc, info=info))
            continue

        lvl = "FAIL" if is_fail else "WARN"
        caller_fld = vm.fld_text(row.get("functional_unit"), row.get("location"), row.get("device"))
        if status == "fld_only":
            ce_addrs = ", ".join(sorted(idx["raw_addr_by_key"].get(k, {}).values())) or "(none)"
            cmp = vm.cmp_detail(vm.raw(row.get("bit")), ce_addrs, caller_fld,
                                idx["raw_fld_by_key"].get(k, ""), addr_eq=False, fld_eq=True)
            out.append(vm.entry(lvl, 140, "iol_cem_fld_only", ctx.lang, location=loc, doc=io_doc,
                                location2=idx["loc_by_key"].get(k, ""), doc2=ce_doc, info=info, cmp=cmp))
        else:  # addr_only
            other = ", ".join(sorted(idx["by_addr"].get(a, set()))) or "(none)"
            cmp = vm.cmp_detail(vm.raw(row.get("bit")), vm.raw(row.get("bit")), caller_fld, other,
                                addr_eq=True, fld_eq=False)
            out.append(vm.entry(lvl, 140, "iol_cem_addr_only", ctx.lang, location=loc, doc=io_doc,
                                location2=idx["loc_by_addr"].get(a, ""), doc2=ce_doc, info=info, cmp=cmp))

    out.append(vm.entry("INFO", 140, "iol_cem_summary", ctx.lang, checked=checked))
    if skipped:
        out.append(vm.entry("INFO", 140, "iol_cem_skip_summary", ctx.lang, skipped=skipped))
    return out

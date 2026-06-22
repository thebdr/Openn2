# Pipeline3App — next-session handoff

Paste the fenced block below into a fresh session. `CLAUDE.md` (architecture/status) + the memory
index auto-load; the approved design lives in the plan
`~/.claude/plans/the-codebase-in-openn2-pipeline2app-rippling-canyon.md`.

---

```
Continue the Pipeline3App rebuild at C:\Source\Repos\_Openn2\Pipeline3App (branch tia181920). First
read Pipeline3App/CLAUDE.md (esp. the phase sections you're touching + Conventions & gotchas).

Run the data-independent green gate first to confirm the baseline:
    cd Pipeline3App && for t in tests/unit/test_*.py; do python "$t" || break; done
(test_golden_validation.py is data-dependent — re-freeze with --freeze if the real docs legitimately changed.)

DONE (phases 100-800): documents validation, fill, staging, interfaces, signals, diagnosis, hardware,
and ALL of Phase 800 software generation:
  - The 8 per-template block builders (00/02/03/04/05/06/07/08) in domain/blocks/builders.py over the
    single staged database; data-independent cases in tests/unit/test_builders.py.
  - FLD dedup (iol_FLD/ce_FLD/combined_FLD) + the "No Operation" DB seed member (the slot pad).
  - 02_COM safe-DB generated in phase 800; 05_DOORS renamed to 07_DOOR everywhere; encoder datablock
    rule fixed (legacy ENC* -> N1/2).
  - 03 Zone Cumulative is emitted as a DIRECT exactly-sized SW.Blocks.FC XML (domain/blocks/xml_emit.py)
    into the Open2App ImportReady surface (UTF-8 BOM + CRLF + multi-line; its CreationInfo CSV is dropped).
  - The shell CreationInfo/SoftwareBlocksBuilderShells.xlsm is the editable working surface (a VALID
    macro-enabled .xlsm; B2 = fill/keep/override): fill seeds each sheet (standard = an exact $/%/@ copy
    of the CSV; 03 = a coil-columns cause->effect sheet, one column per coil), keep = builder drives /
    sheet left alone, override = write the CSV from the sheet VERBATIM (iterator spread preserved; 03
    reads its coil columns -> the FC XML).
  - A file-write OSError (e.g. a locked output) is a logged [ERROR] that HALTS the run, not a traceback.
All committed (c373636 builders+03-XML+halt; 662d9c3 editable shells + override-verbatim). The 03 FC XML
imports cleanly into TIA and the .xlsm shell opens in Excel (user-verified).

OPEN / candidates (follow my lead — ASK before picking one):
  - Extend the direct-FC-XML and/or the coil-columns editable shell to other blocks if useful.
  - Phase 900 Reporting: 910 Pipeline Coverage Report; 920 TIA Project Coverage (920 pending Open2App's
    project text-export).
  - M10 CLI + an Open2App-path contract test (BuilderData byte-stability).
  - M11-13 GUIs (dark, registry-driven phase bar, YAML-explorer config, selectable projects root) + the
    slim designer + Project Manager. M14 packaging (two exes).

HOW WE WORK: one focused change at a time; PROPOSE the mapping/design and SHOW me real output; ASK when
domain judgement is needed (it's mine — you implement); iterate until I bless it; keep the green gate
green; add a data-independent unit case. A question is just a question — answer it, don't change code.

HONOR (full detail in CLAUDE.md): reuse the shared primitives + domain/identity; the Open2App contract
(write only under Shared/OutputTree/TiaPortalProjectInterface/BuilderData/ — byte-stable); comma CSV;
tag/device strings are text (data_type="s"); generated TIA Openness XML = UTF-8 BOM + CRLF + multi-line;
commit/push only when I ask (end commit messages with the Co-Authored-By line in CLAUDE.md).
```

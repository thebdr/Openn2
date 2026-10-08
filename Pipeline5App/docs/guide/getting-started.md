# Getting started

Pipeline5 builds a TIA Portal project from two hand-authored documents - the **I/O List** and the
**Cause & Effect Matrix** - through a chain of phases. Every datum a phase reads, infers, or creates
lands in the **SSOT database** (`Database/` - CSV tables with JSON cells); the `BuilderData/` export
files are byte-stable projections of those tables - the OP5 handoff workspace (VCI-shaped: `Devices &
networks/`, `Templates/`, `<PLC>/Program blocks/`, `<PLC>/PLC tags/`), every file opening with a `#!openn`
header that names its kind and the generation that wrote it (`Shared/PL5_OP5_contract.md`).

## A typical session

- Pick or create a project via **Project ▾** (the title bar shows the active one).
- Set the input documents on the **Documents** tab.
- Click a phase button to run one phase, or **Run Pipeline** for the whole chain.
- Read the **Log** tab; `Sheet!Cell` references are clickable and open Excel at the cell.
- Inspect what was built: the **Files** tab (every produced file) and the **Database Explorer**
  (SQL over the SSOT tables).

## Keys and buttons

- **F1** opens this guide at the section for the focused part of the window.
- **ƒx** on the toolbar opens the Expression Builder - see [Expressions](guide://expressions).
- **Theme / Levels / Lang / Font / Log to file** are the chrome toggles; each persists to
  `config_project/app_config.yaml`.

## When something is off

Every check lands as a **finding** with a severity; blocking FAILs halt the phase. The
[Findings & treatments](guide://treatments) section explains how to re-grade a finding when the
document is right and the rule is too strict.

The app ships with its source - when the guide falls short, read the code:
[pipeline5/](src://pipeline5).

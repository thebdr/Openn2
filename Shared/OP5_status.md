# OP5 status — hand-over to the PL5 session (2026-10-08)

Written by the OP session at the OP3 freeze. Read together with `Shared/PL5_OP5_contract.md` (the contract,
normative) and `Openn5App/CLAUDE.md` (the app's invariants). This note is the *state*, not the spec; delete it
once PL5 has consumed it or fold what still matters into the contract.

## 1. What exists

| | |
|---|---|
| App | `Openn5App/` → `bin\Debug\Openn5.exe` (.NET Framework 4.8 WPF, old-style csproj; TIA Openness V18–V20) |
| Origin | copy of `Openn3App/` (OP3) made 2026-10-07; root namespace still `Openn`; everything OP3 can do, OP5 can do |
| OP3 | **frozen 2026-10-08** (banner in `Openn3App/CLAUDE.md`): bug fixes for shipped PL3/PL4 projects only, mirrored from OP5 |
| Build | `MSBuild.exe Openn5.csproj /t:Build /p:Configuration=Debug` from `Openn5App\`; `packages\` is gitignored (copy from `Openn3App\packages` or restore) |
| Verified | builds clean; attribute dump against the live FVT LaPoste project (TIA V18) works incl. the new transfer-area sections; loader/parser exercised TIA-free by reflection |

## 2. What OP5 has beyond OP3

1. **Contract layer** `Openn5App/00_Contract/` (Siemens-free): `InputKind` (the kind taxonomy = contract §2),
   `OpennHeader` (`#!openn … #!end` parsing = §3), `WorkspaceCatalog.Scan(root)` (classification + placement =
   §4–5). "Scan BuilderData" on the Project tab logs the catalog. `CsvTable.Header` + `HardwareConfigLoader.
   CheckHeader` consume the header: wrong kind or newer schema = load error; legacy `#!format=2` / missing header
   = warning (v1). `BlockXmlGenerator` resolves a relative `template=` via csv folder → `Templates/` upwards →
   `Shared/Templates/Tia Portal Software Blocks`.
2. **PN/PN coupler transfer areas** (also in OP3, last feature before the freeze): dump prints
   `::TransferArea(i)` + `.Addr(j)` / `.PartnerAddr(j)`; Modules.csv rows whose model is of type `TransferArea`
   are created on the station's PROFINET interface. Semantics verified on a GUI-configured coupler dump
   (PLC-side addresses = `PartnerAddresses`; IN ⇒ `PartnerToLocalLength`, OUT ⇒ `LocalToPartnerLength`).
   **A generation run of such a row has not been executed on TIA yet** — first real run: generate one coupler
   with two rows, dump, compare with the hand-made n0006 dump.
3. **DeviceTypesDatabase conventions documented** in contract §2.1: plain ids, default cards `<PARENT>:SUFFIX`,
   transfer-area models; the `_AutoPluggedCard` rows are retired (removed from the shared csv and the Passing
   fixture — TIA-auto-plugged submodules are addressed through the head's station row, `Item(1).Item(3).Item(0).…`).

## 3. What PL5 owes (contract §6) — **done 2026-10-08 by the PL5 session** (see the contract's §6 status, §8 steps 2+3 and Appendix A; left: §6.7 the hand-maintained files, and the TIA smoke of step 1 / step 3)

- `#!openn` header on every BuilderData file (csv lines / XML first comment / `//` source lines / `.openn`
  sidecar for `PLCTags.xlsx`), `run` id per generation + `.openn/workspace.openn.config`.
- VCI-shaped workspace (`<PLC>/Program blocks/<group>`, `Devices & networks`, `Templates/` at the root,
  relative `template=`); OP5 v1 still reads the legacy BuilderData layout with warnings.
- `DeviceTypesDatabase.csv` keeps the three id shapes of §2.1; transfer areas for couplers come from the I/O
  list as module rows (`Module Name` = area name, `Slot` = position, I/Q Addr = PLC start addresses,
  `PartnerToLocalLength=` / `LocalToPartnerLength=` as custom parameters, model `TransferArea-IN|OUT|IN_OUT`).
- Parity oracle `scripts/parity_vs_pl4.py`: header block = allowed difference. It reads `Pipeline4App/` from the
  repo root — if PL4 leaves the working branch, the oracle needs a frozen PL4 output snapshot instead.

## 4. Open on the OP5 side (in order)

1. First real transfer-area generation run (see §2.2).
2. UI rework on top of the catalog (workspace-root picker instead of per-path buttons; the Shared paths are
   still resolved from the exe location by `AppPaths`).
3. Contract v2: require the header; §9 open questions (tag tables xlsx vs XML, UDT emission, `.db` sources,
   multi-PLC, device groups) — decide in the contract document, then `00_Contract/` and this app follow in the
   same commit.
4. Export side (TIA → PL5 coverage report, phase 920) is implemented in OP5 as XML/CAx export but PL5 does not
   read it yet.

## 5. Repository notes

- Branch `pl5` carries the whole monorepo history (Pipeline2/3/4App, Openn3App, FileXYApp). PL5 imports
  `FileXYApp` (`workbench/filexy_shim.py`, `../../FileXYApp`) at runtime — it must stay next to `Pipeline5App`
  on any slimmed branch. `Shared/` is the only exchange surface between OP5 and PL5.
- Openn-side working dirs that must stay out of git: `bin/ obj/ packages/ lib/Siemens.Engineering.dll
  GeneratedBlocks/ AttributeDumps/ Logs/ TiaProjects/` (all in `.gitignore`).

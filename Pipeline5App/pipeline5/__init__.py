"""Pipeline5App (PL5) - the system-type successor to Pipeline4App.

One shared KERNEL (document ingestion, SSOT database, findings/severity, core/expr, GUI framework)
plus a `systems/` tree mirroring the platform -> toolchain -> system taxonomy. A system is an
explicitly registered `System` descriptor (`pipeline5.systems.system_contract`) carrying everything
the kernel must never hardcode: phases, handlers, builders, emitters, symbols, output layout, config
root. Kernel code receives the System object - it NEVER branches on a type id.

Architecture record: the approved PL5 plan (see `.zen/evidence/P-001.md`); contract clauses
C-001..C-020 (the preserved PL4 baseline) + P-008..P-013 (the PL5 capability deltas).
"""

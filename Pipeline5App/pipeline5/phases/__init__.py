"""The phases - one chapter per pipeline capability, in the order the operator runs them.

Every chapter owns its logic, its checks, and (from step 5) its panel.py; chapters NEVER import
each other - they communicate only through the truth/ tables (enforced by the architecture
contracts, tests/unit/test_architecture_contracts.py). Operator phase NUMBERS live in the phase
registry, never in folder names - adding or renumbering a phase touches the registry alone.

CHAPTERS: staging (300/310/320) - fillout (200) - validation (100) - changes (100b) -
interfaces (400) - io_tags (510) - datablocks (520) - diagnosis (600) - hardware (700) -
software_blocks (800) - coverage (900) - chain_reactions (arrives with P-009).

A _siemens_s7/ subfolder inside a chapter is QUARANTINE: TIA-specific code awaiting its
migration-step-4 move to systems/plc_based/siemens_s7/.
"""

"""Phase 800 (Software Generation) - the block-builder package.

A clean-room port of PL3's `domain/blocks/`: the builder spine (`database`/`table`/`registry`), the
hand-written per-template builders (`builders`), the template key-inventory scan (`templates`), and the
engine that runs the builders -> the `software_blocks` + `software_block_members` SSOT tables -> the
`$/#/%/@` CreationInfo CSVs. The editable `.xlsm` shells (a PL3 operator-editing surface, NOT part of the
OP4 import contract) are deferred; the CreationInfo CSVs are produced directly in `fill` mode.
"""

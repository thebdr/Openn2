"""Siemens S7 - Safety: the first registered system (the production pipeline PL4 shipped).

  system.py   SYSTEM - the descriptor the catalog registers; everything Siemens-Safety-specific
              the kernel must never hardcode hangs off it.

Since the step-4 extraction the Safety code lives HERE: block_builders (the 00-08 safety
builders, registering into SYSTEM.builders) + opc_diagnosis_scl; the toolchain-shared
emitters sit one level up.
"""

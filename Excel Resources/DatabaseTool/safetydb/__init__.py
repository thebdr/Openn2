"""safetydb - Python rebuild of the Safety DB pipeline.

documentation (I/O List + C&E matrix)
  -> staging (strikethrough-aware, canonical columns)
  -> validation (consolidated ISSUES report)
  -> database (normalized signals / hardware / diagnosis)
  -> outputs (Openn2 hardware csv, I/O tags, custom DBs, diagnosis, interfaces)

Replaces the Power Query/VBA pipeline: pure Python (openpyxl), runnable and
testable without Excel. Config lives as versioned CSV/JSON under ../config.
"""

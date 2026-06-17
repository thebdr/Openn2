"""pipeline2 - Python rebuild of the Safety DB pipeline.

documentation (I/O List + C&E matrix)
  -> staging (strikethrough-aware, canonical columns)
  -> validation (standalone + cross-checks -> documents_validation_report.txt/.html)
  -> outputs (hardware csv, I/O tags, custom DBs, diagnosis, interfaces)

Replaces the Power Query/VBA pipeline: pure Python (openpyxl), runnable and
testable without Excel. Config lives as versioned CSV/YAML under config_project/.
"""

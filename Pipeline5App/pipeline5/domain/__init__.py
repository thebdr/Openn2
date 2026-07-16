"""The pipeline stages - every module fills or projects the SSOT tables.

WHERE TO LOOK (suffix convention: _builder creates SSOT rows · _schema defines table columns ·
_checks validate · emitters/writers produce delivery artifacts):

  iolist_staging.py       ph300: the I/O List -> the signals table (+ diagnosis_cabinets)
  cematrix_annotation.py  ph320: C&E areas onto the staged signals
  signal_identity.py      FLDs, tag names, per-type templates
  signals_schema.py       the signals fact-table columns
  fillout/                ph200: raw doc -> classified doc (script type, index, diag allocation)
  datablock_generator.py  ph520: the DB registry evaluator + signal write-back
  datablock_templates.py  the member render + for_each evaluation engine
  datablock_schema.py     db_blocks / db_members / instance_dbs columns
  interface_builder.py    ph400: interfaces + interface_elements (mirror set, byte allocation)
  diagnosis_builder.py    ph600: the unified diagnosis_entries (io + logic)
  diagnosis_schema.py     diagnosis_entries / diagnosis_cabinets columns
  diaglist_csv.py         ph610: the DiagList_IO/_Logic CSV projection
  signal_coverage.py      ph900: the per-signal placement trace + ORPHAN/UNPLACED
  validation/             ph100: document validators + the report runner
  changes/                ph100b: the before/after document quality report
  software_blocks/        ph800: builders -> block tables -> the emit surfaces

  TRANSITIONAL (Siemens-specific - move to systems/plc_based/siemens_s7/ at migration step 4):
  datablock_xml.py · io_tags.py · interface_scl.py · interface_xlsx.py · diagnosis_scl.py ·
  hardware.py · hardware_csv.py (+ the TIA emit halves inside software_blocks/)
"""

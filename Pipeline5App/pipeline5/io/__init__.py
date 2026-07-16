"""Document I/O - format-level, system-blind.

WHERE TO LOOK:
  xlsx_reader.py           the one shared workbook reader (by column position)
  xlsx_surgical_writer.py  in-place xlsx editing (stdlib ZIP + regex XML; byte-preserving)
  report_renderer.py       Finding -> the aligned txt + HTML reports
"""

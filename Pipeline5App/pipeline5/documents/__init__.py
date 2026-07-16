"""Documents - reading and surgically writing the customer workbooks.

Format-level and system-blind: these know xlsx, not signals.

WHERE TO LOOK:
  xlsx_reader.py           the one shared workbook reader (by column position)
  xlsx_surgical_writer.py  in-place xlsx editing (stdlib ZIP + regex; byte-preserving; array-freeze)
"""

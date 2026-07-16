"""Staging - the I/O List becomes the signals table (the pipeline's first fact).

  iolist.py    read the matched IoList sheets -> signals + diagnosis_cabinets (oracle 310)
  cematrix.py  layer the Cause&Effect areas on top, re-stamping uids (oracle 320)
"""

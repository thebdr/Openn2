"""Validation - the document checks (phase 100): does the customer paperwork hold together?

  iolist_checks.py    110 - the I/O List standalone checks
  cematrix_checks.py  120 - the C&E standalone checks
  cematrix_refs.py    the io/ce indexes + C&E reference reader the cross-checks share
  crosscheck.py       130/140 - I/O List <-> C&E cross-checks
  diagcheck.py        the diagnosis-slot checks
  runner.py           runs 110->140, records issues, writes the 4 reports (never halts)
"""

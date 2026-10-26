#!/bin/bash
# One PRODUCTION folder from an I/O List (user 2026-10-24: laid out like the FVZ reference `PRODUCTION/`, so it can be
# pasted there): the PL5 handoff of every cifX card into <out>/HilscherIOCard<n>/SyconNetProjectInterface/, each
# card's SYCON.net project built beside it as HilscherIOCard<n>/HilscherPnCard_<n>.spj (canvas laid out, verified
# by read-back: HilscherPnCard_<n>.verification.txt), then <out>/IODriver/BusField.csv for all the cards.
# Usage (Git Bash):  bash scripts/build_production.sh "<list.xlsx>" "<out folder>" [card ...]
#                    RESUME=1 bash scripts/build_production.sh ...      (re-export, then build --resume)
#                    EXPORT_ONLY=1 ...                                   (the handoff alone, no SYCON.net)
# Logs and reports (user 2026-10-24: "keep the _logs folder in the card folder. also, name it _PL_Logs"):
# <out>/_PL_Logs/export.log + build.log (the list), <out>/HilscherIOCard<n>/_PL_Logs/build[_resume].log +
# HilscherPnCard_<n>.verification.txt (the card).
PY=/c/Source/Repos/_Openn5/.venv/Scripts/python.exe
APP=/c/Source/Repos/_Openn5/Sycon5App
PL5=/c/Source/Repos/_Openn5/Pipeline5App
LIST="$1"; OUT="$2"; shift 2
[ -z "$LIST" ] || [ -z "$OUT" ] && { echo "usage: build_production.sh <list.xlsx> <out folder> [card ...]"; exit 2; }
LOGS="$OUT/_PL_Logs"
mkdir -p "$OUT" "$LOGS"
WIN=$(cygpath -w "$OUT")
LISTWIN=$(cygpath -w "$LIST")
echo "$(date +%H:%M:%S) export $LISTWIN -> $WIN" >> "$LOGS/build.log"
(cd "$PL5" && "$PY" -W ignore -m pipeline5.systems.ipc_based.intervalzero_rtx.sycon_handoff --iolist "$LISTWIN" --out "$WIN") > "$LOGS/export.log" 2>&1
grep "^SYCON handoff" "$LOGS/export.log" | tee -a "$LOGS/build.log"
[ -n "$EXPORT_ONLY" ] && exit 0
if [ $# -gt 0 ]; then cards="$@"; else cards=$(ls -d "$OUT"/HilscherIOCard* 2>/dev/null | sed 's/.*HilscherIOCard//' | sort -n); fi
flag=""; [ -n "$RESUME" ] && flag="--resume"; [ -n "$UPDATE" ] && flag="--update"     # UPDATE=1: the existing project brought up to the table
for n in $cards; do
  card="$OUT/HilscherIOCard$n"; name="HilscherPnCard_$n"
  mkdir -p "$card/_PL_Logs"
  report="$card/_PL_Logs/$name.verification.txt"
  echo "$(date +%H:%M:%S) card $n: build $flag" >> "$LOGS/build.log"
  (cd "$APP" && "$PY" -I scripts/build_from_handoff.py --handoff "$(cygpath -w "$card/SyconNetProjectInterface")" --out "$(cygpath -w "$card")\\$name.spj" --report "$(cygpath -w "$report")" $flag) > "$card/_PL_Logs/build${RESUME:+_resume}${UPDATE:+_update}.log" 2>&1
  rc=$?
  echo "$(date +%H:%M:%S) card $n: exit $rc - $(head -1 "$report" 2>/dev/null)" >> "$LOGS/build.log"
done
(cd "$APP" && "$PY" -I scripts/busfield.py --production "$WIN") 2>&1 | tee -a "$LOGS/build.log"

#!/bin/bash
# The four FVT test projects, one per machine type, built in sequence into spike/scratch (user 2026-10-23
# evening: "do a sycon project for us to test for each machine type: 1 sorter, 1 induction lines, 1 upstream,
# 1 chutes (1 card only)"). Each: the PL5 export of the I/O List (one cabinet sheet for a multi-card list), then
# build_from_handoff. Logs: spike/scratch/FVT_<name>/export.log, build.log; the summary in dinner_builds.log.
# Usage (Git Bash):  bash scripts/build_fvt_tests.sh [name ...]      (default: all four)
PY=/c/Source/Repos/_Openn5/.venv/Scripts/python.exe
APP=/c/Source/Repos/_Openn5/Sycon5App
PL5=/c/Source/Repos/_Openn5/Pipeline5App
LISTS='Z:\Work\0 Commesse\FVT_LaPoste\0 Documenti Elettrici\_IOLists'
SUMMARY="$APP/spike/scratch/dinner_builds.log"

build() {
  local name="$1" list="$2" sheet="$3"
  local out="$APP/spike/scratch/FVT_$name"
  local win="C:\\Source\\Repos\\_Openn5\\Sycon5App\\spike\\scratch\\FVT_$name"
  mkdir -p "$out"
  echo "$(date +%H:%M:%S) $name: export" >> "$SUMMARY"
  if [ -n "$sheet" ]; then
    (cd "$PL5" && "$PY" -W ignore -m pipeline5.systems.ipc_based.intervalzero_rtx.sycon_handoff --iolist "$LISTS\\$list" --out "$win\\SyconNetProjectInterface" --sheet "$sheet") > "$out/export.log" 2>&1
  else
    (cd "$PL5" && "$PY" -W ignore -m pipeline5.systems.ipc_based.intervalzero_rtx.sycon_handoff --iolist "$LISTS\\$list" --out "$win\\SyconNetProjectInterface") > "$out/export.log" 2>&1
  fi
  tail -1 "$out/export.log" >> "$SUMMARY"
  echo "$(date +%H:%M:%S) $name: build" >> "$SUMMARY"
  (cd "$APP" && "$PY" -I scripts/build_from_handoff.py --handoff "spike/scratch/FVT_$name/SyconNetProjectInterface" --out "$win\\$name.spj") > "$out/build.log" 2>&1
  local rc=$?
  echo "$(date +%H:%M:%S) $name: build exit $rc - $(head -1 "$out/$name.verification.txt" 2>/dev/null)" >> "$SUMMARY"
}

ALL="Sorter_Lower Induction_LowerGR1 Upstream_ConveyorsLower Chutes_Card1"
for name in ${@:-$ALL}; do
  case "$name" in
    Sorter_Lower)            build "$name" "8FVT_IO0010 - Sorter I-O List - LOWER SORTER_R1.2.xlsx" "" ;;
    Induction_LowerGR1)      build "$name" "8FVT_IO0011 - I-O List Induction lines - LOWER GR1_R1.2.xlsx" "" ;;
    Upstream_ConveyorsLower) build "$name" "8FVT_IO0013 - Conveyors I-O List LOWER_R0.1.xlsx" "" ;;
    Chutes_Card1)            build "$name" "8FVT_IO0030_Chute_IO_List_R1.0.xlsx" "R5.S1.C1" ;;
    *) echo "unknown build $name" >> "$SUMMARY" ;;
  esac
done
echo "$(date +%H:%M:%S) done" >> "$SUMMARY"

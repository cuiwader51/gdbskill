#!/usr/bin/env bash
# Batch-triage a directory of core files into text reports.
#
# Usage:
#   ./triage-core.sh <binary> <core-file-or-dir> [output-dir]
#
# Examples:
#   ./triage-core.sh ./app ./core
#   ./triage-core.sh /usr/bin/myd /var/crash/ ./reports
#
# For each core, writes <output-dir>/<core>.triage.txt containing registers,
# fault address, full backtrace, and all-thread backtraces.

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <binary> <core-file-or-dir> [output-dir]" >&2
  exit 2
fi

BIN="$1"
TARGET="$2"
OUTDIR="${3:-./triage-reports}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GDB_SCRIPT="$SCRIPT_DIR/triage.gdb"

command -v gdb >/dev/null || { echo "gdb not found in PATH" >&2; exit 1; }
[[ -f "$BIN" ]] || { echo "Binary not found: $BIN" >&2; exit 1; }
[[ -f "$GDB_SCRIPT" ]] || { echo "Missing $GDB_SCRIPT" >&2; exit 1; }

mkdir -p "$OUTDIR"

triage_one() {
  local core="$1"
  local name out
  name="$(basename "$core")"
  out="$OUTDIR/${name}.triage.txt"
  echo ">> Triaging $core -> $out"
  {
    echo "# Binary : $BIN"
    echo "# Core   : $core"
    echo "# Date   : $(date -Is)"
    echo "# Build  :"
    readelf -n "$BIN" 2>/dev/null | grep -i 'Build ID' || true
    echo
  } > "$out"
  gdb --batch --nx -x "$GDB_SCRIPT" "$BIN" "$core" >> "$out" 2>&1 || \
    echo "(gdb exited non-zero; report may be partial)" >> "$out"
}

if [[ -d "$TARGET" ]]; then
  shopt -s nullglob
  found=0
  for core in "$TARGET"/core* "$TARGET"/*.core; do
    [[ -f "$core" ]] || continue
    triage_one "$core"
    found=1
  done
  [[ "$found" == 1 ]] || { echo "No core files found in $TARGET" >&2; exit 1; }
else
  [[ -f "$TARGET" ]] || { echo "Core not found: $TARGET" >&2; exit 1; }
  triage_one "$TARGET"
fi

echo "Done. Reports in $OUTDIR/"

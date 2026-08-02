#!/usr/bin/env bash
# Run a native test command and create GDB bundles for any cores it leaves behind.
# Usage: ci-triage.sh <binary> <artifact-dir> -- <test-command> [args...]

set -uo pipefail

if [[ $# -lt 4 || "$3" != "--" ]]; then
  echo "Usage: $0 <binary> <artifact-dir> -- <test-command> [args...]" >&2
  exit 2
fi

BINARY="$1"
ARTIFACT_DIR="$2"
shift 3
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT="$SCRIPT_DIR/gdb_agent.py"

mkdir -p "$ARTIFACT_DIR"
ulimit -c unlimited 2>/dev/null || true

set +e
"$@"
TEST_EXIT=$?
set -e

if [[ $TEST_EXIT -ne 0 ]]; then
  found=0
  while IFS= read -r -d '' core; do
    found=1
    name="$(basename "$core")"
    python3 "$AGENT" collect "$BINARY" "$core" --output "$ARTIFACT_DIR/$name" || true
  done < <(find . -maxdepth 3 -type f \( -name 'core' -o -name 'core.*' -o -name '*.core' \) -print0)

  if [[ $found -eq 0 ]]; then
    printf 'Native test failed with exit code %s, but no local core was found. Check core_pattern or coredumpctl.\n' "$TEST_EXIT" \
      | tee "$ARTIFACT_DIR/no-core.txt"
  fi

  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    {
      echo "## Native crash triage"
      echo
      echo "Test exit code: \`$TEST_EXIT\`. Debug artifacts: \`$ARTIFACT_DIR\`."
    } >> "$GITHUB_STEP_SUMMARY"
  fi
fi

exit "$TEST_EXIT"
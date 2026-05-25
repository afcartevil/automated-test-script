#!/usr/bin/env bash
# Recursively find *.dbg under LOG_ROOT, aee_extract each, then run KSST64 on each *.dbg.DEC/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Skill root = parent of scripts/
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
AEE="${SKILL_ROOT}/tools/aee_extract/aee_extract"
KSST="${SKILL_ROOT}/tools/SpOfflineDebugSuite/linux/KSST64"

usage() {
  echo "Usage: $0 <LOG_ROOT>" >&2
  echo "  LOG_ROOT: root directory of Jira-downloaded logs (searched recursively for *.dbg)" >&2
  exit 1
}

[[ $# -eq 1 ]] || usage
LOG_ROOT="$(cd "$1" && pwd)"

[[ -x "$AEE" ]] || { echo "Missing or not executable: $AEE" >&2; exit 1; }
[[ -x "$KSST" ]] || { echo "Missing or not executable: $KSST" >&2; exit 1; }

mapfile -t DBG_FILES < <(find "$LOG_ROOT" -type f -name '*.dbg' | sort)

if [[ ${#DBG_FILES[@]} -eq 0 ]]; then
  echo "No .dbg files under: $LOG_ROOT" >&2
  exit 1
fi

for dbg in "${DBG_FILES[@]}"; do
  ddir="$(dirname "$dbg")"
  base="$(basename "$dbg")"
  echo "==> aee_extract: $dbg"
  ( cd "$ddir" && "$AEE" "$base" )

  mapfile -t DEC_DIRS < <(find "$ddir" -maxdepth 1 -type d -name '*.dbg.DEC' | sort)
  for dec in "${DEC_DIRS[@]}"; do
    decname="$(basename "$dec")"
    echo "==> KSST64: $ddir/$decname"
    ( cd "$ddir" && printf '\nq\n' | "$KSST" "./${decname}/" )
  done
done

echo "Done."

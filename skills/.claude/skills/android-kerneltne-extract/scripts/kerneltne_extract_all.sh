#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <LOG_ROOT>" >&2
  exit 1
}

[[ $# -eq 1 ]] || usage

LOG_ROOT="$(cd "$1" && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

KSST_BIN="$SKILL_ROOT/tools/SpOfflineDebugSuite/linux/KSST64"
DECOMPRESS_BIN="$SKILL_ROOT/tools/decompress/linux/tne_decompress"

[[ -x "$KSST_BIN" ]] || { echo "Missing KSST64: $KSST_BIN" >&2; exit 1; }
if ! command -v decompress >/dev/null 2>&1; then
  [[ -x "$DECOMPRESS_BIN" ]] || { echo "Missing decompress binary: $DECOMPRESS_BIN" >&2; exit 1; }
fi

mapfile -t TNE_FILES < <(find "$LOG_ROOT" -type f -name "*.tne" | sort)
[[ ${#TNE_FILES[@]} -gt 0 ]] || { echo "No .tne files found under: $LOG_ROOT" >&2; exit 1; }

classify() {
  local name="$1"
  case "$name" in
    0xffffff0c_*.tne) echo "HANG" ;;
    0xffffff0d_*.tne) echo "HWT" ;;
    0xffffff04_*.tne) echo "KE" ;;
    0xffffff15_*.tne) echo "OCP_REBOOT" ;;
    *) echo "OTHER" ;;
  esac
}

for tne in "${TNE_FILES[@]}"; do
  ddir="$(dirname "$tne")"
  tname="$(basename "$tne")"
  etype="$(classify "$tname")"
  echo "==> [$etype] decompress: $tne"

  before_file="$(mktemp)"
  after_file="$(mktemp)"
  trap 'rm -f "$before_file" "$after_file"' EXIT

  find "$ddir" -mindepth 1 -maxdepth 1 -type d | sort > "$before_file"
  if command -v decompress >/dev/null 2>&1; then
    ( cd "$ddir" && decompress "$tname" )
  else
    ( cd "$ddir" && "$DECOMPRESS_BIN" "$tname" )
  fi
  find "$ddir" -mindepth 1 -maxdepth 1 -type d | sort > "$after_file"

  mapfile -t NEW_DIRS < <(comm -13 "$before_file" "$after_file")
  rm -f "$before_file" "$after_file"

  if [[ ${#NEW_DIRS[@]} -eq 0 ]]; then
    echo "WARN: no new extracted dir detected for $tne, skip KSST64"
    continue
  fi

  for full_dir in "${NEW_DIRS[@]}"; do
    dir_name="$(basename "$full_dir")"
    path_part="$(dirname "$full_dir")"
    echo "==> KSST64 path/dir_name: $path_part / $dir_name"
    printf '\nq\n' | "$KSST_BIN" "$path_part/$dir_name/"
  done
done

echo "Done."

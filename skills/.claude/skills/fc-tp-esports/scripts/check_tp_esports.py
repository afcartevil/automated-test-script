#!/usr/bin/env python3
"""TP esports control import check — getprop + esports proc nodes."""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from adb_util import adb_shell, path_exists, require_device  # noqa: E402

_PROP_GROUPS: list[tuple[str, str, str]] = [
    # (new_prop, legacy_prop, version_label)
    ("ro.tr_game.tp_esports10.feature.support", "ro.os_game_tp_esports10.support", "esports10"),
    ("ro.tr_game.tp_esports20.feature.support", "ro.os_game_tp_esports20.support", "esports20"),
    ("ro.tr_game.tp_esports30.feature.support", "ro.os_game_tp_esports30.support", "esports30"),
]

_TRUTHY = frozenset({"true", "1"})

# FEATURE_ESPORT nodes from transsion_node.c
_REQUIRED_NODES: list[tuple[str, str, str]] = [
    # (path, write_probe, read_hint)
    ("/proc/game_mode", "0", r"gear position|\d"),
    ("/proc/game_state", "0", r"\d"),
    ("/proc/tp_transient_report_rate_switch", "0", r"\d"),
    ("/proc/tp_micro_control_accuracy", "0", r"\d"),
]

_OPTIONAL_NODES: list[str] = [
    "/proc/tp_report_rate_switch",
]


@dataclass
class PropResult:
    version: str
    prop: str
    actual: str
    ok: bool


def _getprop(name: str, adb: str | None) -> str:
    out, _ = adb_shell(f"getprop {name}", adb)
    return out.strip()


def _is_truthy(val: str) -> bool:
    return val.lower() in _TRUTHY


def check_properties(adb: str | None) -> tuple[bool, list[PropResult], str]:
    results: list[PropResult] = []
    enabled_version = ""
    for new_prop, legacy_prop, version in _PROP_GROUPS:
        actual = _getprop(new_prop, adb)
        if not actual:
            actual = _getprop(legacy_prop, adb)
            prop_used = legacy_prop if actual else new_prop
        else:
            prop_used = new_prop
        ok = _is_truthy(actual)
        results.append(PropResult(version=version, prop=prop_used, actual=actual, ok=ok))
        if ok and not enabled_version:
            enabled_version = version
    any_ok = any(r.ok for r in results)
    return any_ok, results, enabled_version


def _access_error(text: str) -> str | None:
    low = text.lower()
    if "permission denied" in low:
        return "Permission denied"
    if "no such file" in low or "not found" in low:
        return "No such file"
    if "read-only" in low:
        return "Read-only"
    return None


def check_node(
    path: str,
    write_val: str,
    read_hint: str,
    adb: str | None,
    *,
    do_write: bool,
) -> tuple[bool, str, str, str]:
    """Returns (ok, exists, read_status, write_status)."""
    if not path_exists(path, adb):
        return False, "no", "-", "MISSING"

    out, code = adb_shell(f"cat {path} 2>&1", adb)
    err = _access_error(out)
    if code != 0 or err:
        return False, "yes", err or f"exit {code}", "-"

    read_ok = bool(re.search(read_hint, out, re.I))
    read_st = "OK" if read_ok else f"WARN:{out[:40]!r}"

    write_st = "SKIP"
    if do_write:
        wout, wcode = adb_shell(f"echo {write_val} > {path} 2>&1", adb)
        werr = _access_error(wout)
        if wcode != 0 or werr:
            write_st = werr or f"exit {wcode}"
            return False, "yes", read_st, write_st
        write_st = "OK"

    ok = read_ok and (write_st in ("OK", "SKIP"))
    return ok, "yes", read_st, write_st


def main() -> int:
    p = argparse.ArgumentParser(description="Check TP esports control import")
    p.add_argument("--adb", default=None, help="adb executable path")
    p.add_argument(
        "--skip-write",
        action="store_true",
        help="only check property + node existence/read",
    )
    args = p.parse_args()
    adb = args.adb
    do_write = not args.skip_write

    require_device(adb)
    fail = False

    print("=== TP esports control import ===\n")

    any_prop, prop_results, version = check_properties(adb)
    print("** Properties (any one true/1) **\n")
    print("| version | property | actual | result |")
    print("|---------|----------|--------|--------|")
    for r in prop_results:
        status = "Pass" if r.ok else "Fail"
        print(f"| {r.version} | {r.prop} | {r.actual!r} | {status} |")
    print()
    if not any_prop:
        fail = True
        print("Property gate: Fail — no esports feature property enabled.")
    else:
        print(f"Property gate: Pass — enabled version: {version or 'unknown'}")
    print()

    print("** FEATURE_ESPORT proc nodes **\n")
    print("| node | exists | read | write | result |")
    print("|------|--------|------|-------|--------|")
    for path, write_val, read_hint in _REQUIRED_NODES:
        ok, exists, read_st, write_st = check_node(
            path, write_val, read_hint, adb, do_write=do_write
        )
        status = "Pass" if ok else "Fail"
        if not ok:
            fail = True
        print(f"| {path} | {exists} | {read_st} | {write_st} | {status} |")
    print()

    print("** Optional (dynamic report rate) **\n")
    print("| node | exists | note |")
    print("|------|--------|------|")
    for path in _OPTIONAL_NODES:
        exists = "yes" if path_exists(path, adb) else "no"
        note = "present" if exists == "yes" else "N/A"
        print(f"| {path} | {exists} | {note} |")
    print()

    if fail:
        print("RESULT: Fail — esports property or proc node check failed.")
        return 1
    print("RESULT: Pass — esports control looks imported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

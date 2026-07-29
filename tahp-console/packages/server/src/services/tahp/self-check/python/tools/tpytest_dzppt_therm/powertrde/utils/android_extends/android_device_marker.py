#!/usr/bin/env python3
"""
External marker store for Android devices (no sn in device path).
Markers stored under:
  /sdcard/automation_markers/apps/<pkg_safe>/{markers.json,metadata.json}
  /sdcard/automation_markers/device.json

Automatically attempts to migrate data from old-sn-based path:
  /sdcard/automation_markers/<serial>/apps/ -> /sdcard/automation_markers/apps/
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import shlex
import re
from typing import Optional, Dict, Any, List, Tuple

from powertrde.env import ADB_EXE

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------
DEFAULT_ADB = ADB_EXE
REMOTE_BASE_DIR = "/sdcard/automation_markers"  # <-- no sn here
REMOTE_APPS_DIR = "apps"
REMOTE_DEVICE_FILE = "device.json"
METADATA_FILE = "metadata.json"
MARKERS_FILE = "markers.json"


# ------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------
class MarkerError(Exception):
    pass


class AdbError(MarkerError):
    pass


class NotFoundError(MarkerError):
    pass


# ------------------------------------------------------------
# Helper utilities for adb
# ------------------------------------------------------------
def _adb_prefix(adb_path: str, serial: Optional[str]) -> List[str]:
    p = [adb_path]
    if serial:
        p += ["-s", serial]
    return p


def _adb_shell(adb_path: str, serial: Optional[str], cmd: str, timeout: Optional[int] = 15) -> Tuple[int, str]:
    full = _adb_prefix(adb_path, serial) + ["shell", cmd]
    try:
        out = subprocess.check_output(full, stderr=subprocess.STDOUT, timeout=timeout, text=True)
        return 0, out
    except subprocess.CalledProcessError as e:
        return e.returncode, (e.output or "")
    except subprocess.TimeoutExpired:
        raise AdbError(f"adb shell timeout running: {cmd}")


def _adb_push_file(adb_path: str, serial: Optional[str], local_path: str, remote_path: str) -> None:
    full = _adb_prefix(adb_path, serial) + ["push", local_path, remote_path]
    try:
        subprocess.run(full, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except subprocess.CalledProcessError as e:
        raise AdbError(f"adb push failed: {e}")


def _adb_mkdir_p(adb_path: str, serial: Optional[str], remote_path: str) -> None:
    rc, out = _adb_shell(adb_path, serial, f"mkdir -p {shlex.quote(remote_path)}")
    if rc != 0:
        raise AdbError(f"adb mkdir failed: {out}")


def _adb_cat_file(adb_path: str, serial: Optional[str], remote_path: str) -> Optional[str]:
    rc, out = _adb_shell(adb_path, serial, f"cat {shlex.quote(remote_path)}")
    if rc != 0:
        return None
    return out


def _adb_rm(adb_path: str, serial: Optional[str], remote_path: str) -> None:
    _adb_shell(adb_path, serial, f"rm -f {shlex.quote(remote_path)}")


def _remote_path_exists(adb_path: str, serial: Optional[str], remote_path: str) -> bool:
    rc, out = _adb_shell(adb_path, serial, f"ls -d {shlex.quote(remote_path)} 2>/dev/null || true", timeout=5)
    # If path exists, ls -d prints it (or command return 0). But because we appended || true, rc might be 0 even if missing.
    # So detect by checking if output contains path or not empty.
    if out and remote_path.strip() in out:
        return True
    # alternative: check with test -e
    rc2, out2 = _adb_shell(adb_path, serial,
                           f"sh -c '[ -e {shlex.quote(remote_path)} ] && echo EXISTS || echo MISSING'", timeout=5)
    return rc2 == 0 and "EXISTS" in (out2 or "")


# ------------------------------------------------------------
# DeviceMarkerStore (no sn in path)
# ------------------------------------------------------------
class DeviceMarkerStore:
    def __init__(self, serial: Optional[str] = None, adb_path: str = DEFAULT_ADB):
        """
        :param serial: adb device serial (None -> default device)
        :param adb_path: path to adb executable
        """
        self.serial = serial
        self.adb = adb_path
        self.remote_base = REMOTE_BASE_DIR  # unified base (no sn)
        self.remote_apps_dir = f"{self.remote_base}/{REMOTE_APPS_DIR}"

        try:
            # create new apps dir if not exist
            _adb_mkdir_p(self.adb, self.serial, self.remote_apps_dir)
        except Exception:
            # give up; operations will fail later with clearer messages
            pass

    # ------------------------
    # Path helpers
    # ------------------------
    def _app_dir(self, pkg: str) -> str:
        safe = pkg.replace("/", "_")
        return f"{self.remote_apps_dir}/{safe}"

    def _markers_path(self, pkg: str) -> str:
        return f"{self._app_dir(pkg)}/{MARKERS_FILE}"

    def _metadata_path(self, pkg: str) -> str:
        return f"{self._app_dir(pkg)}/{METADATA_FILE}"

    def _device_file_path(self) -> str:
        return f"{self.remote_base}/{REMOTE_DEVICE_FILE}"

    # ------------------------
    # low level json read/write on device
    # ------------------------
    def _read_json_remote(self, remote_path: str) -> Optional[Dict[str, Any]]:
        txt = _adb_cat_file(self.adb, self.serial, remote_path)
        if not txt:
            return None
        try:
            return json.loads(txt)
        except Exception:
            return None

    def _write_json_remote(self, remote_path: str, obj: Dict[str, Any]) -> None:
        fd, lp = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
            parent = os.path.dirname(remote_path)
            _adb_mkdir_p(self.adb, self.serial, parent)
            _adb_push_file(self.adb, self.serial, lp, remote_path)
        finally:
            try:
                os.remove(lp)
            except Exception:
                pass

    # ------------------------
    # package metadata helpers
    # ------------------------
    def _get_package_raw_dumpsys(self, pkg: str) -> Optional[str]:
        rc, out = _adb_shell(self.adb, self.serial, f"dumpsys package {shlex.quote(pkg)}", timeout=10)
        if rc != 0 or not out:
            return None
        return out

    def _extract_pkg_metadata(self, pkg: str) -> Dict[str, str]:
        out = self._get_package_raw_dumpsys(pkg)
        if not out:
            return {}
        meta = {}
        m = re.search(r"firstInstallTime=([^\n\r]*)", out) or re.search(r"firstInstallTimeMillis=([^\n\r]*)", out)
        if m:
            meta["firstInstallTime"] = m.group(1).strip()
        m = re.search(r"lastUpdateTime=([^\n\r]*)", out)
        if m:
            meta["lastUpdateTime"] = m.group(1).strip()
        m = re.search(r"versionName=([^\s\n\r]+)", out)
        if m:
            meta["versionName"] = m.group(1).strip()
        m = re.search(r"versionCode=(\d+)", out) or re.search(r"versionCodes?[:=]\s*([^\s\n\r]+)", out)
        if m:
            meta["versionCode"] = m.group(1).strip()
        m = re.search(r"Package \[([^\]]+)\]", out)
        if m:
            meta["package_line"] = m.group(1).strip()
        return meta

    def _is_package_installed(self, pkg: str) -> bool:
        rc, out = _adb_shell(self.adb, self.serial, f"pm list packages {shlex.quote(pkg)}", timeout=4)
        if rc != 0:
            out2 = self._get_package_raw_dumpsys(pkg)
            return bool(out2)
        return bool(out and pkg in out)

    # ------------------------
    # core behaviors (same as previous API)
    # ------------------------
    def ensure_group_valid(self, pkg: str) -> None:
        md = self._read_json_remote(self._metadata_path(pkg))
        if not md:
            return
        if not self._is_package_installed(pkg):
            self.clear_app_group(pkg)
            return
        current = self._extract_pkg_metadata(pkg)
        if not current:
            return
        key_fields = ["firstInstallTime", "versionCode", "versionName", "lastUpdateTime"]
        for k in key_fields:
            if k in md and k in current:
                if md[k] != current[k]:
                    self.clear_app_group(pkg)
                    return

    def get_app_group(self, pkg: str) -> Dict[str, Any]:
        try:
            self.ensure_group_valid(pkg)
        except AdbError:
            raise
        d = self._read_json_remote(self._markers_path(pkg))
        return d or {}

    def get_app_key(self, pkg: str, key: str, default=None, raise_if_missing: bool = False) -> Any:
        grp = self.get_app_group(pkg)
        if key in grp:
            return grp[key]
        if raise_if_missing:
            raise NotFoundError(f"key {key!r} not found in group {pkg}")
        return default

    def set_app_key(self, pkg: str, key: str, value: Any) -> None:
        grp = self._read_json_remote(self._markers_path(pkg)) or {}
        first_write = not bool(grp)
        grp[key] = value
        self._write_json_remote(self._markers_path(pkg), grp)
        if first_write:
            meta = self._extract_pkg_metadata(pkg)
            if meta:
                self._write_json_remote(self._metadata_path(pkg), meta)

    def set_app_keys(self, pkg: str, mapping: Dict[str, Any]) -> None:
        grp = self._read_json_remote(self._markers_path(pkg)) or {}
        first_write = not bool(grp)
        grp.update(mapping)
        self._write_json_remote(self._markers_path(pkg), grp)
        if first_write:
            meta = self._extract_pkg_metadata(pkg)
            if meta:
                self._write_json_remote(self._metadata_path(pkg), meta)

    def delete_app_key(self, pkg: str, key: str) -> None:
        grp = self._read_json_remote(self._markers_path(pkg)) or {}
        if key in grp:
            grp.pop(key)
            self._write_json_remote(self._markers_path(pkg), grp)

    def clear_app_group(self, pkg: str) -> None:
        _adb_rm(self.adb, self.serial, self._markers_path(pkg))
        _adb_rm(self.adb, self.serial, self._metadata_path(pkg))

    def list_app_groups(self) -> List[str]:
        rc, out = _adb_shell(self.adb, self.serial, f"ls -1 {shlex.quote(self.remote_apps_dir)}", timeout=6)
        if rc != 0 or not out:
            return []
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        return lines

    # device-level
    def get_device_markers(self) -> Dict[str, Any]:
        d = self._read_json_remote(self._device_file_path()) or {}
        return d

    def get_device_key(self, key: str, default=None, raise_if_missing: bool = False) -> Any:
        d = self.get_device_markers()
        if key in d:
            return d[key]
        if raise_if_missing:
            raise NotFoundError(f"device key {key!r} not found")
        return default

    def set_device_key(self, key: str, value: Any) -> None:
        d = self._read_json_remote(self._device_file_path()) or {}
        d[key] = value
        parent = os.path.dirname(self._device_file_path())
        _adb_mkdir_p(self.adb, self.serial, parent)
        self._write_json_remote(self._device_file_path(), d)

    def delete_device_key(self, key: str) -> None:
        d = self._read_json_remote(self._device_file_path()) or {}
        if key in d:
            d.pop(key)
            self._write_json_remote(self._device_file_path(), d)

    def clear_device_markers(self) -> None:
        _adb_rm(self.adb, self.serial, self._device_file_path())

    def export_app_group_to_local(self, pkg: str, local_path: str) -> None:
        txt = _adb_cat_file(self.adb, self.serial, self._markers_path(pkg))
        if not txt:
            raise NotFoundError("no markers for pkg")
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(txt)

    def import_app_group_from_local(self, pkg: str, local_path: str, overwrite: bool = True) -> None:
        with open(local_path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if overwrite:
            self._write_json_remote(self._markers_path(pkg), obj)
        else:
            grp = self._read_json_remote(self._markers_path(pkg)) or {}
            grp.update(obj)
            self._write_json_remote(self._markers_path(pkg), grp)

    def ensure_and_set(self, pkg: str, key: str, value: Any) -> None:
        grp = self._read_json_remote(self._markers_path(pkg))
        if not grp:
            _adb_mkdir_p(self.adb, self.serial, self._app_dir(pkg))
            meta = self._extract_pkg_metadata(pkg)
            if meta:
                self._write_json_remote(self._metadata_path(pkg), meta)
        self.set_app_key(pkg, key, value)

    def set_login_suggest_level(self, pkg: str, level: int):
        return self.set_app_key(pkg, "login_suggest_level", level)

    def get_login_suggest_level(self, pkg: str) -> int:
        return self.get_app_key(pkg, "login_suggest_level", 0)

    def upgrade_login_suggest_level(self, pkg: str, level: int):
        if self.get_login_suggest_level(pkg) < level:
            self.set_login_suggest_level(pkg, level)
            return True
        return False

    def clear_login_suggest_level(self, pkg: str) -> None:
        self.delete_app_key(pkg, "login_suggest_level")

    def set_login_mark(self, pkg: str, mark: str) -> None:
        self.set_app_key(pkg, "login_mark", mark)

    def get_login_mark(self, pkg: str) -> str:
        return self.get_app_key(pkg, "login_mark", "")

    def clear_login_mark(self, pkg: str) -> None:
        self.delete_app_key(pkg, "login_mark")

    def is_suggest_login_and_no_login_mark(self, pkg: str, at_least_level: int = 1):
        """
        是否建议登录并且没有登录标记记录
        """
        return self.get_login_suggest_level(pkg) >= at_least_level and not self.get_login_mark(pkg)


# --------------------------- Main -----------------------------
def _cli_main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--serial", help="ADB device serial (optional)")
    p.add_argument("--adb", default=DEFAULT_ADB, help="adb path")
    p.add_argument("cmd", nargs="*", help="command: getpkg pkgname | setpkg pkg key val | getdev | setdev key val")
    args = p.parse_args()

    store = DeviceMarkerStore(serial=args.serial, adb_path=args.adb)
    if not args.cmd:
        print("DeviceMarkerStore ready.")
    else:
        cmd = args.cmd[0]
        try:
            if cmd == "getpkg":
                pkg = args.cmd[1]
                print(store.get_app_group(pkg))
            elif cmd == "getpkgkey":
                pkg, key = args.cmd[1:3]
                print(store.get_app_key(pkg, key))
            elif cmd == "setpkg":
                pkg, key, val = args.cmd[1:4]
                store.set_app_key(pkg, key, val)
                print("OK")
            elif cmd == "getdev":
                print(store.get_device_markers())
            elif cmd == "setdev":
                k, v = args.cmd[1:3]
                store.set_device_key(k, v)
                print("OK")
            else:
                print("unknown cmd")
        except Exception as e:
            print("ERR:", e)

# --------------------------- Demo -----------------------------


def _demo():
    from powertrde.utils.trde import adb
    _device_id = adb.first_device()
    store = DeviceMarkerStore(serial=_device_id)
    _demo_pkg = 'com.facebook.katana'
    store.set_app_key(_demo_pkg, 'demo_key', 'demo_value')
    print(store.get_app_key(_demo_pkg, 'demo_key'))


# small CLI for quick testing
if __name__ == "__main__":
    _cli_main()
    # _demo()

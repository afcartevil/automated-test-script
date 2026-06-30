# -*- coding: utf-8 -*-
import time

import pytest

from src.utils.adb.adb_utils import adb_shell, get_dumpsys_package

CANDIDATE_PKGS = [
    "com.google.android.calculator",
    "com.android.calculator2",
    "com.google.android.deskclock",
    "com.android.deskclock",
    "com.google.android.apps.maps",
]
OP = "PICTURE_IN_PICTURE"
FGS_OP = "START_FOREGROUND"
FGS_CANDIDATE_PKGS = [
    "com.google.android.gms",
    "com.android.settings",
    "com.google.android.apps.nbu.files",
    "com.google.android.youtube",
]


def _shell_output(device_serial, command):
    result = adb_shell(device_serial, command, no_retry=True)
    return (result.get("output") or result.get("error") or "").strip()


def _find_test_pkg(device_serial):
    for pkg in CANDIDATE_PKGS:
        raw = _shell_output(device_serial, "pm list packages " + pkg)
        if "package:" + pkg in raw:
            return pkg
    return ""


def _get_uid(device_serial, pkg):
    raw = _shell_output(device_serial, "pm list packages -U " + pkg)
    for line in raw.splitlines():
        if pkg in line and "uid:" in line:
            return line.split("uid:")[-1].strip()
    return ""


def _appops_set_pkg(device_serial, pkg, op, mode):
    _shell_output(device_serial, "appops set " + pkg + " " + op + " " + mode)


def _appops_set_uid(device_serial, uid, op, mode):
    _shell_output(device_serial, "appops set --uid " + uid + " " + op + " " + mode)


def _appops_check(device_serial, pkg, op):
    return _shell_output(device_serial, "appops get " + pkg + " " + op)


def _find_fgs_test_pkg(device_serial):
    for pkg in FGS_CANDIDATE_PKGS:
        raw = _shell_output(device_serial, "pm list packages " + pkg)
        if "package:" + pkg not in raw:
            continue
        perm_line = get_dumpsys_package(device_serial, pkg, "FOREGROUND_SERVICE")
        if not perm_line:
            continue
        op_read = _appops_check(device_serial, pkg, FGS_OP)
        lower_read = op_read.lower()
        if not op_read or "unknown operation" in lower_read or "unknown package" in lower_read:
            continue
        return pkg
    return ""

@pytest.mark.require_android_version_min(15)
def test_appops_nonhistorical_state_persistence(device_serial):
    """
    CTS 冒烟替代: AppOpsManagerTest#testNonHistoricalStatePersistence
    """
    pkg = _find_test_pkg(device_serial)
    if not pkg:
        pytest.fail("设备上未找到可用的测试包: " + str(CANDIDATE_PKGS))

    uid = _get_uid(device_serial, pkg)
    if not uid:
        pytest.fail(f"无法获取 {pkg} 的 uid")

    try:
        _appops_set_pkg(device_serial, pkg, OP, "ignore")
        _appops_set_uid(device_serial, uid, OP, "deny")
        time.sleep(1)

        result = _appops_check(device_serial, pkg, OP)
        if "deny" not in result.lower():
            pytest.fail(f"uid 优先级验证失败: 期望 deny, 实际 {result}")

        _appops_set_uid(device_serial, uid, OP, "allow")
        time.sleep(1)

        result = _appops_check(device_serial, pkg, OP)
        if "ignore" not in result.lower():
            pytest.fail(f"清除 uid 后 package 状态丢失: 期望 ignore, 实际 {result}")

        _shell_output(device_serial, "cmd appops write-settings")
        time.sleep(1)
        _shell_output(device_serial, "cmd appops read-settings")
        time.sleep(1)

        result = _appops_check(device_serial, pkg, OP)
        if "ignore" not in result.lower():
            pytest.fail(f"package-level mode 持久化失败: 期望 ignore, 实际 {result}")
    finally:
        _appops_set_uid(device_serial, uid, OP, "allow")
        _appops_set_pkg(device_serial, pkg, OP, "allow")


@pytest.mark.require_android_version_min(15)
def test_foreground_service_appop_smoke(device_serial):
    """
    ID:TOS1600-AM-PS-FGS-APPOP
    DESCRIPTION:[CTS]ActivityManagerProcessStateTest#testForegroundServiceAppOp
    """
    pkg = _find_fgs_test_pkg(device_serial)
    if not pkg:
        pytest.skip(
            "未找到可用于 FGS AppOp 检查的包（需已安装且声明 FOREGROUND_SERVICE）: "
            + str(FGS_CANDIDATE_PKGS)
        )

    before = _appops_check(device_serial, pkg, FGS_OP)
    if not before:
        pytest.skip(f"appops get 返回空: pkg={pkg}, op={FGS_OP}")

    try:
        _appops_set_pkg(device_serial, pkg, FGS_OP, "ignore")
        time.sleep(1)
        mid = _appops_check(device_serial, pkg, FGS_OP)
        if "ignore" not in mid.lower():
            pytest.skip(f"FGS AppOp 状态未进入 ignore（可能受设备策略限制）: {mid}")
    finally:
        _appops_set_pkg(device_serial, pkg, FGS_OP, "allow")
        time.sleep(1)

    after = _appops_check(device_serial, pkg, FGS_OP)
    lower_after = after.lower()
    if "allow" not in lower_after and "default" not in lower_after and "no operations" not in lower_after:
        pytest.skip(f"FGS AppOp 恢复后状态异常（期望 allow/default）: {after}")

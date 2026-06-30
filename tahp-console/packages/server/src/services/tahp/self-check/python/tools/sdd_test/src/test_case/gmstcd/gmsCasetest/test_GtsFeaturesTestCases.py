# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    adb_shell,
    is_package_exist,
)

ASTREA_PACKAGE = "com.google.android.as.oss"


def _get_allowed_associations_per_sysconfig(device_serial, package_name):
    """
    解析 dumpsys activity allowed-associations 输出，
    获取指定包名作为 target 的系统配置 allow-associations 列表。
    逻辑与 Java 版 getAllowedAssociationPerSystemConfig 一致。
    """
    result = adb_shell(device_serial, f"dumpsys activity allowed-associations {package_name}")
    output = result.get("output", "")

    packages = []
    found_target = False

    for line in output.split("\n"):
        trimmed = line.strip()

        # 遇到 Manifest 声明段落则停止（只取 sysconfig 部分）
        if trimmed == "App declared allow associations (Manifest):":
            break

        if f"* {package_name}:" == trimmed:
            found_target = True
        elif not found_target:
            continue
        elif trimmed.startswith("Allow: "):
            packages.append(trimmed[len("Allow: "):])
        elif trimmed.startswith("* "):
            break

    return packages


@pytest.mark.require_android_version_min(17)
def test_cPlusDevice_pcsHasNoAllowAssociations(device_serial):

    '''
    # GMS-9.23-001
    # 验证 Astrea (PCS) 包作为 target 不应存在 sysconfig allow-associations。
    # 对应 Java: GtsFeaturesTestCases#test_cPlusDevice_pcsHasNoAllowAssociations
    # Android API 37+ (Android 16+) 适用。
    '''

    # 检查 Astrea 包是否存在，不存在则跳过
    if not is_package_exist(device_serial, ASTREA_PACKAGE):
        pytest.skip(f"{ASTREA_PACKAGE} not installed, skip")

    allowed_associations = _get_allowed_associations_per_sysconfig(device_serial, ASTREA_PACKAGE)
    logging.info(f"allowed_associations for {ASTREA_PACKAGE}: {allowed_associations}")

    assert len(allowed_associations) == 0, (
        f"There should be no sysconfig allow associations added for Astrea (PCS) "
        f"as target. Found: {allowed_associations}"
    )

# coding=utf-8
import pytest
import logging
import os
from typing import List, Set, Dict, Tuple
from src.utils.test_case_util.config_utils import UninstallChecker


def testuninstall_check(device_serial):
    """
    测试运营商预装应用的卸载检查

    验证系统预装应用与配置文件中的一致性，确保运营商应用可以正确卸载
    """
    logger = logging.getLogger(__name__)

    checker = UninstallChecker(device_serial)

    uninstall_apps = checker.get_operator_apks()

    package_names = []
    for apk_path in uninstall_apps:
        if pkg_name := checker.get_installed_packages(f"/{apk_path}"):
            package_names.append(pkg_name)
    logger.info(f"系统中存在的应用: {package_names}")

    config_file = checker.create_config_file(device_serial)

    if not os.path.exists(config_file):
        pytest.fail(f"配置文件不存在: {config_file}")

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            removable_apps: Set[str] = set(line.strip() for line in f if line.strip())
    except Exception as e:
        pytest.fail(f"读取配置文件失败: {e}")

    excluded_apps: Set[str] = {
        "com.transsion.letswitch",
        "com.mediatek.vnet",
        "com.iflytek.inputmethod",
        "com.hugeland.cdsplus",
    }

    removable_apps -= excluded_apps
    logger.info(f"配置文件中包含的应用: {removable_apps}")

    system_not_in_config = [pkg for pkg in package_names if pkg not in removable_apps]
    config_not_in_system = [pkg for pkg in removable_apps if pkg not in package_names]
    failure_messages = []
    if system_not_in_config:
        failure_messages.append(
            f"系统中存在但配置文件中未包含的应用: {system_not_in_config}"
        )

    if config_not_in_system:
        failure_messages.append(
            f"配置文件中包含但系统中不存在的应用: {config_not_in_system}"
        )
    assert not failure_messages, "\n".join(failure_messages)

import re
import pytest

from src.utils.adb.adb_utils import getprop, get_tOS_version_number, get_product_name_without_market

from src.conftests.report import ReportCollector, pytest_unconfigure
from src.conftests.device import (
    execution_environment,
    get_device_info,
    load_spd_feature_config,
    optional_pms_info,
    phone_info,
    pms_info,
)
from src.conftests.helpers import (
    _record_test_result,
    _record_warning,
    _reset_warnings,
)
from src.conftests.marker_check import CHECKER_LIST, register_device_markers
from src.conftests.test_level import (
    get_is_weekly_build,
    get_test_level_skip_marker,
    register_test_level_markers,
)

try:
    from _pytest.warning_types import PytestWarning
except Exception:  # pragma: no cover - 兜底，极少触发
    PytestWarning = None

# warning_recorded / logstart hook 无法直接拿到 config，这里在 configure 阶段缓存活动 config
_active_config = None

phone_version = getprop("ro.build.display.id")


def pytest_addoption(parser):
    """添加自定义命令行参数"""
    parser.addoption(
        "--report-path",
        type=str,
        default=f"./report/{phone_version}/SDD_report.json",
        help="指定测试报告的输出路径",
    )
    # 确保已添加此参数（之前已配置）
    parser.addoption("--device-serial", type=str, help="指定设备序列号")
    parser.addoption(
        "--skip-spd-info",
        action="store_true",
        default=False,
        help="跳过从SPD接口拉取特性配置（仅收集/筛选非SPD相关用例时可用）",
    )


@pytest.fixture(scope="session")
def device_serial(request):
    return request.config.getoption("--device-serial")


def pytest_collection_modifyitems(config, items):
    """在测试收集阶段根据设备信息跳过不满足条件的测试"""
    device_serial = config.getoption("--device-serial", None)
    check_list = CHECKER_LIST
    device_info = get_device_info(device_serial)
    device_info["spd_feature_config"] = getattr(config, "_spd_feature_config", {})  # 将特性列表添加到设备信息中。保证参数一致,统一处理
    is_weekly_build = get_is_weekly_build(device_serial)

    # 遍历所有收集到的测试项并应用跳过条件
    for item in items:
        level_skip_marker = get_test_level_skip_marker(item, is_weekly_build)
        if level_skip_marker:
            item.add_marker(level_skip_marker)
            continue

        for checker in check_list:
            required_info = item.get_closest_marker(checker.__name__)
            if not required_info:
                continue
            skip_marker = checker(required_info, device_info)
            if skip_marker:
                item.add_marker(skip_marker)
                break


@pytest.fixture(scope="session")
def file_puller(device_serial):
    """
    文件拉取器 fixture，用于从设备导出文件
    """
    import os
    import logging
    from src.utils.adb.adb_utils import execute_command

    logger = logging.getLogger(__name__)

    def _pull_file(file_name="", cmd="") -> bool:
        """
        从手机导出指定文件到本地

        Args:
            file_name: 文件名
            cmd: 自定义查找命令

        Returns:
            bool: 导出成功返回True，失败返回False
        """
        try:
            find_cmd = (
                cmd
                if cmd != ""
                else f"adb -s {device_serial} shell find tr_region -name {file_name}"
            )
            find_result = execute_command(find_cmd)
            logger.info(f"查找文件结果: {find_result}")

            if not find_result["success"]:
                logger.warning(f"未找到文件: {file_name}")
                return False

            device_file_path = find_result["output"].strip()
            if not device_file_path:
                logger.error("设备文件路径为空")
                return False

            copy_cmd = f"adb -s {device_serial} shell cp {device_file_path} /sdcard/"
            copy_result = execute_command(copy_cmd)

            if not copy_result.get("success", False):
                logger.error(f"复制文件到sdcard失败: {copy_result}")
                return False
            
            # 使用 os.path.join 确保路径正确
            file_path = os.path.join(device_serial, file_name)
            # 确保目标目录存在
            os.makedirs(device_serial, exist_ok=True)
            
            pull_cmd = f"adb -s {device_serial} pull sdcard/{file_name} {device_serial}"
            pull_result = execute_command(pull_cmd)
            logger.info(f"拉取文件结果: {pull_result}")

            if os.path.exists(file_path):
                logger.info(f"文件导出成功: {file_path}")
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"导出文件时发生异常: {e}")
            pytest.fail(f"导出文件时发生异常: {e}")
            return False

    return _pull_file


def pytest_configure(config):
    """配置测试环境"""
    global _active_config
    _active_config = config
    config._report = ReportCollector(config.getoption("--report-path"))

    device_serial = config.getoption("--device-serial", None)
    skip_spd_info = config.getoption("--skip-spd-info")
    if skip_spd_info:
        config._spd_feature_config = {}
    else:
        product_name = get_product_name_without_market(device_serial)
        tos_version = get_tOS_version_number(device_serial)
        config._spd_feature_config = load_spd_feature_config(product_name, tos_version)

    register_device_markers(config)
    register_test_level_markers(config)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """收集测试结果（含 setup 阶段 skip，与 pytest 统计口径对齐）"""
    outcome = yield
    report = outcome.get_result()

    if report.when == "setup" and report.outcome == "skipped":
        _record_test_result(item, report, item.config._report)
    elif report.when == "call":
        _record_test_result(item, report, item.config._report)


def pytest_runtest_logstart(nodeid, location):
    """每条用例（含重跑）开始执行时，清空其上一次执行暂存的 warning。"""
    if _active_config is not None and hasattr(_active_config, "_report"):
        _reset_warnings(nodeid, _active_config._report)


def pytest_warning_recorded(warning_message, when, nodeid, location):
    """收集用例执行阶段通过 warnings.warn() 产生的告警，写入报告 warning 字段。"""
    if when != "runtest" or not nodeid:
        return
    if _active_config is None or not hasattr(_active_config, "_report"):
        return

    category = getattr(warning_message, "category", None)
    # 过滤 pytest 自身告警（如未知 marker、缓存等），仅保留业务用例发出的 warning
    if PytestWarning is not None and category is not None:
        try:
            if issubclass(category, PytestWarning):
                return
        except TypeError:
            pass

    message = str(getattr(warning_message, "message", "")).strip()
    if not message:
        return
    _record_warning(nodeid, message, _active_config._report)

# coding: utf-8

from math import log
import os
import re
import logging
import pytest
from typing import Dict, List, Set, Any, Optional, Callable
from src.utils.test_case_util.CommonUtil import CommonUtil
from src.utils.adb.adb_utils import execute_command


def test_oobe_reinstall(
    device_serial: str, phone_info: Dict[str, Any], file_puller: Callable
) -> None:
    """
    测试OOBE应用的重新安装情况

    Args:
        device_serial: 设备序列号
        phone_info: 手机信息字典
        file_puller: 文件拉取 fixture
    """
    #判断安卓版本是否为16
    if phone_info["android_version"] != "16":
        pytest.skip("Only test on android 16")

    # 创建目录并获取配置文件
    apk_path = CommonUtil.create_dir(device_serial)
    apk_name = "OOBEConfigOverlay.apk"
    sys_xml_path = " /system_ext/etc/vconfig/e_oobe_reinstall/e_oobe_reinstall_list.xml"
    pro_xml_path = " /tr_product/etc/vconfig/e_oobe_reinstall/e_oobe_reinstall_list.xml"
    
    
    # 获取APK文件
    if not file_puller(file_name=apk_name):
        pytest.fail(f"Failed to get config file from phone: {apk_name}")

    # 反编译APK并获取配置
    apk_file = os.path.join(apk_path, apk_name)
    logging.info(f"apk_file: {apk_file}")

    if not os.path.exists(apk_file):
        pytest.fail(f"Failed to get {apk_name} from phone: {apk_name}")

    if not CommonUtil.decompile_apk(apk_file):
        pytest.fail(f"Failed to decompile {apk_name}")

    # 解析XML配置
    oobe_xml = os.path.join(
        apk_file.rsplit(".apk", 1)[0], "res", "values", "arrays.xml"
    )
    if not os.path.exists(oobe_xml):
        pytest.fail(f"Failed to get oobe.xml from {apk_name}")

    oobe_dict = CommonUtil.xml_to_dict(oobe_xml)
    if not isinstance(oobe_dict, dict):
        pytest.fail(f"Failed to convert oobe.xml to dict")

#解析OOBE-arrays.xml中的数据
    arrays_dict = {
        array["@name"]: array["item"]
        for array in oobe_dict["resources"]["string-array"]
    }
    

    sys_xml_outPath = f"{device_serial}/sys_oobe_reinstall_list.xml"
    pro_xml_outPath = f"{device_serial}/pro_oobe_reinstall_list.xml"
    # 获取sys和pro XML文件
    logging.info("获取sys和product XML文件")
    sys_xml_cmd  = f"adb -s {device_serial} pull {sys_xml_path} {sys_xml_outPath}"
    pro_xml_cmd  = f"adb -s {device_serial} pull {pro_xml_path} {pro_xml_outPath}"
    
    sys_exists = execute_command(sys_xml_cmd).get("success", False)
    pro_exists = execute_command(pro_xml_cmd).get("success", False)

    logging.info(f"{sys_xml_outPath} 存在: {sys_exists}")
    logging.info(f"{pro_xml_outPath} 存在: {pro_exists}")

    # 场景1：两个XML都不存在，跳过测试
    if not sys_exists and not pro_exists:
        logging.info("两个XML文件都不存在，跳过测试")
        pytest.skip("No OOBE reinstall config files found")

    # 获取oobe_reinstall_list.xml配置
    logging.info("获取oobe_reinstall_list.xml配置")
    oobe_config = _get_oobe_config(sys_xml_outPath, pro_xml_outPath, sys_exists, pro_exists)
    
    if oobe_config is None:
        logging.info("测试跳过（无配置需要检验）")
        pytest.skip("No valid OOBE config")

    # 打印oobe_reinstall_list.xml配置解析结果
    logging.info("oobe_reinstall_list.xml配置（包名 -> 国家代码集合）:")
    logging.info("-" * 60)
    for package, countries in sorted(oobe_config.items()):
        logging.info(f"{package}: {countries}")

    logging.info("\n" + "-" * 60)
    logging.info(f"oobe_reinstall_list.xml配置总共有 {len(oobe_config)} 个应用包名")

    # 解析OOBE_APK中的uninstall配置
 
    uninstall_config = _parse_apk_uninstall_config(arrays_dict)

    # 打印uninstall配置解析结果
    logging.info("OOBE_APK中的uninstall配置（国家代码 -> 包名集合）:")
    logging.info("-" * 60)
    #for country, packages in sorted(uninstall_config.items()):
    #   logging.info(f"{country}: {packages}")

    logging.info("\n" + "-" * 60)
    logging.info(f"OOBE_APK中的uninstall配置总共有 {len(uninstall_config)} 个国家")

    # 检查冲突
    conflicts = _check_conflicts(oobe_config, uninstall_config)

    # 输出冲突结果
    logging.info("\n冲突检查结果:")
    logging.info("-" * 60)
    if conflicts:
        logging.error(f"发现 {len(conflicts)} 个冲突:")
        for package, country in conflicts:
            logging.error(f"  - 包名: {package}, 国家: {country}")
        pytest.fail(f"发现 {len(conflicts)} 个冲突: {conflicts}")
    else:
        logging.info("未发现冲突")
        logging.info("OOBE重装列表测试通过")


def _parse_reinstall_xml(xml_path: str) -> Dict[str, Set[str]]:
    """
    解析reinstall XML文件，提取国家与包名映射关系

    Args:
        xml_path: XML文件路径

    Returns:
        Dict[str, Set[str]]: 包名到国家集合的映射，格式为 {包名: {国家代码集合}}
    """
    result = {}

    if not os.path.exists(xml_path):
        logging.warning(f"XML文件不存在: {xml_path}")
        return result

    try:
        with open(xml_path, "r", encoding="utf-8") as f:
            content = f.read()

        pattern = r"<reinstalldata>([^(]+)\(([^)]+)\)</reinstalldata>"
        matches = re.findall(pattern, content)

        for package_name, countries_str in matches:
            package_name = package_name.strip()
            countries = {c.strip() for c in countries_str.split(",") if c.strip()}

            if package_name not in result:
                result[package_name] = set()
            result[package_name].update(countries)

            logging.info(f"解析到: {package_name}: {countries}")

        logging.info(f"成功解析XML文件: {xml_path}，oobe配置解析结果: {result}")

    except Exception as e:
        logging.error(f"解析XML文件失败 {xml_path}: {e}")
    return result


def _merge_configs(sys_config: Dict[str, Set[str]], pro_config: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """
    合并sys和pro配置，相同包名采用pro的国家配置，不同包名合并

    Args:
        sys_config: sys XML解析结果
        pro_config: pro XML解析结果

    Returns:
        Dict[str, Set[str]]: 合并后的配置
    """
    merged = {}

    for package, countries in sys_config.items():
        merged[package] = set(countries)

    for package, countries in pro_config.items():
        merged[package] = set(countries)

    logging.info(f"合并配置完成，共 {len(merged)} 个包名")
    return merged


def _get_oobe_config(sys_xml_path: str, pro_xml_path: str, sys_exists: bool, pro_exists: bool) -> Optional[Dict[str, Set[str]]]:
    """
    根据文件存在情况获取合并后的OOBE配置

    Returns:
        Dict[str, Set[str]]: 包名到国家集合的映射，格式为 {包名: {国家代码集合}}
        None: 当两个XML文件都不存在时返回None
    """
    if sys_exists and not pro_exists:
        logging.info("仅sys_e_oobe_reinstall_list.xml存在，解析该文件")
        return _parse_reinstall_xml(sys_xml_path)

    if not sys_exists and pro_exists:
        logging.info("仅pro_e_oobe_reinstall_list.xml存在，解析该文件")
        return _parse_reinstall_xml(pro_xml_path)

    if sys_exists and pro_exists:
        logging.info("两个XML文件都存在，合并配置（相同包名采用pro的配置）")
        sys_config = _parse_reinstall_xml(sys_xml_path)
        pro_config = _parse_reinstall_xml(pro_xml_path)
        return _merge_configs(sys_config, pro_config)

    return None


def _parse_apk_uninstall_config(arrays_dict: Dict[str, Any]) -> Dict[str, Set[str]]:
    """
    解析APK中的uninstall配置，获取国家与包名映射关系

    Args:
        arrays_dict: 从XML解析的string-array字典

    Returns:
        Dict[str, Set[str]]: 国家代码到包名集合的映射，格式为 {国家代码: {包名集合}}
    """
    logging.info("开始解析APK中的uninstall配置")

    result = {}
    for array_name, items in arrays_dict.items():
        if array_name.endswith("_uninstall_apps"):
            country_code = array_name[:-len("_uninstall_apps")]
            # 确保items是列表
            if not isinstance(items, list):
                items = [items]
            result[country_code] = set(items)
            logging.debug(f"解析到uninstall配置: {country_code} -> {items}")

    logging.info(f"成功解析APK，共 {len(result)} 个国家的uninstall配置")
    return result


def _check_conflicts(oobe_config: Dict[str, Set[str]], uninstall_config: Dict[str, Set[str]]) -> list:
    """
    检查oobe配置与uninstall配置之间的冲突

    规则：
    1. oobe配置中的包名，不能出现在uninstall配置的同一国家中
    2. 当国家代码为ALL时，该包名在所有uninstall配置中都不能存在

    Args:
        oobe_config: OOBE配置，格式为 {包名: {国家代码集合}}
        uninstall_config: uninstall配置，格式为 {国家代码: {包名集合}}

    Returns:
        list: 冲突列表，每个元素格式为 (包名, 国家代码)
    """
    conflicts = []

    for package, oobe_countries in oobe_config.items():
        if "ALL" in oobe_countries:
            logging.debug(f"包名 {package} 包含ALL关键字，检查所有国家的uninstall配置")
            for country, uninstall_packages in uninstall_config.items():
                if package in uninstall_packages:
                    conflicts.append((package, country))
                    logging.debug(f"发现冲突: {package} 在国家 {country} 的uninstall配置中存在（ALL规则）")
        else:
            for country in oobe_countries:
                if country in uninstall_config:
                    uninstall_packages = uninstall_config[country]
                    if package in uninstall_packages:
                        conflicts.append((package, country))
                        logging.debug(f"发现冲突: {package} 在国家 {country} 的oobe和uninstall配置中都存在")

    return conflicts
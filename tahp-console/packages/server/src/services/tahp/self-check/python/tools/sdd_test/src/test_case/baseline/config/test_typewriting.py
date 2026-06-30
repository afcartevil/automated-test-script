# coding: utf-8


import os
import logging
import pytest
from typing import Dict, List, Set, Any, Optional, Callable
from src.utils.adb.adb_utils import execute_command, getprop
from data.res_list import (
    TYPEWRITING_APK_LIST,
    TYPEWRITING_PROJECT_WHITE_LIST,
    OperatorMarket,
)
from src.utils.test_case_util.CommonUtil import CommonUtil


# 用于记录满足条件的market的全局列表
satisfied_markets = []

def test_typewriting(
    device_serial: str, phone_info: Dict[str, Any], file_puller: Callable
) -> None:
    """
    测试输入法应用的安装情况

    Args:
        device_serial: 设备序列号
        phone_info: 手机信息字典
        file_puller: 文件拉取 fixture
    """
    # 获取已安装的输入法应用
    installed_typewriting_apk: Set[str] = {
        typewriting
        for typewriting in TYPEWRITING_APK_LIST
        if execute_command(f"adb -s {device_serial} shell pm path {typewriting}")[
            "output"
        ]
        != ""
    }

    logging.info(f"已安装的输入法应用: {installed_typewriting_apk}")

    # 创建目录并获取配置文件
    apk_path = CommonUtil.create_dir(device_serial)
    apk_name = "OOBEConfigOverlay.apk"

    if not file_puller(file_name=apk_name):
        # TODO B 没有overlay文件
        pytest.fail(f"Failed to get config file from phone: {apk_name}")

    # 检查白名单项目
    if phone_info["product_name"] in TYPEWRITING_PROJECT_WHITE_LIST:
        pytest.skip("white list project, skip")

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

    # 获取市场信息
    market_name = getprop("ro.tran.sw.market", device_serial)
    arrays_dict = {
        array["@name"]: array["item"]
        for array in oobe_dict["resources"]["string-array"]
    }
    market_array_upper = market_name.upper()

    # 处理不同市场的检查逻辑
    gttg_country_list = [
        "AR",
        "BO",
        "UY",
        "EC",
        "CL",
        "CO",
        "PA",
        "SV",
        "CR",
        "PE",
        "BR",
        "NI",
        "PR",
        "MX",
        "DO",
        "PY",
        "GT",
        "HN",
    ]

    # 特殊市场处理
    if market_name in ["in", "ru", "tr"]:
        uninstall_apps = arrays_dict.get(f"{market_array_upper}_uninstall_apps")
        check_typewriting_apps(market_name, uninstall_apps, installed_typewriting_apk)
    elif market_array_upper == OperatorMarket.ZAVC.value:
        uninstall_apps = arrays_dict.get("ZA_uninstall_apps")
        check_typewriting_apps(market_name, uninstall_apps, installed_typewriting_apk)
    elif market_array_upper == OperatorMarket.OPPJ.value:
        country_list = arrays_dict.get(f"country_array_op", [])
        # 确保country_list是列表
        if not isinstance(country_list, list):
            country_list = [country_list]
        for country in country_list:
            uninstall_apps = arrays_dict.get(f"{country}_uninstall_apps")
            check_typewriting_apps(country, uninstall_apps, installed_typewriting_apk)
    elif market_array_upper == OperatorMarket.GTTG.value:
        for country in gttg_country_list:
            uninstall_apps = arrays_dict.get(f"{country}_uninstall_apps")
            check_typewriting_apps(country, uninstall_apps, installed_typewriting_apk)
    else:
        # 默认处理逻辑
        country_list_key = f"country_array_{market_name}"
        if country_list_key in arrays_dict:
            country_list = arrays_dict[country_list_key]
            # 确保country_list是列表
            if not isinstance(country_list, list):
                country_list = [country_list]
            for country in country_list:
                uninstall_apps = arrays_dict.get(f"{country}_uninstall_apps")
                check_typewriting_apps(
                    country, uninstall_apps, installed_typewriting_apk
                )
    # 检查是否有满足条件的market，如果有则判定用例失败
    global satisfied_markets
    if satisfied_markets:
        logging.info(f"以下market未预装输入法: {satisfied_markets}")
        pytest.fail(f"以下market未预装输入法: {satisfied_markets}")


def check_typewriting_apps(
    market: str,
    uninstall_apps: Optional[List[str]],
    installed_typewriting_apk: Set[str],
) -> None:
    """
    检查输入法应用是否正确安装

    Args:
        market: 市场名称
        uninstall_apps: 应卸载的应用列表
        installed_typewriting_apk: 已安装的输入法应用集合
    """
    if uninstall_apps is not None:
        # 确保uninstall_apps是列表
        if not isinstance(uninstall_apps, list):
            uninstall_apps = [uninstall_apps]

        # 检查是否有输入法应用未被卸载
        if not any(
            typewriting not in uninstall_apps
            for typewriting in installed_typewriting_apk
        ):
            # 将满足条件的market添加到全局列表中
            global satisfied_markets
            satisfied_markets.append(market)
            # 注释掉原来的pytest.fail调用
            # pytest.fail(f"{market} no typewriting app!")

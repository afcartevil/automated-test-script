# coding: utf-8
import logging

import pytest
from typing import Dict, Optional

from src.utils.adb.adb_utils import getprop, execute_command
from data.res_list import COMMON_LANGUAGE_LIST
from data.res_list import AndroidVersion, Brand, Model

pytestmark = pytest.mark.skip(reason="禁用该用例")

DISPLAY_ID_FANS = "FANS"


def test_language_list_config(device_serial: str, phone_info: Dict[str, str]) -> None:
    """
    测试设备支持的语言列表配置是否符合要求

    Args:
        device_serial: 设备序列号
        phone_info: 设备信息字典
    """
    # 获取Android版本并检查是否满足测试要求
    android_version = getprop("ro.product.build.version.release", device_serial)
    if int(android_version) < AndroidVersion.V:
        pytest.skip(f"Android版本 {android_version} 低于 {AndroidVersion.V}, 跳过测试")

    # 获取设备关键信息
    res = execute_command(
        f"adb -s {device_serial} shell cmd overlay lookup android android:array/supported_locales"
    )
    logging.info(device_serial)
    brand = phone_info.get("ro_product_brand", "")
    market_name = phone_info.get("ro_transsion_device_name", "")
    display_id = phone_info.get("ro_build_display_id", "")

    # 语言列表比较逻辑映射
    comparison_strategies = [
        (
            lambda: brand == Brand.ITEL,
            lambda: compare_itel_language_list(res["output"]),
        ),
        (
            lambda: brand == Brand.TECNO.value and Model.CAMON.value in market_name,
            lambda: compare_tecno_camon_language_list(res["output"]),
        ),
        (
            lambda: DISPLAY_ID_FANS in display_id,
            lambda: pytest.skip("fans版本, 跳过测试"),
        ),
    ]

    # 执行匹配的比较策略
    found_match = False
    for condition, strategy in comparison_strategies:
        if condition():
            found_match = True
            res = strategy()
            if not res:
                pytest.fail("Language list comparison failed")
            break

    # 如果没有匹配的条件，则执行默认比较策略
    if not found_match:
        res = compare_language_list(COMMON_LANGUAGE_LIST, res["output"])
        if not res:
            pytest.fail("Language list comparison failed")


def compare_language_list(common_language_list, res):
    for lang in common_language_list:
        if lang not in res:
            logging.error(f"This product's Language {lang} not found in the list")
            return False
    return True


def compare_itel_language_list(res):
    if "so-SO" in res:
        logging.error("This is itel product, but Language so-SO found in the list")
        return False
    return True


def compare_tecno_camon_language_list(res):
    if "ckb-IQ" in res:
        logging.error("This is Camon product, but Language ckb-IQ found in the list")
        return False
    return True

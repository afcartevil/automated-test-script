# -*- coding: utf-8 -*-
import warnings
import pytest
import logging
from datetime import date

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    getprop,
    get_product_name_without_market,
)
from src.conftests.device import get_device_market


@pytest.mark.require_android_version_min(16)
def test_google_gmsversion_check(device_serial):

    # product_name_without_market = get_product_name_without_market(device_serial)
    # logging.info("product_name_without_market=" + product_name_without_market)

    product_name_with_market = getprop('ro.product.name', sn=device_serial)
    logging.info("product_name_with_market=" + product_name_with_market )


    mGmsversion_value = getprop('ro.com.google.gmsversion', sn=device_serial)
    mGmsversion_value = mGmsversion_value.split(".")[0]
    logging.info("mGmsversion_value:ro.com.google.gmsversion=" + mGmsversion_value)

    '''
    GMS包版本过期日期 固定格式 yyyymmdd
    '''
    dict_A16_gms_version_dateline_sheet = {"16_202508": "20251116",
                                        "16_202509": "20251207",
                                        "16_202510": "20260209",
                                        "16_202512": "20260331",
                                        "16_202603": "0"}    # "0"表示当前GMS版本为最新版本

    get_product_gms_version_end_date = dict_A16_gms_version_dateline_sheet.get(mGmsversion_value)

    if get_product_gms_version_end_date is None:
        reason = mGmsversion_value + " is not in dict_A16_gms_version_dateline_sheet"
        pytest.skip(reason)
    else:
        logging.info("get_product_gms_version_end_date=" + get_product_gms_version_end_date)

    '''
    GMS Approve项目product_name白名单
    '''

    mApprove_16_202510_projects = ["X6879-OP","X6879-OPPJ","X6879-IN","X6879-RU","X6879-TR","X6879-EU",
                                    "CN5-OP","CN5-TR","CN5-RU",
                                    "CN5c-OP","CN5c-OPPJ",
                                    "CN7c-OP","CN7c-OPPJ","CN7c-IN","CN7c-RU","CN7c-TR",
                                    "X6887-OP","X6887-OPPJ","X6887-IN","X6887-RU","X6887-EU",
                                    "LK7k-OP","LK7k-IN",
                                    "X6877-OP",
                                    "X6878-OP","X6878-OPPJ","X6878-IN","X6878-RU","X6878-EU",
                                    "X6891-OP","X6891-OPPJ","X6891-IN","X6891-RU","X6891-EU",
                                    "X6840B-OP","X6840B-RU",
                                    "X6840-OP","X6840-OPPJ","X6840-IN",
                                    "KN4-OP","KN4-OPPJ","KN4-GTTG",
                                    "KN4n-OP","KN4n-RU","KN4n-TR",
                                    ]

    mApprove_16_202512_projects = ["LK6-OP","LK6-OPPJ","LK6-IN","LK6-RU","LK6-TR","LK6-COCL",
                                    "X6895-OP","X6895-OPPJ","X6895-RU","X6895-TR",
                                    "X6895B-OP","X6895B-OPPJ","X6895B-RU","X6895B-TR","X6895B-EU",
                                    "KN8-OP","KN8-OPPJ","KN8-IN","KN8-TR","KN8-COCL",
                                    "CM5-OP","CM5-OPPJ","CM5-RU","CM5-TR",
                                    "CM7-OP","CM7-RU","CM7-TR","CM7-COCL",
                                    "X6856-OP","X6856-RU","X6856-TR",
                                    "X6840-TR",
                                    "CN6c-OP",
                                    ]

    mApprove_16_202603_projects = ["LK7-OP","LK7-OPPJ","LK7-IN","LK7-RU","LK7-TR",
                                    "X6896-OP","X6896-OPPJ","X6896-IN","X6896-RU","X6896-TR",
                                    "X6890-OP","X6890-OPPJ","X6890-IN","X6890-RU",
                                    "CN6c-TR","CN6c-OPPJ",
                                    "CN6-OP","CN6-OPPJ","CN6-COCL","CN6-RU","CN6-TR",
                                    "KO5-OP","KO5-OPPJ","KO5-RU","KO5-TR",
                                    ]

    dict_A16_approve_products_value = {
        "16_202510": mApprove_16_202510_projects,
        "16_202512": mApprove_16_202512_projects,
        "16_202603": mApprove_16_202603_projects
    }

    if product_name_with_market in dict_A16_approve_products_value.get(mGmsversion_value,[]):
        logging.info(product_name_with_market + " market has got gms approve for gms version " + mGmsversion_value)
        return
    # else:
    #     if product_name_without_market in dict_A16_approve_products_value.get(mGmsversion_value,[]):
    #         logging.info(product_name_without_market + " product has got gms approve for gms version " + mGmsversion_value)
    #         return

    # 获取当前日期
    today = date.today()
    # 更改当前日期格式
    today_date = today.strftime("%Y%m%d")
    # print(today_date)

    '''
    "0"表示当前GMS版本为最新版本
    '''
    if get_product_gms_version_end_date == "0":
        return


    end_date = int(get_product_gms_version_end_date)  # or int(get_product_gms_version_end_date())
    today = int(today_date)

    if today > end_date:
        logging.info(mGmsversion_value + " GMS package has expired.")
        reason = "The GMS package has expired."
        pytest.fail(reason)
        # pytest.warns(reason)

    elif today >= end_date - 10:    # 提前10天，比较日期大小
        logging.info(mGmsversion_value + " GMS package will expire soon.")
        reason = "The GMS package will expire within 10 days."
        pytest.skip(reason)

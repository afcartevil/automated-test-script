import pytest
import logging


def test_devinfo_r(phone_info, optional_pms_info):
    # 检查两个字典中的属性是否相等
    # 在所有的键检查完之后再断言
    # 写一个需要check的列表
    check_list = [
        "ro_product_brand",
        "product_name",
        "ro_product_device",
        "ro_product_model",
        "ro_product_manufacturer",
    ]
    msg = ""
    # 遍历列表
    for key in check_list:
        if not optional_pms_info[key] == phone_info[key]:
            msg += f"{key} is different: {phone_info[key]} != {optional_pms_info[key]}\n"
    # 单独检查属性 ro_product_model,"ro_transsion_device_name","tran_device_name"
    if "Fans" in phone_info["ro_build_display_id"]:
        pass
    elif not optional_pms_info["ro_product_model"].strip() == phone_info["ro_product_model"]:
        msg += f"ro_product_model is different: {phone_info['ro_product_model']}!={optional_pms_info['ro_product_model']}\n"

    if (
        "Amst".lower() in phone_info["ro_build_display_id"].lower()
        or "FANS".lower() in phone_info["ro_build_display_id"].lower()
    ):
        pass
    else:
        if (
            not optional_pms_info["ro_transsion_device_name"].strip()
            == phone_info["ro_transsion_device_name"]
        ):
            msg += f"ro_transsion_device_name is different: {phone_info['ro_transsion_device_name']}!={optional_pms_info['ro_transsion_device_name']}\n"
    # 断言
    assert msg == "", "project devinfo config error: \n" + msg

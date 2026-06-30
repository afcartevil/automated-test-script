# -*- coding: utf-8 -*-
import pytest
import logging
from src.utils.adb.adb_utils import (
    adb_cat,
    is_file_exist,
    is_package_exist,
    find_file_in_trregion_etc_asset,
    getprop,
    is_apk_exist,
    get_apkpath_by_package,
)
from data.channel_list import CHANNEL_TYPE, CHANNEL_DICT


def test_channel(device_serial):
    failed = "\n"
    af_text = None
    af_file = None

    def after_AF():
        nonlocal failed
        nonlocal af_text
        nonlocal af_file
        # 检查AF渠道号文件是否存在

        af_file_tr = "/tr_region/etc/asset/transsion_prebuilt/pre_install.appsflyer"
        af_file_1 = "/product/etc/asset/transsion_prebuilt/pre_install.appsflyer"
        if is_file_exist(device_serial, af_file_tr):
            af_file = af_file_tr
        elif is_file_exist(device_serial, af_file_1):
            af_file = af_file_1
        else:
            logging.warning(f"af 缺少渠道号文件 pre_install.appsflyer")
        if af_file:
            af_text = adb_cat(device_serial, af_file)
            logging.info(f"af文件内容：{af_text}")

    def deal_CP(apk_package, channel_file):
        nonlocal failed

        if is_package_exist(device_serial, apk_package):
            logging.info(f"CP渠道号：{channel_file}")
            # 特殊处理：当多个三方应用同包名时处理
            if isinstance(channel_file, list) and len(channel_file) == 2:
                channel_txt, apk_name = channel_file
                # if not is_apk_exist(device_serial,apk_name):
                if apk_name not in get_apkpath_by_package(device_serial, apk_package):
                    logging.warning(f"CP 包名：{channel_file} 不对应应用名 {apk_name} ")
                    return
                channel_file = channel_txt
            # 特殊处理end
            if not find_file_in_trregion_etc_asset(device_serial, channel_file):
                failed += f"应用 {apk_package} 缺少渠道号文件 {channel_file} \n"
                logging.error(f"应用 {apk_package} 缺少渠道号文件 {channel_file}")

    def deal_AF(apk_package, channel_text):
        nonlocal failed
        nonlocal af_text

        if is_package_exist(device_serial, apk_package):
            logging.info(f"AF渠道号：{channel_text},{len(channel_text)}")
            # 特殊处理：当多个三方应用同包名时处理
            if isinstance(channel_text, list) and len(channel_text) == 2:
                channel_txt, apk_name = channel_text
                # if not is_apk_exist(device_serial,apk_name):
                if apk_name not in get_apkpath_by_package(device_serial, apk_package):
                    logging.warning(f"CP 包名：{channel_text} 不对应应用名 {apk_name} ")
                    return
                channel_text = channel_txt
            # 特殊处理end
            if not af_file:
                failed += f"应用 {apk_package} 缺少渠道号文件 pre_install.appsflyer \n"
                return
            if af_text:
                # logging.info(f"channel_text:{channel_text}, {af_text}在af   {channel_text in af_text}")
                if channel_text not in af_text:
                    failed += (
                        f"应用 {apk_package} 的渠道号 {channel_text} 不在af文件中 \n"
                    )
            else:
                failed += f"应用 {apk_package} 但无渠道号 AF文件 \n"

    def deal_PC(apk_package, channel_chombe: list):
        nonlocal failed

        if is_package_exist(device_serial, apk_package):
            logging.info(f"PC渠道号：{channel_chombe}")

            file_path = getprop(channel_chombe[0], device_serial)
            logging.info(f"prop file_path:{file_path}")
            if file_path:
                if is_file_exist(device_serial, file_path):
                    channel_text = adb_cat(device_serial, file_path)
                    if channel_chombe[1] not in channel_text:
                        failed += f"应用 {apk_package} 的渠道号 异常 \n"
                else:
                    failed += f"应用 {apk_package} 的渠道号 文件 {file_path} 不存在 \n"
            else:
                failed += (
                    f"应用 {apk_package} 的渠道号 prop {channel_chombe[0]} 不存在 \n"
                )

    def deal_PROP(apk_package, prop_KV: list):
        nonlocal failed
        # 特殊处理：多渠道号配置，特殊情况 start
        if len(prop_KV) == 1:
            prop_KV = prop_KV[0]
        # 特殊处理：多渠道号配置，特殊情况 end

        if is_package_exist(device_serial, apk_package):
            logging.info(f"PROP渠道号：{prop_KV}")
            value = getprop(prop_KV[0], device_serial).strip()
            if prop_KV[1].strip() != value:
                failed += f"应用 {apk_package} 的渠道号 异常 \n"
            else:
                logging.info(f"应用 {apk_package} 的渠道号 正常 \n")

    def deal_CAT(apk_package, channel_name):
        nonlocal failed
        pass

    fun_dict = {
        CHANNEL_TYPE.CP: deal_CP,
        CHANNEL_TYPE.AF: deal_AF,
        CHANNEL_TYPE.PC: deal_PC,
        CHANNEL_TYPE.PROP: deal_PROP,
        CHANNEL_TYPE.CAT: deal_CAT,
    }

    after_AF()

    for apk_package, channel_info in CHANNEL_DICT.items():
        # logging.info(f"apk_package:{apk_package},type:{channel_info[0]},是否安装{is_package_exist(device_serial,apk_package)},是否在字典中:{channel_info[0] in fun_dict.keys()}")
        if isinstance(channel_info[0], list):
            for item in channel_info:
                channel_type, *channel_name = item
                fun_dict[channel_type](apk_package, channel_name)
        else:
            channel_type, channel_name = channel_info
            fun_dict[channel_type](apk_package, channel_name)

    if failed.strip() != "":
        pytest.fail(failed)

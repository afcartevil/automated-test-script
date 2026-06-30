# coding: utf-8

import pytest
import datetime
import sys
import os
import logging as log
import warnings

from dateutil.parser import parse
from src.utils.adb.adb_utils import execute_command, getprop
from src.utils.warning.CommonWarning import PartitionWarning


@pytest.mark.order(1)
def test_partition(optional_pms_info, device_serial):
    if sys.platform != "linux" or getprop("ro.boot.hardware", device_serial) == "qcom":
        pytest.skip("Only support linux platform! or  it is qcom device")
    user_type = getprop("ro.build.type", sn=device_serial)
    root_type = getprop("persist.user.root.support", sn=device_serial)
    if user_type != "user":
        pytest.skip(f"It is {user_type} phone, pls use user version!")
    elif root_type:
        pytest.skip(f"It is {root_type} phone, pls use root version!")
    version = getprop("ro.build.display.id", sn=device_serial)
    product_name = getprop("ro.product.name", sn=device_serial)
    if "CL6" in version and "V" in product_name:
        pytest.skip()
    if "CL8" in version:
        pytest.skip()

    virtual_ab = getprop("ro.boot.slot_suffix", sn=device_serial)
    if virtual_ab:
        log.info("virtual_ab: enabled")
        superGroupListStr = execute_command(
            "adb -s "
            + device_serial
            + " shell lpdump | grep \"sectors\" | sed 's/ //g' | awk -F \".\" '{print $NF}' | awk -F \":\" '{print $1}'"
        )
        superGroupList = superGroupListStr.split()
        super_data = execute_command(
            "adb -s "
            + device_serial
            + " shell lpdump -j | grep -A 1 \"super\" | grep -w \"size\" | awk -F ':' '{print $2}' | tr -d ',' | sed 's/\"//g'"
        )
        super_available = int(super_data) - int(superGroupList[-1]) * 512
        data = int(
            execute_command(
                "adb -s " + device_serial + " shell df |grep /data | awk '{print $4}'"
            )
        )

        log.info("Super: %s (Byte)", super_data)
        log.info("super_available: %d (Byte)", super_available)
        log.info("data_available: %s (KB)", data)
    else:
        log.info("virtual_ab: disabled")
        system = execute_command(
            "adb -s "
            + device_serial
            + " shell lpdump -j | grep -w -A 3 \"system\" | grep \"size\" | awk -F ':' '{print $2}' | tr -d ',' | sed 's/\"//g'"
        )
        system_ext = execute_command(
            "adb -s "
            + device_serial
            + " shell lpdump -j | grep -A 3 \"system_ext\" | grep \"size\" | awk -F ':' '{print $2}' | tr -d ',' | sed 's/\"//g'"
        )
        vendor = execute_command(
            "adb -s "
            + device_serial
            + " shell lpdump -j | grep -A 3 \"vendor\" | grep \"size\" | awk -F ':' '{print $2}' | tr -d ',' | sed 's/\"//g'"
        )
        product = execute_command(
            "adb -s "
            + device_serial
            + " shell lpdump -j | grep -A 3 \"product\" | grep \"size\" | awk -F ':' '{print $2}' | tr -d ',' | sed 's/\"//g'"
        )
        super_data = execute_command(
            "adb -s "
            + device_serial
            + " shell lpdump -j | grep -A 1 \"super\" | grep \"size\" | awk -F ':' '{print $2}' | tr -d ',' | sed 's/\"//g'"
        )
        data = execute_command(
            "adb -s " + device_serial + " shell df |grep /data | awk '{print $4}'"
        )
        super_available = int(super_data) - (
            int(system) + int(vendor) + int(product) + int(system_ext) - 2097152
        )

        log.info(f"System: {system} (Byte)")
        log.info(f"Vendor: {vendor} (Byte)")
        log.info(f"Product: {product} (Byte)")
        log.info(f"system_ext: {system_ext} (Byte)")
        log.info(f"Super: {super_data} (Byte)")
        log.info(f"super_available: {super_available} (Byte)")
        log.info(f"data_available: {data} (KB)")

        super_available = super_available // 1000 // 1000
        log.info(f"\033[36m Super available = {super_available}(M) \033[0m")
        cal_super_available(super_available, optional_pms_info, device_serial)
        data_available = data * 1024 // 1000 // 1000
        cal_data_available(optional_pms_info, device_serial, data, data_available)
        log.info(f"\033[36m data available = {data}(M) \033[0m")


def get_node_date(pms_info, node):
    try:
        if node not in pms_info["milestones"]["base"].keys():
            log.error(node + " date is not set at pms")
            return parse("2000-01-01")
    except Exception as e:
        log.error("get node date fail, node=" + node)
        log.debug(pms_info)
        return parse("2000-01-01")

    node_dict = pms_info["milestones"]["base"][node]
    node_date = (
        node_dict["real_time"] if node_dict["real_time"] else node_dict["plan_time"]
    )

    if node_date:
        node_date = parse(node_date)
        log.info(f"{node} date is {node_date}")
        return node_date
    return parse("2000-01-01")


def isgoprj(device_serial, rom_size):
    tag1 = getprop("ro.vendor.gmo.rom_optimize", sn=device_serial)
    return (rom_size <= 16) and (tag1 == "1")


def cal_data_available(pms_info, device_serial, rom_size, data_available):
    # 为字典
    data_whitelist = {}
    zram = getprop("ro.zram_writeback.support", sn=device_serial)
    go_prj = isgoprj(device_serial, rom_size)
    systembit = int(pms_info["system_bits"][:2])
    memfusion2_1 = getprop("ro.vendor.memfusion2_1.support", sn=device_serial)
    data_standard = 0

    if go_prj:
        if rom_size <= 4:
            data_standard = 1500
        elif rom_size <= 8:
            data_standard = 5000
        elif rom_size <= 16:
            data_standard = 12000
    else:
        if systembit > 32 and 32 < rom_size <= 64:
            data_standard = 49500 if memfusion2_1 == "true" else 50500

    if zram == "1" and not go_prj:
        data_standard -= 256
    log.info(f"rom_size={rom_size} data_standard={data_standard}")

    if data_available < data_standard:
        reason = f"Data Available test fail! Must be > {data_standard}M, but got {data_available}M"
        prj_name = pms_info["product_version_sample"].split("-")[0]
        if prj_name in data_whitelist and data_available < data_whitelist[prj_name]:
            pytest.fail(reason)
        elif prj_name in data_whitelist:
            reason = f"{prj_name} in the whitelist, but the data is not standard"
            warnings.warn(reason, PartitionWarning)
        else:
            pytest.fail(reason)


def cal_super_available(super_available, pms_info, device_serial):
    # 为字典
    super_whitelist = {}
    cur_date = parse(datetime.datetime.now().strftime("%Y-%m-%d"))
    sdk = getprop("ro.product.first_api_level", sn=device_serial)
    global reason
    super_check_result = ""
    if cur_date < get_node_date(pms_info, "Beta"):
        log.info("check super in Alpha now")
        if super_available < 700:
            super_check_result = "fail"
            reason = (
                "super_available check fail, super_available="
                + str(round(super_available))
                + "M~"
                + " it must large than 700M!"
            )
    elif cur_date < get_node_date(pms_info, "RC"):
        log.info("check super in Beta now")
        if super_available < 550:
            super_check_result = "fail"
            reason = (
                "super_available check fail, super_available="
                + str(round(super_available))
                + "M~"
                + " it must large than 550M!"
            )
    elif cur_date < get_node_date(pms_info, "RC"):
        log.info("check super in Beta now")
        if super_available < 550:
            super_check_result = "fail"
            reason = (
                "super_available check fail, super_available="
                + str(round(super_available))
                + "M~"
                + " it must large than 550M!"
            )
    elif cur_date < get_node_date(pms_info, "FR"):
        log.info("check super in RC now")
        if super_available < 550:
            super_check_result = "fail"
            reason = (
                "super_available check fail, super_available="
                + str(round(super_available))
                + "M~"
                + " it must large than 550M!"
            )
    elif cur_date < get_node_date(pms_info, "MQR"):
        log.info("check super in FR now")
        if super_available < 500:
            super_check_result = "fail"
            reason = (
                "super_available check fail, super_available="
                + str(round(super_available))
                + "M~"
                + " it must large than 500M!"
            )
    else:
        log.info("check super in MR now")
        if super_available < 250:
            if int(sdk) < 30:
                if super_available < 150:
                    super_check_result = "fail"
                    reason = (
                        "super_available check fail, super_available="
                        + str(round(super_available))
                        + "M~"
                        + " it must large than 150M!"
                    )
            else:
                super_check_result = "fail"
                reason = (
                    "super_available check fail, super_available="
                    + str(round(super_available))
                    + "M~"
                    + " it must large than 250M!"
                )
        elif super_available < 300:
            reason = (
                "super_available check warning, super_available="
                + str(round(super_available))
                + "M~"
                + " APK can't update yet!"
            )
            warnings.warn(reason, PartitionWarning)
            assert True
        elif super_available < 400:
            reason = (
                "super_available check warning, super_available="
                + str(round(super_available))
                + "M~"
                + " APK can't add yet!"
            )
            warnings.warn(reason, PartitionWarning)
            assert True
    if super_check_result == "fail":
        log.info(reason)
        prj_name = pms_info["product_version_sample"].split("-")[0]
        if prj_name in super_whitelist.keys():
            if super_available < super_whitelist[prj_name]:
                reason = (
                    "super_available check fail, super_available="
                    + str(round(super_available))
                    + "M~"
                    + " it must large than "
                    + str(super_whitelist[prj_name])
                    + " M!"
                )
                pytest.fail(reason)
        else:
            pytest.fail(reason)

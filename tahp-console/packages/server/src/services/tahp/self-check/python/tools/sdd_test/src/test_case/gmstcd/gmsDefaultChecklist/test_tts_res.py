# -*- coding: utf-8 -*-
"""检查 TTS 资源版本与 SpeechServicesByGoogle.apk 的版本是否对应一致。"""

import json
import logging
import os
import zipfile

import pytest

from src.utils.adb.adb_utils import (
    getprop,
    is_file_exist,
    pull_file,
    ls_dir,
)

# 使用 tr_carrier 路径的 market 列表（小写）
_CARRIER_MARKETS = ("cocl", "tocc", "gttg")

_APK_NAME = "SpeechServicesByGoogle.apk"
_APK_REGION_PATH = f"tr_region/app/SpeechServicesByGoogle/{_APK_NAME}"
_APK_CARRIER_PATH = f"tr_carrier/app/SpeechServicesByGoogle/{_APK_NAME}"
_TTS_LOAD_PATH = "/product/tts/google/"


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------


def _ls_device(device_serial: str, path: str) -> list[str]:
    """返回设备上指定路径的文件/目录列表，失败时返回空列表。"""
    result = ls_dir(device_serial, path)
    return result if result else []


def _checkout_version_local(device_serial: str, loadpath: str) -> list[dict]:
    """解析设备上 TTS 资源目录，返回各语言包的名称和版本信息。

    Returns:
        [{'name': 'zh-CN', 'version': 'r123'}, ...]
    """
    checkbox = []
    listdirs = _ls_device(device_serial, loadpath)
    for listdir in listdirs:
        landirs = _ls_device(device_serial, os.path.join(loadpath, listdir).replace("\\", "/"))
        if not landirs:
            continue
        version1 = landirs[0].split(".")[0].split("-")[-1]
        version2 = landirs[-1].split(".")[0].split("-")[-1]
        nameparse = landirs[0].split(".")[0].split("-")[:2]
        name = "-".join(nameparse)
        if version1 == version2:
            checkbox.append({"name": name, "version": version1})
    return checkbox


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


@pytest.mark.require_android_version_min(15)
def test_check_tts_version(device_serial):
    """检查 TTS 资源版本与 SpeechServicesByGoogle.apk 的版本是否对应一致。

    仅针对 Android 15 及以后的项目。
    """
    android_version = int(getprop("ro.build.version.release", sn=device_serial) or 0)

    # 检查设备是否预置了 TTS 资源
    if android_version >= 16:
        tr_path = _ls_device(device_serial, "tr_product/etc/asset")
        if "tts" not in tr_path:
            pytest.skip("设备未预置 TTS 资源（tr_product/etc/asset），跳过检查")
    else:
        pr_path = _ls_device(device_serial, "product/tts/google")
        if not pr_path:
            pytest.skip("设备未预置 TTS 资源（product/tts/google），跳过检查")

    # 根据 market 确定 APK 路径
    special_market = (getprop("ro.tran.sw.market", sn=device_serial) or "").strip().lower()
    logging.info(f"special_market={special_market}")
    appdir = _APK_CARRIER_PATH if special_market in _CARRIER_MARKETS else _APK_REGION_PATH
    logging.info(f"SpeechServicesByGoogle APK path on device: {appdir}")

    if not is_file_exist(device_serial, appdir):
        pytest.skip(f"未找到 {_APK_NAME}（{appdir}），跳过 TTS 版本检查")

    apk_local = _APK_NAME  # 下载到项目根目录

    try:
        ok = pull_file(device_serial, appdir, apk_local)
        if not ok:
            pytest.skip(f"pull {appdir} 失败，跳过 TTS 版本检查")

        # 解析 APK 内的 manifest
        with zipfile.ZipFile(apk_local, "r") as z:
            with z.open("assets/superpacks_manifest.json", "r") as f:
                manifest = json.loads(f.read())

        # 读取设备上的本地资源版本
        checkboxes = _checkout_version_local(device_serial, _TTS_LOAD_PATH)
        logging.info(f"找到 {len(checkboxes)} 个本地 TTS 语言包")

        failures = []
        for checkbox in checkboxes:
            for pack in manifest.get("packs", []):
                locale = "-".join(pack["name"].split("-")[:2])
                if locale == checkbox["name"]:
                    apk_version = f"r{pack['revision']}"
                    if apk_version != checkbox["version"]:
                        msg = (
                            f"{checkbox['name']}: APK 版本={apk_version}，"
                            f"资源版本={checkbox['version']}"
                        )
                        logging.error(f"TTS 版本不匹配: {msg}")
                        failures.append(msg)
                    break

        if failures:
            pytest.fail("TTS 资源版本与 APK 不一致:\n" + "\n".join(failures))

        logging.info("check tts version pass")

    finally:
        if os.path.exists(apk_local):
            os.remove(apk_local)

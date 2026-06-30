import logging
from os import path
import platform
import pytest
from src.utils.adb.adb_utils import (
    get_device_android_version,
    get_device_fps,
    get_device_ram_size,
    get_first_sn,
    get_kernel_version,
    get_soc_paltform,
    get_tOS_version,
    getprop,
    is_cuttlefish_device,
    is_gmse_plus_device,
    is_GO_device,
    is_slim_device,
)
from src.utils.fileloader.json_loader import load_json
from src.utils.http.spd_info import SpdInfo

SPD_FEATURE_CONFIG = {}

"""
获取手机信息，sn
"""


@pytest.fixture(scope="session")
def phone_info(device_serial):
    # 获取adb devices 返回的第一行sn号 当无设备时返回None
    logging.info(device_serial)
    phone_info = {"device_serial": device_serial}
    if phone_info["device_serial"] is None:
        pytest.fail("No devices connected")
    phone_info["ro_product_brand"] = getprop("ro.product.brand", device_serial)
    phone_info["product_name"] = getprop("ro.product.name", device_serial)
    phone_info["ro_product_device"] = getprop("ro.product.device", device_serial)
    phone_info["ro_product_model"] = getprop("ro.product.model", device_serial)
    phone_info["ro_product_board"] = getprop("ro.product.board", device_serial)
    phone_info["ro_product_manufacturer"] = getprop(
        "ro.product.manufacturer", device_serial
    )
    phone_info["ro_transsion_device_name"] = getprop(
        "ro.product.tran.device.name", device_serial
    )
    phone_info["ro_build_display_id"] = getprop("ro.build.display.id", device_serial)
    phone_info["fingerprint"] = getprop("ro.build.fingerprint", device_serial)
    phone_info["android_version"] = getprop("ro.build.version.release", device_serial)
    # 兼容多市场名
    if not phone_info["ro_transsion_device_name"]:
        phone_info["ro_transsion_device_name"] = getprop(
            "persist.sys.tran.device.name", device_serial
        )
    phone_info["version_phone"] = getprop("ro.build.display.id", device_serial)
    logging.info(f"phone_info: {phone_info}")
    return phone_info


def get_pms_info(device_serial):
    version_phone = getprop("ro.build.display.id", device_serial)
    pmsinfo_file = path.join("./", f"{version_phone}_pms.json")
    return load_json(pmsinfo_file), pmsinfo_file


@pytest.fixture(scope="session")
def pms_info(device_serial):
    pmsf, pmsinfo_file = get_pms_info(device_serial)
    if not pmsf:
        pytest.fail(f"pms_info file not found: {pmsinfo_file}")
    logging.info(f"pms_info file: {pmsinfo_file}")
    return pmsf


@pytest.fixture(scope="session")
def optional_pms_info(device_serial):
    pmsf, pmsinfo_file = get_pms_info(device_serial)
    if not pmsf:
        pytest.skip(f"pms_info file not found: {pmsinfo_file}")
    logging.info(f"pms_info file: {pmsinfo_file}")
    return pmsf


@pytest.fixture(scope="session")
def execution_environment():
    """判断执行环境是Linux还是Windows"""
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "linux":
        return "linux"
    else:
        return system  # 返回其他系统类型


def load_spd_feature_config(product_name=None, tos_version=None):
    """通过SPD API获取特性配置，结果缓存到模块全局变量供pytest全局使用。"""
    global SPD_FEATURE_CONFIG
    if not product_name or not tos_version:
        logging.warning("product_name 或 tos_version 为空，跳过SPD特性配置加载")
        return SPD_FEATURE_CONFIG
    try:
        spd_info = SpdInfo()
        SPD_FEATURE_CONFIG = spd_info.one_step_feature_list(product_name, tos_version)
        logging.info(f"SPD feature config loaded from API: {len(SPD_FEATURE_CONFIG)} items")
    except Exception as e:
        logging.error(f"通过API获取SPD特性配置失败: {e}")
        SPD_FEATURE_CONFIG = {}
    return SPD_FEATURE_CONFIG


def get_device_build_brand(device_serial):
    platform = getprop("ro.board.platform", device_serial)
    if platform and "mt" in platform.lower():
        return "MTK"
    elif platform and (
        "qcom" in platform.lower()
        or "msm" in platform.lower()
        or "apq" in platform.lower()
    ):
        return "QCOM"
    elif platform and "ums" in platform.lower():
        return "UMS"
    elif platform and "spr" in platform.lower():
        return "SPRD"

    hardware = getprop("ro.hardware", device_serial)
    if hardware and "mt" in hardware.lower():
        return "MTK"
    elif hardware and (
        "qcom" in hardware.lower()
        or "msm" in hardware.lower()
        or "apq" in hardware.lower()
    ):
        return "QCOM"
    elif hardware and "ums" in hardware.lower():
        return "UMS"
    elif hardware and "spr" in hardware.lower():
        return "SPRD"

    return platform or "UNKNOWN"


def get_device_market(device_serial):
    """获取当前设备市场，用于匹配SPD表中的OP/RU/TR/OPPJ等市场列。"""
    market = getprop("ro.tran.sw.market", device_serial) or getprop(
        "ro.tr_build.sw_market", device_serial
    )
    if market:
        return market.strip().upper()

    product_name = getprop("ro.product.name", device_serial) or ""
    if "-" in product_name:
        return product_name.split("-")[-1].strip().upper()
    return product_name.strip().upper() or "UNKNOWN"


def get_soc_model_code(device_serial):
    """获取芯片平台代号"""
    cpu_to_soc_mapping = {
        "mt6580": "MT80",
        "mt6765vx": "G36",
        "mt6769": "G70",
        "mt6769v": "G81",
        "mt6769cb": "G81",
        "mt6769h": "G88",
        "mtk6789": "G99",
        "mt6789": "G99",
        "mt6768": "G81",
        "mt6835": "D6100",
        "mt6855": "D6300",
        "mt6878": "D7300",
        "mt6878v": "D7400",
        "mt6878taz": "D7400",
        "mt6895": "D8200Ultimate",
        "mt6896": "D8200",
        "mt6897": "D8300",
        "mt6983": "D9000",
        "mt6989": "D9300",
        "sc7731e": "7731e",
        "sc9832e": "9832e",
        "sc9863a": "9863a",
        "ums9230": "T606",
        "ums9230h": "T612",
        "ums9230e": "T615",
        "ums9230t": "T616",
        "ums9230s": "T620",
    }

    platform = getprop("ro.board.platform", device_serial) or ""
    logging.info(f"debug Platform: {platform}")
    platform_lower = platform.lower()

    known_codes = [
        "MT80",
        "7731e",
        "9832e",
        "9863a",
        "G36",
        "T606",
        "T612",
        "G70",
        "G81",
        "T615",
        "T616",
        "G88",
        "T620",
        "G99",
        "G100",
        "L8",
        "D6100",
        "D6300",
        "D7300",
        "D7400",
        "D8200",
        "D8200Ultimate",
        "D8300",
        "D9000",
        "D9300",
    ]

    for code in known_codes:
        if code.lower() in platform_lower:
            return code

    for cpu_model, soc_code in cpu_to_soc_mapping.items():
        if cpu_model in platform_lower:
            return soc_code

    hardware = getprop("ro.hardware", device_serial) or ""
    hardware_lower = hardware.lower()

    for code in known_codes:
        if code.lower() in hardware_lower:
            return code

    for cpu_model, soc_code in cpu_to_soc_mapping.items():
        if cpu_model in hardware_lower:
            return soc_code

    return platform or hardware or "UNKNOWN"


# 当前专门给 maerker_check.py 使用。用于用例筛选
def get_device_info(device_serial):
    return {
        "device_serial": device_serial,
        "market": get_device_market(device_serial),
        "android_version": get_device_android_version(device_serial),
        "ram_size": get_device_ram_size(device_serial),
        "build_brand": get_device_build_brand(device_serial),
        "fps": get_device_fps(device_serial),
        "tOS_version": get_tOS_version(device_serial),
        "is_go_device": is_GO_device(device_serial),
        "is_slim_device": is_slim_device(device_serial),
        "soc_paltform": get_soc_paltform(device_serial),
        "kernel_version": get_kernel_version(device_serial),
        "soc_model_code": get_soc_model_code(device_serial),
        "is_cuttlefish": is_cuttlefish_device(device_serial),
        "is_gmse_plus": is_gmse_plus_device(device_serial),
    }

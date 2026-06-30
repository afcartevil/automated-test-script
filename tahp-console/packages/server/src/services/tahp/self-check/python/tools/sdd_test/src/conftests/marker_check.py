import pytest
import re
from src.utils.adb.adb_utils import get_feature, is_package_exist

# 芯片平台代号优先级定义（从低到高）
SOC_MODEL_PRIORITY = {
    "7731e": 1,
    "9832e": 2,
    "9863a": 3,
    "T606": 4,
    "T612": 5,
    "G36": 6,
    "T615": 7,
    "T616": 8,
    "G70": 9,
    "G81": 10,
    "G88": 11,
    "T620": 12,
    "G99": 13,
    "G100": 13,
    "D6100": 14,
    "D6300": 15,
    "D7300": 16,
    "D7400": 17,
    "D8200": 18,
    "D8200Ultimate": 18,
    "D8300": 19,
    "D9000": 20,
    "D9300": 21,
    "MT80": 22,
}


def _skip_if_missing(required_info, device_info, field_name):
    marker_name = getattr(required_info, "name", "unknown_marker")
    value = device_info.get(field_name)
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return pytest.mark.skip(
            reason=f"marker {marker_name} 依赖字段 {field_name} 为空，跳过该用例"
        )
    return None


def require_android_version_min(required_info, device_info):
    required_android_version = (
        required_info.args[0] if len(required_info.args) > 0 else None
    )
    if required_android_version is not None:
        skip_marker = _skip_if_missing(required_info, device_info, "android_version")
        if skip_marker:
            return skip_marker
        if required_android_version > int(device_info["android_version"]):
            return pytest.mark.skip(
                reason=f"需要Android {required_android_version}或更高版本，当前版本: {device_info['android_version']}"
            )


def require_android_version(required_info, device_info):
    required_android_version = (
        required_info.args[0] if len(required_info.args) > 0 else None
    )
    if required_android_version is not None:
        skip_marker = _skip_if_missing(required_info, device_info, "android_version")
        if skip_marker:
            return skip_marker
        if int(required_android_version) != int(device_info["android_version"]):
            return pytest.mark.skip(
                reason=f"需要Android {required_android_version}版本，当前版本: {device_info['android_version']}"
            )


def require_ram_min(required_info, device_info):
    required_ram = required_info.args[0] if len(required_info.args) > 0 else None
    if required_ram is not None:
        skip_marker = _skip_if_missing(required_info, device_info, "ram_size")
        if skip_marker:
            return skip_marker
        if required_ram > device_info["ram_size"]:
            return pytest.mark.skip(
                reason=f"需要RAM {required_ram}或更高版本，当前版本: {device_info['ram_size']}"
            )


def require_build_brand(required_info, device_info):
    required_build_brand = (
        required_info.args[0] if len(required_info.args) > 0 else None
    )
    if required_build_brand is not None:
        skip_marker = _skip_if_missing(required_info, device_info, "build_brand")
        if skip_marker:
            return skip_marker
        if required_build_brand != device_info["build_brand"]:
            return pytest.mark.skip(
                reason=f"需要品牌 {required_build_brand}，当前品牌: {device_info['build_brand']}"
            )


def require_fps(required_info, device_info):
    required_fps = required_info.args[0] if len(required_info.args) > 0 else None
    if required_fps is not None:
        skip_marker = _skip_if_missing(required_info, device_info, "fps")
        if skip_marker:
            return skip_marker
        if required_fps > device_info["fps"]:
            return pytest.mark.skip(
                reason=f"需要fps {required_fps}或更高版本，当前fps: {device_info['fps']}"
            )


def require_tOS_version_min(required_info, device_info):
    required_tOS_version = (
        required_info.args[0] if len(required_info.args) > 0 else None
    )
    if required_tOS_version is not None:
        skip_marker = _skip_if_missing(required_info, device_info, "tOS_version")
        if skip_marker:
            return skip_marker
        cur_version_match = re.match(
            r"[a-zA-Z]*(\d+(?:\.\d+)*)", device_info["tOS_version"]
        )
        tar_version_match = re.match(r"[a-zA-Z]*(\d+(?:\.\d+)*)", required_tOS_version)
        if cur_version_match and tar_version_match:
            cur_version = cur_version_match.group(1)
            tar_version = tar_version_match.group(1)

            cur_version_parts = [int(x) for x in cur_version.split(".")]
            tar_version_parts = [int(x) for x in tar_version.split(".")]

            max_length = max(len(cur_version_parts), len(tar_version_parts))
            cur_version_parts.extend([0] * (max_length - len(cur_version_parts)))
            tar_version_parts.extend([0] * (max_length - len(tar_version_parts)))

            i = 0
            while i < max_length:
                if cur_version_parts[i] > tar_version_parts[i]:
                    break
                elif cur_version_parts[i] < tar_version_parts[i]:
                    return pytest.mark.skip(
                        reason=f"需要tOS版本 {required_tOS_version} 或更高版本，当前版本: {device_info['tOS_version']}"
                    )
                elif cur_version_parts[i] == tar_version_parts[i]:
                    i += 1


def require_go_device(required_info, device_info):
    skip_marker = _skip_if_missing(required_info, device_info, "is_go_device")
    if skip_marker:
        return skip_marker
    if not device_info["is_go_device"]:
        return pytest.mark.skip(reason="需要GO设备")


def require_non_go_device(required_info, device_info):
    skip_marker = _skip_if_missing(required_info, device_info, "is_go_device")
    if skip_marker:
        return skip_marker
    if device_info["is_go_device"]:
        return pytest.mark.skip(reason="需要非GO设备")


def require_slim_device(required_info, device_info):
    skip_marker = _skip_if_missing(required_info, device_info, "is_slim_device")
    if skip_marker:
        return skip_marker
    if not device_info["is_slim_device"]:
        return pytest.mark.skip(reason="需要SLIM设备")


def require_non_slim_device(required_info, device_info):
    skip_marker = _skip_if_missing(required_info, device_info, "is_slim_device")
    if skip_marker:
        return skip_marker
    if device_info["is_slim_device"]:
        return pytest.mark.skip(reason="需要非SLIM设备")


def require_non_cuttlefish(required_info, device_info):
    """标记的用例仅在非 CuttleFish 虚拟机上执行；两属性同时命中时跳过。"""
    skip_marker = _skip_if_missing(required_info, device_info, "is_cuttlefish")
    if skip_marker:
        return skip_marker
    if device_info["is_cuttlefish"]:
        return pytest.mark.skip(reason="CuttleFish 虚拟机上不执行该用例")


def require_gmse_plus(required_info, device_info):
    """标记的用例仅在 GMSE+（GMS Express Plus）项目上执行，否则跳过。"""
    skip_marker = _skip_if_missing(required_info, device_info, "is_gmse_plus")
    if skip_marker:
        return skip_marker
    if not device_info["is_gmse_plus"]:
        return pytest.mark.skip(reason="非 GMSE+ 项目，跳过该用例")


def require_soc_paltform(required_info, device_info):
    required_soc_paltform: list = (
        required_info.args[0] if len(required_info.args) > 0 else None
    )
    if required_soc_paltform is not None:
        skip_marker = _skip_if_missing(required_info, device_info, "soc_paltform")
        if skip_marker:
            return skip_marker
        if device_info["soc_paltform"] not in required_soc_paltform:
            return pytest.mark.skip(
                reason=f"需要SOC平台 {required_soc_paltform}，当前SOC平台: {device_info['soc_paltform']}"
            )


def require_kernel_version_min(required_info, device_info):
    required_kernel_version = (
        required_info.args[0] if len(required_info.args) > 0 else None
    )
    if required_kernel_version is not None:
        if not isinstance(required_kernel_version, str):
            return None
        skip_marker = _skip_if_missing(required_info, device_info, "kernel_version")
        if skip_marker:
            return skip_marker

        cur_version_match = re.match(r"(\d+(?:\.\d+)*)", device_info["kernel_version"])
        tar_version_match = re.match(r"(\d+(?:\.\d+)*)", required_kernel_version)

        if cur_version_match and tar_version_match:
            cur_version = cur_version_match.group(1)
            tar_version = tar_version_match.group(1)

            cur_version_parts = [int(x) for x in cur_version.split(".")]
            tar_version_parts = [int(x) for x in tar_version.split(".")]

            max_length = max(len(cur_version_parts), len(tar_version_parts))
            cur_version_parts.extend([0] * (max_length - len(cur_version_parts)))
            tar_version_parts.extend([0] * (max_length - len(tar_version_parts)))

            for i in range(max_length):
                if cur_version_parts[i] > tar_version_parts[i]:
                    break
                elif cur_version_parts[i] < tar_version_parts[i]:
                    return pytest.mark.skip(
                        reason=f"需要内核版本 {required_kernel_version}或更高版本，当前版本: {device_info['kernel_version']}"
                    )


def require_kernel_version_in(required_info, device_info):
    """检查内核版本是否在指定的版本列表中"""
    required_kernel_versions = (
        required_info.args[0] if len(required_info.args) > 0 else None
    )
    if required_kernel_versions is not None:
        if not isinstance(required_kernel_versions, list):
            return None
        skip_marker = _skip_if_missing(required_info, device_info, "kernel_version")
        if skip_marker:
            return skip_marker

        cur_version_match = re.match(r"(\d+(?:\.\d+)*)", device_info["kernel_version"])
        if not cur_version_match:
            return pytest.mark.skip(
                reason=f"无法解析当前内核版本: {device_info['kernel_version']}"
            )

        cur_version = cur_version_match.group(1)

        current_in_list = False
        for required_version in required_kernel_versions:
            tar_version_match = re.match(r"(\d+(?:\.\d+)*)", required_version)
            if tar_version_match:
                tar_version = tar_version_match.group(1)
                if cur_version == tar_version:
                    current_in_list = True
                    break

        if not current_in_list:
            return pytest.mark.skip(
                reason=f"需要内核版本 {required_kernel_versions}，当前版本: {device_info['kernel_version']}"
            )


def require_features(required_info, device_info):
    required_features: list[str] = (
        required_info.args[0] if len(required_info.args) > 0 else None
    )
    if required_features is not None:
        skip_marker = _skip_if_missing(required_info, device_info, "device_serial")
        if skip_marker:
            return skip_marker
        for feature in required_features:
            real_value = get_feature(device_info["device_serial"], feature)
            if (
                real_value is None
                or real_value.split("feature:")[1].strip() != feature.strip()
            ):
                return pytest.mark.skip(
                    reason=f"需要Feature {feature}，手机查询Feature值: {real_value}"
                )


def require_packages(required_info, device_info):
    required_packages: list[str] = (
        required_info.args[0] if len(required_info.args) > 0 else None
    )
    if required_packages is not None:
        skip_marker = _skip_if_missing(required_info, device_info, "device_serial")
        if skip_marker:
            return skip_marker
        for package in required_packages:
            real_value = is_package_exist(device_info["device_serial"], package)
            if not real_value:
                return pytest.mark.skip(
                    reason=f"需要Package {package}，但该包在设备上不存在"
                )


def require_soc_model_min(required_info, device_info):
    """检查芯片平台代号是否满足最低要求"""
    required_soc_model = required_info.args[0] if len(required_info.args) > 0 else None

    if required_soc_model is not None:
        skip_marker = _skip_if_missing(required_info, device_info, "soc_model_code")
        if skip_marker:
            return skip_marker
        current_soc_model = device_info.get("soc_model_code", "UNKNOWN")

        current_priority = SOC_MODEL_PRIORITY.get(current_soc_model, 0)
        required_priority = SOC_MODEL_PRIORITY.get(required_soc_model, 0)

        if current_priority < required_priority:
            return pytest.mark.skip(
                reason=f"需要芯片平台 {required_soc_model} 或更高版本，当前芯片平台: {current_soc_model}"
            )


def require_markets(required_info, device_info):
    """根据设备市场筛选用例，仅在指定市场（如 IN/EU）上执行，否则跳过。

    支持以下写法：
        @pytest.mark.require_markets("IN", "EU")
        @pytest.mark.require_markets(["IN", "EU"])
    """
    if len(required_info.args) == 0:
        return None
    if len(required_info.args) == 1 and isinstance(required_info.args[0], (list, tuple)):
        required_markets = list(required_info.args[0])
    else:
        required_markets = list(required_info.args)
    if not required_markets:
        return None

    required_markets = [str(m).strip().upper() for m in required_markets]

    skip_marker = _skip_if_missing(required_info, device_info, "market")
    if skip_marker:
        return skip_marker

    current_market = device_info["market"].strip().upper()
    if current_market not in required_markets:
        return pytest.mark.skip(
            reason=f"需要市场 {required_markets}，当前市场: {current_market}"
        )


def require_spd_feature_support(required_info, device_info):
    """根据SPD API返回的特性列表中当前市场是否为支持(值为'1')筛选用例。"""
    required_feature_codes = (
        required_info.args[0] if len(required_info.args) > 0 else None
    )
    if required_feature_codes is None:
        return None
    if isinstance(required_feature_codes, str):
        required_feature_codes = [required_feature_codes]

    spd_feature_config = device_info.get("spd_feature_config", {})
    if not spd_feature_config:
        return pytest.mark.skip(reason="SPD特性配置为空，跳过该用例")

    skip_marker = _skip_if_missing(required_info, device_info, "market")
    if skip_marker:
        return skip_marker

    market = device_info["market"].upper()
    for feature_code in required_feature_codes:
        feature_info = spd_feature_config.get(feature_code)
        if not feature_info:
            return pytest.mark.skip(reason=f"SPD特性编码 {feature_code} 不存在")
        support_value = feature_info.get(market)
        if support_value != "1":
            return pytest.mark.skip(
                reason=f"SPD特性 {feature_code} 在市场 {market} 不支持，当前值: {support_value}"
            )


CHECKER_LIST = [
    require_android_version_min,
    require_android_version,
    require_ram_min,
    require_build_brand,
    require_tOS_version_min,
    require_fps,
    require_go_device,
    require_non_go_device,
    require_soc_paltform,
    require_kernel_version_min,
    require_kernel_version_in,
    require_features,
    require_soc_model_min,
    require_markets,
    require_spd_feature_support,
    require_packages,
    require_slim_device,
    require_non_slim_device,
    require_non_cuttlefish,
    require_gmse_plus,
]


DEVICE_MARKERS = [
    "require_android_version_min(version): mark test to run only on android with specified version or higher",
    "require_android_version(version): mark test to run only on android with specified version",
    "require_ram_min(size): mark test to run only on device with specified ram size or higher",
    "require_build_brand(brand): mark test to run only on device with specified soc brand",
    "require_fps(fps): mark test to run only on device with specified fps or higher",
    "require_tOS_version_min(version): mark test to run only on device with specified tOS version or higher",
    "require_go_device: mark test to run only on go device",
    "require_non_go_device: mark test to run only on non go device",
    "require_slim_device: mark test to run only on slim device",
    "require_non_slim_device: mark test to run only on non slim device",
    "require_soc_paltform(soc_paltform): mark test to run only on device with specified soc paltform",
    "require_kernel_version_min(version): mark test to run only on device with specified kernel version or higher",
    "require_kernel_version_in(versions): mark test to run only on device with specified kernel versions",
    "require_features(features): mark test to run only on device with specified features",
    "require_soc_model_min(soc_model): mark test to run only on device with specified soc model or higher",
    "require_markets(markets): mark test to run only on device with specified market(s), e.g. IN/EU",
    "require_spd_feature_support(feature_codes): mark test to run only when SPD feature supports current market",
    "require_packages(packages): mark test to run only on device with specified packages",
    "require_non_cuttlefish: mark test to skip on MTK CuttleFish virtual device (vendor model + cs_arm64_only)",
    "require_gmse_plus: mark test to run only on GMSE+ (GMS Express Plus) project",
]


def register_device_markers(config):
    """注册设备能力相关markers"""
    for marker in DEVICE_MARKERS:
        config.addinivalue_line("markers", marker)

import pkgutil
import importlib
import importlib.metadata
import subprocess
from typing import Optional

from powertrde.env import ADB_EXE
from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase
from tpy_aw.aw_configs.supported_os_config import SupportedOS
from tpy_aw.aw_defines import PhoneOsInfo
from tpytest.aw_framework.aw_base import _global_registry, register_aw
from tpy_aw.aw_feature_base import AwFeatureBase

_loaded_modules = set()

_cached_aw_app_ins = {}
_cached_aw_feature_ins = {}
_cached_aw_helper_ins = {}


def _load_plugins(load_module):
    """
    扫描项目下 tpy_aw.aw_apps 包中所有以 aw_ 开头的子包，
    导入它们自身和子模块，以触发 AWMeta 注册。
    """
    if load_module in _loaded_modules:
        return
    for finder, app_name, ispkg in pkgutil.iter_modules(load_module.__path__):
        if not ispkg or not app_name.startswith("aw_"):
            continue
        full_pkg = f"{load_module.__name__}.{app_name}"
        # 导入包本身（会执行包 __init__.py）
        importlib.import_module(full_pkg)
        # 扫描并导入包下的所有模块
        pkg = importlib.import_module(full_pkg)
        for _, mod_name, is_subpkg in pkgutil.iter_modules(pkg.__path__):
            # 如果还有子包也直接导入（递归可根据需要扩展）
            importlib.import_module(f"{full_pkg}.{mod_name}")
    _loaded_modules.add(load_module)


# 获取功能层 AW
def get_aw_feature(u2d_helper, name: str, variant: Optional[str] = None) -> AwFeatureBase:
    import tpy_aw.aw_features as aw_features_pkg
    _load_plugins(aw_features_pkg)
    var = (variant or u2d_helper.get_aw_logic_variant_key(name)).lower()
    impls = _global_registry.get('feature', {}).get(name.lower(), {})
    cls = impls.get(var) or impls.get('')
    if not cls:
        raise RuntimeError(f"Feature AW not found: {name}@{var}")
    tuple_key = (cls, u2d_helper)
    ins = _cached_aw_feature_ins.get(tuple_key)
    if ins is None:
        ins = cls()
        ins.u2d_helper = u2d_helper
        _cached_aw_feature_ins[tuple_key] = ins
    return ins


# 获取应用层 AW
def get_aw_app(u2d_helper, name: str, variant: Optional[str] = None) -> AwAppBase:
    import tpy_aw.aw_apps as aw_apps_pkg
    _load_plugins(aw_apps_pkg)
    var = (variant or u2d_helper.get_aw_app_variant_key(name)).lower()
    impls = _global_registry.get('app', {}).get(name.lower(), {})
    cls = impls.get(var) or impls.get('')
    if not cls:
        raise RuntimeError(f"App AW not found: {name}@{var}")
    tuple_key = (cls, u2d_helper)
    ins = _cached_aw_app_ins.get(tuple_key)
    if ins is None:
        ins = cls()
        ins.u2d_helper = u2d_helper
        _cached_aw_app_ins[tuple_key] = ins
    return ins


# 获取封装层 AW
def get_aw_helper(u2d_or_device_id, name: str, variant: Optional[str] = None):
    cls = get_aw_helper_type(name, variant)
    tuple_key = (cls, u2d_or_device_id)
    ins = _cached_aw_helper_ins.get(tuple_key)
    if ins is None:
        ins = cls(u2d_or_device_id)
        _cached_aw_helper_ins[tuple_key] = ins
    return ins


# 获取封装层 AW 类型
def get_aw_helper_type(name: str, variant: Optional[str] = None):
    import tpy_aw.aw_helpers as aw_helpers_pkg
    _load_plugins(aw_helpers_pkg)
    from tpy_aw.u2d_test_helper import U2DTestHelper
    register_aw(U2DTestHelper)
    var = variant.lower() if variant is not None else ''
    name = name.lower() if name is not None else ''
    impls = _global_registry.get('u2_helper', {}).get(name, {})
    cls = impls.get(var) or impls.get('')
    if not cls:
        raise RuntimeError(f"Helper AW not found: {name}@{var}")
    return cls


def get_aw_helper_by_os_info(u2d_or_device_id, os_info: PhoneOsInfo):
    return get_aw_helper(u2d_or_device_id, os_info.vendor_name, os_info.os_name)


def get_aw_helper_type_by_os_info(os_info: PhoneOsInfo):
    return get_aw_helper_type(os_info.vendor_name, os_info.os_name)


def get_aw_helper_by_detect_os_info(device_id):
    if not isinstance(device_id, str):
        device_id = device_id.serial
    return get_aw_helper_by_os_info(device_id, detect_os_info(device_id))


def get_aw_helper_type_by_detect_os_info(device_id):
    if not isinstance(device_id, str):
        device_id = device_id.serial
    return get_aw_helper_type_by_os_info(detect_os_info(device_id))


def get_aw_app_by_app_info(u2d_helper, app_info) -> AwAppBase:
    key = app_info.get_closest_variant_key(u2d_helper.device_real_sn)
    return get_aw_app(u2d_helper, app_info.ori_id, key)


def detect_os_info(device_id: str) -> PhoneOsInfo:
    # 使用 adb shell 获取 prop 列表
    result = subprocess.run(
        [ADB_EXE, "-s", device_id, "shell", "getprop"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
        encoding='utf-8'
    )
    if result.returncode != 0:
        raise Exception(f"ADB failed for {device_id}: {result.stderr}")

    prop_output = result.stdout

    for os_enum in SupportedOS:
        keyword = os_enum.value.props_keyword
        if keyword in prop_output:
            return os_enum.value
    t_log.warning('Detect UNSUPPORTED OS type, will fallback to UNKNOWN OS info.')
    return SupportedOS.UNKNOWN.value

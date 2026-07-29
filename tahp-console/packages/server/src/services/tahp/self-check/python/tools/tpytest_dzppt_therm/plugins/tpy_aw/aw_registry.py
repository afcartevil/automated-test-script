import pkgutil
import importlib
import importlib.metadata
import subprocess
from typing import Optional, Union, List

from powertrde.env import ADB_EXE
from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase
from tpy_aw.aw_configs.supported_os_config import SupportedOS
from tpy_aw.aw_defines import PhoneOsInfo
from tpytest.aw_framework.aw_base import _global_registry, AwBase
from tpy_aw.aw_feature_base import AwFeatureBase

_loaded_modules = set()

_cached_aw_app_ins = {}
_cached_aw_feature_ins = {}
_cached_aw_helper_ins = {}


class AwNotFoundError(RuntimeError):
    pass


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
def get_aw_feature(u2d_helper, name: str, variant: Optional[str] = None, nickname: Optional[str] = None,
                   base_type: Optional[type] = None) -> AwFeatureBase:
    if not nickname:
        try:
            return _get_aw_feature(u2d_helper, name, variant, nickname, base_type)
        except AwNotFoundError as e1:
            try:
                return _get_aw_feature(u2d_helper, '', variant, name, base_type)
            except AwNotFoundError:
                raise e1
    else:
        return _get_aw_feature(u2d_helper, name, variant, nickname, base_type)


def _get_aw_feature(u2d_helper, name: str, variant: Optional[str] = None, nickname: Optional[str] = None,
                    base_type: Optional[type] = None) -> AwFeatureBase:
    import tpy_aw.aw_features as aw_features_pkg
    _load_plugins(aw_features_pkg)
    merged_name = AwBase.merge_aw_name_nickname(name, nickname, to_lower=False)
    merged_name_lower = merged_name.lower()
    var = (variant or u2d_helper.get_aw_feature_variant_key(merged_name_lower)).lower()
    impls = _global_registry.get('feature', {}).get(merged_name_lower, {})
    if base_type:
        fallbacks_var_empty = None
        fallbacks_same_type = None
        for _var, _cls in impls.items():
            if issubclass(_cls, base_type):
                if not _var:
                    fallbacks_var_empty = _cls
                if _cls is base_type:
                    fallbacks_same_type = _cls
                if _var == var:
                    cls = _cls
                    break
        else:
            cls = fallbacks_var_empty or fallbacks_same_type
    else:
        cls = impls.get(var) or impls.get('')

        # only nickname fallback 机制
        if not cls and not name and nickname and not var and impls:
            for _v in impls.values():
                if len(impls) == 1:
                    cls = _v
                    break
                _first_aw_name = getattr(_v, 'aw_name', None)
                if _first_aw_name:
                    _var = u2d_helper.get_aw_feature_variant_key(_first_aw_name)
                    if _var:
                        cls = impls.get(var)
                break
    if not cls:
        raise AwNotFoundError(f"Feature AW not found: {merged_name}@{var}")
    tuple_key = (cls, u2d_helper)
    ins = _cached_aw_feature_ins.get(tuple_key)
    if ins is None:
        ins = cls()
        ins.u2d_helper = u2d_helper
        _cached_aw_feature_ins[tuple_key] = ins
    return ins


# 获取应用层 AW
def get_aw_app(u2d_helper, name: str, variant: Optional[str] = None, nickname: Optional[str] = None,
               base_type: Optional[type] = None) -> AwAppBase:
    if not nickname:
        try:
            return _get_aw_app(u2d_helper, name, variant, nickname, base_type)
        except AwNotFoundError as e1:
            try:
                return _get_aw_app(u2d_helper, '', variant, name, base_type)
            except AwNotFoundError:
                raise e1
    else:
        return _get_aw_app(u2d_helper, name, variant, nickname, base_type)


def _get_aw_app(u2d_helper, name: str, variant: Optional[str] = None, nickname: Optional[str] = None,
                base_type: Optional[type] = None) -> AwAppBase:
    import tpy_aw.aw_apps as aw_apps_pkg
    _load_plugins(aw_apps_pkg)
    merged_name = AwBase.merge_aw_name_nickname(name, nickname, to_lower=False)
    merged_name_lower = merged_name.lower()
    var = (variant or u2d_helper.get_aw_app_variant_key(merged_name_lower)).lower()
    impls = _global_registry.get('app', {}).get(merged_name_lower, {})
    if base_type:
        fallbacks_var_empty = None
        fallbacks_same_type = None
        for _var, _cls in impls.items():
            if issubclass(_cls, base_type):
                if not _var:
                    fallbacks_var_empty = _cls
                if _cls is base_type:
                    fallbacks_same_type = _cls
                if _var == var:
                    cls = _cls
                    break
        else:
            cls = fallbacks_var_empty or fallbacks_same_type
    else:
        cls = impls.get(var) or impls.get('')

        # only nickname fallback 机制
        if not cls and not name and nickname and not var and impls:
            for _v in impls.values():
                if len(impls) == 1:
                    cls = _v
                    break
                _first_aw_name = getattr(_v, 'aw_name', None)
                if _first_aw_name:
                    _var = u2d_helper.get_aw_app_variant_key(_first_aw_name)
                    if _var:
                        cls = impls.get(var)
                break
    if not cls:
        raise AwNotFoundError(f"App AW not found: {merged_name}@{var}")
    tuple_key = (cls, u2d_helper)
    ins = _cached_aw_app_ins.get(tuple_key)
    if ins is None:
        ins = cls()
        ins.u2d_helper = u2d_helper
        _cached_aw_app_ins[tuple_key] = ins
    return ins


# 获取封装层 AW
def get_aw_helper(u2d_or_device_id, name: str, variants: Union[str, List[str]] = None, nickname: Optional[str] = None,
                  base_type: Optional[type] = None):
    cls = get_aw_helper_type(name, variants, nickname, base_type)
    tuple_key = (cls, u2d_or_device_id)
    ins = _cached_aw_helper_ins.get(tuple_key)
    if ins is None:
        ins = cls(u2d_or_device_id)
        _cached_aw_helper_ins[tuple_key] = ins
    return ins


# 获取封装层 AW 类型
def get_aw_helper_type(name: str, variants: Union[str, List[str]] = None, nickname: Optional[str] = None,
                       base_type: Optional[type] = None):
    if not nickname:
        try:
            return _get_aw_helper_type(name, variants, nickname, base_type)
        except AwNotFoundError as e1:
            try:
                return _get_aw_helper_type('', variants, name, base_type)
            except AwNotFoundError:
                raise e1
    else:
        return _get_aw_helper_type(name, variants, nickname, base_type)


def _get_aw_helper_type(name: str, variants: Union[str, List[str]] = None, nickname: Optional[str] = None,
                        base_type: Optional[type] = None):
    import tpy_aw.aw_helpers as aw_helpers_pkg
    _load_plugins(aw_helpers_pkg)
    from tpy_aw.u2d_test_helper import U2DTestHelper
    _ = U2DTestHelper  # 自动注册到AW

    merged_name = AwBase.merge_aw_name_nickname(name, nickname, to_lower=False)
    merged_name_lower = merged_name.lower()
    _vars = []
    if variants:
        if isinstance(variants, str):
            _vars = [variants.lower()]
        else:
            for _v in variants:
                _vars.append(_v.lower())
    _vars = _vars[::-1]
    impls = _global_registry.get('u2_helper', {}).get(merged_name_lower, {})
    _max_var_idx = -1
    _ret_cls = None
    _used_var = ''
    if base_type:
        fallbacks_var_empty = None
        fallbacks_same_type = None
        for _var, _cls in impls.items():
            if issubclass(_cls, base_type):
                if not _var:
                    fallbacks_var_empty = _cls
                if _cls is base_type:
                    fallbacks_same_type = _cls

                var_idx = _vars.index(_var) if _var in _vars else -1
                if var_idx > _max_var_idx:
                    _used_var = _var
                    _ret_cls = _cls
        else:
            _ret_cls = fallbacks_var_empty or fallbacks_same_type
    else:
        for _v in _vars:
            _ret_cls = impls.get(_v)
            if _ret_cls:
                _used_var = _v
                break
        else:
            _ret_cls = impls.get('')
    if not _ret_cls:
        raise AwNotFoundError(f"Helper AW not found: {merged_name}@{_used_var}")
    return _ret_cls


def get_aw_helper_by_os_info(u2d_or_device_id, os_info: PhoneOsInfo):
    return get_aw_helper(u2d_or_device_id, os_info.vendor_name, os_info.os_name)


def get_aw_helper_type_by_os_info(os_info: PhoneOsInfo):
    _vars = os_info.os_name
    if os_info.extra_env_keys:
        _vars = [os_info.os_name]
        _vars.extend(os_info.extra_env_keys)
    return get_aw_helper_type(os_info.vendor_name, _vars)


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
        if keyword.startswith('@:'):
            if getattr(SupportedOS, keyword[2:])(prop_output):
                return os_enum.value
        else:
            if keyword in prop_output:
                return os_enum.value
    t_log.warning('Detect UNSUPPORTED OS type, will fallback to UNKNOWN OS info.')
    return SupportedOS.UNKNOWN.value

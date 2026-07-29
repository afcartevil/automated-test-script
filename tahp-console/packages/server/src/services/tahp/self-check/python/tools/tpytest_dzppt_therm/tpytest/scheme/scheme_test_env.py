import logging
import os
import sys
import time
from datetime import datetime
from threading import Lock
from typing import Tuple, List, Set, Dict, Any, Optional

import pytest

from powertrde import env
from powertrde.framework.table.feishu_static_table_loader import FeishuStaticTableLoader
from powertrde.framework.tran_logger.device_logger import DeviceLogger
from powertrde.framework.tran_logger.log_device import LocalLogDevice, AdbLogDevice, MultiLogDevice
from powertrde.framework import t_inject
from powertrde.framework.tran_logger.tran_logger import ObfuscatingFilter
from powertrde.utils import misc_utils, net_utils, confuse_utils
from powertrde.utils.android_extends.android_device_marker import DeviceMarkerStore
from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper
from powertrde.utils.lazy_shared_pool import LazySharedPool
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2patches
from powertrde.utils.u2_extends.base_u2d_test_helper import BaseU2DTestHelper
from powertrde.utils.u2_extends.i_has_u2d_helper import IHasU2DHelper, IHasCopilotU2DHelper, IHasObserveU2DHelper
from powertrde.utils.simple_event_center import SimpleEventCenter
from powertrde.utils.u2_extends.u2d_test_helper_factory import U2DTestHelperFactory
from powertrde.utils.wifiadb import wifi_adb_utils
from tpytest.app_repo_client_protocol import AppRepoClientProtocol
from tpytest.preset_recorder import PresetRecorder
from tpytest.resource_provider import FeishuProvider
from tpytest.scheme.scheme_task_session_life import SchemeTaskSessionLife
from tpytest.scheme.scheme_user_config import SchemeUserConfig
from tpytest.test_case_counter import TestCaseCounter
from tpytest.u2_serial_provider_factory import U2SerialProviderFactory, CopilotU2SerialProviderFactory
from tpytest_extends.scheme.apps_static_info import AppsStaticInfo
from tpytest.app_installer_client import AppInstallerForClient


class _ErrorTagFileLogHandler(logging.FileHandler):
    def __init__(self, file_path: str, log_list: list):
        super().__init__(file_path, delay=True, encoding="utf-8")
        self.log_list = log_list

    def emit(self, record):
        try:
            tag = getattr(record, 'tag', None)
            if tag and 'error' in tag:
                self.log_list.append(self.format(record))
                super().emit(record)
        except Exception:
            self.handleError(record)


class _EventLogHandler(logging.Handler):
    def emit(self, record):
        try:
            # 通过 getattr 获取 extra 中的 'event' 属性，默认为 None
            need_send_logger_event = getattr(record, 'event', None)
            if need_send_logger_event:
                get_scheme_env().send_log_event(record.levelno, self.format(record))
        except Exception:
            self.handleError(record)


class SchemeTestEnv(IHasU2DHelper, IHasCopilotU2DHelper, IHasObserveU2DHelper):
    option_user_config_class_type = SchemeUserConfig
    option_user_session_life_class_type = SchemeTaskSessionLife
    option_user_u2d_helper_class_type = None

    # 是否通过此测试环境完全接管task_session_life类的u2d, device id等属性，防止其拥有单独的设定值（一般建议打开）
    option_fully_take_over_task_session_life_properties = True

    _instance = None

    _from_singleton = False

    _has_apply_u2_patches = False

    _has_apply_u2d_helper_factory_injections = False

    _selected_instance = None

    _builder_configs = None

    _builder_locker = Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._from_singleton = True
            cls._instance = cls()
            cls._from_singleton = False
            if env.get_user_runtime_phase() != 'batch_entry':
                cls._instance.try_fill_devices()
        if not (cls._instance is cls._selected_instance):
            cls._instance.set_self_as_selected_instance()
        return cls._instance

    @classmethod
    def purge_instance(cls):
        cls._instance = None

    def _on_interrupt_signal(self, signum, frame):
        if self.device_id:
            # 尝试停止未完成的 perfetto 进程，防止持续占用资源
            adb.try_stop_exist_detached_perfetto(self.device_id)

    @property
    def interrupt_signal_manager(self):
        return env.interrupt_signal_manager

    def is_env_default_instance(self):
        return bool(self is self._instance)

    @classmethod
    def create(cls, specific_user_config: Optional[SchemeUserConfig] = None):
        with SchemeTestEnv._builder_locker:
            try:
                SchemeTestEnv._builder_configs = (specific_user_config,)
                return cls()
            finally:
                SchemeTestEnv._builder_configs = None

    def __init__(self):
        super().__init__()

        if self._from_singleton:
            # 注入中断检测
            self.interrupt_signal_manager.register(self._on_interrupt_signal)

            # 拉取运行时参数
            self.sys_kwargs = misc_utils.parse_args_to_dict(sys.argv[1:])
        else:
            self.sys_kwargs = {}

        # 加载用户参数（多层级覆盖算法）
        self._user_config: SchemeUserConfig = SchemeTestEnv._builder_configs[0] if SchemeTestEnv._builder_configs else None
        self._load_user_config()

        # 注入TAEP支持（前）
        self._taep_pre_injected = False
        self._taep_post_injected = False
        if self._from_singleton:
            if self.is_use_taep:
                _added_taep_root_dir = self._try_add_taep_root_dir_to_env()
                if _added_taep_root_dir:
                    self._taep_pre_injected = self._apply_taep_pre_injections(self.is_use_taep)
                elif self.is_use_taep:
                    raise Exception(
                        'You specified the use of TAEP CASE support in CONFIG, but did not find the taep directory in the project root directory.')

        # 注入U2补丁
        self._apply_u2_patches()

        # 注入 U2D Helper 工厂
        if self.option_user_u2d_helper_class_type:
            self._apply_u2d_helper_factory_injections()

        self._event_center = None
        self._preset_record_groups = None
        self._ever_init = False
        self._logger = None
        self._session_id = None
        self._tran_cpu_platform = None
        self._feishu_static_table_loader = None
        self._feishu_helper = None
        self._feishu_res_provider = None
        self._feishu_app_repo_provider = None
        self._app_repo_cache_lock_manager = None
        self._app_repo_client_feishu = None
        self._app_repo_client_internal = None
        self.error_tag_logs = []
        self._os_version = None
        self._retests_combiner = None
        self._device_marker_stores: Dict[str, DeviceMarkerStore] = {}

        self._is_transsion_network = None

        self.pretest_counter = TestCaseCounter('pretest', on_changed_event=self._on_test_counter_send_vm_event)
        self.test_counter = TestCaseCounter('case', on_changed_event=self._on_test_counter_send_vm_event)
        self.test_cases: List[Tuple[str, pytest.Item]] = []
        self.test_apps: List[AppsStaticInfo] = []
        self.copilot_apps: List[AppsStaticInfo] = []
        self.has_any_need_copilot_mark: bool = False
        self.has_any_need_observe_mark: bool = False
        self.back_apps: List[AppsStaticInfo] = []
        self.collected_pretest_names: Set[str] = set()
        self.collected_pretest_flags: Set[str] = set()

        self.last_task_session_life: Optional[SchemeTaskSessionLife] = None

        self.set_self_as_selected_instance()

        self.scheme_request.set_user_env_arg('scheme_env', self)
        self.scheme_request.set_user_env_arg('logger', lambda: self.logger)

    def set_self_as_selected_instance(self):
        self.__class__._selected_instance = self
        if env.scheme is self.scheme_request:
            env.set_custom_env_args_dict(None)
        else:
            env.set_custom_env_args_dict(self.scheme_request.user_env_args)
        t_inject.clear_and_configure(self._bind_injections)

    def _load_user_config(self):
        if self._user_config is None:
            self._user_config = self.option_user_config_class_type.get_instance()
        _override_config_sys_str = self.sys_kwargs.pop('config', '')
        _override_config_dict_from_shared = self.scheme_request.get_scheme_shared_kwargs()
        _override_config_dict_from_sys = self.load_override_user_config(_override_config_sys_str)

        # _override_config_sys_str_p_arg = self.sys_kwargs.pop('p', '')
        # if _override_config_sys_str_p_arg:
        #     # 如果遇到了-p参数，自动将其带入系统级config传参中，以后类似参数也做这样的特殊处理
        #     if _override_config_dict_from_sys is None:
        #         _override_config_dict_from_sys = {'log_dir': _override_config_sys_str_p_arg}
        #     else:
        #         _override_config_dict_from_sys['log_dir'] = _override_config_sys_str_p_arg

        _user_passed_override_config_dict = {}
        if _override_config_dict_from_shared:
            _user_passed_override_config_dict.update(_override_config_dict_from_shared)
        if _override_config_dict_from_sys:
            _user_passed_override_config_dict.update(_override_config_dict_from_sys)
        _override_config_dict = self._load_user_override_config_dict(_user_passed_override_config_dict)
        if _override_config_dict:
            self._user_config.overwrite_config(_override_config_dict)

    def _load_user_override_config_dict(self, _user_passed_override_config_dict: dict):
        """加载用户覆写config，参数是用户传入的原始dict，如果你不需要更改该dict，直接返回即可，否则可自定义hook你的config进去"""
        return _user_passed_override_config_dict

    def _try_add_taep_root_dir_to_env(self):
        _taep_root_path = os.path.join(env.PROJ_DIR, 'taep')
        if os.path.exists(_taep_root_path):
            if _taep_root_path not in sys.path:
                sys.path.insert(0, _taep_root_path)
            return True
        return False

    def _apply_taep_pre_injections(self, check_error: bool):
        try:
            from tpytest_extends.taep_support import taep_injections
            taep_injections.pre_inject_all(self)
            return True
        except Exception:
            if check_error:
                raise
        return False

    def _apply_taep_post_injections(self):
        from tpytest_extends.taep_support import taep_injections
        taep_injections.post_inject_all(self)

    @classmethod
    def _apply_u2d_helper_factory_injections(cls):
        if cls._has_apply_u2d_helper_factory_injections:
            return

        if issubclass(cls.option_user_u2d_helper_class_type, BaseU2DTestHelper):
            # 如果自定义的helper类型是BaseU2DTestHelper的父类，则不生成混合类，直接将其作为最终生成类
            U2DTestHelperFactory.get_instance().default_u2d_test_helper_class_or_factory = cls.option_user_u2d_helper_class_type
        else:
            # 生成动态组合的 U2D Helper（动态取OS info对应的aw helper作为基类，并且把self.option_user_u2d_helper_class_type进行MixIn
            def _helper_factory(device_id):
                if not device_id:
                    return None
                if not isinstance(device_id, str):
                    device_id = device_id.serial
                try:
                    aw_module = env.load_module('tpy_aw.aw_registry')
                    detect_os_info = aw_module.detect_os_info
                    get_aw_helper_type_by_os_info = aw_module.get_aw_helper_type_by_os_info
                except Exception:
                    raise Exception(
                        f'Not support instantiate test helper type "{cls.option_user_u2d_helper_class_type.__name__}" when not import "tpy_aw" module plugin.')

                # 检查缓存，防止重复检查
                _cached_os_info = env.get_user_env_arg('device_os_info')
                if _cached_os_info and env.get_user_env_arg('device_id') == device_id:
                    aw_helper_type = get_aw_helper_type_by_os_info(_cached_os_info)
                else:
                    aw_helper_type = get_aw_helper_type_by_os_info(detect_os_info(device_id))
                pre_name = cls.option_user_u2d_helper_class_type.__name__.replace('U2DTestHelper', '')
                post_name = aw_helper_type.__name__
                return type(f'_{pre_name}{post_name}', (cls.option_user_u2d_helper_class_type, aw_helper_type),
                            {})(device_id)

            U2DTestHelperFactory.get_instance().default_u2d_test_helper_class_or_factory = _helper_factory

        cls._has_apply_u2d_helper_factory_injections = True

    @classmethod
    def _apply_u2_patches(cls):
        if cls._has_apply_u2_patches:
            return
        u2patches.patch_u2_swipe_to_adb_swipe()
        cls._has_apply_u2_patches = True

    def _on_test_counter_send_vm_event(self, counter: TestCaseCounter):
        self.send_test_counter_event(counter)
        self.send_vm_event('case_result_count', (counter.total_count, counter.pass_count, counter.fail_count),
                           counter.name)

    @staticmethod
    def load_override_user_config(text_to_load: str):
        _user_overwrite_config_dict = None
        if not text_to_load:
            return _user_overwrite_config_dict
        if os.path.exists(text_to_load):
            try:
                from powertrde.utils import yaml_utils
                _user_overwrite_config_dict = yaml_utils.read_yaml(text_to_load, ignore_yaml_error=False)
            except Exception:
                from powertrde.utils import json_utils
                _user_overwrite_config_dict = json_utils.read_json_file(text_to_load)
        else:
            try:
                import json
                _user_overwrite_config_dict = json.loads(text_to_load)
            except Exception:
                import ast
                _user_overwrite_config_dict = ast.literal_eval(text_to_load)
        return _user_overwrite_config_dict

    @property
    def is_taep_injected(self):
        return self._taep_pre_injected

    @property
    def app_multi_package_keys(self):
        if not self.device_id:
            return self.base_app_multi_package_keys
        return self.get_app_multi_package_keys(self.device_id)

    @property
    def env_keys(self):
        return self.app_multi_package_keys

    @property
    def c_app_multi_package_keys(self):
        if not self.c_device_id:
            return self.base_app_multi_package_keys
        return self.get_app_multi_package_keys(self.c_device_id)

    @property
    def c_env_keys(self):
        return self.c_app_multi_package_keys

    @property
    def base_app_multi_package_keys(self):
        return self.scheme_request.get_user_env_arg('app_multi_package_keys', [])

    def get_app_multi_package_keys(self, device_id: str):
        ret = []
        base = self.scheme_request.get_user_env_arg('app_multi_package_keys', None)
        update = None
        if device_id:
            update = self.scheme_request.get_user_env_arg(f'app_multi_package_keys_{device_id}', None)
        if base:
            ret.extend(base)
        if update:
            for u in update:
                if u not in base:
                    ret.append(u)
        return ret

    def has_env_key(self, key: str):
        return key in self.env_keys

    def c_has_env_key(self, key: str):
        return key in self.c_env_keys

    def add_multi_package_keys(self, device_id: str, keys: List[str]):
        arg_key = f'app_multi_package_keys_{device_id}' if device_id else 'app_multi_package_keys'
        exist = self.scheme_request.get_user_env_arg(arg_key, None)
        if not exist:
            exist = list(keys)
            self.scheme_request.set_user_env_arg(arg_key, exist)
        else:
            for k in keys:
                if k not in exist:
                    exist.append(k)
        return exist

    def _bind_injections(self, binder: t_inject.Binder):
        self._feishu_bind_injections(binder)

    @property
    def has_copilot_case(self):
        return bool(self.copilot_apps or self.has_any_need_copilot_mark)

    @property
    def has_observe_case(self):
        return bool(self.has_any_need_observe_mark)

    @property
    def is_auto_lock_copilot_on_copilot_case_setup(self):
        return self.has_trunk_flag('auto_lock_copilot_on_copilot_case_setup')

    @property
    def is_use_taep(self):
        return self.has_trunk_flag('use_taep')

    @property
    def user_config(self):
        return self._user_config

    @property
    def has_error_logs(self):
        return bool(self.error_tag_logs)

    def run_collector_for_session(self, data_collector, suffix: str, override_params: Optional[Dict[str, Any]] = None):
        data_collector.run_all(label=self.gen_node_collect_label_name_for_session(suffix),
                               override_params=override_params)

    def gen_node_collect_label_name_for_session(self, suffix: str):
        if suffix:
            suffix = '-' + suffix
        elif suffix is None:
            suffix = ''
        return f'session-{misc_utils.get_date_time_filename_str()}{suffix}'

    def gen_data_node_collector(self, data_node_collector_configs: List[Dict[str, Any]]):
        """
        通过信息收集器所需的一组configs，创建一个信息收集器，用于session或者case的信息收集
        """
        assert self.device_id, 'Device_id is empty, unable to use gen_data_node_collector!'
        data_collector_class = env.load_class('data_collector.data_node_collector.DataNodeCollector')
        return data_collector_class(data_node_collector_configs, output_dir=self.get_collects_report_dir(),
                                    device_id=self.device_id)

    def try_fill_devices(self, forced=False):
        if self._ever_init and not forced:
            return

        self._ever_init = True
        ori_device_id = self.device_id

        if self.has_trunk_flag('allow_env_detect_wifi_adb'):
            devices = adb.adb_devices()
        else:
            devices = wifi_adb_utils.get_usb_adb_devices()

        # 从配置文件中获取优先级最高
        _device_id = self.user_config.device_id
        _c_device_id = self.user_config.c_device_id
        _o_device_id = self.user_config.o_device_id

        def _read_copilot_phone():
            """
            从测试机读取/推断辅助机ID，按优先级返回第一个可用的ID。
            配对文件 /sdcard/device_pairing.json 支持：
            {
                "copilot_device_ids": ["5E6F7G8H", "8Z9X0Y1W"],
                "main_device": "1A2B3C4D",
                "created_time": "2024-01-01 10:00:00",
                "description": "测试机与辅助机配对关系"
            }
            """
            if _device_id:
                # 从用户设置的device_name里获取推荐配置的辅助机ID列表
                _suggested_copilot_ids = BaseU2DTestHelper.static_get_user_defined_device_name_copilot_ids(_device_id)
                if _suggested_copilot_ids:
                    for _id in _suggested_copilot_ids:
                        if _id in devices and _id != _device_id:
                            return _id

            # Fallback 模式：使用测试机读取配对文件
            try:
                candidates = []
                if _device_id:
                    # 从测试机读取配对文件
                    lines = adb.exec_cmd(_device_id, 'cat /sdcard/device_pairing.json')
                    if lines:
                        import json
                        content = '\n'.join(lines).strip()
                        pairing_data = json.loads(content)
                        if pairing_data.get('main_device') == _device_id:
                            ids = pairing_data.get('copilot_device_ids', [])
                            if isinstance(ids, list):
                                candidates.extend(ids)
                for cid in candidates:
                    if cid and cid in devices and cid != _device_id:
                        return cid
            except Exception as e:
                raise Exception(f"读取设备配对信息失败: {e}")
            return None

        # 入口参数传入如环境变量
        env_device_id = os.environ.get('DEVICE_ID')
        if env_device_id and not _device_id:
            _device_id = env_device_id

        env_c_device_id = os.environ.get('C_DEVICE_ID')
        if env_c_device_id and not _c_device_id:
            _c_device_id = env_c_device_id

        _extra_pair_log = None

        if _device_id and not env_c_device_id and not _c_device_id:
            copilot_from_device = _read_copilot_phone()
            if copilot_from_device:
                _c_device_id = copilot_from_device
                _extra_pair_log = f"自动配对成功: {env_device_id} -> {copilot_from_device}"

        if _device_id and _device_id not in devices:
            raise Exception(f"Not found TEST PHONE you specified '{_device_id}' in adb devices.")

        if _c_device_id and _c_device_id.lower() != 'none' and _c_device_id not in devices:
            raise Exception(f"Not found COPILOT PHONE you specified '{_c_device_id}' in adb devices.")

        if _o_device_id.lower() == 'auto':
            need_find_o_device_id = True
            _o_device_id = ''
        else:
            need_find_o_device_id = False

        if _o_device_id and _o_device_id.lower() != 'none' and _o_device_id not in devices:
            raise Exception(f"Not found OBSERVE PHONE you specified '{_o_device_id}' in adb devices.")

        _device_model = ''
        _rom_version = ''
        for d in devices:
            # 检查息屏显示，如果True，强制亮屏，防止is_pointer_location_on获取不准
            if adb.is_aod_enabled(d):
                adb.poweron_phone_screen(d)
                time.sleep(0.3)
            p_on = adb.is_pointer_location_on(d)
            o_on = (need_find_o_device_id and adb.is_fps_show(d))
            if not _c_device_id and p_on:
                _c_device_id = d
            if not _o_device_id and o_on:
                _o_device_id = d
            if not _device_id and not p_on and not o_on:
                _device_id = d
        # 如果是debug use_copilot_as_main模式，那么可以将头上标“辅助机”或“观测机”的手机当做测试机
        if self.is_debug_use_copilot_as_main and _c_device_id and not _device_id:
            _device_id = _c_device_id
            _c_device_id = ''
        if self.is_debug_use_copilot_as_main and _o_device_id and not _device_id:
            _device_id = _o_device_id
            _o_device_id = ''
        if _device_id:
            _device_model = adb.device_model_simple(_device_id)
            _rom_version = adb.get_device_rom_version(_device_id)

        if ori_device_id != _device_id:
            self._preset_record_groups = None

        last_device_id = self.device_id
        if last_device_id != _device_id:
            self.device_id = _device_id
        self.c_device_id = _c_device_id if _c_device_id.lower() != 'none' else ''
        self.o_device_id = _o_device_id if _o_device_id.lower() != 'none' else ''

        self.scheme_request.set_user_env_arg('device_info', self.device_info)
        self.scheme_request.set_user_env_arg('device_sn', self.device_sn)
        self.scheme_request.set_user_env_arg('device_id', lambda: self.device_id)
        self.scheme_request.set_user_env_arg('c_device_id', self.c_device_id)
        if self.c_device_id:
            self.scheme_request.set_user_env_arg('c_device_sn', self.c_device_sn)
        self.scheme_request.set_user_env_arg('o_device_id', self.o_device_id)
        if self.o_device_id:
            self.scheme_request.set_user_env_arg('o_device_sn', self.o_device_sn)
        self.scheme_request.set_user_env_arg('device_model', self.device_model)
        self.scheme_request.set_user_env_arg('device_brand', self.device_brand)
        self.scheme_request.set_user_env_arg('device_rom_version', self.device_rom_version)
        self.scheme_request.set_user_env_arg('u2d', lambda: self.u2d)
        self.scheme_request.set_user_env_arg('c_u2d', lambda: self.c_u2d)
        self.scheme_request.set_user_env_arg('o_u2d', lambda: self.o_u2d)
        self.scheme_request.set_user_env_arg('u2d_helper', lambda: self.u2d_helper)
        self.scheme_request.set_user_env_arg('c_u2d_helper', lambda: self.c_u2d_helper)
        self.scheme_request.set_user_env_arg('o_u2d_helper', lambda: self.o_u2d_helper)
        self.scheme_request.set_user_env_arg('tran_cpu_platform', self.tran_cpu_platform)
        if self.device_id:
            self.scheme_request.set_user_env_arg('os_version', self.os_version)
            self._on_device_reinit(self.device_id)
            self._on_main_device_reinit()
        if self.c_device_id:
            self._on_device_reinit(self.c_device_id)

        # 注入TAEP支持（后）
        if self._taep_pre_injected and not self._taep_post_injected:
            self._apply_taep_post_injections()
            self._taep_post_injected = True
            print('Discovered the TAEP framework and successfully injected its support.')

        # 后置打出额外日志
        if _extra_pair_log:
            print(_extra_pair_log)

        # Config-后处理
        self.user_config.post_fill({'device_id': self.device_id, 'c_device_id': self.c_device_id})

    def _on_device_reinit(self, target_device_id: str):
        if adb.is_transsion_device(target_device_id) and adb.is_qcom(target_device_id):
            self.add_multi_package_keys(target_device_id, ['TQCOM'])
        if adb.package_is_installed(target_device_id, 'com.google.android.apps.searchlite'):
            self.add_multi_package_keys(target_device_id, ['Googlego'])
        if adb.package_is_installed(target_device_id, 'com.google.android.dialer'):
            self.add_multi_package_keys(target_device_id, ['AndroidDialer'])
        if not adb.package_is_installed(target_device_id, 'com.transsion.smartmessage'):
            self.add_multi_package_keys(target_device_id, ['GOOGLE_SMS'])
        self.device_info.register_other_info_factory('tran_cpu_platform', lambda _: self.tran_cpu_platform,
                                                     perform_factory=True)
        try:
            tpy_aw_os_info_entry = env.load_member('tpy_aw.aw_registry.detect_os_info')
            if tpy_aw_os_info_entry:
                device_os_info = tpy_aw_os_info_entry(target_device_id)
                if device_os_info:
                    if target_device_id == self.device_id:
                        self.scheme_request.set_user_env_arg('device_os_info', device_os_info)
                    os_key: str = device_os_info.key
                    if os_key != 'UNKNOWN':
                        append_multi_key_list = []
                        os_key_splits = os_key.split('_')
                        _short_os_key = ''
                        for osk in os_key_splits:
                            if _short_os_key:
                                _short_os_key += '_'
                                _short_os_key += osk
                            else:
                                _short_os_key = osk
                            append_multi_key_list.append(_short_os_key)
                        append_multi_key_list.extend(device_os_info.extra_env_keys)
                        self.add_multi_package_keys(target_device_id, append_multi_key_list)
        except Exception:
            pass

    def _on_main_device_reinit(self):
        # 主设备初始化时即尝试停止perfetto，防止后续出现trace无法抓取的情况
        adb.try_stop_exist_detached_perfetto(self.device_id)

    @property
    def retests_combiner(self):
        if not self.user_config.retest_target:
            return None
        if self._retests_combiner is None:
            from tpytest.reports_combiner import ReportsCombiner, ReportMergeMode
            _retest_target_normalized = self.get_retest_target_normalized()
            if not _retest_target_normalized:
                raise Exception(f'Not found retest target path: {self.user_config.retest_target}')
            self._retests_combiner = ReportsCombiner(self.scheme_request.name, _retest_target_normalized,
                                                     ReportMergeMode.PassRelace, search_retests=True)
            self._retests_combiner.parse_report_processors()
            self._retests_combiner.merge_reports()
        return self._retests_combiner

    def get_retest_target_normalized(self):
        _rt = self.user_config.retest_target
        if not _rt or not os.path.exists(_rt):
            return None
        return _rt

    def get_device_id(self):
        if self._u2d_helper is None:
            return super().get_device_id()
        return self.u2d_helper.device_id

    @property
    def scheme_request(self):
        return self.user_config.scheme_request

    @property
    def device_static_info(self):
        raise NotImplementedError('必须由子类实现获取设备静态信息的逻辑')

    @property
    def is_low_end_device(self) -> bool:
        try:
            return self.device_static_info.is_low_end
        except Exception:
            pass
        # 当没有子类实现覆盖逻辑时，直接Fallback到通用判定逻辑
        return self.u2d_helper.is_low_end

    @property
    def team_name(self):
        return self.scheme_request.team

    @property
    def scheme_name(self):
        return self.scheme_request.name

    @property
    def nickname(self):
        return self.scheme_request.nickname

    @property
    def event_center(self):
        if not self._event_center:
            self._event_center = SimpleEventCenter.get_instance()
        return self._event_center

    def send_test_counter_event(self, counter: TestCaseCounter):
        self.event_center.dispatch_event('test_counter_event', counter=counter, tag='cross_process')

    def send_vm_event(self, vm_key: str, vm_value, vm_group: str = ''):
        self.event_center.dispatch_event('scheme_vm_event', group=vm_group, key=vm_key, value=vm_value,
                                         tag='cross_process')

    def send_log_event(self, level: int, message: str):
        self.event_center.dispatch_event('scheme_log_event', level=level, message=message, tag='cross_process')

    def print_log_dir(self):
        self.logger.info(f'Logs path is here: {self.get_log_root_dir()}', ext_event=True)

    @property
    def preset_record_groups(self):
        if self._preset_record_groups:
            return self._preset_record_groups
        if not self.device_sn or not self.device_model:
            raise Exception('运行时环境变量中没有找到 device_sn 或者 device_model')
        self._preset_record_groups = PresetRecorder.load_record_groups(self.device_model, self.device_sn,
                                                                       self.is_debug_fallback)
        return self._preset_record_groups

    @property
    def runtime_phase(self):
        return self.scheme_request.get_user_runtime_phase()

    @runtime_phase.setter
    def runtime_phase(self, value: str):
        self.scheme_request.set_user_runtime_phase(value)

    @property
    def debug_modes(self):
        return self.scheme_request.get_user_env_debug_modes()

    @debug_modes.setter
    def debug_modes(self, value):
        self.scheme_request.set_user_env_debug_modes(value)

    @property
    def is_debug(self):
        return self.scheme_request.user_env_is_debug()

    @property
    def is_debug_use_copilot_as_main(self):
        return self.scheme_request.has_user_env_debug_mode('use_copilot_as_main')

    @property
    def is_debug_fallback(self):
        return self.scheme_request.has_user_env_debug_mode('fallback')

    @property
    def is_debug_setup_case(self):
        return self.scheme_request.has_user_env_debug_mode('setup_case')

    @property
    def is_case_phase_or_debug_setup_case(self):
        return self.runtime_phase.startswith('case') or self.is_debug_setup_case

    @property
    def is_debug_setup_task(self):
        return self.scheme_request.has_user_env_debug_mode('setup_task')

    @property
    def is_case_phase_or_debug_setup_task(self):
        return self.runtime_phase.startswith('case') or self.is_debug_setup_task

    @property
    def is_pretest_phase_or_case_phase_or_debug_setup_task(self):
        return self.runtime_phase.startswith('pretest') or self.runtime_phase.startswith('case') or self.is_debug_setup_task

    def has_debug_mode(self, debug_mode_flag: str):
        return debug_mode_flag in self.debug_modes

    @property
    def trunk_flags(self):
        return self.scheme_request.get_user_env_trunk_flags()

    @trunk_flags.setter
    def trunk_flags(self, value):
        self.scheme_request.set_user_env_trunk_flags(value)

    def has_trunk_flag(self, flag: str):
        return flag in self.trunk_flags

    @property
    def is_short_test_debug(self):
        return self.has_debug_mode('short_test')

    def create_recorder_node(self, group_name: str):
        if not self.device_sn or not self.device_model:
            raise Exception('user_env_arg 环境变量中没有配置 device_sn 或者 device_model')
        return PresetRecorder.create_recorder_node(self.device_model, self.device_sn, group_name)

    def create_main_recorder_node(self):
        return self.create_recorder_node('main')

    def create_recorder_node_u2d(self, group_name: str):
        if not self.device_sn or not self.device_model:
            raise Exception('user_env_arg 环境变量中没有配置 device_sn 或者 device_model')
        return PresetRecorder.create_recorder_node_u2d(self.u2d, group_name)

    @property
    def res_provider(self):
        return self.user_config.res_provider

    @property
    def res_provider_app_repo(self):
        return self.user_config.res_provider_app_repo

    @property
    def logs_uploader(self):
        return self.user_config.logs_uploader

    @property
    def logger(self) -> DeviceLogger:
        if self._logger is None:
            self._gen_logger()
        return self._logger

    def set_logger(self, value: DeviceLogger, add_error_log_file_handler=True):
        if self._logger != value:
            self._logger = value
            if self._logger:
                self._init_logger(add_error_log_file_handler)

    def _init_logger(self, add_error_log_file_handler: bool):
        _event_log_handler = _EventLogHandler()
        self._logger.add_log_handler(logging.INFO, _event_log_handler)
        if self.is_publish_mode_odm:
            # 如果是ODM模式，混淆LOG之后再输出（仅INFO级别）
            _filter = ObfuscatingFilter(lambda _oig: confuse_utils.confuse_string(_oig),
                                        levels={logging.INFO},
                                        logger_name_pattern=None,
                                        marker=confuse_utils._MARKER,
                                        marker_skip=True,
                                        preserve_original=True)
            _event_log_handler.addFilter(_filter)
            self._logger._console_handler.addFilter(_filter)
            if self._logger._current_file_handler is not None:
                self._logger._current_file_handler.addFilter(_filter)

        if add_error_log_file_handler:
            self._logger.add_log_handler(logging.ERROR,
                                         _ErrorTagFileLogHandler(
                                             os.path.join(self.get_session_logs_dir(), "error.log"),
                                             self.error_tag_logs))
        from powertrde.framework.tran_logger import t_log
        t_log.set_default_logger(self._logger)

    def _gen_logger(self):
        pc_logger = LocalLogDevice(device_name='pc')
        device_logger = AdbLogDevice(device_name='main', device_id=lambda: U2SerialProviderFactory(self),
                                     lazy_device_id_call_factory_every_time=True)
        c_device_logger = AdbLogDevice(device_name='copilot', device_id=lambda: CopilotU2SerialProviderFactory(self),
                                       lazy_device_id_call_factory_every_time=True)
        multi_logger = MultiLogDevice(main_device=pc_logger, devices=[device_logger, c_device_logger])
        self._logger = DeviceLogger(log_device=multi_logger,
                                    base_log_dir=self.get_log_root_dir(),
                                    log_session_id='session_logs',
                                    name=self.scheme_name)
        self._init_logger(True)

    @property
    def session_id(self):
        if self._session_id is None:
            time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            s_name = self.scheme_name
            if s_name:
                s_name = '_' + s_name
            m_name = self.device_model
            if m_name:
                m_name = '_' + m_name
            m_sn = self.device_sn
            if m_sn:
                m_sn = '_' + m_sn
            self._session_id = f'{time_str}{s_name}{m_name}{m_sn}'
        return self._session_id

    @session_id.setter
    def session_id(self, value: str):
        self._session_id = value

    def get_runtime_log_parent_dir(self):
        _rtn = self.get_retest_target_normalized()
        if _rtn:
            return os.path.join(_rtn, 'retests')
        return self.user_config.log_parent_dir

    def get_log_root_dir(self):
        """
        如果重测，都获取的是重测的根目录
        """
        return os.path.join(self.get_runtime_log_parent_dir(), self.user_config.user_defined_log_dir_name or self.session_id)

    def get_log_root_dir_retest_root(self):
        """
        无论是否重测，都获取最根源的目录
        """
        _rtn = self.get_retest_target_normalized()
        if _rtn:
            return _rtn
        else:
            return self.get_log_root_dir()

    def get_session_logs_dir(self):
        log_root_dir = str(self.get_log_root_dir())
        return os.path.join(log_root_dir, 'session_logs')

    def get_session_video_logs_dir(self):
        return os.path.join(self.get_session_logs_dir(), 'video')

    def get_meta_report_dir(self):
        log_root_dir = str(self.get_log_root_dir())
        return os.path.join(log_root_dir, 'meta_report')

    @property
    def tran_cpu_platform(self):
        if not self.device_id:
            return ''
        if self._tran_cpu_platform is None:
            self._tran_cpu_platform = 'other'
            if adb.is_mtk(self.device_id):
                self._tran_cpu_platform = 'mtk'
            elif adb.is_sprd(self.device_id):
                self._tran_cpu_platform = 'sprd'
            elif adb.is_qcom(self.device_id):
                self._tran_cpu_platform = 'qcom'
        return self._tran_cpu_platform

    @property
    def os_version(self):
        if self._os_version is None:
            self._os_version = int(adb.device_android_version(self.device_id))
        return self._os_version

    @property
    def is_tran_cpu_mtk(self):
        return self.tran_cpu_platform == 'mtk'

    @property
    def is_tran_cpu_sprd(self):
        return self.tran_cpu_platform == 'sprd'

    @property
    def is_tran_cpu_qcom(self):
        return self.tran_cpu_platform == 'qcom'

    @property
    def feishu_helper(self):
        if self._feishu_helper is None:
            assert self.user_config.feishu_app_id and self.user_config.feishu_app_secret
            self._feishu_helper = FeishuApiHelper(self.user_config.feishu_app_id, self.user_config.feishu_app_secret)

            for name, token in self.user_config.feishu_root_table_tokens.items():
                self._feishu_helper.register_table_group_token(name, token)
                if name == 'default':
                    self._feishu_helper.register_table_group_token('', token)

            for name, token in self.user_config.feishu_root_folder_tokens.items():
                self._feishu_helper.register_root_folder_token(name, token)
                if name == 'default':
                    self._feishu_helper.register_root_folder_token('', token)

        return self._feishu_helper

    def create_app_installer(self, device_id: str, app_info: AppsStaticInfo, update_version: bool, install_options=('-r', '-g', '-t')):
        return AppInstallerForClient(self.app_repo_client, device_id, app_info.package, update_version, install_options)

    def try_update_app_repo_index(self):
        try:
            self.logger.info('Start update app repo index...')
            AppInstallerForClient.update_app_repo_index(self.app_repo_client)
        except Exception as e:
            self.logger.warning(f'Update app repo index failed：{e}')

    def get_device_marker_store(self, device_id: str) -> DeviceMarkerStore:
        assert device_id, 'Param "device_id" must not be none or empty!'
        _exist = self._device_marker_stores.get(device_id)
        if _exist is None:
            _exist = DeviceMarkerStore(device_id)
            self._device_marker_stores[device_id] = _exist
        return _exist

    @property
    def device_marker_store(self) -> DeviceMarkerStore:
        return self.get_device_marker_store(self.device_id)

    @property
    def c_device_marker_store(self) -> DeviceMarkerStore:
        return self.get_device_marker_store(self.c_device_id)

    @property
    def o_device_marker_store(self) -> DeviceMarkerStore:
        return self.get_device_marker_store(self.o_device_id)

    @property
    def user_cache_dir(self):
        return self.scheme_request.cache_dir

    @property
    def app_repo_cache_dir(self):
        return os.path.join(self.user_cache_dir, 'app_repo_cache')

    @property
    def app_repo_cache_lock_manager(self):
        if self._app_repo_cache_lock_manager is None:
            os.makedirs(self.app_repo_cache_dir, exist_ok=True)
            self._app_repo_cache_lock_manager = LazySharedPool(os.path.join(self.app_repo_cache_dir, 'res_lock.db'))
        return self._app_repo_cache_lock_manager

    @property
    def app_repo_client_feishu(self) -> AppRepoClientProtocol:
        if self._app_repo_client_feishu is None:
            _ = self.feishu_app_repo_provider

            app_repo_client_class = None
            try:
                app_repo_client_class = env.load_class('apk_updates.app_repo_client.AppRepoClient')
            except Exception:
                pass

            if not app_repo_client_class:
                raise Exception(
                    'Can not use app_repo_client_feishu due to not found class apk_updates.app_repo_client.AppRepoClient')

            self._app_repo_client_feishu = app_repo_client_class(self.feishu_app_repo_provider,
                                                                 cache_dir=self.app_repo_cache_dir,
                                                                 index_ttl_seconds=180,
                                                                 resource_lock_manager=self.app_repo_cache_lock_manager)
        return self._app_repo_client_feishu

    @property
    def app_repo_client_internal(self) -> AppRepoClientProtocol:
        if self._app_repo_client_internal is None:
            app_repo_client_class = None
            try:
                app_repo_client_class = env.load_class('apk_updates.app_repo_client.AppRepoClient')
            except Exception:
                pass

            if not app_repo_client_class:
                raise Exception(
                    'Can not use app_repo_client_feishu due to not found class apk_updates.app_repo_client.AppRepoClient')

            self._app_repo_client_internal = app_repo_client_class(self.res_provider_app_repo,
                                                                   cache_dir=self.app_repo_cache_dir,
                                                                   index_ttl_seconds=180,
                                                                   resource_lock_manager=self.app_repo_cache_lock_manager)
        return self._app_repo_client_internal

    @property
    def is_publish_mode_odm(self):
        """
        是否为ODM发布模式
        """
        return env.is_publish_mode_odm()

    @property
    def is_publish_mode_overseas(self):
        """
        是否为海外发布模式
        """
        return env.is_publish_mode_overseas()

    @property
    def is_external_publish_mode(self):
        """
        是否为任意外部发布模式
        """
        return env.is_external_publish_mode()

    @property
    def is_transsion_network(self):
        """
        是否处于传音网络（内网）
        """
        if self._is_transsion_network is None:
            self._is_transsion_network = net_utils.is_transsion_network()
        return bool(self._is_transsion_network)

    @property
    def is_transsion_os(self):
        """
        是否是传音测试机
        """
        return self.u2d_helper.phone_os_info.is_transsion_os

    @property
    def is_external_publish_mode_or_outer_network(self):
        """
        是否是ODM发布模式或者处于外网
        """
        return self.is_external_publish_mode or not self.is_transsion_network

    @property
    def app_repo_client(self) -> AppRepoClientProtocol:
        if self.is_external_publish_mode_or_outer_network:
            return self.app_repo_client_feishu
        else:
            return self.app_repo_client_internal

    @property
    def resource_lock_pool(self):
        return env.get_lazy_shared_pool()

    @staticmethod
    def get_resource_lock_pool_by_group_id(group_id: str, db_name: str = 'powertrde_shared_pool.db'):
        return env.get_lazy_shared_pool(group_id, db_name)

    @property
    def feishu_res_provider(self):
        if self._feishu_res_provider is None:
            self._feishu_res_provider = FeishuProvider(self.feishu_helper, '')
        return self._feishu_res_provider

    @property
    def feishu_app_repo_provider(self):
        if self._feishu_app_repo_provider is None:
            self._feishu_app_repo_provider = FeishuProvider(self.feishu_helper, 'app_repo')
        return self._feishu_app_repo_provider

    @property
    def feishu_static_table_loader(self):
        if self._feishu_static_table_loader is None:
            self._feishu_static_table_loader = FeishuStaticTableLoader(self.feishu_helper)
        return self._feishu_static_table_loader

    def _feishu_bind_injections(self, binder: t_inject.Binder):
        binder.bind_to_constructor(FeishuApiHelper, lambda: self.feishu_helper)
        binder.bind_to_constructor(FeishuStaticTableLoader, lambda: self.feishu_static_table_loader)

    @property
    def sn_log_tag(self):
        if self.device_sn:
            if self.c_device_id:
                return f'{self.device_sn},{self.c_device_id}'
            else:
                return self.device_sn
        return ''

    def get_collects_report_dir(self):
        return os.path.join(self.get_session_logs_dir(), 'collects')

    def try_start_txn_status_dispatcher(self):
        pass

    def try_stop_txn_status_dispatcher(self):
        pass


# ---------------------------------------------------------------------------------

def get_scheme_env():
    exist = env.scheme.scheme_env_single_instance
    if not exist:
        exist = SchemeTestEnv.get_instance()
        env.scheme.scheme_env_class = SchemeTestEnv
    return exist

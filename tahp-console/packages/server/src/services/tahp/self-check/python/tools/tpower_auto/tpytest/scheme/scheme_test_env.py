import logging
import os
import sys
import time
from datetime import datetime
from typing import Tuple, List, Set, Dict, Any, Optional

import pytest

from powertrde import env
from powertrde.env import RUNTIME_LOG_DIR
from powertrde.framework.table.feishu_static_table_loader import FeishuStaticTableLoader
from powertrde.framework.tran_logger.device_logger import DeviceLogger
from powertrde.framework.tran_logger.log_device import LocalLogDevice, AdbLogDevice, MultiLogDevice
from powertrde.framework import t_inject
from powertrde.utils import misc_utils
from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends.base_u2d_test_helper import BaseU2DTestHelper
from powertrde.utils.u2_extends.i_has_u2d_helper import IHasU2DHelper, IHasCopilotU2DHelper, IHasObserveU2DHelper
from powertrde.utils.simple_event_center import SimpleEventCenter
from powertrde.utils.u2_extends.u2d_test_helper_factory import U2DTestHelperFactory
from powertrde.utils.wifiadb import wifi_adb_utils
from tpytest.preset_recorder import PresetRecorder
from tpytest.scheme.scheme_task_session_life import SchemeTaskSessionLife
from tpytest.scheme.scheme_user_config import SchemeUserConfig
from tpytest.test_case_counter import TestCaseCounter
from tpytest.u2_serial_provider_factory import U2SerialProviderFactory, CopilotU2SerialProviderFactory
from tpytest_extends.scheme.apps_static_info import AppsStaticInfo


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

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            if env.get_user_runtime_phase() != 'batch_entry':
                cls._instance.try_fill_devices()
        return cls._instance

    @classmethod
    def purge_instance(cls):
        cls._instance = None

    def __init__(self):
        super().__init__()
        if self.option_user_u2d_helper_class_type:
            if issubclass(self.option_user_u2d_helper_class_type, BaseU2DTestHelper):
                # 如果自定义的helper类型是BaseU2DTestHelper的父类，则不生成混合类，直接将其作为最终生成类
                U2DTestHelperFactory.get_instance().default_u2d_test_helper_class_or_factory = self.option_user_u2d_helper_class_type
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
                            f'Not support instantiate test helper type "{self.option_user_u2d_helper_class_type.__name__}" when not import "tpy_aw" module plugin.')

                    # 检查缓存，防止重复检查
                    _cached_os_info = env.get_user_env_arg('device_os_info')
                    if _cached_os_info and env.get_user_env_arg('device_id') == device_id:
                        aw_helper_type = get_aw_helper_type_by_os_info(_cached_os_info)
                    else:
                        aw_helper_type = get_aw_helper_type_by_os_info(detect_os_info(device_id))
                    pre_name = self.option_user_u2d_helper_class_type.__name__.replace('U2DTestHelper', '')
                    post_name = aw_helper_type.__name__
                    return type(f'_{pre_name}{post_name}', (self.option_user_u2d_helper_class_type, aw_helper_type),
                                {})(device_id)

                U2DTestHelperFactory.get_instance().default_u2d_test_helper_class_or_factory = _helper_factory
        self.sys_kwargs = misc_utils.parse_args_to_dict(sys.argv[1:])
        self._event_center = None
        self._preset_record_groups = None
        self._ever_init = False
        self._logger = None
        self._session_id = None
        self._tran_cpu_platform = None
        self._feishu_static_table_loader = None
        self._feishu_helper = None
        self.error_tag_logs = []
        self._user_config = self.option_user_config_class_type.get_instance()
        self._os_version = None

        _override_config_sys_str = self.sys_kwargs.pop('config', '')
        _override_config_dict_from_shared = env.get_scheme_shared_kwargs()
        _override_config_dict_from_sys = self._load_override_user_config(_override_config_sys_str)
        _override_config_dict = {}
        if _override_config_dict_from_shared:
            _override_config_dict.update(_override_config_dict_from_shared)
        if _override_config_dict_from_sys:
            _override_config_dict.update(_override_config_dict_from_sys)
        if _override_config_dict:
            self._user_config.overwrite_config(_override_config_dict)

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

        t_inject.configure(self._bind_injections)
        env.set_user_env_arg('scheme_env', self)
        env.set_user_env_arg('logger', lambda: self.logger)

    def _on_test_counter_send_vm_event(self, counter: TestCaseCounter):
        self.send_test_counter_event(counter)
        self.send_vm_event('case_result_count', (counter.total_count, counter.pass_count, counter.fail_count), counter.name)

    @staticmethod
    def _load_override_user_config(text_to_load: str):
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
    def app_multi_package_keys(self):
        if not self.device_id:
            return self.base_app_multi_package_keys
        return self.get_app_multi_package_keys(self.device_id)

    @property
    def c_app_multi_package_keys(self):
        if not self.c_device_id:
            return self.base_app_multi_package_keys
        return self.get_app_multi_package_keys(self.c_device_id)

    @property
    def base_app_multi_package_keys(self):
        return env.get_user_env_arg('app_multi_package_keys', [])

    def get_app_multi_package_keys(self, device_id: str):
        ret = []
        base = env.get_user_env_arg('app_multi_package_keys', None)
        update = None
        if device_id:
            update = env.get_user_env_arg(f'app_multi_package_keys_{device_id}', None)
        if base:
            ret.extend(base)
        if update:
            for u in update:
                if u not in base:
                    ret.append(u)
        return ret

    def add_multi_package_keys(self, device_id: str, keys: List[str]):
        arg_key = f'app_multi_package_keys_{device_id}' if device_id else 'app_multi_package_keys'
        exist = env.get_user_env_arg(arg_key, None)
        if not exist:
            exist = list(keys)
            env.set_user_env_arg(arg_key, exist)
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
    def user_config(self):
        return self._user_config

    @property
    def has_error_logs(self):
        return bool(self.error_tag_logs)

    def run_collector_for_session(self, data_collector, suffix: str, override_params: Optional[Dict[str, Any]] = None):
        data_collector.run_all(label=self.gen_node_collect_label_name_for_session(suffix), override_params=override_params)

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
        return data_collector_class(data_node_collector_configs, output_dir=self.get_collects_report_dir(), device_id=self.device_id)

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

        # 入口参数传入如环境变量
        env_device_id = os.environ.get('DEVICE_ID')
        if env_device_id and not _device_id:
            _device_id = env_device_id

        env_c_device_id = os.environ.get('C_DEVICE_ID')
        if env_c_device_id and not _c_device_id:
            _c_device_id = env_c_device_id

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

        env.set_user_env_arg('device_info', self.device_info)
        env.set_user_env_arg('device_sn', self.device_sn)
        env.set_user_env_arg('device_id', lambda: self.device_id)
        env.set_user_env_arg('c_device_id', self.c_device_id)
        if self.c_device_id:
            env.set_user_env_arg('c_device_sn', self.c_device_sn)
        env.set_user_env_arg('o_device_id', self.o_device_id)
        if self.o_device_id:
            env.set_user_env_arg('o_device_sn', self.o_device_sn)
        env.set_user_env_arg('device_model', self.device_model)
        env.set_user_env_arg('device_brand', self.device_brand)
        env.set_user_env_arg('device_rom_version', self.device_rom_version)
        env.set_user_env_arg('u2d', lambda: self.u2d)
        env.set_user_env_arg('c_u2d', lambda: self.c_u2d)
        env.set_user_env_arg('o_u2d', lambda: self.o_u2d)
        env.set_user_env_arg('u2d_helper', lambda: self.u2d_helper)
        env.set_user_env_arg('c_u2d_helper', lambda: self.c_u2d_helper)
        env.set_user_env_arg('o_u2d_helper', lambda: self.o_u2d_helper)
        env.set_user_env_arg('tran_cpu_platform', self.tran_cpu_platform)
        if self.device_id:
            env.set_user_env_arg('os_version', self.os_version)
            self._on_device_reinit(self.device_id)
        if self.c_device_id:
            self._on_device_reinit(self.c_device_id)

    def _on_device_reinit(self, target_device_id: str):
        if adb.package_is_installed(target_device_id, 'com.google.android.apps.searchlite'):
            self.add_multi_package_keys(target_device_id, ['Googlego'])
        if not adb.package_is_installed(target_device_id, 'com.transsion.smartmessage'):
            self.add_multi_package_keys(target_device_id, ['GOOGLE_SMS'])
        self.device_info.register_other_info_factory('tran_cpu_platform', lambda _: self.tran_cpu_platform, perform_factory=True)
        try:
            tpy_aw_os_info_entry = env.load_member('tpy_aw.aw_registry.detect_os_info')
            if tpy_aw_os_info_entry:
                device_os_info = tpy_aw_os_info_entry(target_device_id)
                if device_os_info:
                    if target_device_id == self.device_id:
                        env.set_user_env_arg('device_os_info', device_os_info)
                    os_key: str = device_os_info.key
                    if os_key != 'UNKNOWN':
                        append_multi_key_list = []
                        g_pos = os_key.find('_')
                        if g_pos > 0:
                            append_multi_key_list.append(os_key[:g_pos])
                        append_multi_key_list.append(os_key)
                        self.add_multi_package_keys(target_device_id, append_multi_key_list)
        except Exception:
            pass

    def get_device_id(self):
        if self._u2d_helper is None:
            return super().get_device_id()
        return self.u2d_helper.device_id

    @property
    def scheme_request(self):
        return self.user_config.scheme_request

    @property
    def scheme_name(self):
        return self.scheme_request.name

    @property
    def event_center(self):
        if not self._event_center:
            self._event_center = SimpleEventCenter.get_instance()
        return self._event_center

    def send_test_counter_event(self, counter: TestCaseCounter):
        self.event_center.dispatch_event('test_counter_event', counter=counter, tag='cross_process')

    def send_vm_event(self, vm_key: str, vm_value, vm_group: str = ''):
        self.event_center.dispatch_event('scheme_vm_event', group=vm_group, key=vm_key, value=vm_value, tag='cross_process')

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
        return env.get_user_runtime_phase()

    @runtime_phase.setter
    def runtime_phase(self, value: str):
        env.set_user_runtime_phase(value)

    @property
    def debug_modes(self):
        return env.get_user_env_debug_modes()

    @debug_modes.setter
    def debug_modes(self, value):
        env.set_user_env_debug_modes(value)

    @property
    def is_debug(self):
        return env.user_env_is_debug()

    @property
    def is_debug_use_copilot_as_main(self):
        return env.has_user_env_debug_mode('use_copilot_as_main')

    @property
    def is_debug_fallback(self):
        return env.has_user_env_debug_mode('fallback')

    @property
    def is_debug_setup_case(self):
        return env.has_user_env_debug_mode('setup_case')

    @property
    def is_case_phase_or_debug_setup_case(self):
        return self.runtime_phase == 'case' or self.is_debug_setup_case

    @property
    def is_debug_setup_task(self):
        return env.has_user_env_debug_mode('setup_task')

    @property
    def is_case_phase_or_debug_setup_task(self):
        return self.runtime_phase == 'case' or self.is_debug_setup_task

    def has_debug_mode(self, debug_mode_flag: str):
        return debug_mode_flag in self.debug_modes

    @property
    def trunk_flags(self):
        return env.get_user_env_trunk_flags()

    @trunk_flags.setter
    def trunk_flags(self, value):
        env.set_user_env_trunk_flags(value)

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
        self._logger.add_log_handler(logging.INFO, _EventLogHandler())
        if add_error_log_file_handler:
            self._logger.add_log_handler(logging.ERROR,
                                         _ErrorTagFileLogHandler(
                                             os.path.join(self.get_session_logs_dir(), "error.log"),
                                             self.error_tag_logs))
        from powertrde.framework.tran_logger import t_log
        t_log.set_default_logger(self._logger)

    def _gen_logger(self):
        pc_logger = LocalLogDevice(device_name='pc')
        device_logger = AdbLogDevice(device_name='main', device_id=lambda: U2SerialProviderFactory(self), lazy_device_id_call_factory_every_time=True)
        c_device_logger = AdbLogDevice(device_name='copilot', device_id=lambda: CopilotU2SerialProviderFactory(self), lazy_device_id_call_factory_every_time=True)
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

    def get_log_root_dir(self):
        return os.path.join(RUNTIME_LOG_DIR, self.session_id)

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
        return self._tran_cpu_platform

    @property
    def os_version(self):
        if self._os_version is None:
            self._os_version = int(adb.device_android_version(self.device_id))
        return self._os_version

    @property
    def is_tran_cpu_sprd(self):
        return self.tran_cpu_platform == 'sprd'

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
        return os.path.join(self.get_meta_report_dir(), 'collects')


# ---------------------------------------------------------------------------------

def get_scheme_env():
    exist = env.scheme.scheme_env_single_instance
    if not exist:
        exist = SchemeTestEnv.get_instance()
        env.scheme.scheme_env_class = SchemeTestEnv
    return exist

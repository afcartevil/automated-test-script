import json
import os
import sys
from typing import Optional

from powertrde import env
from powertrde.framework.defines import HasHandledException
from powertrde.utils import yaml_utils, json_utils, misc_utils
from powertrde.utils.trde import adb
from tpytest.scheme.scheme_test_env import get_scheme_env
from tpytest.tpypre.pretest_collectors.pretest_collector import PretestCollector
from tpytest.tpypre.pretest_runtime import PretestRuntime
from tpytest.tpytest_runtime import TPytestRuntime


class BatchEntry:
    pretest_runtime_class = PretestRuntime
    pretest_exe_path = ''
    detach_run_executors = True
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.pretest_runtime: Optional[PretestRuntime] = None
        self.env_pc_pretest_collector: Optional[PretestCollector] = None
        self.batch_config_files = []
        self.batch_config_dict = {}
        self.device_configs = []
        self.is_run_pc_pretests = 1
        self.pc_pretest_level = 2
        self._override_config_dict = {}
        self._auto_collect_devices_dict = {}
        env.set_user_runtime_phase('batch_entry')
        tpytest_runtime = TPytestRuntime.get_instance()
        tpytest_runtime.runtime_logger.write_log_file_enabled = False
        self.scheme_env = get_scheme_env()
        self.scheme_env.session_id = tpytest_runtime.runtime_session_id
        self.scheme_env.set_logger(tpytest_runtime.runtime_logger, False)

    @property
    def is_auto_collect_devices(self):
        return self._auto_collect_devices_dict and self._auto_collect_devices_dict.get('test_phone_count')

    def _auto_collect_devices(self, fallback_for_no_devices_config: bool):
        self.device_configs.clear()

        all_phones_sn = []
        phones_sn = []
        copilots_sn = []
        need_phone_count = self._auto_collect_devices_dict.get('test_phone_count', 0)
        need_copilot_count = self._auto_collect_devices_dict.get('copilot_phone_count', 0)
        for sn in adb.adb_devices():
            all_phones_sn.append(sn)
            if adb.is_pointer_location_on(sn):
                copilots_sn.append(sn)
            else:
                phones_sn.append(sn)

        if fallback_for_no_devices_config:
            if copilots_sn:
                if not phones_sn:
                    need_phone_count = 1
                    phones_sn = copilots_sn[:1]
                    if len(copilots_sn) > 1:
                        need_copilot_count = 1
                        copilots_sn = copilots_sn[1:2]
                    else:
                        need_copilot_count = 0
                else:
                    need_copilot_count = 1
                    copilots_sn = copilots_sn[:1]
                    need_phone_count = 1
                    phones_sn = phones_sn[:1]
            else:
                if phones_sn:
                    need_copilot_count = 0
                    need_phone_count = 1
                    phones_sn = phones_sn[:1]
                else:
                    return

        all_phone_count = len(all_phones_sn)
        phone_count = len(phones_sn)
        copilot_count = len(copilots_sn)

        if need_phone_count < 0:
            if need_copilot_count == 0:
                need_phone_count = all_phone_count
                phones_sn = all_phones_sn
            else:
                need_phone_count = phone_count
        elif need_copilot_count == 0:
            if need_phone_count == all_phone_count:
                phones_sn = all_phones_sn
            elif need_phone_count != phone_count:
                raise Exception(f'Need auto collect {need_phone_count} TEST PHONES, but {all_phone_count} phones found: {all_phones_sn}')

        if need_copilot_count < 0:
            need_copilot_count = copilot_count
            if need_copilot_count == 0 and need_copilot_count > 0:
                raise Exception(f'Need auto collect at least one COPILOT PHONE for pair {need_phone_count} test phones, but not copilot phone found!')
        elif need_copilot_count > 0 and need_copilot_count != copilot_count:
            raise Exception(
                f'Need auto collect {need_copilot_count} COPILOT PHONES, but {copilot_count} copilot phones found: {copilots_sn}')

        ratio = need_copilot_count / need_phone_count

        for i in range(need_phone_count):
            d = dict(self._override_config_dict)
            d['device_id'] = phones_sn[i]
            if need_copilot_count > 0:
                c_i = int(i * ratio)
                d['c_device_id'] = copilots_sn[c_i]
            else:
                d['c_device_id'] = 'none'
            self.device_configs.append(d)

    def _resolve_batch_config_files(self):
        self.batch_config_files.clear()

        base_batch_file = os.path.join(self.scheme_env.user_config.config_dir, 'base_batch_config.yaml')
        if os.path.exists(base_batch_file):
            self.batch_config_files.append(base_batch_file)

        _user_batch_config_file = os.path.join(self.scheme_env.user_config.user_cache_config_dir, f'{self.scheme_env.scheme_name}_batch_config.yaml')
        if os.path.exists(_user_batch_config_file):
            self.batch_config_files.append(_user_batch_config_file)
        else:
            os.makedirs(self.scheme_env.user_config.user_cache_config_dir, exist_ok=True)
            misc_utils.write_all_text(_user_batch_config_file,
                                      '# 该placeholder配置仅为占位符，正式配置时，请删除\nplaceholder: placeholder\n')

        if len(sys.argv) > 1:
            _args_batch_config_file = os.path.abspath(os.path.normpath(sys.argv[1]))
            if not os.path.exists(_args_batch_config_file):
                raise FileNotFoundError(f'Not found batch config file: {_args_batch_config_file}')
            self.batch_config_files.append(_args_batch_config_file)

    def _load_batch_config(self):
        if not self.batch_config_files:
            self.scheme_env.logger.info(
                'Not found batch config file input, will fallback to auto use first device and copilot.')
            return
        _batch_config_dict = {}
        for config_file in self.batch_config_files:
            yaml_utils.read_yaml_append_to_dict(config_file, _batch_config_dict)

        self.batch_config_dict = _batch_config_dict
        self.device_configs.clear()
        if self.batch_config_dict:
            self.is_run_pc_pretests = self.batch_config_dict.get('run_pc_pretests', 1)
            self.pc_pretest_level = self.batch_config_dict.get('pc_pretest_level', 2)
            self.detach_run_executors = self.batch_config_dict.get('detach_run_executors', self.detach_run_executors)
            self.case_loading_balance = self.batch_config_dict.get('case_loading_balance', 0)
            self._auto_collect_devices_dict = self.batch_config_dict.get('auto_collect_devices', {})
            if self._auto_collect_devices_dict is None:
                self._auto_collect_devices_dict = {}
            self._override_config_dict = self.union_load_config_dict(self.batch_config_dict.get('override_config'))
            _ori_device_configs = self.batch_config_dict.get('devices', {})
            if _ori_device_configs is None:
                _ori_device_configs = {}
            for sn, device_ori_dict in _ori_device_configs.items():
                _dd = device_ori_dict
                if _dd is None:
                    _dd = {}
                single_override = dict(self._override_config_dict)
                single_override.update(self.union_load_config_dict(_dd.get('config')))
                single_override['device_id'] = str(sn)
                copilot_sn_override = _dd.get('copilot')
                if copilot_sn_override:
                    single_override['c_device_id'] = str(copilot_sn_override)
                self.device_configs.append(single_override)

    @staticmethod
    def union_load_config_dict(config_obj):
        if config_obj is None:
            return {}

        if isinstance(config_obj, dict):
            return config_obj

        if not isinstance(config_obj, str):
            raise Exception("Config must be 'json/yaml file path' or 'yaml dict' or 'json text' or 'dict text'")

        _user_overwrite_config_dict = None
        try:
            if os.path.exists(config_obj):
                try:
                    _user_overwrite_config_dict = yaml_utils.read_yaml(config_obj, ignore_yaml_error=False)
                except Exception:
                    _user_overwrite_config_dict = json_utils.read_json_file(config_obj)
            else:
                try:
                    _user_overwrite_config_dict = json.loads(config_obj)
                except Exception:
                    import ast
                    _user_overwrite_config_dict = ast.literal_eval(config_obj)
        except Exception:
            raise Exception(f'Can not load config from: {config_obj}')
        return _user_overwrite_config_dict

    def _run_pc_pretests(self):
        try:
            self.scheme_env.runtime_phase = 'pc_pretest_collect'
            self.env_pc_pretest_collector.test_scheduler.pre_collect_tests(disable_output=True)
            self.env_pc_pretest_collector.collect(clear_pre_collected_items=False)

            self.scheme_env.runtime_phase = 'pretest'
            self.env_pc_pretest_collector.execute()
            if self.scheme_env.has_error_logs:
                # raise HasHandledException(f'Batch entry pc pretest failed, see detail error logs here: {self.pretest_runtime.scheme_env.get_session_logs_dir()}')
                raise HasHandledException(
                    f'Batch entry pc pretest failed, please see detail error logs')
        except Exception as e:
            print(flush=True)
            if isinstance(e, HasHandledException):
                self.scheme_env.logger.error_with_tag(str(e), ext_event=True)
            else:
                self.scheme_env.logger.exception(str(e))
                self.scheme_env.logger.error_with_tag(str(e), ext_event=True)
            raise

    def _dispatch_executors(self):
        # 只能在Windows下使用纯Detach方式运行代码
        is_windows = (os.name == 'nt')
        is_detach_run_executors = (self.detach_run_executors and is_windows)
        run_method = misc_utils.run_command_detached if is_detach_run_executors else misc_utils.run_command_background
        background_process_list = []
        if not self.device_configs:
            cmd = [sys.executable, self.pretest_exe_path]
            p = run_method(cmd, shell=is_windows)
            if not is_detach_run_executors:
                background_process_list.append(p)
        else:
            device_index = 0
            devices_count = len(self.device_configs)
            for dc in self.device_configs:
                if self.case_loading_balance:
                    dc['case_loading_balance'] = 1
                    dc['device_index'] = device_index
                    dc['total_devices'] = devices_count
                cmd = [sys.executable, self.pretest_exe_path, f'--config={str(dc)}']
                p = run_method(cmd, shell=is_windows)
                if not is_detach_run_executors:
                    background_process_list.append(p)
                device_index += 1

        if not is_detach_run_executors:
            for proc in background_process_list:
                proc.wait()

    def start(self):
        if not self.pretest_exe_path:
            raise Exception('You must set pretest_exe_path in your batch entry child class!')
        self._resolve_batch_config_files()
        self._load_batch_config()

        if self.is_auto_collect_devices:
            self._auto_collect_devices(False)
        elif not self.device_configs:
            self.scheme_env.logger.warning(
                f"※ No 'devices' or 'auto_collect_devices' config found in Batch Config, will fallback to first found adb device to test.")
            self._auto_collect_devices(True)

        if self.device_configs:
            def _internal():
                ret = []
                for i in self.device_configs:
                    sn = i['device_id']
                    c_sn = i.get('c_device_id')
                    if c_sn and c_sn.lower() != 'none':
                        ret.append((sn, c_sn))
                    else:
                        ret.append(sn)
                return ret
            self.scheme_env.logger.info(f'※ Batch will test these phones: {_internal()}')
        else:
            self.scheme_env.logger.warning(f"※ Not found any adb devices for testing, will only run some PC pretest if needed.")

        if self.is_run_pc_pretests:
            self.pretest_runtime = self.pretest_runtime_class.get_instance()
            self.scheme_env.user_config.pretest_level = self.pc_pretest_level
            self.env_pc_pretest_collector = PretestCollector('env.pc.collector', self.pretest_runtime, ['env.pc'])
            self.scheme_env.logger.info(
                f'※ --------- [{self.scheme_env.scheme_name.upper()} BEGIN] Batch entry PC Pretest start! ---------')
            self._run_pc_pretests()
            self.scheme_env.logger.info(
                f'※ --------- [{self.scheme_env.scheme_name.upper()} END] Batch entry PC Pretest pass! ---------')
        self.scheme_env.logger.info(
            f'※ --------- [{self.scheme_env.scheme_name.upper()} Dispatch BEGIN] Batch will dispatch tests to devices! ---------')
        self._dispatch_executors()
        self.scheme_env.logger.info(
            f'※ --------- [{self.scheme_env.scheme_name.upper()} Dispatch END] Batch dispatch tests FINISHED! ---------')

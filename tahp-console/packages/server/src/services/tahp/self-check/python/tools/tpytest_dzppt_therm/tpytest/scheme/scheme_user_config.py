import copy
import os.path
import shutil
from threading import Lock
from typing import List, Union, Mapping, Optional

from powertrde import env
from powertrde.env import RUNTIME_LOG_DIR
from powertrde.utils import yaml_utils, misc_utils, confuse_utils
from powertrde.utils.u2_extends.base_u2d_test_helper import BaseU2DTestHelper
from tpytest.resource_provider import ResourceProviderFactory
from tpytest.case_original_request import CaseOriginalRequest
from tpytest.task_session_config import TaskSessionConfig


class SchemeUserConfig(TaskSessionConfig):
    option_accounts_bundle_provider = None

    _instance = None

    _builder_configs = None

    _builder_locker = Lock()

    @classmethod
    def create(cls, config_path: Union[None, str, os.PathLike] = None, scheme_request: Optional[env.Scheme] = None):
        with SchemeUserConfig._builder_locker:
            try:
                SchemeUserConfig._builder_configs = (config_path, scheme_request)
                return cls()
            finally:
                SchemeUserConfig._builder_configs = None

    def __init__(self):
        super().__init__()

        _builder_config_path = None
        _builder_scheme_request = None

        try:
            _builder_config_path = SchemeUserConfig._builder_configs[0]
            _builder_scheme_request = SchemeUserConfig._builder_configs[1]
        except Exception:
            pass

        self.scheme_request = _builder_scheme_request or env.scheme
        self._configured_config_dict = {}
        self._scheme_marks_dict = None
        self._run_mode = ''
        self.debug_modes = set()
        self.trunk_flags = set()
        self.case_set = ''
        self.cases: List[CaseOriginalRequest] = []
        self.run_pc_pretests = 0
        self.pretest_level = 2
        self.app_pretest = -1
        self.pretest_skip_pass_hours = 0.0
        self.test_app_install_check_flag = 11
        self.back_app_install_check_flag = 3
        self.copilot_app_install_check_flag = 9
        self.test_loop = 1
        self.small_test_loop = 1
        self.retry = 0
        self.app_multi_package_keys = []
        self.res_provider_path = ''
        self.res_provider_username = ''
        self.res_provider_password = ''
        self.logs_uploader_path = ''
        self.logs_uploader_username = ''
        self.logs_uploader_password = ''
        self._accounts = {}
        self._c_accounts = {}
        self.back_apps: List[str] = []
        self.test_region = 'CN'

        # For 用例负载均衡
        self.case_loading_balance = False
        self.device_index = 0
        self.total_devices = 1

        self._single_case_path = ''
        self._smart_single_case_path_dict = {}
        self._smart_utp_full_case_paths_dict = {}

        # PowerMonitor的配对编号
        self.powermonitor_num = ''

        self.task_id = ''

        self._res_provider = None
        self._res_provider_app_repo = None
        self._logs_uploader = None
        self._log_parent_dir = ''
        self._log_dir_name = ''
        self._log_dir_path = ''

        self.txn_status_server_port = 0

        self.post_fill_kwargs: Optional[dict] = None
        self.post_filled_dict = {}

        self.config_path = os.path.join(self.config_dir, 'base_config.yaml') if _builder_config_path is None and self.scheme_request.name else _builder_config_path
        self.load_scheme_config()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_skip_pretest(self):
        return self.pretest_level < 0 or self.is_run_mode_single or self.is_run_mode_pretest

    @property
    def configured_config_dict(self):
        return self._configured_config_dict

    @property
    def config_dir(self):
        return self.scheme_request.config_dir

    @property
    def user_cache_config_dir(self):
        return self.scheme_request.cache_dir

    @property
    def user_cache_scheme_marks_dir(self):
        return os.path.join(self.user_cache_config_dir, 'scheme_marks')

    @property
    def scheme_name(self):
        return self.scheme_request.name

    @property
    def user_cache_scheme_mark_file(self):
        return os.path.join(self.user_cache_scheme_marks_dir, f'{self.scheme_name}_scheme_mark.yaml')

    @property
    def scheme_mark_dict(self):
        if self._scheme_marks_dict is None:
            self._scheme_marks_dict = yaml_utils.read_yaml(self.user_cache_scheme_mark_file)
            if not isinstance(self._scheme_marks_dict, dict):
                self._scheme_marks_dict = {'placeholder': 0}
        return self._scheme_marks_dict

    def save_last_session_log_root_dir(self, last_session_log_root_dir: str):
        self.set_scheme_mark('last_session_log_root_dir', last_session_log_root_dir, save_file=True)

    def get_last_session_log_root_dir(self):
        return self.get_scheme_mark('last_session_log_root_dir')

    def set_scheme_mark(self, key: str, value, save_file=False):
        exists_value = self.scheme_mark_dict.get(key)
        if exists_value == value:
            return
        self.scheme_mark_dict[key] = value
        if save_file:
            self.save_scheme_mark_dict()

    def get_scheme_mark(self, key: str, default_value=None):
        return self.scheme_mark_dict.get(key, default_value)

    def save_scheme_mark_dict(self):
        yaml_utils.write_yaml(self.scheme_mark_dict, self.user_cache_scheme_mark_file)

    @property
    def user_cache_config_file(self):
        return os.path.join(self.user_cache_config_dir, f'{self.scheme_name}_user_config.yaml')

    @property
    def external_overwrite_config_file(self):
        return os.path.join(self.config_dir, f'external_overwrite.yaml')

    def copy_user_cache_config_to(self, to_dir: str, filename: str):
        os.makedirs(to_dir, exist_ok=True)
        shutil.copy(self.user_cache_config_file, os.path.join(to_dir, filename))

    @property
    def is_run_mode_utp(self):
        return 'utp' in self.run_mode.split('/')

    @property
    def is_run_mode_pretest(self):
        return 'pretest' in self.run_mode.split('/')

    @property
    def is_run_mode_pretest_by_cases(self):
        return 'pretest_by_cases' in self.run_mode.split('/')

    @property
    def utp_report_file(self):
        filepath = self._configured_config_dict.get('utp_report_file', '')
        if filepath and not filepath.lower().endswith('.json'):
            filepath = os.path.join(filepath, 'report.json')
        return filepath

    @property
    def utp_report_dir(self):
        dir_path = self._configured_config_dict.get('utp_report_file', '')
        return dir_path

    @property
    def is_overseas_test(self):
        return self.test_region and self.test_region != 'CN'

    @property
    def is_run_mode_single(self):
        return 'single' in self.run_mode.split('/')

    @property
    def is_run_mode_utp_single(self):
        return self.is_run_mode_utp and self.is_run_mode_single

    @property
    def is_run_mode_utp_full(self):
        return self.is_run_mode_utp and 'full' in self.run_mode.split('/')

    @property
    def utp_single_tcid(self):
        return self.config_dict.get('tcid', '')

    @property
    def single_case_path(self):
        return self._single_case_path

    @property
    def smart_single_case_path(self):
        """带自动搜索的single_case_path"""
        s = self.single_case_path
        if '::' not in s:
            if not s:
                if self.utp_single_tcid:
                    s = 'test_' + self.utp_single_tcid
                else:
                    return s
        else:
            return s

        exist = self._smart_single_case_path_dict.get(s)
        if exist is None:
            from tpytest.tpytest_scheduler import TPytestTestScheduler
            search_ret = TPytestTestScheduler.find_first_test_node(self.scheme_request.scheme_env_class_name_parent_path, s)
            if search_ret:
                exist = search_ret
            else:
                exist = ''
            self._smart_single_case_path_dict[s] = exist
        return exist

    def _convert_case_id(self, case_id: str) -> str:
        """默认的case_id转换，子类可以重写"""
        return f'test_{case_id}'

    @property
    def smart_utp_full_case_paths(self):
        """带自动搜索的utp_full_case_paths"""
        cases = self.cases
        if not cases:
            return []

        tcids = [case.case_id for case in cases]
        cache_key = tuple(tcids)
        cached_requests = self._smart_utp_full_case_paths_dict.get(cache_key)
        if cached_requests is None:
            from tpytest.case_original_request import CaseOriginalRequest
            smart_requests = []
            for case in cases:
                case_ori_request = CaseOriginalRequest()
                # 可以在各自的config里重写这个方法来匹配case_id
                case_ori_request.case_id = self._convert_case_id(case.case_id)
                # case_ori_request.case_id = f'test_{case.case_id}'
                case_ori_request.loop = case.loop if hasattr(case, 'loop') else self.small_test_loop
                case_ori_request.retry = case.retry if hasattr(case, 'retry') else self.retry
                case_ori_request.group_loop = case.group_loop if hasattr(case, 'group_loop') else 1
                smart_requests.append(case_ori_request)
            self._smart_utp_full_case_paths_dict[cache_key] = smart_requests
            cached_requests = smart_requests
        return cached_requests

    def load_scheme_config(self):
        self.config_dict.clear()
        if self.config_path:
            if os.path.exists(self.config_path):
                yaml_utils.read_yaml_append_to_dict(self.config_path, self.config_dict)
            user_cache_config_file = self.user_cache_config_file
            if not os.path.exists(user_cache_config_file):
                os.makedirs(self.user_cache_config_dir, exist_ok=True)
                misc_utils.write_all_text(user_cache_config_file,
                                          '# 该placeholder配置仅为占位符，正式配置时，请删除\nplaceholder: placeholder\n')
            yaml_utils.read_yaml_append_to_dict(user_cache_config_file, self.config_dict)

            # 如果是对外模式，需要额外加载一个"external_overwrite.yaml"文件
            if env.is_external_publish_mode() and os.path.exists(self.external_overwrite_config_file):
                yaml_utils.read_yaml_append_to_dict(self.external_overwrite_config_file, self.config_dict)

        _defused_dict = confuse_utils.defuse_data(self.config_dict)
        self.config_dict.update(_defused_dict)
        self._fill_fields()
        self._sync_to_env()

    def _load_scheme_release_version(self):
        _version_file = os.path.join(env.PROJ_DIR, f'{self.scheme_name}_version.yaml')
        _version_text = None
        try:
            config = yaml_utils.read_yaml(_version_file)
            _version_text = config['version']
            # _version_text = misc_utils.read_all_text(_version_file).strip()
        except Exception:
            pass
        if _version_text:
            self.configured_config_dict['scheme_release_version'] = _version_text

    def overwrite_config(self, overwrite_config_file_or_dict: Union[str, os.PathLike, dict]):
        if isinstance(overwrite_config_file_or_dict, dict):
            self.override_config_dict.update(overwrite_config_file_or_dict)
        else:
            yaml_utils.read_yaml_append_to_dict(overwrite_config_file_or_dict, self.override_config_dict)
        d = self.override_config_dict.get('device_id')
        if isinstance(d, int):
            self.override_config_dict['device_id'] = str(d)
        c_d = self.override_config_dict.get('c_device_id')
        if isinstance(c_d, int):
            self.override_config_dict['c_device_id'] = str(c_d)

        _defused_dict = confuse_utils.defuse_data(self.override_config_dict)
        self.override_config_dict.update(_defused_dict)

        self.config_dict.update(self.override_config_dict)
        self._fill_fields()
        self._sync_to_env()

    def write_config_dict_to_file(self, filepath: Union[str, os.PathLike], runtime_variant_keys: List[str]):
        d = dict(self.configured_config_dict)

        for _k in ('feishu', 'logs_uploader_password', 'logs_uploader_username', 'res_provider_password', 'res_provider_username', 'accounts', 'c_accounts'):
            _v = d.pop(_k, None)
            if _v is not None:
                _confused_v = confuse_utils.confuse_data(_v)
                d[_k] = _confused_v
        if runtime_variant_keys:
            d['runtime_variant_keys'] = runtime_variant_keys
        try:
            _dd: dict = d['post_filled_dict']
            if 'extracted_accounts' in _dd:
                _dd = dict(_dd)
                del _dd['extracted_accounts']
                d['post_filled_dict'] = _dd
        except Exception:
            pass
        yaml_utils.write_yaml(d, filepath, ignore_yaml_error=False, confuse_file=env.is_publish_mode_odm())

    def _resolve_text_or_text_method_result(self, text: str):
        if not text:
            return text
        method = None
        try:
            method = getattr(self, text)
        except Exception:
            pass
        if callable(method):
            return method()
        return text

    def magic_update_dict(self, ori_dict, new_dict):
        for key, value in new_dict.items():
            if key.startswith("magic_"):
                target = key[6:]
                if target in ori_dict and isinstance(ori_dict[target], Mapping) and isinstance(value, Mapping):
                    self.magic_update_dict(ori_dict[target], value)
                elif target in ori_dict and isinstance(ori_dict[target], list) and isinstance(value, list):
                    ori_dict[target].extend(value)
                else:
                    ori_dict[target] = copy.deepcopy(value)
            else:
                ori_dict[key] = copy.deepcopy(value)
        return ori_dict

    def _cases_import(self, case_set_single_path, _finally_value_dict, _visited_case_files):
        parts = case_set_single_path.split("/")
        if len(parts) > 1:
            base_config_dir = os.path.join(self.config_dir, *parts[:-1])
            case_name = parts[-1]
        else:
            base_config_dir = self.config_dir
            case_name = case_set_single_path

        # 查找 yaml 文件
        case_set_config_file = os.path.join(base_config_dir, f"case_set_{case_name}.yaml")
        if not os.path.exists(case_set_config_file):
            case_set_config_file = os.path.join(base_config_dir, f"{case_name}.yaml")
            if not os.path.exists(case_set_config_file):
                case_set_config_file = os.path.join(env.PROJ_DIR, f"{case_name}.yaml")
            if not os.path.exists(case_set_config_file):
                raise FileNotFoundError(f"Case file not found for {case_set_single_path}")

        abs_file = os.path.abspath(case_set_config_file)
        if abs_file in _visited_case_files:
            raise ValueError(f"{abs_file} 造成循环导入，请检查配置文件")

        _visited_case_files.add(abs_file)
        # 读取 yaml
        _cases_set_dict = yaml_utils.read_yaml(case_set_config_file, False)
        if not _cases_set_dict:
            # 返回空 dict 表示此文件无内容
            return {}

        assert isinstance(_cases_set_dict, dict), "The case set must be a dict-like yaml file!"

        # 把 import 弄出来，先处理每个被 import 的子文件，**每个子文件独立合并**
        import_list = _cases_set_dict.pop("import", [])

        # this_file_acc 用来表示“当前文件（含其imports）合并后的结果”
        this_file_acc = {}

        if import_list:
            for sub_case in import_list:
                # 递归获取子模块自己的合并结果（一个 dict）
                sub_dict = self._cases_import(sub_case, {}, _visited_case_files)  # 每个子 import 用独立的空 accumulator
                if not sub_dict:
                    continue
                # **关键**：把子模块的每个顶层 key 当作 magic_key 合并到 this_file_acc，
                # 这样不同子模块之间不会用普通 key 相互覆盖（例如某个子模块的 'cases' 不会覆盖其他子模块的 'magic_cases'）
                wrapped = {}
                for k, v in sub_dict.items():
                    wrapped[f"magic_{k}"] = v
                # 用现有的 magic_update_dict 合并 wrapped 到 this_file_acc（增量、递归、list extend）
                self.magic_update_dict(this_file_acc, wrapped)

        # 再把当前文件本身合并到 this_file_acc（当前文件应当覆盖/增量修改 imports 的基底）
        # 原来的语义：magic_update_dict(_finally_value_dict, _cases_set_dict)
        self.magic_update_dict(this_file_acc, _cases_set_dict)

        # 最后把 this_file_acc 合并到传入的 _finally_value_dict（就地修改外部传入的 accumulator）
        self.magic_update_dict(_finally_value_dict, this_file_acc)

        # 返回当前文件合并后的结果（供父级调用/上层合并使用）
        return this_file_acc

    def _fill_fields(self):
        super()._fill_fields()
        self.config_dict.update({'task_id': self.task_id})
        config_dict = self.config_dict

        self.case_set = config_dict.get('case_set', '')
        _finally_value_dict = {}

        self._cases_import(self.case_set, _finally_value_dict, set())

        if _finally_value_dict:
            # 如果是 case set 切入，需要复制一份新的字典作为 configured_config_dict
            config_dict = copy.deepcopy(self.config_dict)

            # 将_finally_value_dict解密后，使用魔术更新到复制后的新字典
            self.magic_update_dict(config_dict, confuse_utils.defuse_data(_finally_value_dict))

            # 最后切入 override config，其优先级比 case set 更高
            config_dict.update(self.override_config_dict)

        self._configured_config_dict = config_dict

        self._run_mode = config_dict.get('run_mode', '')

        self.run_pc_pretests = config_dict.get('run_pc_pretests', 1)

        self.pretest_level = config_dict.get('pretest_level', 2)

        self.app_pretest = config_dict.get('app_pretest', -1)

        self.test_app_install_check_flag = config_dict.get('test_app_install_check_flag', 11)

        self.back_app_install_check_flag = config_dict.get('back_app_install_check_flag', 3)

        self.copilot_app_install_check_flag = config_dict.get('copilot_app_install_check_flag', 9)

        self.pretest_skip_pass_hours = config_dict.get('pretest_skip_pass_hours', 0)

        self.case_loading_balance = config_dict.get('case_loading_balance', False)
        self.device_index = config_dict.get('device_index', 0)
        self.total_devices = config_dict.get('total_devices', 1)

        self.test_region = config_dict.get('test_region', 'CN')

        debug_modes_list = config_dict.get('debug_modes', [])
        self.debug_modes = set(debug_modes_list)
        try:
            self.debug_modes.remove('placeholder')
        except KeyError:
            pass

        trunk_flags_list = config_dict.get('trunk_flags', [])
        self.trunk_flags = set(trunk_flags_list)
        try:
            self.trunk_flags.remove('placeholder')
        except KeyError:
            pass

        self._accounts = config_dict.get('accounts', {})
        self._c_accounts = config_dict.get('c_accounts', {})
        self.feishu = config_dict.get('feishu', {})
        self.back_apps = config_dict.get('back_apps', [])
        try:
            self.back_apps.remove('placeholder')
        except ValueError:
            pass

        self.test_loop = config_dict.get('test_loop', 1)
        self.small_test_loop = config_dict.get('small_test_loop', 1)
        self.retry = config_dict.get('retry', 0)
        self.task_id = config_dict.get('task_id', '')

        self.powermonitor_num = config_dict.get('powermonitor_num', '')

        self.txn_status_server_port = config_dict.get('txn_status_server_port', 0)

        self._single_case_path = config_dict.get('single_case_path', '')

        _cases = config_dict.get('cases')
        _utp_tcids = config_dict.get('utp_tcids', [])

        if _utp_tcids:
            assert isinstance(_utp_tcids, list), 'The SCHEME CONFIG utp_tcids filed must be type of list!'
            self.cases = CaseOriginalRequest.parse_lines(_utp_tcids, self.small_test_loop, self.retry, self.test_case_timeout)
        elif _cases:
            assert isinstance(_cases, list), 'The SCHEME CONFIG cases filed must be type of list!'
            self.cases = CaseOriginalRequest.parse_lines(_cases, self.small_test_loop, self.retry, self.test_case_timeout)
        else:
            self.cases = []

        self.app_multi_package_keys = config_dict.get('app_multi_package_keys', [])
        _runtime_variant_keys = config_dict.get('runtime_variant_keys', None)
        if isinstance(_runtime_variant_keys, (list, tuple)):
            for _rvk in _runtime_variant_keys:
                if _rvk not in self.app_multi_package_keys:
                    self.app_multi_package_keys.append(_rvk)

        self.res_provider_path = self._resolve_text_or_text_method_result(config_dict.get('res_provider_path', ''))
        if self.res_provider_path:
            self.res_provider_username = self._resolve_text_or_text_method_result(
                config_dict.get('res_provider_username', ''))
            if not self.res_provider_username:
                self.res_provider_username = 'monkeytest'
            elif self.res_provider_username == '-':
                self.res_provider_username = ''
            self.res_provider_password = self._resolve_text_or_text_method_result(
                config_dict.get('res_provider_password', ''))
            if not self.res_provider_password:
                self.res_provider_password = 'Monkey123'
            elif self.res_provider_password == '-':
                self.res_provider_password = ''
        else:
            self.res_provider_username = ''
            self.res_provider_password = ''

        self.logs_uploader_path = self._resolve_text_or_text_method_result(config_dict.get('logs_uploader_path', ''))
        if self.logs_uploader_path:
            self.logs_uploader_username = self._resolve_text_or_text_method_result(
                config_dict.get('logs_uploader_username', ''))
            if not self.logs_uploader_username:
                self.logs_uploader_username = 'monkeytest'
            elif self.logs_uploader_username == '-':
                self.logs_uploader_username = ''
            self.logs_uploader_password = self._resolve_text_or_text_method_result(
                config_dict.get('logs_uploader_password', ''))
            if not self.logs_uploader_password:
                self.logs_uploader_password = 'Monkey123'
            elif self.logs_uploader_password == '-':
                self.logs_uploader_password = ''
        else:
            self.logs_uploader_username = ''
            self.logs_uploader_password = ''

        self._log_parent_dir = config_dict.get('log_parent_dir', '')
        self._log_dir_name = config_dict.get('log_dir_name', '')
        self._log_dir_path = config_dict.get('log_dir', '')

        self._load_scheme_release_version()

        self._fields_post_merge()

        if self.post_fill_kwargs is not None:
            self._on_post_fill()

    def _fields_post_merge(self):
        # 处理single_case_path竖线前的模式与run_mode字段合并
        if '|' in self._single_case_path:
            _ss = self._single_case_path.split('|', maxsplit=2)
            if self._run_mode:
                self._run_mode += f'/{_ss[0]}'
            else:
                self._run_mode = _ss[0]
            self._single_case_path = _ss[1]

        # 处理utp/single测试模式下的日志保存路径
        if self.is_run_mode_utp_single and self.utp_report_dir:
            self._log_dir_path = os.path.join(self.utp_report_dir, 'logs')

    def post_fill(self, filled_kwargs: dict):
        self.post_fill_kwargs = dict(filled_kwargs)
        self._on_post_fill()

    def _on_post_fill(self):
        self._configured_config_dict['post_fill_kwargs'] = self.post_fill_kwargs
        self.post_filled_dict.clear()
        self._configured_config_dict['post_filled_dict'] = self.post_filled_dict
        _post_fill_passed_device_id = self.post_fill_passed_device_id
        if _post_fill_passed_device_id:
            self._try_load_accounts_bundle('accounts_bundle', _post_fill_passed_device_id)
        _post_fill_passed_c_device_id = self.post_fill_passed_c_device_id
        if _post_fill_passed_c_device_id:
            self._try_load_accounts_bundle('c_accounts_bundle', _post_fill_passed_c_device_id)

    @property
    def post_fill_passed_device_id(self):
        return self.post_fill_kwargs.get('device_id', '') if self.post_fill_kwargs else ''

    @property
    def post_fill_passed_c_device_id(self):
        return self.post_fill_kwargs.get('c_device_id', '') if self.post_fill_kwargs else ''

    @property
    def _extracted_accounts(self):
        try:
            return self._configured_config_dict['post_filled_dict']['extracted_accounts']
        except Exception:
            return None

    @property
    def _extracted_c_accounts(self):
        try:
            return self._configured_config_dict['post_filled_dict']['extracted_c_accounts']
        except Exception:
            return None

    @property
    def accounts(self):
        _e_a = self._extracted_accounts
        return _e_a if _e_a else self._accounts

    @property
    def c_accounts(self):
        _e_a = self._extracted_c_accounts
        return _e_a if _e_a else self._c_accounts

    @property
    def run_mode(self):
        return self._run_mode

    def _try_load_accounts_bundle(self, _accounts_bundle_key_name: str, device_id: str):
        _accounts_bundle: Optional[str] = self.configured_config_dict.get(_accounts_bundle_key_name)
        if not _accounts_bundle:
            return

        _accounts_type_name = _accounts_bundle_key_name[:-7]
        _base_accounts = self.configured_config_dict.get(_accounts_type_name)
        if not _base_accounts:
            _base_accounts = {}
        else:
            _base_accounts = copy.deepcopy(_base_accounts)

        assert SchemeUserConfig.option_accounts_bundle_provider, 'You must set the option_accounts_bundle_provider before configuring the accounts_bundle!'

        _online_accounts = None
        if _accounts_bundle == 'auto':
            _accounts_bundle = device_id
            try:
                _online_accounts = SchemeUserConfig.option_accounts_bundle_provider(_accounts_bundle)
            except Exception:
                pass
            if not _online_accounts:
                try:
                    _accounts_bundle = BaseU2DTestHelper.static_get_user_defined_device_name_account_bundles(device_id)[0]
                    _online_accounts = SchemeUserConfig.option_accounts_bundle_provider(_accounts_bundle)
                except Exception:
                    pass
                self.post_filled_dict[f'extracted_{_accounts_bundle_key_name}_method'] = 'device_name'
            else:
                self.post_filled_dict[f'extracted_{_accounts_bundle_key_name}_method'] = 'device_sn'
        else:
            _online_accounts = SchemeUserConfig.option_accounts_bundle_provider(_accounts_bundle)
            self.post_filled_dict[f'extracted_{_accounts_bundle_key_name}_method'] = 'specific'

        self.post_filled_dict[f'extracted_{_accounts_bundle_key_name}'] = _accounts_bundle
        if _online_accounts is None:
            _online_accounts = {}
        _need_add_pairs = {}
        for _k, _v in _base_accounts.items():
            if _k in _online_accounts:
                _ov = _online_accounts.get(_k)
                if isinstance(_v, dict) and isinstance(_ov, dict):
                    _v.update(_ov)
        for _ok, _ov in _online_accounts.items():
            if _ok not in _base_accounts:
                _base_accounts[_ok] = _ov
        self.post_filled_dict[f'extracted_{_accounts_type_name}'] = _base_accounts

    def _sync_to_env(self):
        if self.scheme_request.name:
            self.scheme_request.set_user_env_debug_modes(self.debug_modes)
            self.scheme_request.set_user_env_trunk_flags(self.trunk_flags)

            new_keys = list(self.app_multi_package_keys)
            if self.test_region and self.test_region not in new_keys:
                new_keys.append(self.test_region)
            self.scheme_request.set_user_env_arg('app_multi_package_keys', new_keys)

    @property
    def log_parent_dir(self):
        return (os.path.dirname(self._log_dir_path) if self._log_dir_path else self._log_parent_dir) or RUNTIME_LOG_DIR

    @property
    def user_defined_log_dir_name(self):
        return os.path.basename(self._log_dir_path) if self._log_dir_path else self._log_dir_name

    @property
    def user_defined_log_dir_path(self):
        return self._log_dir_path if self._log_dir_path else (os.path.join(self.log_parent_dir, self._log_dir_name) if self._log_dir_name else '')

    @log_parent_dir.setter
    def log_parent_dir(self, value: str):
        self._log_parent_dir = value
        self.override_config_dict['log_parent_dir'] = value
        self._configured_config_dict['log_parent_dir'] = value

    @property
    def accounts_bundle(self):
        return self._configured_config_dict.get('accounts_bundle', '')

    @property
    def c_accounts_bundle(self):
        return self._configured_config_dict.get('c_accounts_bundle', '')

    @property
    def res_provider(self):
        if not self._res_provider:
            pp = self.res_provider_path
            if not pp:
                raise Exception('res_provider_path 未配置')
            pp_u = self.res_provider_username
            # if not pp_u:
            #     raise Exception('res_provider_username 未配置')
            pp_p = self.res_provider_password
            # if not pp_p:
            #     raise Exception('res_provider_password 未配置')
            res_provider = ResourceProviderFactory.create(pp, username=pp_u, password=pp_p)
            if not res_provider.test_connection():
                raise Exception(f'资源提供者连接失败：{pp}')
            self._res_provider = res_provider
        return self._res_provider

    @property
    def res_provider_app_repo(self):
        if not self._res_provider_app_repo:
            pp = self.res_provider_path
            if not pp:
                raise Exception('res_provider_path 未配置')
            pp_u = self.res_provider_username
            # if not pp_u:
            #     raise Exception('res_provider_username 未配置')
            pp_p = self.res_provider_password
            # if not pp_p:
            #     raise Exception('res_provider_password 未配置')
            if '\\' in pp:
                pp = pp.rstrip('\\') + '\\app_repo'
            else:
                pp = pp.rstrip('/') + '/app_repo'
            res_provider = ResourceProviderFactory.create(pp, username=pp_u, password=pp_p)
            if not res_provider.test_connection():
                raise Exception(f'资源提供者连接失败：{pp}')
            self._res_provider_app_repo = res_provider
        return self._res_provider_app_repo

    @property
    def logs_uploader(self):
        if not self._logs_uploader:
            pp = self.logs_uploader_path
            if not pp:
                raise Exception('logs_uploader_path 未配置')
            pp_u = self.logs_uploader_username
            # if not pp_u:
            #     raise Exception('logs_uploader_username 未配置')
            pp_p = self.logs_uploader_password
            # if not pp_p:
            #     raise Exception('logs_uploader_password 未配置')
            logs_uploader = ResourceProviderFactory.create(pp, username=pp_u, password=pp_p)
            if not logs_uploader.test_connection():
                raise Exception(f'Log上传者连接失败：{pp}')
            self._logs_uploader = logs_uploader
        return self._logs_uploader

    @property
    def scheme_release_version(self):
        return self._configured_config_dict.get('scheme_release_version', '0.0.0')

    @property
    def pretest_case_timeout(self):
        return self._configured_config_dict.get('pretest_case_timeout', 0)

    @property
    def notify_group_name(self):
        return self._configured_config_dict.get('notify_group_name', "")

    @property
    def notify_user_email(self):
        return self._configured_config_dict.get('notify_user_email', "")

    @property
    def test_case_timeout(self):
        return self._configured_config_dict.get('test_case_timeout', 0)

    @property
    def feishu_app_id(self):
        return self.feishu.get('feishu_app_id', '')

    @property
    def feishu_app_secret(self):
        return self.feishu.get('feishu_app_secret') or 'nTOW0ZolI9RssVN8gact5eVcLVtljJC2'

    @property
    def feishu_root_folder_tokens(self):
        return self.feishu.get('feishu_root_folder_tokens', {})

    @property
    def feishu_root_table_tokens(self):
        return self.feishu.get('feishu_root_table_tokens', {})

    @property
    def feishu_default_root_folder_token(self):
        return self.feishu_root_folder_tokens.get('default', '')

    @property
    def feishu_default_root_table_token(self):
        return self.feishu_root_table_tokens.get('default', '')

    def get_feishu_root_folder_token(self, root_folder_name: str):
        return self.feishu_root_folder_tokens.get(root_folder_name, '')

    def get_feishu_root_table_token(self, root_table_name: str):
        return self.feishu_root_table_tokens.get(root_table_name, '')

    @staticmethod
    def load_collect_node_configs(collect_node_request_dict_list: List[dict]):
        ret_configs = []
        for ori_d in collect_node_request_dict_list:
            d = dict(ori_d)
            n = d.pop('name', None)
            assert n, 'The collect node name must not be empty!'
            t = d.pop('type', 'android_cmd')
            ret_d = {'type': t, 'name': n, 'params': d}
            ret_configs.append(ret_d)
        return ret_configs

    @property
    def is_enable_app_pretest(self):
        if self.app_pretest == 0 or self.pretest_level < 0:
            return False
        return self.pretest_level >= 2 or self.app_pretest == 1

    @property
    def retest_target(self):
        return self._configured_config_dict.get('retest_target')

    @property
    def is_retest(self):
        return bool(self.retest_target)

    def is_check_apps_install(self, is_copilot: bool, is_background_app: bool, exclude_flag: int = 0, include_flag: int = 0):
        _flag = self.copilot_app_install_check_flag if is_copilot else (self.back_app_install_check_flag if is_background_app else self.test_app_install_check_flag)
        return ((_flag | include_flag) & (~exclude_flag) & 7) != 0

    def is_check_to_install_apps(self, is_copilot: bool, is_background_app: bool, exclude_flag: int = 0, include_flag: int = 0):
        _flag = self.copilot_app_install_check_flag if is_copilot else (self.back_app_install_check_flag if is_background_app else self.test_app_install_check_flag)
        return ((_flag | include_flag) & (~exclude_flag) & 6) != 0

    def is_check_to_update_apps(self, is_copilot: bool, is_background_app: bool, exclude_flag: int = 0, include_flag: int = 0):
        _flag = self.copilot_app_install_check_flag if is_copilot else (self.back_app_install_check_flag if is_background_app else self.test_app_install_check_flag)
        return ((_flag | include_flag) & (~exclude_flag) & 4) != 0

    def is_check_to_grant_apps_all_permissions(self, is_copilot: bool, is_background_app: bool, exclude_flag: int = 0, include_flag: int = 0):
        _flag = self.copilot_app_install_check_flag if is_copilot else (self.back_app_install_check_flag if is_background_app else self.test_app_install_check_flag)
        return ((_flag | include_flag) & (~exclude_flag) & 8) != 0

    def is_check_to_auto_login(self, is_copilot: bool, exclude_flag: int = 0, include_flag: int = 0):
        _flag = self.copilot_app_install_check_flag if is_copilot else self.test_app_install_check_flag
        return ((_flag | include_flag) & (~exclude_flag) & 16) != 0

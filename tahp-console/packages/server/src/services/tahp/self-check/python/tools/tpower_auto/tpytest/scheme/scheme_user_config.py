import os.path
import shutil
from typing import List, Union

from powertrde import env
from powertrde.utils import yaml_utils, misc_utils
from tpytest.resource_provider import ResourceProviderFactory
from tpytest.case_original_request import CaseOriginalRequest
from tpytest.task_session_config import TaskSessionConfig


class SchemeUserConfig(TaskSessionConfig):
    _instance = None

    def __init__(self):
        super().__init__()
        self.scheme_request = env.scheme
        self._configured_config_dict = {}
        self.run_mode = ''
        self.debug_modes = set()
        self.trunk_flags = set()
        self.case_set = ''
        self.cases: List[CaseOriginalRequest] = []
        self.run_pc_pretests = 0
        self.pretest_level = 2
        self.pretest_skip_pass_hours = 0.0
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
        self.accounts = {}
        self.back_apps: List[str] = []
        self.test_region = 'CN'

        # For 用例负载均衡
        self.case_loading_balance = False
        self.device_index = 0
        self.total_devices = 1

        self._smart_single_case_path_dict = {}

        self._res_provider = None
        self._logs_uploader = None

        self.load_scheme_config()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_skip_pretest(self):
        return self.pretest_level < 0 or self.is_run_mode_single

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
    def user_cache_config_file(self):
        return os.path.join(self.user_cache_config_dir, f'{self.scheme_request.name}_user_config.yaml')

    def copy_user_cache_config_to(self, to_dir: str, filename: str):
        os.makedirs(to_dir, exist_ok=True)
        shutil.copy(self.user_cache_config_file, os.path.join(to_dir, filename))

    @property
    def is_run_mode_utp(self):
        return self.run_mode == 'utp' or self.run_mode.startswith('utp/')

    @property
    def utp_report_file(self):
        filepath = self.config_dict.get('utp_report_file', '')
        if filepath:
            filepath = os.path.join(filepath, 'report.json')
        return filepath

    @property
    def is_overseas_test(self):
        return self.test_region and self.test_region != 'CN'

    @property
    def is_run_mode_single(self):
        return 'single' in self.run_mode

    @property
    def utp_single_tcid(self):
        return self.config_dict.get('tcid', '')

    @property
    def single_case_path(self):
        return self.config_dict.get('single_case_path', '')

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
            search_ret = TPytestTestScheduler.find_first_test_node(env.scheme.scheme_env_class_name_parent_path, s)
            if search_ret:
                exist = search_ret
            else:
                exist = ''
            self._smart_single_case_path_dict[s] = exist
        return exist

    def load_scheme_config(self):
        self.config_dict.clear()
        if self.scheme_request.name:
            # 不再使用原有的模板拷贝模式，不方便
            # template_config = os.path.join(self.config_dir, 'config_template.yaml')
            # if os.path.exists(template_config):
            #     user_cache_config_file = self.user_cache_config_file
            #     if not os.path.exists(user_cache_config_file):
            #         os.makedirs(self.user_cache_config_dir, exist_ok=True)
            #         shutil.copy(template_config, user_cache_config_file)
            #     else:
            #         merge_yaml_and_save(user_cache_config_file, template_config, user_cache_config_file)
            #     yaml_utils.read_yaml_append_to_dict(user_cache_config_file, self.config_dict)
            base_config = os.path.join(self.config_dir, 'base_config.yaml')
            if os.path.exists(base_config):
                yaml_utils.read_yaml_append_to_dict(base_config, self.config_dict)
            user_cache_config_file = self.user_cache_config_file
            if not os.path.exists(user_cache_config_file):
                os.makedirs(self.user_cache_config_dir, exist_ok=True)
                misc_utils.write_all_text(user_cache_config_file,
                                          '# 该placeholder配置仅为占位符，正式配置时，请删除\nplaceholder: placeholder\n')
            yaml_utils.read_yaml_append_to_dict(user_cache_config_file, self.config_dict)
        self._fill_fields()
        self._sync_to_env()

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
        self.config_dict.update(self.override_config_dict)
        self._fill_fields()
        self._sync_to_env()

    def write_config_dict_to_file(self, filepath: Union[str, os.PathLike]):
        yaml_utils.write_yaml(self.configured_config_dict, filepath, ignore_yaml_error=False)

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

    def _fill_fields(self):
        super()._fill_fields()
        config_dict = self.config_dict

        self.case_set = config_dict.get('case_set', '')
        for _ in range(1):
            if not self.case_set:
                break
            case_set_config_file = os.path.join(self.config_dir, f'case_set_{self.case_set}.yaml')
            if not os.path.exists(case_set_config_file):
                case_set_config_file = os.path.join(self.config_dir, f'{self.case_set}.yaml')
                if not os.path.exists(case_set_config_file):
                    break

            _cases_set_dict = yaml_utils.read_yaml(case_set_config_file, False)
            if _cases_set_dict:
                assert isinstance(_cases_set_dict, dict), 'The case set must be DICT LIKE yaml file!'
                config_dict = dict(self.config_dict)
                config_dict.update(_cases_set_dict)
                config_dict.update(self.override_config_dict)

        self._configured_config_dict = config_dict

        self.run_mode = config_dict.get('run_mode', '')

        self.run_pc_pretests = config_dict.get('run_pc_pretests', 1)

        self.pretest_level = config_dict.get('pretest_level', 2)

        self.pretest_skip_pass_hours = config_dict.get('pretest_skip_pass_hours', 0)

        self.case_loading_balance = config_dict.get('case_loading_balance', False)
        self.device_index = config_dict.get('device_index', 0)
        self.total_devices = config_dict.get('total_devices', 1)

        self.test_region = self.config_dict.get('test_region', 'CN')

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

        self.accounts = config_dict.get('accounts', {})
        self.feishu = config_dict.get('feishu', {})
        self.back_apps = config_dict.get('back_apps', [])
        try:
            self.back_apps.remove('placeholder')
        except ValueError:
            pass

        self.test_loop = config_dict.get('test_loop', 1)
        self.small_test_loop = config_dict.get('small_test_loop', 1)
        self.retry = config_dict.get('retry', 0)

        _cases = config_dict.get('cases')
        if _cases:
            assert isinstance(_cases, list), 'The SCHEME CONFIG cases filed must be type of list!'
            self.cases = CaseOriginalRequest.parse_lines(_cases, self.small_test_loop, self.retry)
        else:
            self.cases = []

        self.app_multi_package_keys = config_dict.get('app_multi_package_keys', [])

        self.res_provider_path = self._resolve_text_or_text_method_result(config_dict.get('res_provider_path', ''))
        if self.res_provider_path:
            self.res_provider_username = self._resolve_text_or_text_method_result(config_dict.get('res_provider_username', ''))
            if not self.res_provider_username:
                self.res_provider_username = 'monkeytest'
            self.res_provider_password = self._resolve_text_or_text_method_result(config_dict.get('res_provider_password', ''))
            if not self.res_provider_password:
                self.res_provider_password = 'Monkey123'
        else:
            self.res_provider_username = ''
            self.res_provider_password = ''

        self.logs_uploader_path = self._resolve_text_or_text_method_result(config_dict.get('logs_uploader_path', ''))
        if self.logs_uploader_path:
            self.logs_uploader_username = self._resolve_text_or_text_method_result(config_dict.get('logs_uploader_username', ''))
            if not self.logs_uploader_username:
                self.logs_uploader_username = 'monkeytest'
            self.logs_uploader_password = self._resolve_text_or_text_method_result(config_dict.get('logs_uploader_password', ''))
            if not self.logs_uploader_password:
                self.logs_uploader_password = 'Monkey123'
        else:
            self.logs_uploader_username = ''
            self.logs_uploader_password = ''

    def _sync_to_env(self):
        env.set_user_env_debug_modes(self.debug_modes)
        env.set_user_env_trunk_flags(self.trunk_flags)

        new_keys = list(self.app_multi_package_keys)
        if self.test_region and self.test_region not in new_keys:
            new_keys.append(self.test_region)
        env.set_user_env_arg('app_multi_package_keys', new_keys)

    @property
    def res_provider(self):
        if not self._res_provider:
            pp = self.res_provider_path
            if not pp:
                raise Exception('res_provider_path 未配置')
            pp_u = self.res_provider_username
            if not pp_u:
                raise Exception('res_provider_username 未配置')
            pp_p = self.res_provider_password
            if not pp_p:
                raise Exception('res_provider_password 未配置')
            res_provider = ResourceProviderFactory.create(pp, username=pp_u, password=pp_p)
            if not res_provider.test_connection():
                raise Exception(f'资源提供者连接失败：{pp}')
            self._res_provider = res_provider
        return self._res_provider

    @property
    def logs_uploader(self):
        if not self._logs_uploader:
            pp = self.logs_uploader_path
            if not pp:
                raise Exception('logs_uploader_path 未配置')
            pp_u = self.logs_uploader_username
            if not pp_u:
                raise Exception('logs_uploader_username 未配置')
            pp_p = self.logs_uploader_password
            if not pp_p:
                raise Exception('logs_uploader_password 未配置')
            logs_uploader = ResourceProviderFactory.create(pp, username=pp_u, password=pp_p)
            if not logs_uploader.test_connection():
                raise Exception(f'Log上传者连接失败：{pp}')
            self._logs_uploader = logs_uploader
        return self._logs_uploader

    @property
    def feishu_app_id(self):
        return self.feishu.get('feishu_app_id', '')

    @property
    def feishu_app_secret(self):
        return self.feishu.get('feishu_app_secret', '')

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

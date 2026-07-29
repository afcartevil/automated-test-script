import os.path
import re
from typing import Optional

from powertrde import env
from powertrde.env import RUNTIME_LOG_DIR
from powertrde.utils import path_utils, yaml_utils
from tpytest.preset_recorder import PresetRecorderNode
from tpytest.scheme.scheme_test_env import SchemeTestEnv


def parse_excel_string_to_dict(input_string, target_dict: dict):
    lines = input_string.strip().split('\n')

    for line in lines:
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        key = key.strip()
        value = value.strip()

        # 尝试将value转换为int、float或str
        if value.isdigit():
            value = int(value)
        else:
            try:
                value = float(value)
            except ValueError:
                value = str(value)

        target_dict[key] = value


def get_last_runtime_log_dir(scheme_name: str, team_name=None):
    if not team_name:
        team_name = env.DEFAULT_TEAM_NAME
    if team_name:
        scheme = env.Scheme()
        scheme.try_init(f'{team_name}/{scheme_name}')
        _scheme_mark_file = os.path.join(scheme.cache_dir, 'scheme_marks', f'{scheme_name}_scheme_mark.yaml')
        if os.path.exists(_scheme_mark_file):
            _d = yaml_utils.read_yaml(_scheme_mark_file)
            if isinstance(_d, dict):
                lslrd = _d.get('last_session_log_root_dir')
                if lslrd:
                    if os.path.exists(lslrd):
                        return lslrd
                    lslrd = os.path.join(RUNTIME_LOG_DIR, os.path.basename(lslrd))
                    if os.path.exists(lslrd):
                        return lslrd
    return path_utils.find_largest_filename_include_text(RUNTIME_LOG_DIR, scheme_name, only='dir')


def record_app_change_search_index(app_recorder: PresetRecorderNode, app_search_index: int):
    """将app的动态搜索索引存于该App动态储存值中，用于以后调用auto_trav_records_to_set_app_info_index将该值还原回动态搜索索引中"""
    app_recorder.record('change_app_search_index', app_search_index)


def auto_trav_records_to_set_app_info_index(scheme_env_ins: SchemeTestEnv):
    """自动遍历所有App储存的动态值，如果发现该App储存的值里包含'change_app_search_index'，则将该值自动设置到该App的AppsStaticInfo中"""
    from tpytest_extends.scheme.apps_static_info import AppsStaticInfo
    for k, v_dict in scheme_env_ins.preset_record_groups.groups_dict.items():
        change_app_search_index = None
        try:
            change_app_search_index = v_dict.get('change_app_search_index')
        except KeyError:
            pass
        if isinstance(change_app_search_index, int):
            app_info = AppsStaticInfo.get_app_info_no_raise(k)
            if app_info is not None:
                app_info.set_search_index(change_app_search_index)


def check_to_correct_retest_root_dir(target_report_dir: str):
    """
    检查并切换报告目录到根目录下，同时返回如下内容：
    (切换后或者未切换的路径[str]，是否发生切换[bool]，是否存在复测文件夹[bool]）
    """

    def _check_to_up(_current: str):
        try:
            _target_check_dir = os.path.dirname(_current)
            if os.path.basename(_target_check_dir) == 'retests':
                return os.path.dirname(_target_check_dir)
            if os.path.exists(os.path.join(_current, 'session_process_report.yaml')):
                _target_check_dir = os.path.dirname(_target_check_dir)
                if os.path.basename(_target_check_dir) == 'retests':
                    return os.path.dirname(_target_check_dir)
        except Exception:
            pass
        return None

    _root_dir = target_report_dir

    for _ in range(10):
        _temp_dir = _check_to_up(_root_dir)
        if not _temp_dir:
            break
        _root_dir = _temp_dir
    else:
        raise Exception('The log level for retesting is too deep!')

    has_any_retests = bool(os.path.exists(os.path.join(_root_dir, 'retests')))

    if not has_any_retests:
        if os.path.exists(os.path.join(_root_dir, 'session_process_report.yaml')):
            has_any_retests = bool(os.path.exists(os.path.join(os.path.dirname(_root_dir), 'retests')))
            if not has_any_retests and not os.path.basename(_root_dir) == 'meta_report':
                return target_report_dir, False, False
            _root_dir = os.path.dirname(_root_dir)
        else:
            return target_report_dir, False, False

    return _root_dir, bool(_root_dir != target_report_dir), has_any_retests


def try_to_get_scheme_env_keys():
    _scheme_env = env.get_user_env_arg('scheme_env')
    if not _scheme_env:
        return None
    return _scheme_env.env_keys


def read_latest_changelogs_version(scheme_name: str, team: str) -> Optional[str]:
    try:
        base = env.LAUNCHERS_DIR
        change_logs_path = os.path.join(base, team, scheme_name, 'change_logs.txt')
        if not os.path.exists(change_logs_path):
            return None
        with open(change_logs_path, 'r', encoding='utf-8') as fp:
            for line in fp:
                s = line.strip()
                m = re.match(r"^\[(\d+\.\d+\.\d+)\]$", s)
                if m:
                    return m.group(1)
    except Exception:
        ...
    return None

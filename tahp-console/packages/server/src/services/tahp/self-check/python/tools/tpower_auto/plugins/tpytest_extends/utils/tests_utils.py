from powertrde.env import RUNTIME_LOG_DIR
from powertrde.utils import path_utils
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


def get_last_runtime_log_dir(test_group_name: str):
    return path_utils.find_largest_filename_include_text(RUNTIME_LOG_DIR, test_group_name)


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

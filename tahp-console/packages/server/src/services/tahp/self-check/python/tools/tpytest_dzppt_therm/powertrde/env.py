import fnmatch
import importlib
import locale

import os
import sys
import tempfile
import threading
import time
from typing import Optional, Dict, Any
from appdirs import user_cache_dir

import yaml

from powertrde.interrupt_signal_manager import InterruptSignalManager

PROJ_NAME = "powertrde"

PUBLISH_MODE = ''

TEXT_CONFUSED_KEY = '_$E$C$IG'

DEFAULT_TEAM_NAME = ''

PYTHON_EXECUTOR = 'python' if os.name == 'nt' else 'python3'

INITIAL_WORKSPACE = os.getcwd()

interrupt_signal_manager = InterruptSignalManager(support_atexit=True)
# interrupt_signal_manager.activate()

ENV_ID = str(time.time_ns())

_path_lock = threading.RLock()


def is_publish_mode_odm():
    return PUBLISH_MODE == 'odm'


def is_publish_mode_overseas():
    return PUBLISH_MODE == 'overseas'


def is_external_publish_mode():
    return bool(PUBLISH_MODE)


def is_run_on_windows():
    return os.name == 'nt'


def is_run_on_linux():
    return os.name == 'posix'


def suggest_shell_run(cmd, always_true_in_windows=False):
    if isinstance(cmd, list):
        # if os.name == 'nt':
        #     return True
        # else:
        #     return False
        return False
    else:
        return True


def add_path_to_python_env():
    """
    将工程根目录和其下的plugins目录添加到sys.path中，以便可以导入当前目录下的模块。
    如果当前程序是打包后的可执行文件，则不执行此操作。
    """
    if getattr(sys, 'frozen', False) or get_user_env_arg('has_set_python_env'):
        return
    root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    plugins_path = os.path.join(root_path, 'plugins')
    if os.path.exists(plugins_path):
        sys.path.insert(0, plugins_path)
    set_user_env_arg('has_set_python_env', True)


class LazyPath(os.PathLike):

    def __fspath__(self):
        return self.value

    def __init__(self, factory_or_str):
        self._value = None
        if isinstance(factory_or_str, str):
            self._value = factory_or_str
        else:
            self._factory = factory_or_str

    @property
    def value(self):
        if self._value is None:
            self._value = self._factory()
            return self._value
        return self._value

    def __str__(self):
        return self.value

    def __repr__(self):
        return self.value


def load_class(full_class_path: str):
    """
    根据完整类路径动态导入类对象
    :param full_class_path: 例如 'tests.dzppt.dou3.dou3_env.Dou3Env'
    :return: 类对象
    """
    module_path, class_name = full_class_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    class_type = getattr(module, class_name)
    if not class_type:
        raise Exception(f"Can not find class '{class_name}' in module '{module_path}'")
    return class_type


def load_member(full_member_path: str):
    module_path, member_name = full_member_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    class_type = getattr(module, member_name)
    if not class_type:
        raise Exception(f"Can not find member '{member_name}' in module '{module_path}'")
    return class_type


def load_module(full_module_path: str):
    return importlib.import_module(full_module_path)


def _normalize_entry(p: str) -> str:
    """Normalize a single PATH entry for stable comparison."""
    if not isinstance(p, str):
        p = str(p)
    p = os.path.expanduser(p)
    try:
        p = os.path.abspath(p)
    except Exception:
        # fallback: keep as-is
        p = os.path.normpath(p)
    p = os.path.normpath(p)
    # normalize case on platforms where PATH is case-insensitive (Windows)
    p = os.path.normcase(p)
    return p


def _split_path(env_path: Optional[str]) -> list:
    if env_path is None:
        env_path = os.environ.get("PATH", "")
    if env_path == "":
        return []
    return env_path.split(os.pathsep)


def _join_path(parts: list) -> str:
    return os.pathsep.join(parts)


def get_path_list() -> list:
    """Return current PATH entries (as stored in os.environ) without normalization."""
    return _split_path(os.environ.get("PATH", ""))


def ensure_path_prepend(dirpath: str) -> bool:
    """
    Ensure `dirpath` is present in PATH and is the first entry.
    - Idempotent: repeated calls won't add duplicates.
    - Returns True if PATH was modified, False if already in desired state.
    """
    with _path_lock:
        env = os.environ
        cur = _split_path(env.get("PATH", ""))
        norm_target = _normalize_entry(dirpath)

        # Build normalized list for comparison while keeping original strings
        normalized_map = [_normalize_entry(p) for p in cur]

        changed = False
        # Remove all occurrences of target (by normalized comparison)
        new_parts = [p for p, n in zip(cur, normalized_map) if n != norm_target]

        if not new_parts or _normalize_entry(new_parts[0]) != norm_target:
            # Insert at front
            new_parts.insert(0, os.path.abspath(os.path.expanduser(dirpath)))
            changed = True
        else:
            # already at front, no change
            changed = False

        if changed:
            env["PATH"] = _join_path(new_parts)
        return changed


def ensure_path_prepend_many(dirpaths) -> bool:
    """
    Ensure multiple directories (in the given order) are each present at the front (first one ends up at position 0).
    Example: ensure_path_prepend_many(["A", "B"]) -> final PATH starts with A, B, ...
    Returns True if PATH was modified.
    """
    with _path_lock:
        env = os.environ
        cur = _split_path(env.get("PATH", ""))

        # normalize targets preserving order and deduplicate among targets
        targets = []
        seen_norm = set()
        for d in dirpaths:
            nn = _normalize_entry(d)
            if nn not in seen_norm:
                seen_norm.add(nn)
                targets.append(d)

        if not targets:
            return False

        cur_norm = [_normalize_entry(p) for p in cur]

        # Remove any occurrences of any target from current list
        new_parts = [p for p, n in zip(cur, cur_norm) if n not in seen_norm]

        # Prepend targets in the order provided
        prepend_list = [os.path.abspath(os.path.expanduser(d)) for d in targets]
        new_parts = prepend_list + new_parts

        new_env = _join_path(new_parts)
        if new_env != env.get("PATH", ""):
            env["PATH"] = new_env
            return True
        return False


def ensure_path_contains(dirpath: str) -> bool:
    """Return True if PATH already contains dirpath (normalized comparison)."""
    with _path_lock:
        cur = _split_path(os.environ.get("PATH", ""))
        norm_target = _normalize_entry(dirpath)
        for p in cur:
            if _normalize_entry(p) == norm_target:
                return True
        return False


def remove_from_path(dirpath: str) -> bool:
    """
    Remove all occurrences matching dirpath from PATH.
    Returns True if PATH changed.
    """
    with _path_lock:
        env = os.environ
        cur = _split_path(env.get("PATH", ""))
        norm_target = _normalize_entry(dirpath)

        new_parts = [p for p in cur if _normalize_entry(p) != norm_target]
        if _join_path(new_parts) != env.get("PATH", ""):
            env["PATH"] = _join_path(new_parts)
            return True
        return False


if getattr(sys, 'frozen', False):
    PROJ_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
else:
    PROJ_DIR = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))

PROJ_DIR_NAME = os.path.basename(PROJ_DIR)
LAUNCHERS_DIR = os.path.join(PROJ_DIR, "launchers")
ASSETS_DIR = os.path.join(PROJ_DIR, "assets")
CONFIG_DIR = os.path.join(PROJ_DIR, "config")
PROJ_CONFIG_FILE = os.path.join(CONFIG_DIR, "proj.yaml")
RUNTIME_DIR = os.path.join(PROJ_DIR, ".runtime")

RES_PLUGINS_DIR = os.path.join(ASSETS_DIR, 'res_plugins')
RES_CORE_DIR = os.path.join(ASSETS_DIR, 'res_core')
PHONEMONITOR_DIR = os.path.join(RES_PLUGINS_DIR, 'phonemonitor')

TOOLS_DIR = RES_PLUGINS_DIR
RUNTIME_REPORT_DIR = os.path.join(RUNTIME_DIR, "report")
RUNTIME_LOG_DIR = os.path.join(RUNTIME_DIR, "log")
UIA2_ASSETS_DIR = os.path.join(RES_CORE_DIR, "uia2")
UIA2_BODY_APK_PATH = os.path.join(UIA2_ASSETS_DIR, 'app-uiautomator.apk')
UIA2_TEST_APK_PATH = os.path.join(UIA2_ASSETS_DIR, 'app-uiautomator-test.apk')
UIA2_TEST_JAR_PATH = os.path.join(UIA2_ASSETS_DIR, 'u2.jar')
UIA2_BODY_APP_PACKAGE_NAME = 'com.github.uiautomator'
UIA2_TEST_APP_PACKAGE_NAME = 'com.github.uiautomator.test'
LOG_DIR = os.path.join(PROJ_DIR, "log")
PERF_TOOL_DIR = os.path.join(TOOLS_DIR, 'perf')

ADB_EXE = os.path.join(RES_CORE_DIR, 'adb', 'adb.exe')
if os.name != 'nt':
    ADB_EXE = os.path.join(RES_CORE_DIR, 'adb', 'adb_linux')
if not os.path.exists(ADB_EXE):
    ADB_EXE = 'adb'
else:
    # 如果ADB存在，直接把ADB所在文件夹添加到环境中
    ensure_path_prepend(os.path.normpath(os.path.dirname(ADB_EXE)))

# 先临时写一个
SCREEN_DIR = os.path.join(RUNTIME_DIR, "screen")
if not os.path.exists(SCREEN_DIR):
    os.makedirs(SCREEN_DIR)

DEFAULT_CACHE_DIR = str(user_cache_dir('powertrde'))

_RES_TEAM_DIR = ''
_TEAM_TABLES_DIR = ''
_TEAM_PRE_RECORDS_DIR = ''
_RES_SCHEME_DIR = ''
_SCHEME_CONFIG_DIR = CONFIG_DIR


def GET_RES_TEAM_DIR():
    return _RES_TEAM_DIR


def GET_TEAM_TABLES_DIR():
    return _TEAM_TABLES_DIR


def GET_TEAM_PRE_RECORDS_DIR():
    return _TEAM_PRE_RECORDS_DIR


def GET_RES_SCHEME_DIR(custom_scheme_name=None):
    if custom_scheme_name:
        return os.path.join(os.path.dirname(_RES_SCHEME_DIR), custom_scheme_name)
    return _RES_SCHEME_DIR


def GET_SCHEME_CONFIG_DIR(custom_scheme_name=None):
    if custom_scheme_name:
        return os.path.join(os.path.dirname(_SCHEME_CONFIG_DIR), custom_scheme_name)
    return _SCHEME_CONFIG_DIR


proj_config_dict: Optional[dict] = None

if os.path.exists(PROJ_CONFIG_FILE):
    try:
        with open(PROJ_CONFIG_FILE, 'r', encoding='utf-8') as config_file:
            proj_config_dict = yaml.safe_load(config_file)
    except Exception:
        pass

if proj_config_dict is None:
    proj_config_dict = {}
else:
    project_name_from_file = proj_config_dict.get('project_name')
    if project_name_from_file:
        PROJ_NAME = project_name_from_file
    default_team_name_from_file = proj_config_dict.get('default_team')
    if default_team_name_from_file:
        DEFAULT_TEAM_NAME = default_team_name_from_file

if not DEFAULT_TEAM_NAME:
    if os.path.exists(CONFIG_DIR):
        for _d in os.listdir(CONFIG_DIR):
            _dpc = os.path.join(CONFIG_DIR, _d, 'scheme.yaml')
            if os.path.exists(_dpc):
                try:
                    with open(_dpc, 'r', encoding='utf-8') as f:
                        _dpc_dict = yaml.safe_load(f)
                        DEFAULT_TEAM_NAME = _dpc_dict['team']
                    break
                except Exception:
                    pass


def smart_convert_path(ab_path: str):
    """智能转换路径，如果路径是windows的，则模拟为Linux的，如果是Linux的，则在前方增加盘符"""
    if os.name == 'nt':
        if ':' in ab_path:
            return ab_path
        else:
            return (f'D:' + ab_path).replace('/', '\\')
    else:
        if ':' in ab_path:
            # 提取盘符（如 "D:"）并移除冒号
            path_splits = ab_path.split(":")
            drive_letter = path_splits[0].lower()

            linux_root = "/opt/powertrde/mock_drives"

            # 定义在 Linux 中模拟的盘符文件夹
            linux_drive_folder = f"{linux_root}/{drive_letter}"

            # 获取盘符后面的相对路径，并替换反斜杠为正斜杠
            relative_path = path_splits[1].replace("\\", "/").lstrip("/")

            # 拼接 Linux 路径
            linux_path = os.path.join(linux_drive_folder, relative_path)

            return linux_path
        else:
            return ab_path


class Scheme:
    def __init__(self):
        self.name = ''
        self.team = ''
        self.nickname = ''
        self.config_dir = CONFIG_DIR
        self.config_dict = {}
        self.user_env_args = {'debug_modes': set(), 'trunk_flags': set(), 'runtime_phase': 'default'}
        self._scheme_env_class = None
        self._scheme_env_class_name_parent_path = None
        self._tool_language = None

    def try_init(self, scheme_name_path: str, force_init=False):
        if not force_init and self.name:
            return False

        _scheme_config_dir = os.path.normpath(os.path.join(CONFIG_DIR, scheme_name_path))
        scheme_config_file = os.path.join(_scheme_config_dir, 'scheme.yaml')
        if os.path.exists(scheme_config_file):
            def _path_converter(p):
                return os.path.normpath(os.path.join(CONFIG_DIR, p, 'scheme.yaml'))

            _scheme_config_dict = load_dict_config(scheme_name_path, path_converter=_path_converter)
        else:
            raise Exception(f'Can not init scheme with reqeust path: {scheme_name_path}')

        self.name = _scheme_config_dict['name']
        self.team = _scheme_config_dict['team']
        self.nickname = _scheme_config_dict['nickname']
        self.config_dir = _scheme_config_dir
        self.config_dict = _scheme_config_dict
        return True

    @property
    def override_cache_dir(self):
        return self.config_dict.get('override_cache_dir', '')

    @property
    def scheme_env_class_name(self):
        return self.config_dict.get('env_class', '')

    @property
    def tool_language(self):
        if self._tool_language is None:
            self._tool_language = self.config_dict.get('tool_language', '')
            if not self._tool_language:
                # 检查当前系统语言是否是中文或者繁体中文，如果是，则使用中文语言，否则使用英文语言
                self._tool_language = 'zh' if 'zh' in locale.getdefaultlocale()[0] else 'en'
        return self._tool_language

    @property
    def scheme_env_class_name_parent_path(self):
        if self._scheme_env_class_name_parent_path is None:
            env_class_name = self.scheme_env_class_name
            if env_class_name:
                self._scheme_env_class_name_parent_path = '/'.join(env_class_name.split('.')[:-2])
            else:
                self._scheme_env_class_name_parent_path = ''
        return self._scheme_env_class_name_parent_path

    @property
    def scheme_env_class(self):
        if self._scheme_env_class is None:
            if self.scheme_env_class_name:
                try:
                    self._scheme_env_class = load_class(self.scheme_env_class_name)
                except Exception:
                    pass
                if self._scheme_env_class is None:
                    self._scheme_env_class = 0
            else:
                self._scheme_env_class = 0
        if not isinstance(self._scheme_env_class, type):
            return None
        return self._scheme_env_class

    @scheme_env_class.setter
    def scheme_env_class(self, value):
        self._scheme_env_class = value

    @property
    def scheme_env_single_instance(self):
        if self.scheme_env_class and hasattr(self._scheme_env_class, 'get_instance'):
            return self._scheme_env_class.get_instance()
        return None

    @property
    def cache_dir(self):
        if self.config_dict and os.name == 'nt':
            _override_cache_dir = self.override_cache_dir
            if _override_cache_dir:
                return _override_cache_dir
        return DEFAULT_CACHE_DIR

    def get_user_env_arg(self, key, fallback=None):
        """
        从参数字典中获取用户参数。
        :param key: 参数的键。
        :param fallback: 如果键不存在时的备用返回值。
        :return: 参数的值或运行后返回的结果。
        """
        value = self.user_env_args.get(key, fallback)  # 获取字典中的值，如果不存在则使用fallback
        if callable(value):  # 检查值是否为可调用的
            return value()  # 运行可调用对象并返回结果
        return value

    def assert_get_user_env_arg(self, key):
        """
        从参数字典中获取用户参数（不存在时抛出异常）。
        :param key: 参数的键。
        :return: 参数的值或运行后返回的结果。
        """
        value = self.user_env_args[key]  # 获取字典中的值，如果不存在则使用fallback
        if callable(value):  # 检查值是否为可调用的
            return value()  # 运行可调用对象并返回结果
        return value

    def set_user_env_arg(self, key, value):
        """
        设置用户参数。
        :param key: 参数的键。
        :param value: 参数的值，可以是任何类型，也可以是一个可调用的对象。如果是一个可调用的对象，则在获取时运行它。
        """
        self.user_env_args[key] = value

    def get_user_env_debug_modes(self):
        """
        获取调试模式的值（标记组）。
        """
        return self.get_user_env_arg('debug_modes')

    def set_user_env_debug_modes(self, debug_modes: set):
        """
        设置调试模式的值（标记组）。
        """
        self.set_user_env_arg('debug_modes', debug_modes)

    def user_env_is_debug(self):
        """
        判断是否为调试模式。
        """
        return bool(self.get_user_env_debug_modes())

    def get_scheme_shared_kwargs(self):
        """
        获取测试方案的共享键值对参数（共享环境传参）
        """
        exist_kwargs = self.get_user_env_arg('scheme_shared_kwargs')
        if exist_kwargs is None:
            exist_kwargs = {}
            self.set_user_env_arg('scheme_shared_kwargs', exist_kwargs)
        return exist_kwargs

    def get_scheme_shared_kwargs_kv(self, key, fallback=None):
        """
        设置测试方案的共享键值对参数（共享环境传参）
        """
        return self.get_scheme_shared_kwargs().get(key, fallback)

    def set_scheme_shared_kwargs_kv(self, key, value):
        """
        设置测试方案的共享键值对参数（共享环境传参）
        """
        self.get_scheme_shared_kwargs()[key] = value

    def delete_scheme_shared_kwargs_kv(self, key):
        """
        删除测试方案的共享键值对参数（共享环境传参）
        """
        try:
            del self.get_scheme_shared_kwargs()[key]
        except KeyError:
            pass

    def get_user_env_trunk_flags(self):
        """
        获取主干标记，用于标记一些设定。
        """
        return self.get_user_env_arg('trunk_flags')

    def set_user_env_trunk_flags(self, flags: set):
        """
        设置主干标记组。
        """
        self.set_user_env_arg('trunk_flags', flags)

    def has_user_env_trunk_flag(self, flag: str):
        """
        检查某种标记是否在主干标记组中。
        """
        flags = self.get_user_env_trunk_flags()
        return flags and flag in flags

    def has_user_env_debug_mode(self, debug_mode_flag: str):
        """
        检查某种调试模式是否在调试标记组中。
        """
        debug_modes = self.get_user_env_debug_modes()
        return debug_modes and debug_mode_flag in debug_modes

    def get_user_runtime_phase(self):
        return self.get_user_env_arg('runtime_phase')

    def set_user_runtime_phase(self, runtime_phase: str):
        self.set_user_env_arg('runtime_phase', runtime_phase)


scheme = Scheme()


def update_team_dir():
    global _RES_TEAM_DIR, _TEAM_TABLES_DIR, _TEAM_PRE_RECORDS_DIR, _RES_SCHEME_DIR
    if scheme.team:
        _RES_TEAM_DIR = os.path.join(ASSETS_DIR, scheme.team)
    else:
        _RES_TEAM_DIR = ASSETS_DIR
    _TEAM_TABLES_DIR = os.path.join(_RES_TEAM_DIR, "tables")
    _TEAM_PRE_RECORDS_DIR = os.path.join(_RES_TEAM_DIR, "pre_records")
    if scheme.name:
        _RES_SCHEME_DIR = os.path.join(_RES_TEAM_DIR, scheme.name)
    else:
        _RES_SCHEME_DIR = _RES_TEAM_DIR


update_team_dir()

_custom_env_args_dict = None


def get_user_env_args_dict() -> dict:
    return _custom_env_args_dict if _custom_env_args_dict is not None else scheme.user_env_args


def set_custom_env_args_dict(custom_env_args_dict: Optional[dict]):
    global _custom_env_args_dict
    _custom_env_args_dict = custom_env_args_dict


def get_user_env_arg(key, fallback=None):
    """
    从参数字典中获取用户参数。
    :param key: 参数的键。
    :param fallback: 如果键不存在时的备用返回值。
    :return: 参数的值或运行后返回的结果。
    """
    value = get_user_env_args_dict().get(key, fallback)  # 获取字典中的值，如果不存在则使用fallback
    if callable(value):  # 检查值是否为可调用的
        return value()  # 运行可调用对象并返回结果
    return value


def assert_get_user_env_arg(key):
    """
    从参数字典中获取用户参数（不存在时抛出异常）。
    :param key: 参数的键。
    :return: 参数的值或运行后返回的结果。
    """
    value = get_user_env_args_dict()[key]  # 获取字典中的值，如果不存在则使用fallback
    if callable(value):  # 检查值是否为可调用的
        return value()  # 运行可调用对象并返回结果
    return value


def set_user_env_arg(key, value):
    """
    设置用户参数。
    :param key: 参数的键。
    :param value: 参数的值，可以是任何类型，也可以是一个可调用的对象。如果是一个可调用的对象，则在获取时运行它。
    """
    get_user_env_args_dict()[key] = value


def get_user_env_debug_modes():
    """
    获取调试模式的值（标记组）。
    """
    return get_user_env_arg('debug_modes')


def set_user_env_debug_modes(debug_modes: set):
    """
    设置调试模式的值（标记组）。
    """
    set_user_env_arg('debug_modes', debug_modes)


def user_env_is_debug():
    """
    判断是否为调试模式。
    """
    return bool(get_user_env_debug_modes())


def get_scheme_shared_kwargs():
    """
    获取测试方案的共享键值对参数（共享环境传参）
    """
    exist_kwargs = get_user_env_arg('scheme_shared_kwargs')
    if exist_kwargs is None:
        exist_kwargs = {}
        set_user_env_arg('scheme_shared_kwargs', exist_kwargs)
    return exist_kwargs


def get_scheme_shared_kwargs_kv(key, fallback=None):
    """
    设置测试方案的共享键值对参数（共享环境传参）
    """
    return get_scheme_shared_kwargs().get(key, fallback)


def set_scheme_shared_kwargs_kv(key, value):
    """
    设置测试方案的共享键值对参数（共享环境传参）
    """
    get_scheme_shared_kwargs()[key] = value


def delete_scheme_shared_kwargs_kv(key):
    """
    删除测试方案的共享键值对参数（共享环境传参）
    """
    try:
        del get_scheme_shared_kwargs()[key]
    except KeyError:
        pass


def get_user_env_trunk_flags():
    """
    获取主干标记，用于标记一些设定。
    """
    return get_user_env_arg('trunk_flags')


def set_user_env_trunk_flags(flags: set):
    """
    设置主干标记组。
    """
    set_user_env_arg('trunk_flags', flags)


def has_user_env_trunk_flag(flag: str):
    """
    检查某种标记是否在主干标记组中。
    """
    flags = get_user_env_trunk_flags()
    return flags and flag in flags


def has_user_env_debug_mode(debug_mode_flag: str):
    """
    检查某种调试模式是否在调试标记组中。
    """
    debug_modes = get_user_env_debug_modes()
    return debug_modes and debug_mode_flag in debug_modes


def get_user_runtime_phase():
    return get_user_env_arg('runtime_phase')


def set_user_runtime_phase(runtime_phase: str):
    set_user_env_arg('runtime_phase', runtime_phase)


def get_proj_temp_dir(gen_if_not_exist: bool):
    d = os.path.join(tempfile.gettempdir(), 'powertrde', PROJ_NAME)
    if gen_if_not_exist and not os.path.exists(d):
        os.makedirs(d)
    return d


def get_cache_dir():
    return scheme.cache_dir


def get_proj_cache_dir(gen_if_not_exist: bool):
    # 获取应用程序专用的缓存目录
    cache_dir = os.path.join(get_cache_dir(), PROJ_NAME)

    # 如果目录不存在，则创建它
    if gen_if_not_exist and not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    return cache_dir


def get_framework_shared_cache_dir(gen_if_not_exist: bool, shared_name='shared'):
    # 获取应用程序专用的缓存目录
    cache_dir = os.path.join(get_cache_dir(), shared_name)

    # 如果目录不存在，则创建它
    if gen_if_not_exist and not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    return cache_dir


def load_dict_config(path: str, visited: set = None, path_converter=None) -> Dict[str, Any]:
    """
    加载并合并具有继承关系的YAML配置文件

    参数:
        path: YAML文件路径
        visited: 用于检测循环引用的已访问路径集合

    返回:
        合并后的配置字典
    """
    # 初始化已访问路径集合
    visited = visited or set()

    if not path_converter:
        path_converter = os.path.abspath

    # 获取规范化的绝对路径
    canonical_path = path_converter(path)

    # 检测循环引用
    if canonical_path in visited:
        raise ValueError(f"检测到循环继承引用: {canonical_path}")

    # 将当前路径加入已访问集合（使用新集合保持调用隔离）
    new_visited = visited | {canonical_path}

    try:
        # 加载YAML文件
        with open(canonical_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

            # 验证配置类型
            if not isinstance(config, dict):
                raise ValueError(f"文件 {canonical_path} 内容不是字典格式")

            # 提取并删除parent配置项
            parent_relative = config.pop('parent', None)
            current_config = config.copy()

            # 处理父配置
            if parent_relative:
                parent_relative = str(parent_relative)
                # 构建父配置绝对路径
                parent_dir = os.path.dirname(canonical_path)
                if parent_relative.endswith('.yaml'):
                    parent_path = path_converter(os.path.normpath(os.path.join(parent_dir, parent_relative)))
                else:
                    parent_path = parent_relative
                # 递归加载父配置
                parent_config = load_dict_config(parent_path, new_visited, path_converter)

                current_assets = set(current_config.get('assets', []))
                parent_assets = set(parent_config.get('assets', []))
                current_assets.update(parent_assets)
                if current_assets:
                    current_config['assets'] = list(current_assets)

                current_plugins = set(current_config.get('plugins', []))
                parent_plugins = set(parent_config.get('plugins', []))
                current_plugins.update(parent_plugins)
                if current_plugins:
                    current_config['plugins'] = list(current_plugins)

                # 合并配置（父配置在前，当前配置覆盖父配置）
                return {**parent_config, **current_config}

            return current_config

    except FileNotFoundError:
        raise FileNotFoundError(f"找不到配置文件: {canonical_path}") from None


def try_init_scheme(scheme_name_path: str, force_init=False):
    if not scheme.try_init(scheme_name_path, force_init):
        return

    global _SCHEME_CONFIG_DIR
    _SCHEME_CONFIG_DIR = scheme.config_dir
    update_team_dir()

    print(f"POWERTRDE scheme init with: PROJ '{PROJ_NAME}' | SCHEME '{scheme.name}' | CACHE DIR '{get_cache_dir()}'")


_lazy_shared_pool = {}


def get_lazy_shared_pool(group_id: str = "", db_name: str='powertrde_shared_pool.db'):
    global _lazy_shared_pool
    group_id = group_id+ENV_ID

    if group_id not in _lazy_shared_pool:
        db_path = os.path.join(get_framework_shared_cache_dir(True), db_name)
        from powertrde.utils.lazy_shared_pool import LazySharedPool
        _lazy_shared_pool[group_id] = LazySharedPool(db_path, group_id)

    return _lazy_shared_pool[group_id]


def get_result_dir(res_time):
    """
    获取结果存储路径的根路径
    """
    _res_dir = os.path.join(RUNTIME_DIR, res_time)
    if not os.path.exists(_res_dir):
        os.makedirs(_res_dir, exist_ok=True)
    return _res_dir


def get_result_data_screenshot_dir(res_time):
    """
    获取结果存储路径的,需要保留的图片存储路径的根路径
    """
    _res_dir = os.path.join(get_result_dir(res_time), "dataScreenshot")
    if not os.path.exists(_res_dir):
        os.makedirs(_res_dir, exist_ok=True)
    return _res_dir


def get_result_path(sn, res_time):
    """
    根据传入的device_version字符串，返回拼接后的RUNTIME_device_version_DIR路径。
    """
    _path = os.path.join(RUNTIME_DIR, res_time)
    if not os.path.exists(_path):
        os.makedirs(_path, exist_ok=True)

    file_path = os.path.join(_path, sn + ".txt")
    return file_path


def get_trace_folder_path(sn, res_time, simple_devicemodel):
    """
    根据传入的device_version字符串，返回拼接后的RUNTIME_device_version_DIR路径。
    """
    _path = os.path.join(RUNTIME_DIR, res_time, f"trace_{sn}_{simple_devicemodel}")
    if not os.path.exists(_path):
        os.makedirs(_path, exist_ok=True)
    return _path


def get_excel_path(sn, res_time):
    """
    根据传入的device_version字符串，返回trace_analyse_result路径。
    """
    excel_path = []
    _path = os.path.join(RUNTIME_DIR, res_time)
    pattern = 'trace_analyse_result.xls'
    for root, dirs, files in os.walk(_path):
        for filename in fnmatch.filter(files, pattern):
            excel_path.append(os.path.join(root, filename))
    return excel_path


def find_autodump_dir(base_dir, pattern):
    if not os.path.isdir(base_dir):
        # 路径不存在
        return None

    pattern = pattern + "*"
    matched_dirs = [d for d in os.listdir(base_dir) if
                    fnmatch.fnmatch(d, pattern) and os.path.isdir(os.path.join(base_dir, d))]

    if len(matched_dirs) == 0:
        raise FileNotFoundError(f"No directory found starting with {pattern}")
    elif len(matched_dirs) > 1:
        raise Exception(f"Multiple directories found starting with {pattern}")

    return os.path.join(base_dir, matched_dirs[0])


TRACE_DIR = os.path.join(RES_PLUGINS_DIR, "trace")
AUTODUMP_DIR = LazyPath(lambda: find_autodump_dir(TRACE_DIR, "performance_issue_log_autodump"))
CONV_DIR = LazyPath(lambda: find_autodump_dir(TRACE_DIR, "perfconv"))
LOGSCAN_TRAN_DIR = LazyPath(lambda: find_autodump_dir(TRACE_DIR, "start_log_scan_tran"))
LOGSCAN_OTHER_DIR = LazyPath(lambda: find_autodump_dir(TRACE_DIR, "start_log_scan_other"))

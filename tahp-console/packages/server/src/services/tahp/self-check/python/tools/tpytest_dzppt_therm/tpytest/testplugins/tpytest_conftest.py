import os.path
from collections import defaultdict
from datetime import datetime

import pytest
from _pytest.outcomes import XFailed, Skipped

from powertrde.utils import yaml_utils, json_utils
from tpytest.core_utils import log_safety
from tpytest.task_session_life import TaskSessionLife
from tpytest.scheme.scheme_test_env import get_scheme_env

# 全局字典：key = nodeid（用例唯一标识），value = 当前已重试次数
_retry_counts = defaultdict(int)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    with log_safety():  # 每个测试用例使用独立上下文
        yield


def pytest_addoption(parser):
    parser.addoption("--config", action="store",
                     help="Config json/yaml filepath or json config text, the config can specify the device_id, c_device_id, session_id, etc")
    parser.addoption("--extra_args", action="store", help="User extra args like 'my_param1:value1,my_param2:value2'")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """一个钩子，将call阶段的pytest测试结果存入item的rep_call动态字段中"""
    # 默认执行测试报告生成逻辑
    outcome = yield
    report = outcome.get_result()

    # 将测试结果存储在 node 的 user_properties 中
    if report.when == "call":
        setattr(item, "rep_call", (report, call))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    class_ins = item.instance
    try:
        class_ins._on_pre_call()
    except (Exception, XFailed) as exc:
        class_ins.cs.case_request.is_xfail = isinstance(exc, XFailed)
        class_ins.cs.case_request.error_sub_phase = class_ins.cs.case_request.current_sub_phase
        class_ins._on_post_call(exc)
        raise
    except Skipped as exc_skip:
        class_ins.cs.case_request.is_skip = True
        class_ins.cs.case_request.skip_reason = exc_skip.msg
        class_ins._on_post_call(None)
        raise

    class_ins.cs.case_request.current_sub_phase = 'call'
    outcome = yield

    try:
        outcome.get_result()
    except (Exception, XFailed) as exc:
        class_ins.cs.case_request.is_xfail = isinstance(exc, XFailed)
        class_ins.cs.case_request.error_sub_phase = class_ins.cs.case_request.current_sub_phase
        try:
            class_ins._on_post_call(exc)
        except (XFailed, Skipped) as post_xfail:
            class_ins.cs.case_request.is_xfail = True
            class_ins.cs.logger.exception(str(exc), exc_info=exc)
            outcome.force_exception(post_xfail)
        except Exception as post_exc:
            if not isinstance(exc, (XFailed, Skipped)):
                from tpytest.tpytest_exceptions import CombinedTestException
                outcome.force_exception(CombinedTestException([exc, post_exc]))
    except Skipped as exc_skip:
        class_ins.cs.case_request.is_skip = True
        class_ins.cs.case_request.skip_reason = exc_skip.msg

        try:
            class_ins._on_post_call(None)
        except XFailed as post_xfail:
            class_ins.cs.case_request.is_xfail = True
            class_ins.cs.case_request.error_sub_phase = class_ins.cs.case_request.current_sub_phase
            outcome.force_exception(post_xfail)
        except Skipped as exc_skip:
            outcome.force_exception(exc_skip)
        except Exception as post_exc:
            class_ins.cs.case_request.error_sub_phase = class_ins.cs.case_request.current_sub_phase
            outcome.force_exception(post_exc)
    else:
        try:
            class_ins._on_post_call(None)
        except XFailed as post_xfail:
            class_ins.cs.case_request.is_xfail = True
            class_ins.cs.case_request.error_sub_phase = class_ins.cs.case_request.current_sub_phase
            outcome.force_exception(post_xfail)
        except Skipped as exc_skip:
            class_ins.cs.case_request.is_skip = True
            class_ins.cs.case_request.skip_reason = exc_skip.msg
            outcome.force_exception(exc_skip)
        except Exception as post_exc:
            class_ins.cs.case_request.error_sub_phase = class_ins.cs.case_request.current_sub_phase
            outcome.force_exception(post_exc)


def pytest_runtest_teardown(item, nextitem):
    """
    每执行完一个用例的 teardown（包括 fixture teardown）后都会调用这里。
    :param item: 当前测试项对象（_pytest.nodes.Item）
    :param nextitem: 下一个测试项，可能为 None
    """

    def _get_item_big_loop_index(_item):
        _or = getattr(_item, 'original_request', None)
        if _or is None:
            return 1
        return _or.big_loop_index

    idx = _get_item_big_loop_index(item)
    if not nextitem or idx < _get_item_big_loop_index(nextitem):
        item.instance._big_loop_teardown_flag = idx
    else:
        item.instance._big_loop_teardown_flag = 0


def pytest_runtest_logreport(report):
    """
    pytest 在每个阶段（setup/call/teardown）结束后都会调用一次这个钩子。
    我们只关心 'setup' 阶段：
    - 如果 report.rerun 属性存在（pytest-rerunfailures 会设置它），
      就用它直接覆盖计数；
    - 否则，如果失败且未设置 rerun，可自行 ++。
    """
    if report.when != "setup":
        return

    # pytest-rerunfailures 会在 report 上设置 .rerun
    rerun = getattr(report, "rerun", None)
    if rerun is not None:
        # 直接取插件给的 rerun 次数
        _retry_counts[report.nodeid] = rerun + 1
    else:
        # 不使用插件时，可以这样简单累加失败次数：
        if report.failed:
            _retry_counts[report.nodeid] += 1


@pytest.fixture
def current_retry_index(request):
    """
    在测试函数里，你可以注入这个 fixture 来拿到当前重试次数，
    第一次运行时为 0，第二次运行为 1，以此类推。
    """
    return _retry_counts.get(request.node.nodeid, 0)


def pytest_sessionfinish(session, exitstatus):
    """确保无论是否发生 rerun，都执行清理逻辑"""
    task_session_life = getattr(session, 'task_session_life', None)
    if task_session_life:
        task_session_life.session_end_time = datetime.now()
        if task_session_life.bound_cs_class:
            teardown_session_life_method = getattr(task_session_life.bound_cs_class, 'teardown_session_life')
            teardown_session_life_method(task_session_life)


@pytest.fixture(scope="class", autouse=True)
def class_process_management(request, task_session_life: TaskSessionLife):
    yield
    task_session_life.has_init_test_classes[request.cls].on_teardown_class(task_session_life, request.cls)


@pytest.fixture(scope="session")
def task_session_life(request, user_task_session_config: dict) -> TaskSessionLife:
    s_env = get_scheme_env()
    t = s_env.option_user_session_life_class_type
    if not t:
        t = TaskSessionLife
    tls = t()
    tls.pytest_session = request.session
    request.session.task_session_life = tls
    if not s_env.option_fully_take_over_task_session_life_properties:
        tls.session_config.overwrite_config(user_task_session_config)
    return tls


@pytest.fixture(scope="session")
def user_task_session_config(request):
    _user_overwrite_config_file = None
    try:
        _user_overwrite_config_file = request.config.getoption("--config")
    except:
        pass
    if _user_overwrite_config_file:
        if os.path.exists(_user_overwrite_config_file):
            try:
                _user_overwrite_config_dict = yaml_utils.read_yaml(_user_overwrite_config_file, ignore_yaml_error=False)
            except Exception:
                _user_overwrite_config_dict = json_utils.read_json_file(_user_overwrite_config_file)
        else:
            import ast
            _user_overwrite_config_dict = ast.literal_eval(_user_overwrite_config_file)
            # _user_overwrite_config_dict = json.loads(_user_overwrite_config_file)
    else:
        _user_overwrite_config_dict = {}
    return _user_overwrite_config_dict


@pytest.fixture(scope="session")
def user_extra_args(request):
    _user_extra_args = {}
    _user_extra_args_str: str = ''
    try:
        _user_extra_args_str = request.config.getoption("--extra_args")
    except:
        pass
    if _user_extra_args_str:
        for pair in _user_extra_args_str.split(','):
            splits = pair.split(':')
            _user_extra_args[splits[0].strip()] = splits[1].strip()
    return _user_extra_args


def pytest_sessionstart(session):
    _retry_counts.clear()

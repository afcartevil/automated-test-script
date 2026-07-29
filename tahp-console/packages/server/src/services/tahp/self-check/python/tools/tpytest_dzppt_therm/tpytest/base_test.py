import inspect
from typing import Optional

import pytest
from _pytest.fixtures import FixtureRequest

from tpytest.case_test_report import CaseTestReport
from tpytest.cases_steps import CasesSteps, CasesPhone
from tpytest.case_request import CaseRequest
from tpytest.task_session_life import TaskSessionLife
from tpytest.tpytest_exceptions import CaseDataAssertionError, CombinedTestException


def assert_case_data(condition, message="Case data assertion failed!"):
    if not condition:
        # 获取调用assert_case_data的上一层帧信息
        frame = inspect.currentframe().f_back
        # 获取源代码行
        code_context = inspect.getframeinfo(frame).code_context
        # 提取表达式
        expression = code_context[0].strip()
        raise CaseDataAssertionError(message, expression)


class BaseTest:
    # 设定该测试类绑定的测试用例设计类，该类必须继承自CasesSteps类，用以绑定测试用例步骤
    option_bind_cs_class: type = None
    # 设定该类的测试用例运行时打出的Log的前缀
    option_test_log_header: str = 'Test'
    # 设定该类是否自动写入测试报告文件
    option_auto_write_report_file: bool = False
    # 设定该测试类绑定的测试用例报告类，该类必须继承自CaseTestReport类，用以绑定测试用例报告
    option_bind_report_class: type = None

    @property
    def cs(self) -> CasesSteps:
        return self.get_bound_cs()

    @staticmethod
    def assert_data(condition, message="Case data assertion failed!"):
        if not condition:
            # 获取调用assert_case_data的上一层帧信息
            frame = inspect.currentframe().f_back
            # 获取源代码行
            code_context = inspect.getframeinfo(frame).code_context
            # 提取表达式
            expression = code_context[0].strip()
            raise CaseDataAssertionError(message, expression)

    @property
    def session_life(self) -> TaskSessionLife:
        return getattr(self, '_ss')

    def get_bound_cs(self):
        return getattr(self, '_cs')

    @pytest.fixture
    def case_request(self, request: FixtureRequest, current_retry_index: int):
        if self.option_bind_report_class:
            report_ins = self.option_bind_report_class()
        else:
            report_ins = CaseTestReport()
        case_request = CaseRequest(request, report_ins, current_retry_index)
        return case_request

    @pytest.fixture(autouse=True)
    def process_management(self, case_request: CaseRequest, task_session_life: TaskSessionLife):
        if self.option_bind_cs_class:
            cs = self.option_bind_cs_class()
            setattr(self, '_cs', cs)
            cs.case_request = case_request

        if not hasattr(self, '_ss'):
            setattr(self, '_ss', task_session_life)

        # 会话 setup
        if not task_session_life.has_init:
            self._setup_session_life(case_request, task_session_life)

        # 大循环开始
        if not task_session_life.last_case_request or task_session_life.last_case_request.original_request.big_loop_index < case_request.original_request.big_loop_index:
            self._on_big_loop_setup(case_request.original_request.big_loop_index)

        # 测试类 setup
        task_session_life.setup_test_class_if_needed(case_request)

        request = case_request.fixture_request
        not_call_phase_exceptions = []
        summary_header = f'[{self.option_test_log_header} {case_request.case_short_node_id}]{case_request.case_desc_one_line_with_bracket}'

        try:
            self._on_setup(case_request)
        except Exception as e:
            not_call_phase_exceptions.append(e)
            case_request.result = 'error'
            case_request.exception = e
            case_request.error_phase = 'setup'
            error_msg = f'{summary_header} Setup Error: {e}'
            case_request.report.append_error_message('setup', error_msg)
            task_session_life.logger.exception(error_msg)
            self._on_phases_error(case_request, 'setup', e, error_msg)

        if not case_request.exception:
            case_request.start_test_call()
            case_request.current_phase = 'call'
            yield
            case_request.end_test_call()
            result_obj = request.node.rep_call[0]
            if result_obj.failed or (result_obj.skipped and not case_request.is_skip):
                exc_info = request.node.rep_call[1].excinfo
                exc = exc_info.value
                error_sub_phase_str = case_request.error_sub_phase
                if error_sub_phase_str == 'pre_call':
                    error_sub_phase_str = 'Pre-Call'
                    push_error_phase = 'call/pre_call'
                elif error_sub_phase_str == 'post_call':
                    error_sub_phase_str = 'Post-Call'
                    push_error_phase = 'call/post_call'
                else:
                    error_sub_phase_str = 'Call'
                    push_error_phase = 'call'
                if isinstance(exc, CaseDataAssertionError):
                    case_request.result = 'fail'
                    case_request.exception = exc
                    case_request.error_phase = 'call'
                    summary = f'{summary_header} {error_sub_phase_str} Fail: {exc}'
                    case_request.report.append_error_message(push_error_phase, summary)
                    self._on_phase_call_fail(case_request, summary)
                else:
                    case_request.result = 'error'
                    case_request.exception = exc
                    case_request.error_phase = 'call'
                    summary = f'{summary_header} {error_sub_phase_str} Error: {exc}'
                    case_request.report.append_error_message(push_error_phase, summary)
                    task_session_life.logger.exception(summary, exc_info=exc)
                    self._on_phases_error(case_request, 'call', exc, summary)
                    self._on_phase_call_error(case_request, exc, summary)
            else:
                case_request.result = 'pass'
                if case_request.is_skip:
                    summary = f'{summary_header} Call Pass (by skip)'
                else:
                    summary = f'{summary_header} Call Pass'
                self._on_phase_call_pass(case_request)
            self._on_phase_call_finish(case_request, case_request.result, case_request.exception, summary)

        try:
            try:
                if case_request.error_phase == 'setup':
                    self._on_teardown_setup_error(case_request)
                else:
                    self._on_teardown(case_request)
            except Exception as _e:
                self._on_post_teardown_anyway(case_request)
                raise
            self._on_post_teardown_anyway(case_request)
        except Exception as e:
            not_call_phase_exceptions.append(e)
            case_request.result = 'error'
            case_request.post_exception = e
            case_request.post_error_phase = 'teardown'
            error_msg = f'{summary_header} Teardown Error: {e}'
            case_request.report.append_error_message('teardown', error_msg)
            task_session_life.logger.exception(error_msg)
            self._on_phases_error(case_request, 'teardown', e, error_msg)

        try:
            self._on_make_report(case_request)
        except Exception as e:
            not_call_phase_exceptions.append(e)
            case_request.result = 'error'
            case_request.post_exception = e
            case_request.post_error_phase = 'make_report'
            error_msg = f'{summary_header} MakeReport Error: {e}'
            case_request.report.append_error_message('make_report', error_msg)
            task_session_life.logger.exception(error_msg)
            self._on_phases_error(case_request, 'make_report', e, error_msg)

        big_loop_teardown_flag = getattr(self, '_big_loop_teardown_flag', 0)
        if big_loop_teardown_flag > 0:
            try:
                self._on_big_loop_teardown(big_loop_teardown_flag)
            except Exception as e:
                not_call_phase_exceptions.append(e)
                case_request.result = 'error'
                case_request.post_exception = e
                case_request.post_error_phase = 'big_loop_teardown'
                error_msg = f'{summary_header} BigLoopTeardown Error: {e}'
                case_request.report.append_error_message('big_loop_teardown', error_msg)
                task_session_life.logger.exception(error_msg)
                self._on_phases_error(case_request, 'big_loop_teardown', e, error_msg)

        if not_call_phase_exceptions:
            if len(not_call_phase_exceptions) == 1:
                raise not_call_phase_exceptions[0]
            else:
                raise CombinedTestException(not_call_phase_exceptions)

    def _on_big_loop_setup(self, big_loop_index: int):
        self.cs.on_big_loop_setup(big_loop_index)

    def _on_big_loop_teardown(self, big_loop_index: int):
        self.cs.on_big_loop_teardown(big_loop_index)

    def _setup_session_life(self, case_request: CaseRequest, task_session_life: TaskSessionLife):
        task_session_life.bound_test_class = self.__class__
        task_session_life.bound_cs_class = self.option_bind_cs_class
        task_session_life.setup_case_request = case_request
        task_session_life.init()
        self.cs.setup_session_life(task_session_life)

    def _on_pre_call(self):
        self.cs.case_request.current_sub_phase = 'pre_call'
        self.cs.on_pre_call()
        _single_pre_call = getattr(self, f'pre_call_{self.cs.case_name}', None)
        if _single_pre_call is not None:
            _single_pre_call()

    def _on_post_call(self, exception: Optional[Exception]):
        self.cs.case_request.current_sub_phase = 'post_call'
        self.cs.on_post_call(exception)

        _post_call_name = f'post_call_{self.cs.case_name}'
        _single_post_call = getattr(self, _post_call_name, None)
        if _single_post_call is not None:
            sig = inspect.signature(_single_post_call)
            params = sig.parameters
            params_count = len(params)

            # 根据参数数量调用函数
            if params_count == 0:  # 无参数
                _single_post_call()
            elif params_count == 1:  # 一个参数
                _single_post_call(exception)
            else:
                raise ValueError(f"Single post call '{_post_call_name}' has unexpected number {params_count} of parameters!")

    def _on_setup(self, case_request: CaseRequest):
        case_request.current_phase = 'setup'
        if case_request.is_retry_test:
            # 如果本次是重试，需要延续上一次测试的起始时间(start_time_through_retry)
            if self.session_life.last_case_request and self.session_life.last_case_request.case_base_node_id_no_retry == case_request.case_base_node_id_no_retry:
                case_request.report.start_time_through_retry = self.session_life.last_case_request.report.start_time_through_retry
        case_request.start_report()
        self.session_life.last_case_request = case_request
        self.cs.on_setup()

    def _on_teardown(self, case_request: CaseRequest):
        case_request.current_phase = 'teardown'
        self.cs.on_teardown()

    def _on_teardown_setup_error(self, case_request: CaseRequest):
        case_request.current_phase = 'teardown'
        self.cs.on_teardown_setup_error()

    def _on_post_teardown_anyway(self, case_request: CaseRequest):
        self.cs.on_post_teardown_anyway()

    def _on_make_report(self, case_request: CaseRequest):
        case_request.current_phase = 'make_report'
        case_request.end_report()
        self.cs.on_make_report()

    def _on_phases_error(self, case_request: CaseRequest, phase: str, exception: Exception, summary: str):
        self.cs.on_phases_error(phase, exception, summary)

    def _on_phase_call_error(self, case_request: CaseRequest, exception: Exception, summary: str):
        self.cs.on_phase_call_error(exception, summary)

    def _on_phase_call_fail(self, case_request: CaseRequest, summary: str):
        self.cs.on_phase_call_fail(summary)

    def _on_phase_call_pass(self, case_request: CaseRequest):
        self.cs.on_phase_call_pass()

    def _on_phase_call_finish(self, case_request: CaseRequest, result: str, exception: Exception, summary: str):
        self.cs.on_phase_call_finish(result, exception, summary)


class BaseTestPhone(BaseTest):
    @property
    def cs(self) -> CasesPhone:
        return self.get_bound_cs()

import inspect
from contextlib import contextmanager
from typing import Optional, List, Union

from deprecation import deprecated

from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_manager import U2WatcherManager
from powertrde.utils.u2_extends.u2utils import is_u2_element_not_found_exception
from tpytest.case_request import CaseRequest
from tpytest.case_test_report import CaseTestReport
from tpytest.task_session_life import TaskSessionLife
from tpytest.tpytest_exceptions import CaseDataAssertionError


class CasesSteps:
    def __init__(self):
        super().__init__()
        self.case_request: Optional[CaseRequest] = None
        self.phase_error_log_device_name = 'main'

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
    def instance_test_class(self):
        return None if not self.case_request else self.case_request.fixture_request.node.instance

    @property
    def session_life(self) -> Optional[TaskSessionLife]:
        instance_test_class = self.instance_test_class
        return None if not instance_test_class else instance_test_class.session_life

    @property
    def logger(self):
        return self.session_life.logger

    @property
    def session_id(self) -> Optional[str]:
        return None if not self.session_life else self.session_life.session_id

    @property
    def case_report(self) -> Optional[CaseTestReport]:
        return None if not self.case_request else self.case_request.report

    @property
    def case_name(self):
        return '' if not self.case_request else self.case_request.case_name

    @property
    def case_short_node_id(self):
        return '' if not self.case_request else self.case_request.case_short_node_id

    @property
    def case_base_node_id(self):
        return '' if not self.case_request else self.case_request.case_base_node_id

    @property
    def is_auto_write_report_file(self) -> bool:
        if self.instance_test_class:
            return self.instance_test_class.option_auto_write_report_file
        return False

    @classmethod
    def setup_session_life(cls, session_life: TaskSessionLife):
        session_life.on_session_start()

    @classmethod
    def teardown_session_life(cls, session_life: TaskSessionLife):
        session_life.on_session_end()

    @property
    def logger_header(self):
        return 'Test' if not self.instance_test_class else self.instance_test_class.option_test_log_header

    @classmethod
    def on_setup_class(cls, session_life: TaskSessionLife, test_class: type):
        # session_life.logger.debug(f'{test_class} 测试类开始')
        ...

    @classmethod
    def on_teardown_class(cls, session_life: TaskSessionLife, test_class: type):
        # session_life.logger.debug(f'{test_class} 测试类结束')
        ...

    def on_setup(self):
        self.on_log_case_start()
        if self.is_auto_write_report_file:
            self.session_life.session_report.last_run_case_id = self.case_short_node_id
            self.session_life.write_session_report_for_in_process()
        if self.case_request.is_retry_test:
            self.session_life.test_case_counter.update_current_case_report(self.case_report)
        else:
            self.session_life.test_case_counter.require_next_case(self.case_report)

    def on_log_case_start(self):
        self.logger.info(f'※-S- [{self.logger_header} {self.case_request.case_short_node_id}]{self.case_request.case_desc_one_line_with_bracket} Start', ext_event=True)

    def on_log_case_end(self):
        self.logger.info(f'※-E- [{self.logger_header} {self.case_request.case_short_node_id}]{self.case_request.case_desc_one_line_with_bracket} End: {self.case_report.test_result} in {int(self.case_report.test_duration)}s', ext_event=True)

    def on_log_case_error(self, phase: str, exception: Exception, summary: str):
        from powertrde.framework.tran_logger.log_device import MultiLogDevice
        has_log_success = False
        if isinstance(self.logger.device, MultiLogDevice):
            if self.logger.device.has_device(self.phase_error_log_device_name):
                if self.case_request.is_last_retry:
                    self.logger.error_with_tag(summary, device=self.phase_error_log_device_name, ext_event=True,
                                               screenshot=f'error_shot/err_{self.case_short_node_id}', error_shot=is_u2_element_not_found_exception(exception))
                    has_log_success = True
                else:
                    self.logger.warning(summary, device=self.phase_error_log_device_name, ext_event=True,
                                               screenshot=f'error_shot/err_{self.case_short_node_id}', error_shot=is_u2_element_not_found_exception(exception))
                    has_log_success = True
        if not has_log_success:
            self.logger.error_with_tag(summary, ext_event=True)

    def on_pre_call(self):
        pass

    def on_post_call(self, exception: Optional[Exception]):
        pass

    def on_teardown(self):
        """仅在setup阶段未发生错误时，该teardown才会被执行"""
        pass

    def on_teardown_setup_error(self):
        """仅在setup阶段发生错误时，该特殊的teardown才会被执行"""
        pass

    def on_post_teardown_anyway(self):
        """无论是否是setup阶段发生错误，该后置teardown都会在on_teardown或者on_teardown_setup_error之后被执行"""
        pass

    def on_make_report(self):
        self.on_log_case_end()
        self.session_life.update_report(self.case_report)
        if self.case_report.is_pass:
            self.session_life.test_case_counter.gain_pass_count()
        elif not self.case_request.need_retry_next:
            self.session_life.test_case_counter.gain_fail_count()

    def on_phases_error(self, phase: str, exception: Exception, summary: str):
        self.on_log_case_error(phase, exception, summary)

    def on_phase_call_error(self, exception: Exception, summary: str):
        pass

    def on_phase_call_fail(self, summary: str):
        pass

    def on_phase_call_pass(self):
        pass

    def on_phase_call_finish(self, result: str, exception: Exception, summary: str):
        pass

    def on_big_loop_setup(self, big_loop_index: int):
        pass

    def on_big_loop_teardown(self, big_loop_index: int):
        pass


class CasesPhone(CasesSteps):
    @property
    def device_id(self) -> str:
        return self.session_life.device_id

    @property
    def c_device_id(self) -> str:
        return self.session_life.c_device_id

    @property
    def u2d(self):
        return self.session_life.u2d

    @property
    def c_u2d(self):
        return self.session_life.c_u2d

    @property
    def device_real_sn(self):
        return self.session_life.device_info.device_sn

    @property
    def u2_watcher_manager(self):
        return U2WatcherManager.get_instance()

    @deprecated("该方法管理成本太高，请使用 apply_watchers() 替代")
    def u2_start_watchers(self, *, names: Optional[List[str]] = None, tags_any: Optional[List[str]] = None, tags_all: Optional[List[str]] = None, tags_none: Optional[List[str]] = None, watchers: Optional[List[Union[U2WatcherDef, type]]] = None):
        self.u2_watcher_manager.start_watchers(self.u2d, names=names, tags_any=tags_any, tags_all=tags_all, tags_none=tags_none, watchers=watchers)

    def u2_remove_watchers(self, *, names: Optional[List[str]] = None, watchers: Optional[List[Union[U2WatcherDef, type]]] = None):
        self.u2_watcher_manager.remove_watchers(self.u2d, names=names, watchers=watchers)

    def u2_stop_watchers(self):
        self.u2_watcher_manager.stop_watchers(self.u2d)

    # @contextmanager
    # def u2_apply_watchers(self, *, names: Optional[List[str]] = None, tags_any: Optional[List[str]] = None, tags_all: Optional[List[str]] = None, tags_none: Optional[List[str]] = None, watchers: Optional[List[Union[U2WatcherDef, type]]] = None):
    #     with self.u2_watcher_manager.apply_watchers(self.u2d, names=names, tags_any=tags_any, tags_all=tags_all, tags_none=tags_none, watchers=watchers):
    #         yield
    #
    # @contextmanager
    # def c_u2_apply_watchers(self, *, names: Optional[List[str]] = None, tags_any: Optional[List[str]] = None, tags_all: Optional[List[str]] = None, tags_none: Optional[List[str]] = None, watchers: Optional[List[Union[U2WatcherDef, type]]] = None):
    #     with self.u2_watcher_manager.apply_watchers(self.c_u2d, names=names, tags_any=tags_any, tags_all=tags_all, tags_none=tags_none, watchers=watchers):
    #         yield

    def u2_apply_watchers(self, *, names: Optional[List[str]] = None, tags_any: Optional[List[str]] = None, tags_all: Optional[List[str]] = None, tags_none: Optional[List[str]] = None, watchers: Optional[Union[List[Union[U2WatcherDef, type]], U2WatcherDef, type]] = None):
        return self.u2_watcher_manager.apply_watchers(self.u2d, names=names, tags_any=tags_any, tags_all=tags_all, tags_none=tags_none, watchers=watchers)

    def c_u2_apply_watchers(self, *, names: Optional[List[str]] = None, tags_any: Optional[List[str]] = None, tags_all: Optional[List[str]] = None, tags_none: Optional[List[str]] = None, watchers: Optional[Union[List[Union[U2WatcherDef, type]], U2WatcherDef, type]] = None):
        return self.u2_watcher_manager.apply_watchers(self.c_u2d, names=names, tags_any=tags_any, tags_all=tags_all, tags_none=tags_none, watchers=watchers)

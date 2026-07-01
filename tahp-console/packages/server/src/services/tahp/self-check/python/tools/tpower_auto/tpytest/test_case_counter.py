from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, List

import pytest

from powertrde.framework.weak_events import WeakEvents
from tpytest.case_original_request import CaseOriginalRequest
from tpytest.case_test_report import CaseTestReport
from tpytest.tpytest_scheduler import ScheduledOrderItem


class CaseTestStatus(Enum):
    NOT_START = 0,
    TESTING = 1,
    PASS = 2,
    FAIL = 3,
    ERROR = 4


@dataclass
class CaseTestInfo:
    case_id: str = ''
    case_name: str = ''
    case_desc: str = ''
    class_name: str = ''
    user_kwargs: dict = field(default_factory=dict)
    case_report: Optional[CaseTestReport] = None
    case_ori_request: Optional[CaseOriginalRequest] = None

    @classmethod
    def from_test_item(cls, item: pytest.Item):
        ins = cls()
        splits = item.nodeid.rsplit("::", 2)
        ins.class_name = splits[-2]
        ins.case_id = splits[-1]
        ins.case_name = item.name[5:]
        ins.case_desc = item.obj.__doc__
        if ins.case_desc:
            ins.case_desc = '|'.join(strip_line for strip_line in (line.strip() for line in ins.case_desc.split('\n')) if strip_line)
        else:
            ins.case_desc = ''
        ins.case_ori_request = getattr(item, 'original_request', None)
        return ins

    @property
    def case_short_id(self):
        return '' if len(self.case_id) < 5 else self.case_id[5:]

    @property
    def is_finished(self):
        return bool(self.case_report and self.case_report.test_result)

    @property
    def is_pass(self):
        return bool(self.case_report and self.case_report.is_pass)

    @property
    def is_error_or_fail(self):
        return bool(self.case_report and self.case_report.is_error_or_fail)

    @property
    def is_testing(self):
        return bool(self.case_report and not self.case_report.test_result)

    @property
    def has_ever_started(self):
        return bool(self.case_report)

    @property
    def has_not_started(self):
        return not self.case_report

    @property
    def status(self):
        if self.case_report:
            if self.case_report.test_result == 'pass':
                return CaseTestStatus.PASS
            elif self.case_report.test_result == 'error':
                return CaseTestStatus.ERROR
            elif self.case_report.test_result == 'fail':
                return CaseTestStatus.FAIL
            else:
                return CaseTestStatus.TESTING
        else:
            return CaseTestStatus.NOT_START


class TestCaseCounter:
    def __init__(self, name='', on_changed_event: Optional[Callable[['TestCaseCounter'], None]] = None):
        self.name = name
        self._total_count: int = 0
        self._pass_count: int = 0
        self._fail_count: int = 0
        self.case_test_infos: List[CaseTestInfo] = []
        self.on_changed_event = WeakEvents()
        self.on_changed_event += on_changed_event
        self._current_case_index = -1

    def __getstate__(self):
        """
        返回一个 dict，作为 pickle 的“状态”。
        在这里把 _thread 字段剔除，就不会尝试序列化它。
        """
        state = self.__dict__.copy()
        # 跳过不可序列化字段
        if "on_changed_event" in state:
            del state["on_changed_event"]
        return state

    def __setstate__(self, state):
        """
        pickle 恢复时调用。这里先把原来的字段赋回，
        然后可以重新初始化被跳过的字段。
        """
        self.__dict__.update(state)
        # 恢复或重建 on_changed_event 字段
        self.on_changed_event = WeakEvents()

    def gain_pass_count(self):
        self._pass_count += 1
        self.on_changed()

    def gain_fail_count(self):
        self._fail_count += 1
        self.on_changed()

    def clear(self):
        self._total_count = 0
        self._pass_count = 0
        self._fail_count = 0
        self.case_test_infos.clear()
        self.on_changed()

    def on_changed(self):
        self.on_changed_event(self)

    @property
    def has_ever_started(self):
        return self._current_case_index >= 0 or self.finished_count > 0

    @property
    def current_case_index(self):
        return self._current_case_index

    @current_case_index.setter
    def current_case_index(self, value: int):
        self._current_case_index = value
        self.on_changed()

    def update_current_case_report(self, case_report: CaseTestReport):
        if not self.current_case_info:
            # t_log.error('No current cases available in this counter.', ext_event=True)
            return

        if self.current_case_info.case_id == case_report.case_id_no_retry:
            self.current_case_info.case_report = case_report
        # else:
        #     t_log.error(f'The current case does not match the case ID of the report you need to bind to. The details are as follows: {self.current_case_info.case_id} != {case_report.case_id_no_retry}', ext_event=True)

    def require_next_case(self, bind_case_report: CaseTestReport):
        if self._current_case_index < 0:
            self._current_case_index = 0
        elif self._current_case_index < self.total_count - 1:
            self._current_case_index += 1
        else:
            self._current_case_index = -1
        if self._current_case_index >= 0:
            if self.current_case_info and self.current_case_info.case_id == bind_case_report.case_id_no_retry:
                self.current_case_info.case_report = bind_case_report
            else:
                # t_log.error(f'The next case you requested does not match the case ID of the report you need to bind to. The details are as follows: {self.current_case_info.case_id} != {bind_case_report.case_id_no_retry}', ext_event=True)
                return
        self.on_changed()

    @property
    def current_case_info(self):
        if 0 <= self.current_case_index < len(self.case_test_infos):
            return self.case_test_infos[self.current_case_index]
        return None

    @property
    def pass_count(self):
        return self._pass_count

    @property
    def fail_count(self):
        return self._fail_count

    @property
    def total_count(self):
        if not self._total_count:
            return self.finished_count
        return self._total_count

    @total_count.setter
    def total_count(self, value: int):
        if self._total_count != value:
            self._total_count = value
            self.on_changed()

    @property
    def is_all_finished(self):
        return self.finished_count >= self.total_count

    @property
    def finished_count(self):
        return self._pass_count + self._fail_count

    @property
    def left_count(self):
        return max(0, self.total_count - self.finished_count)

    @property
    def finished_rate(self):
        if not self.total_count:
            return 0.0
        return self.finished_count / self.total_count

    @property
    def pass_rate(self):
        if not self.finished_count:
            return 0.0
        return self._pass_count / self.finished_count

    @property
    def fail_rate(self):
        if not self.finished_count:
            return 0.0
        return self._fail_count / self.finished_count

    def extend_case_infos(self, items: List[ScheduledOrderItem]):
        if items:
            for i in items:
                self.case_test_infos.append(CaseTestInfo.from_test_item(i.test_item))
            self.total_count += len(items)

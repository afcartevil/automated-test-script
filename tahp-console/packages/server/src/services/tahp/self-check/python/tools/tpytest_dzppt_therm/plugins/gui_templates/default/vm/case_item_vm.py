from datetime import timedelta, datetime
from functools import partial
from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel

from powertrde import env
from powertrde.framework.i18n import I18n
from powertrde.utils import confuse_utils
from qt_extends.q_view_model import QViewModel
from tpytest.test_case_counter import CaseTestInfo


class CaseItemVM(QViewModel):
    def __init__(self):
        super().__init__()
        self._case_status = ''
        self._case_name = ''
        self._case_desc = ''
        self._time_text = ''
        self.bound_widget = None

        self._cached_case_info: Optional[CaseTestInfo] = None

    def refresh_view(self, *, case_info: Optional[CaseTestInfo] = None, **kwargs):
        if case_info is not None:
            self._cached_case_info = case_info

            # 如果是ODM，混淆测试用例名
            if env.is_publish_mode_odm():
                self.case_name = confuse_utils.confuse_string(case_info.case_short_id)
            else:
                self.case_name = case_info.case_short_id

            if not env.is_external_publish_mode():
                # 仅传音内网显示注释
                self.case_desc = case_info.case_desc or I18n.gen_str('<No Comments>', '<无注释>')
            else:
                self.case_desc = ''
            if not case_info.has_ever_started and case_info.user_kwargs.get('can_skip'):
                self.case_status = 'CAN_SKIP'
            else:
                if case_info.case_report and case_info.case_report.is_skip:
                    self.case_status = 'SKIPPED'
                else:
                    self.case_status = case_info.status.name

        self.time_text = self.cal_time_text()

    # --------------------------------------------------------------------------------------

    @staticmethod
    def timedelta_to_hms(td: timedelta) -> str:
        """
        将 timedelta 转换为 H:M:S 字符串格式，如 03:05:36。
        小时位可以超过两位数，例如 154:03:58。
        """
        if td is None:
            return ''
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    @staticmethod
    def datetime_to_hms(dt: datetime) -> str:
        """
        将 datetime 对象转换为 H:M:S 字符串格式（24小时制），忽略日期。
        """
        if dt is None:
            return ''
        return dt.strftime("%H:%M:%S")

    def cal_time_text(self):
        tt = ''
        if self._cached_case_info is None:
            return tt

        start_time_text = ''
        end_time_text = ''
        duration_time_text = ''
        retry_text = ''

        def _append_text(_t: str, _prefix: str):
            if not _t:
                return
            nonlocal tt
            if tt:
                tt += '    '
            tt += f'{_prefix}={_t}'

        status = self.case_status

        if status == 'TESTING':
            start_time_text = self.datetime_to_hms(self._cached_case_info.case_report.start_time_through_retry)
            duration_time_text = self.timedelta_to_hms(datetime.now() - self._cached_case_info.case_report.start_time_through_retry)
            if self._cached_case_info.case_report.is_retry_test:
                retry_text = str(self._cached_case_info.case_report.retry_index)
        elif status == 'PASS' or status == 'SKIPPED' or status == 'FAIL' or status == 'ERROR':
            start_time_text = self.datetime_to_hms(self._cached_case_info.case_report.start_time_through_retry)
            end_time_text = self.datetime_to_hms(self._cached_case_info.case_report.end_time)
            duration_time_text = self.timedelta_to_hms(self._cached_case_info.case_report.end_time - self._cached_case_info.case_report.start_time_through_retry)
            if self._cached_case_info.case_report.is_retry_test:
                retry_text = str(self._cached_case_info.case_report.retry_index)
        elif status == 'CAN_SKIP':
            return I18n.gen_str('Will auto skip', '将自动跳过')
        elif not status or status == 'NOT_START':
            return I18n.gen_str('To be tested', '待测')
        else:
            return I18n.gen_str('Error state', '错误状态')

        _append_text(start_time_text, 'S')
        _append_text(end_time_text, 'E')
        _append_text(duration_time_text, 'D')
        _append_text(retry_text, 'R')
        return tt

    # --------------------------------------------------------------------------------------

    case_name_signal_changed = pyqtSignal(str)

    @property
    def case_name(self) -> str:
        return self._case_name

    @case_name.setter
    def case_name(self, v: str):
        if self._set_case_name(v):
            self.case_name_signal_changed.emit(v)

    def _set_case_name(self, v: str):
        if self._case_name != v:
            self._case_name = v
            return True
        return False

    def bind_case_name(self, q: QLabel):
        self.case_name_signal_changed.connect(q.setText)
        self.case_name_signal_changed.emit(self.case_name)

    # --------------------------------------------------------------------------------------

    case_desc_signal_changed = pyqtSignal(str)

    @property
    def case_desc(self) -> str:
        return self._case_desc

    @case_desc.setter
    def case_desc(self, v: str):
        if self._set_case_desc(v):
            self.case_desc_signal_changed.emit(v)

    def _set_case_desc(self, v: str):
        if self._case_desc != v:
            self._case_desc = v
            return True
        return False

    def bind_case_desc(self, q: QLabel):
        self.case_desc_signal_changed.connect(q.setText)
        self.case_desc_signal_changed.emit(self.case_desc)

    # --------------------------------------------------------------------------------------

    time_text_signal_changed = pyqtSignal(str)

    @property
    def time_text(self) -> str:
        return self._time_text

    @time_text.setter
    def time_text(self, v: str):
        if self._set_time_text(v):
            self.time_text_signal_changed.emit(v)

    def _set_time_text(self, v: str):
        if self._time_text != v:
            self._time_text = v
            return True
        return False

    def bind_time_text(self, q: QLabel):
        self.time_text_signal_changed.connect(q.setText)
        self.time_text_signal_changed.emit(self.time_text)

    # --------------------------------------------------------------------------------------

    case_status_signal_changed = pyqtSignal(str)

    @property
    def case_status(self) -> str:
        return self._case_status

    @case_status.setter
    def case_status(self, v: str):
        if self._set_case_status(v):
            self.case_status_signal_changed.emit(v)

    def _set_case_status(self, v: str):
        if self._case_status != v:
            self._case_status = v
            return True
        return False

    @staticmethod
    def _on_case_status_signal_changed(q: QLabel, status: str):
        if status == 'TESTING':
            q.setText('→')
            q.setStyleSheet("color: #AAAA00;")
        elif status == 'PASS':
            q.setText('√')
            q.setStyleSheet("color: green;")
        elif status == 'FAIL' or status == 'ERROR':
            q.setText('×')
            q.setStyleSheet("color: red;")
        elif status == 'SKIPPED':
            q.setText('√s')
            q.setStyleSheet("color: green;")
        elif status == 'CAN_SKIP':
            q.setText('s')
            q.setStyleSheet("color: gray;")
        else:
            q.setText('')

    def bind_case_status(self, q: QLabel):
        self.case_status_signal_changed.connect(partial(self._on_case_status_signal_changed, q))
        self.case_status_signal_changed.emit(self.case_status)

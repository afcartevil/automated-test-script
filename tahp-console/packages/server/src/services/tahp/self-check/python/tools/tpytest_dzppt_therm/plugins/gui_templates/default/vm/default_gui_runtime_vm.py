import asyncio
import logging
import os.path
from datetime import datetime
from functools import partial
from typing import Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QTextCursor, QTextBlockFormat, QTextCharFormat, QColor
from PyQt6.QtWidgets import QPlainTextEdit, QCheckBox, QLabel, QProgressBar, QStyleFactory, QListWidget, \
    QListWidgetItem, QAbstractItemView, QPushButton

from gui_templates.default.gui_options import GuiOptions
from powertrde import env
from powertrde.framework.i18n import I18n
from powertrde.utils import misc_utils
from powertrde.utils.simple_event_center import SimpleEventCenter, SimpleEventListener, SimpleEvent
from qt_extends.q_view_model import QViewModel
from tpytest.test_case_counter import TestCaseCounter
from tpytest_extends.utils import tests_utils


class SubProcessEventListener:
    def __init__(self):
        super().__init__()
        log_listener = SimpleEventListener('scheme_log_event',
                                           lambda e: self.on_displayed_log(e.kwargs['level'], e.kwargs['message']))
        SimpleEventCenter.get_instance().add_listener_directly(log_listener)
        counter_listener = SimpleEventListener('test_counter_event',
                                               lambda e: self.on_test_counter_changed(e.kwargs['counter']))
        SimpleEventCenter.get_instance().add_listener_directly(counter_listener)
        vm_listener = SimpleEventListener('scheme_vm_event', self._on_vm_event)
        SimpleEventCenter.get_instance().add_listener_directly(vm_listener)

        self.last_runtime_phase = ''

    def _on_vm_event(self, e: SimpleEvent):
        vm_key = e.kwargs['key']
        if vm_key == 'runtime_phase':
            ori_phase = e.kwargs['value']
            self.last_runtime_phase = ori_phase
            self.on_runtime_phase_changed()
        elif vm_key == 'session_log_dir':
            session_log_dir = e.kwargs['value']
            self.on_session_log_dir_changed(session_log_dir)

    def on_session_log_dir_changed(self, session_log_dir: str):
        ...

    def on_runtime_phase_changed(self):
        ...

    def on_test_counter_changed(self, test_counter: TestCaseCounter):
        ...

    def on_displayed_log(self, log_level: int, log_text: str):
        ...


class DefaultGuiRuntimeVM(QViewModel, SubProcessEventListener):
    def __init__(self):
        super().__init__()
        self.ui_binder = None
        self._only_show_error = False
        self._test_progress_desc = ''
        self._test_progress_bar = 0
        self._test_progress_bar_component = None
        self._case_info_list_widget: Optional[QListWidget] = None
        self._text_stage = ''
        self._text_timer = ''

        self.log_text_edit: Optional[QPlainTextEdit] = None  # 获取plainTextEdit控件
        self.log_text_edit_error: Optional[QPlainTextEdit] = None  # 获取plainTextEditError控件
        self.log_entries = []
        self.log_entries_error = []

        self._start_test_time: Optional[datetime] = None
        self._timer_task_handler = None
        self._case_items: Optional[TestCaseCounter] = None

        self._case_counter = None
        self._last_updated_case_counter = None
        self._case_item_vms = []

        self._open_log_dir = tests_utils.get_last_runtime_log_dir(GuiOptions.instance.gui_constants_class.SCHEME_NAME)

    # --------------------------------------------------------------------------------------

    def on_session_log_dir_changed(self, session_log_dir: str):
        self.open_log_dir = session_log_dir

    # --------------------------------------------------------------------------------------

    def restart_timer(self):
        if not self._timer_task_handler:
            async def _timer_task():
                while True:
                    await asyncio.sleep(1)
                    self.update_timer()
                    self.update_case_info_timer()

            self._timer_task_handler = asyncio.create_task(_timer_task())
        self._start_test_time = datetime.now()
        self.update_timer()

    def stop_timer(self):
        if self._timer_task_handler:
            self._timer_task_handler.cancel()
            self._timer_task_handler = None

    def update_timer(self):
        if self._start_test_time:
            self.text_timer = misc_utils.format_seconds_to_time(
                (datetime.now() - self._start_test_time).total_seconds())
        else:
            self.text_timer = ''

    def update_case_info_timer(self):
        if self._last_updated_case_counter and self._case_item_vms:
            self._case_item_vms[self._last_updated_case_counter.current_case_index].refresh_view()

    # --------------------------------------------------------------------------------------

    def clear_progress(self):
        self.test_progress_desc = I18n.gen_str('Init...', '初始化...')
        self.test_progress_bar = 0

    def finish_progress(self):
        self.test_progress_bar = 100

    def clear_logs(self):
        self.log_text_edit.setPlainText('')
        self.log_text_edit_error.setPlainText('')
        self.log_entries.clear()
        self.log_entries_error.clear()

    def clear_cases(self):
        self._last_updated_case_counter = None
        self.case_counter = None

    # --------------------------------------------------------------------------------------

    def on_test_counter_changed(self, test_counter: TestCaseCounter):
        self._update_progress_bar(test_counter)
        self._update_case_show(test_counter)

    def on_displayed_log(self, log_level: int, log_text: str):
        self.refresh_logview(log_level, log_text)
        self.refresh_logview_error(log_level, log_text)

    def on_runtime_phase_changed(self):
        _text = None
        if self.last_runtime_phase == 'checking':
            _text = I18n.gen_str('Case Checking', '用例检查中')
        if self.last_runtime_phase == 'pretest':
            _text = I18n.gen_str('Pretesting', '预测试中')
        elif self.last_runtime_phase == 'case':
            if env.get_scheme_shared_kwargs_kv('retest_target'):
                _text = I18n.gen_str('Case Re-Testing', '失败用例复测中')
            else:
                _text = I18n.gen_str('Case Testing', '用例测试中')
        elif self.last_runtime_phase == 'case_phase_teardown':
            _text = I18n.gen_str('Tests Teardown', '测试收尾中')
        elif self.last_runtime_phase == 'case_phase_end':
            _text = I18n.gen_str('Tests Finished', '测试完成')

        if _text is not None:
            self.text_stage = _text
        if self.last_runtime_phase == 'case_phase_end':
            self.finish_progress()
        elif self.last_runtime_phase == 'case_phase_teardown' or self.last_runtime_phase.startswith('exception_'):
            pass
        else:
            self.clear_progress()
            self.clear_logs()
            self.clear_cases()

    def clear_all(self):
        self.text_stage = ''
        self.clear_progress()
        self.clear_logs()
        self.clear_cases()

    # --------------------------------------------------------------------------------------

    def _update_case_show(self, test_counter: TestCaseCounter):
        self._last_updated_case_counter = test_counter
        if self.case_counter is None or test_counter.user_args == 'refresh_all':
            self.case_counter = test_counter
        if test_counter.current_case_info:
            try:
                self._case_item_vms[test_counter.current_case_index].refresh_view(case_info=test_counter.current_case_info)
                self._case_info_list_widget.scrollToItem(self._case_info_list_widget.item(test_counter.current_case_index), QAbstractItemView.ScrollHint.EnsureVisible)
            except Exception:
                pass

    # --------------------------------------------------------------------------------------

    def _update_progress_bar(self, test_counter: TestCaseCounter):
        total_count = test_counter.total_count
        pass_count = test_counter.pass_count
        fail_count = test_counter.fail_count
        self.test_progress_desc = f"{pass_count + fail_count}/{total_count},   Pass/Fail: {pass_count}/{fail_count}"
        _percent = (pass_count + fail_count) * 100 // total_count if total_count != 0 else 0
        # 在Case阶段营造一个没有完全到100%的进度，防止作业人员误解，除非case阶段结束，才会到100%
        if _percent == 100 and (self.last_runtime_phase == 'case' or self.last_runtime_phase == 'pretest'):
            _percent = 99
        self.test_progress_bar = _percent

    # --------------------------------------------------------------------------------------

    def refresh_logview(self, lv, message):
        self.log_entries.append(message)

        # 删除旧日志（保持最大行数限制）
        if len(self.log_entries) > 10000:
            cursor = QTextCursor(self.log_text_edit.document())
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            self.log_entries.pop(0)

        # 创建格式化的文本块
        cursor = QTextCursor(self.log_text_edit.textCursor())
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # 创建新的文本块格式
        block_format = QTextBlockFormat()
        char_format = QTextCharFormat()

        # 设置颜色
        color_dict = {
            logging.WARNING: "#999900",
            logging.ERROR: "red",
            logging.INFO: "black"
        }
        color = color_dict.get(lv, "black")
        char_format.setForeground(QColor(color))

        # 插入新块（相当于<div>）
        cursor.insertBlock(block_format, char_format)
        cursor.insertText(message)

        # 自动滚动到最底部（仅在用户未手动滚动时）
        scrollbar = self.log_text_edit.verticalScrollBar()
        if scrollbar.value() >= scrollbar.maximum() - 5:
            scrollbar.setValue(scrollbar.maximum())

    def refresh_logview_error(self, lv, message):
        if lv != logging.ERROR:  # 如果只展示fail log，并且当前新成的不是fail log，不增加
            return
        self.log_entries_error.append(message)
        if len(self.log_entries_error) > 10000:
            # Remove the oldest line (log and UI)
            document = self.log_text_edit_error.document()
            first_block = document.firstBlock()
            cursor = QTextCursor(document)
            cursor.setPosition(first_block.position())
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            self.log_entries_error.pop(0)

        # Append new message
        self.log_text_edit_error.appendPlainText(message)
        # Get the last block (just added block)
        document = self.log_text_edit_error.document()
        last_block = document.lastBlock()
        cursor = QTextCursor(last_block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)  # 移动到这一行的第一列
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor)  # 带着锚点，移动到最后一列，实现最后一行文本的全选

        # Create red format and apply
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("red"))
        cursor.mergeCharFormat(fmt)

        # Scroll to the bottom
        self.log_text_edit_error.verticalScrollBar().setValue(
            self.log_text_edit_error.verticalScrollBar().maximum()
        )

    # --------------------------------------------------------------------------------------

    test_progress_bar_signal_changed = pyqtSignal(int)

    @property
    def test_progress_bar(self) -> int:
        return self._test_progress_bar

    @test_progress_bar.setter
    def test_progress_bar(self, v: int):
        if self._set_test_progress_bar(v):
            self.test_progress_bar_signal_changed.emit(v)

    def _set_test_progress_bar(self, v: int) -> bool:
        if self._test_progress_bar != v:
            self._test_progress_bar = v
            return True
        return False

    def bind_test_progress_bar(self, q_progressbar: QProgressBar):
        self._test_progress_bar_component = q_progressbar
        self.test_progress_bar_signal_changed.connect(q_progressbar.setValue)
        self.test_progress_bar_signal_changed.emit(self._test_progress_bar)

    def set_test_progress_bar_start_stop(self, is_start: bool):
        if is_start:
            self._test_progress_bar_component.setStyle(QStyleFactory.create('windowsvista'))
        else:
            self._test_progress_bar_component.setStyle(QStyleFactory.create('Fusion'))

    # --------------------------------------------------------------------------------------

    test_progress_desc_signal_changed = pyqtSignal(str)

    @property
    def test_progress_desc(self) -> str:
        return self._test_progress_desc

    @test_progress_desc.setter
    def test_progress_desc(self, v: str):
        if self._set_test_progress_desc(v):
            self.test_progress_desc_signal_changed.emit(v)

    def _set_test_progress_desc(self, v: str) -> bool:
        if self._test_progress_desc != v:
            self._test_progress_desc = v
            return True
        return False

    def bind_test_progress_desc(self, q_label: QLabel):
        self.test_progress_desc_signal_changed.connect(q_label.setText)
        self.test_progress_desc_signal_changed.emit(self.test_progress_desc)

    # --------------------------------------------------------------------------------------

    text_stage_signal_changed = pyqtSignal(str)

    @property
    def text_stage(self) -> str:
        return self._text_stage

    @text_stage.setter
    def text_stage(self, v: str):
        if self._set_text_stage(v):
            self.text_stage_signal_changed.emit(v)

    def _set_text_stage(self, v: str) -> bool:
        if self._text_stage != v:
            self._text_stage = v
            return True
        return False

    def bind_text_stage(self, q_label: QLabel):
        def _update_label(_text):
            if _text in ("用例测试中", "Case Testing"):
                q_label.setStyleSheet("color: green; font-weight: bold;")
            elif _text in ("失败用例复测中", "Case Re-Testing"):
                q_label.setStyleSheet("color: blue; font-weight: bold;")
            else:
                q_label.setStyleSheet("")
            q_label.setText(_text)

        self.text_stage_signal_changed.connect(_update_label)
        # self.text_stage_signal_changed.connect(q_label.setText)
        self.text_stage_signal_changed.emit(self.text_stage)

    # --------------------------------------------------------------------------------------

    text_timer_signal_changed = pyqtSignal(str)

    @property
    def text_timer(self) -> str:
        return self._text_timer

    @text_timer.setter
    def text_timer(self, v: str):
        if self._set_text_timer(v):
            self.text_timer_signal_changed.emit(v)

    def _set_text_timer(self, v: str) -> bool:
        if self._text_timer != v:
            self._text_timer = v
            return True
        return False

    def bind_text_timer(self, q_label: QLabel):
        self.text_timer_signal_changed.connect(q_label.setText)
        self.text_timer_signal_changed.emit(self.text_timer)

    # --------------------------------------------------------------------------------------

    open_log_dir_signal_changed = pyqtSignal(str)

    @property
    def open_log_dir(self) -> str:
        return self._open_log_dir

    @open_log_dir.setter
    def open_log_dir(self, v: str):
        if self._set_open_log_dir(v):
            self.open_log_dir_signal_changed.emit(v)

    def _set_open_log_dir(self, v: str) -> bool:
        if self._open_log_dir != v:
            self._open_log_dir = v
            return True
        return False

    def bind_open_log_dir(self, q_button: QPushButton):
        def _text_wrapper(_text):
            _t = I18n.gen_str('Latest report path', '最近报告路径')
            _wrapped_text = f'{_t}: {os.path.basename(_text)}'
            q_button.setText(_wrapped_text)
        self.open_log_dir_signal_changed.connect(_text_wrapper)
        self.open_log_dir_signal_changed.emit(self.open_log_dir)

    # --------------------------------------------------------------------------------------

    only_show_error_signal_changed = pyqtSignal(bool)

    @property
    def only_show_error(self) -> bool:
        return self._only_show_error

    @only_show_error.setter
    def only_show_error(self, v: bool):
        if self._set_only_show_error(v):
            self.only_show_error_signal_changed.emit(v)

    def _set_only_show_error(self, v) -> bool:
        if v == Qt.CheckState.Checked.value:
            v = True
        else:
            v = False
        if self._only_show_error != v:
            self._only_show_error = v
            if self._only_show_error:
                self.log_text_edit.hide()
                self.log_text_edit_error.show()
            else:
                self.log_text_edit.show()
                self.log_text_edit_error.hide()
            return True
        return False

    # --------------------------------------------------------------------------------------
    def bind_only_show_error(self, q_checkbox: QCheckBox):
        q_checkbox.stateChanged.connect(self._set_only_show_error)
        self.only_show_error_signal_changed.connect(q_checkbox.setChecked)
        self.only_show_error_signal_changed.emit(self.only_show_error)

    def bind_log_plain(self, q_input: QPlainTextEdit):
        self.log_text_edit = q_input

    def bind_log_plain_error(self, q_input: QPlainTextEdit):
        self.log_text_edit_error = q_input
        self.log_text_edit_error.hide()

    # --------------------------------------------------------------------------------------

    case_counter_signal_changed = pyqtSignal()

    @property
    def case_counter(self) -> Optional[TestCaseCounter]:
        return self._case_counter

    @case_counter.setter
    def case_counter(self, v: Optional[TestCaseCounter]):
        if self._case_counter != v:
            self._case_counter = v
            self.case_counter_signal_changed.emit()

    def _on_case_counter_signal_changed(self, q: QListWidget):
        q.clear()
        self._case_item_vms.clear()
        counter = self._case_counter
        if counter is not None:
            for case_info in counter.case_test_infos:
                list_item = QListWidgetItem()
                q.addItem(list_item)
                list_item_widget = GuiOptions.instance.case_item_widget_class()
                self._case_item_vms.append(list_item_widget.vm)
                q.setItemWidget(list_item, list_item_widget)
                list_item.setSizeHint(list_item_widget.size())
                list_item_widget.vm.refresh_view(case_info=case_info)

    def bind_case_counter(self, q: QListWidget):
        self._case_info_list_widget = q
        q.setSpacing(0)
        q.setContentsMargins(0, 0, 0, 0)
        self.case_counter_signal_changed.connect(partial(self._on_case_counter_signal_changed, q))

    # --------------------------------------------------------------------------------------

    def on_stop_test(self):
        self.set_test_progress_bar_start_stop(False)
        if self.text_stage.startswith(I18n.gen_str('Tests Finished', '测试完成')):
            self.text_stage = I18n.gen_str('Tests Finished: Stop', '测试完成-已停止')
        else:
            if self.last_runtime_phase:
                if self.last_runtime_phase.startswith(('case', 'exception_case')):
                    self.text_stage = I18n.gen_str('Tests: Exception Stop', '用例测试-已异常停止')
                else:
                    self.text_stage = I18n.gen_str('Pretests: Exception Stop', '预测试-已异常停止')
            else:
                self.text_stage = I18n.gen_str('Exception Stop', '已异常停止')
        self.stop_timer()

    def on_start_test(self):
        self.clear_all()
        self.set_test_progress_bar_start_stop(True)
        self.text_stage = I18n.gen_str('Init..', '初始化中')
        self.restart_timer()

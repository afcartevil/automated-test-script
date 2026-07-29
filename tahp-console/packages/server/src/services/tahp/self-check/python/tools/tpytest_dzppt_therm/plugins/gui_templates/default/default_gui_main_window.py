import datetime
import os
import random
import sys
import time
from typing import Optional

from PyQt6.QtGui import QGuiApplication

from gui_templates.default.gui_options import GuiOptions

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QProgressBar, QVBoxLayout, QLabel, QDialog, QFileDialog
from qasync import asyncSlot
from gui_templates.default.ui.ui_default_gui_english_translate import apply_embedded_i18n
from powertrde import env
from powertrde.env import LAUNCHERS_DIR
from powertrde.framework.defines import HasHandledException
from powertrde.framework.i18n import I18n
from powertrde.framework.tran_logger import t_log
from powertrde.utils import yaml_utils
from powertrde.utils.trde import adb
from qt_extends.base_q_ui import BaseQWindow


class DefaultGuiMainWindow(BaseQWindow):
    _instance = None

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._ui_binder = GuiOptions.instance.main_ui_binder_class()
        self._ui_binder.setupUi(self)
        apply_embedded_i18n(self._ui_binder, self)

        self.setWindowTitle(GuiOptions.instance.gui_constants_class.get_window_title_with_version_gui())

        self._vm_main = GuiOptions.instance.gui_main_vm_class.get_instance()
        self._vm_runtime = self._vm_main.runtime_vm
        self._active_interruption_once = False  # 主动中断一次
        self._update_progress_dlg: Optional[QProgressDialog] = None

        self._bind_view_models()
        self._init_views()
        self._init_logics()
        self._connect_update_signals()
        self.show()
        self.update_button_visibility()
        QTimer.singleShot(300, self._post_init)

    def _connect_update_signals(self):
        try:
            self._vm_main.update_started.connect(self._on_update_started)
            self._vm_main.update_message.connect(self._on_update_message)
            self._vm_main.update_progress.connect(self._on_update_progress)
            self._vm_main.update_finished.connect(self._on_update_finished)
            self._vm_main.update_no_update.connect(self._on_no_update)
        except Exception as e:
            t_log.warning(I18n.gen_str(f"Failed to bind update signal: {e}",f"绑定更新信号失败: {e}"))

    def _ensure_update_progress(self, text: str):
        try:
            if self._update_progress_dlg is None:
                dlg = QProgressDialog(text, "", 0, 0, self)
                dlg.setWindowTitle(I18n.gen_str("Updating","更新中"))
                dlg.setCancelButton(None)
                dlg.setMinimumDuration(0)
                dlg.setAutoClose(False)
                dlg.setAutoReset(False)
                # 使用非模态对话框，避免阻塞主窗口操作，允许一边下载一边执行用例
                dlg.setWindowModality(Qt.WindowModality.NonModal)
                dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
                dlg.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, False)
                dlg.setStyleSheet(
                    """
                    QProgressDialog { background: #ffffff; }
                    QLabel { font-size: 13px; color: #333; }
                    QProgressBar {
                        border: 1px solid #C8C8C8; border-radius: 4px;
                        height: 18px; background: #F2F2F2;
                    }
                    QProgressBar::chunk {
                        background-color: #4CAF50;  /* 绿色 */
                        border-radius: 4px;
                    }
                    """
                )
                dlg.resize(520, dlg.height())
                dlg.setRange(0, 0)
                dlg.show()
                bar = dlg.findChild(QProgressBar)
                if bar:
                    bar.setTextVisible(True)
                    bar.setFormat("%p%")
                    bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._update_progress_dlg = dlg
            self._update_progress_dlg.setLabelText(text)
            QApplication.processEvents()
        except Exception as e:
            t_log.warning(I18n.gen_str(f"Failed to display update progress: {e}",f"显示更新进度失败: {e}"))

    def _on_update_started(self):
        # 更新开始：确保仅创建一次进度框，并禁用交互
        self._active_interruption_once = True  # 阻断本次“测试已结束”提示
        try:
            adb.adb_kill_server()
        except Exception as e:
            t_log.warning(I18n.gen_str(f"ADB kill-server failed: {e}",f"ADB kill-server 失败: {e}"))
        self._ensure_update_progress(I18n.gen_str(
            "Initializing update process...",
            "正在初始化更新流程..."
        ))
        self._vm_runtime.text_stage = I18n.gen_str("Updating","更新中")
        try:
            self._ui_binder.controlBoxGroup.setEnabled(False)
        except Exception:
            pass
        try:
            self._ui_binder.menuRetest.setEnabled(False)
        except Exception:
            pass

    async def _start_test(self, retest_target: str):
        self._active_interruption_once = False

        try:
            self._vm_main.save_user_config()
        except Exception:
            pass
        await self._vm_main.start_test(retest_target)

    def _on_update_message(self, msg: str):
        self._ensure_update_progress(msg)

    def _on_update_progress(self, stage: str, current: int, total: int):
        try:
            if self._update_progress_dlg is None:
                self._ensure_update_progress(I18n.gen_str("Updating...","更新中..."))
                if self._update_progress_dlg is None:
                    return
            if stage in ("download", "downloaded", "download_overseas"):
                if total and total > 0:
                    total_mb = max(1, total // (1024 * 1024))
                    current_mb = min(total_mb, max(0, current // (1024 * 1024)))
                    self._update_progress_dlg.setRange(0, total_mb)
                    self._update_progress_dlg.setValue(current_mb)
                    # 显示下载进度：已下载/总大小 (百分比)
                    percent = int((current_mb / total_mb) * 100) if total_mb > 0 else 0
                    if stage == "download_overseas":
                        self._update_progress_dlg.setLabelText(I18n.gen_str(
                            f"Downloading overseas package: {current_mb}/{total_mb} MB ({percent}%)",
                            f"正在下载海外包: {current_mb}/{total_mb} MB ({percent}%)"
                        ))
                    else:
                        self._update_progress_dlg.setLabelText(I18n.gen_str(
                            f"Downloading update package: {current_mb}/{total_mb} MB ({percent}%)",
                            f"正在下载更新包: {current_mb}/{total_mb} MB ({percent}%)"
                        ))
                else:
                    cur_mb = max(0, current // (1024 * 1024))
                    self._update_progress_dlg.setRange(0, 0)
                    if stage == "download_overseas":
                        self._update_progress_dlg.setLabelText(I18n.gen_str(
                            f"Downloading overseas package: {cur_mb} MB",
                            f"正在下载海外包: {cur_mb} MB"
                        ))
                    else:
                        self._update_progress_dlg.setLabelText(I18n.gen_str(
                            f"Downloading update package: {cur_mb} MB",
                            f"正在下载更新包: {cur_mb} MB"
                        ))
            elif stage == "complete":
                if total and total > 0:
                    total_mb = max(1, total // (1024 * 1024))
                    self._update_progress_dlg.setRange(0, total_mb)
                    self._update_progress_dlg.setValue(total_mb)
                else:
                    self._update_progress_dlg.setRange(0, 1)
                    self._update_progress_dlg.setValue(1)
                self._update_progress_dlg.setLabelText(I18n.gen_str(
                    "Download complete, extracting update package...",
                    "下载完成，正在解压更新包..."
                ))
            else:
                # 其它阶段统一不确定进度并提示当前阶段文案
                stage_label = {
                    "meta": I18n.gen_str(
                        "Downloading metadata...",
                        "正在下载元数据..."
                    ),
                    "meta_downloaded": I18n.gen_str(
                        "Metadata downloaded, preparing update...",
                        "元数据下载完成，正在准备更新..."
                    ),
                    "extract": I18n.gen_str(
                        "Extracting update package, please wait...",
                        "正在解压更新包，请稍候..."
                    ),
                    "merge": I18n.gen_str(
                        "Merging overseas package...",
                        "正在合并海外包..."
                    ),
                    "backup": I18n.gen_str(
                        "Backing up current version...",
                        "正在备份当前版本..."
                    ),
                    "finalize": I18n.gen_str(
                        "Finalizing update, application will restart soon...",
                        "正在完成更新，应用即将重启..."
                    ),
                }.get(stage, I18n.gen_str("Updating...","更新中..."))
                self._update_progress_dlg.setRange(0, 0)
                self._update_progress_dlg.setLabelText(stage_label)
            QApplication.processEvents()
        except Exception as e:
            t_log.warning(I18n.gen_str(
                f"Failed to refresh update progress UI: {e}",
                f"更新进度UI刷新失败: {e}"
            ))

    def _on_update_finished(self, success: bool, msg: str):
        try:
            if self._update_progress_dlg:
                try:
                    self._update_progress_dlg.close()
                except Exception:
                    pass
                self._update_progress_dlg = None
            # 更新结束后恢复可操作
            try:
                self._ui_binder.controlBoxGroup.setEnabled(True)
                try:
                    self._ui_binder.menuRetest.setEnabled(True)
                except Exception:
                    pass
            except Exception:
                pass
            if success:
                QMessageBox.information(self,I18n.gen_str("Update Completed", "更新完成"),msg)
            else:
                QMessageBox.warning(self,I18n.gen_str("Update Failed", "更新失败"),msg)
        except Exception as e:
            t_log.warning(I18n.gen_str(f"Failed to close update progress: {e}",f"关闭更新进度失败: {e}"))

    def _on_no_update(self, msg: str):
        try:
            # 确保无对话框残留
            if self._update_progress_dlg:
                try:
                    self._update_progress_dlg.close()
                except Exception:
                    pass
                self._update_progress_dlg = None
            # 没有更新时确保恢复可操作
            try:
                self._ui_binder.controlBoxGroup.setEnabled(True)
                try:
                    self._ui_binder.menuRetest.setEnabled(True)
                except Exception:
                    pass
            except Exception:
                pass
            QMessageBox.information(self, I18n.gen_str("Check for Updates", "检查更新"), msg or I18n.gen_str("It is already the latest version", "已是最新版本"))
        except Exception as e:
            t_log.warning(I18n.gen_str(f"Failed to display no update prompt: {e}", f"显示无更新提示失败: {e}"))

    def update_button_visibility(self):
        try:
            """根据 SUPPORT_RETEST 的值更新复测按钮"""
            if not GuiOptions.instance.gui_constants_class.SUPPORT_RETEST:
                self._ui_binder.menuRetest.deleteLater()
        except Exception:
            pass
        try:
            """根据 SUPPORT_TASKID 的值更新task_id按钮"""
            if not GuiOptions.instance.gui_constants_class.SUPPORT_TASKID:
                self._ui_binder.taskIDLabel.deleteLater()
                self._ui_binder.fillLastTimeButton.deleteLater()
                self._ui_binder.taskIDLineEdit.deleteLater()
                self._ui_binder.disableButton.deleteLater()
        except Exception:
            pass
        try:
            """根据 SUPPORT_POWER_MONITOR 的值更新power_monitor按钮 """
            if not GuiOptions.instance.gui_constants_class.SUPPORT_POWER_MONITOR:
                self._ui_binder.powerMonitorLabel.deleteLater()
                self._ui_binder.powerMonitorComboBox.deleteLater()
        except Exception:
            pass
        try:
            """根据 SUPPORT_HVPM 的值更新HVPM输入框 """
            if not GuiOptions.instance.gui_constants_class.SUPPORT_HVPM:
                self._ui_binder.hVPMLabel.deleteLater()
                self._ui_binder.hVPMLineEdit.deleteLater()
        except Exception:
            pass

    def showEvent(self, event):
        """在窗口即将显示时，随机移动位置一次（如果直接启动的话）"""
        if not self._check_need_start_directly():
            return super().showEvent(event)

        screen_geom = QGuiApplication.primaryScreen().availableGeometry()
        win_w = self.frameGeometry().width()
        win_h = self.frameGeometry().height()

        # 计算可用范围：保证整个窗口都在屏幕内
        max_x = max(0, screen_geom.width() - win_w)
        max_y = max(0, screen_geom.height() - win_h)
        # 随机位置（加上屏幕左上角坐标）
        rand_x = screen_geom.x() + random.randint(0, max_x)
        rand_y = screen_geom.y() + random.randint(0, max_y)

        self.move(rand_x, rand_y)
        # 只想第一次随机，后续不再改变，就断开这个重写：
        self.showEvent = super().showEvent

        super().showEvent(event)

    def _check_need_start_directly(self):
        try:
            if sys.argv[1] == '--start':
                from gui_templates.default.default_gui_entry import DefaultGuiEntry
                override_config_dict = DefaultGuiEntry.get_overwrite_sys_argv_config_dict()

                _device_id = None
                _c_device_id = None
                _o_device_id = None
                _case_set = None
                _pretest_level = None
                _app_pretest = None
                _task_id = None
                if override_config_dict:
                    _device_id = override_config_dict.get('device_id')
                    _c_device_id = override_config_dict.get('c_device_id')
                    _o_device_id = override_config_dict.get('o_device_id')
                    _case_set = override_config_dict.get('case_set')
                    _pretest_level = override_config_dict.get('pretest_level')
                    _app_pretest = override_config_dict.get('app_pretest')
                    _task_id = override_config_dict.get('task_id')

                if _device_id:
                    if _device_id not in self._vm_main.device_id_list:
                        raise HasHandledException(f'Device id "{_device_id}" not in available DUT device list.')
                    self._vm_main.device_id_index = self._vm_main.device_id_list.index(_device_id)
                if _c_device_id:
                    if _c_device_id == 'none':
                        if self._vm_main.c_device_id_list:
                            self._vm_main.c_device_id_index = len(self._vm_main.c_device_id_list) - 1
                    else:
                        if _c_device_id not in self._vm_main.c_device_id_list:
                            # raise HasHandledException(f'Device id "{_c_device_id}" not in available AUX device list.')
                            _l: list = self._vm_main.c_device_id_list
                            _l.insert(0, _c_device_id)
                            if len(_l) == 1:
                                _l.append('<None>')
                            self._vm_main._c_device_id_index = self._vm_main.c_device_id_list.index(_c_device_id)
                            try:
                                self._vm_main.refresh_c_device_id()
                            except Exception:
                                pass
                        else:
                            self._vm_main.c_device_id_index = self._vm_main.c_device_id_list.index(_c_device_id)
                if _o_device_id:
                    if _o_device_id == 'none':
                        if self._vm_main.o_device_id_list:
                            self._vm_main.o_device_id_index = len(self._vm_main.o_device_id_list) - 1
                    else:
                        if _o_device_id not in self._vm_main.o_device_id_list:
                            # raise HasHandledException(f'Device id "{_o_device_id}" not in available OBSV device list.')
                            _l: list = self._vm_main.o_device_id_list
                            _l.insert(0, _o_device_id)
                            if len(_l) == 1:
                                _l.append('<None>')
                            self._vm_main._o_device_id_index = self._vm_main.o_device_id_list.index(_o_device_id)
                            try:
                                self._vm_main.refresh_o_device_id()
                            except Exception:
                                pass
                        else:
                            self._vm_main.o_device_id_index = self._vm_main.o_device_id_list.index(_o_device_id)

                if _case_set is not None:
                    self._vm_main.case_set_index = self._vm_main.case_set_list.index(_case_set)
                if _pretest_level is not None:
                    self._vm_main.pretest_level_index = _pretest_level + 1
                if _app_pretest is not None:
                    self._vm_main.app_pretest_index = _app_pretest + 1
                if _task_id is not None:
                    self._vm_main.task_id = _task_id
                self._vm_main.user_config.runtime_overwrite_record = override_config_dict
                return True
        except HasHandledException as e:
            t_log.error(str(e))
            self.show_error_window(str(e))
        except Exception:
            pass
        return False

    def _bind_view_models(self):
        # 绑定Main
        self._vm_main.ui_binder = self._ui_binder
        try:
            self._vm_main.bind_case_set(self._ui_binder.caseSetComboBox)
        except Exception:
            pass
        try:
            self._vm_main.bind_pretest_level(self._ui_binder.pretestLevelComboBox)
        except Exception:
            pass
        try:
            self._vm_main.bind_app_pretest(self._ui_binder.appPretestComboBox)
        except Exception:
            pass
        try:
            self._vm_main.bind_device_id(self._ui_binder.testPhoneComboBox, self._ui_binder.testPhoneLabel)
        except Exception:
            pass
        try:
            self._vm_main.bind_c_device_id(self._ui_binder.copilotPhoneComboBox, self._ui_binder.copilotPhoneLabel)
        except Exception:
            pass
        try:
            self._vm_main.bind_o_device_id(self._ui_binder.observePhoneComboBox, self._ui_binder.observePhoneLabel)
        except Exception:
            pass
        try:
            self._vm_main.bind_power_monitor(self._ui_binder.powerMonitorComboBox, self._ui_binder.powerMonitorLabel)
        except Exception:
            pass
        try:
            self._vm_main.bind_hvpm(self._ui_binder.hVPMLineEdit)
        except Exception:
            pass
        try:
            self._vm_main.bind_task_id(self._ui_binder.taskIDLineEdit)
        except Exception:
            pass
        try:
            self._vm_main.bind_fill_last_task_id(self._ui_binder.fillLastTimeButton, self._ui_binder.taskIDLineEdit)
        except Exception:
            pass

        try:
            self._vm_main.bind_disable_button_task_id(self._ui_binder.disableButton, self._ui_binder.fillLastTimeButton,
                                                      self._ui_binder.taskIDLineEdit)
        except Exception:
            pass

        # 绑定Runtime
        self._vm_runtime.ui_binder = self._ui_binder
        try:
            self._vm_runtime.bind_test_progress_bar(self._ui_binder.test_progress_bar)
        except Exception:
            pass
        try:
            self._vm_runtime.bind_test_progress_desc(self._ui_binder.test_progress_desc)
        except Exception:
            pass
        try:
            self._vm_runtime.bind_only_show_error(self._ui_binder.only_show_error)
        except Exception:
            pass
        try:
            self._vm_runtime.bind_log_plain(self._ui_binder.log_plain)
        except Exception:
            pass
        try:
            self._vm_runtime.bind_log_plain_error(self._ui_binder.log_plain_error)
        except Exception:
            pass
        try:
            self._vm_runtime.bind_text_stage(self._ui_binder.textStage)
        except Exception:
            pass
        try:
            self._vm_runtime.bind_text_timer(self._ui_binder.textTimer)
        except Exception:
            pass
        try:
            self._vm_runtime.bind_case_counter(self._ui_binder.caseListWidget)
        except Exception:
            pass

        try:
            # 绑定日志路径更新信号
            self._vm_runtime.bind_open_log_dir(self._ui_binder.open_log_dir)
        except Exception:
            pass

    def _init_views(self):
        # 设定标题
        try:
            self._ui_binder.textTitle.setText(str(GuiOptions.instance.gui_constants_class.GUI_DISPLAY_TITLE))
        except Exception:
            pass

        # 绑定本类函数
        try:
            self._ui_binder.actionOpenLastReport.triggered.connect(self.open_last_report_dir)
        except Exception:
            pass
        try:
            self._ui_binder.actionOpenConfigDir.triggered.connect(self.open_config_dir)
        except Exception:
            pass
        try:
            self._ui_binder.startTestButton.clicked.connect(self.start_test)
        except Exception:
            pass
        try:
            self._ui_binder.actionStopTest.triggered.connect(self.stop_test)
        except Exception:
            pass

        try:
            # 绑定“打开最近一次报告复测”菜单项点击事件
            self._ui_binder.actionOpenLatestRetest.triggered.connect(self.retest_last_report)
        except Exception:
            pass

        try:
            # 绑定“打开最近一次报告复测”菜单项点击事件
            self._ui_binder.actionOpenCustomizeRetest.triggered.connect(self.retest_customize_report)
        except Exception:
            pass

        try:
            # 绑定指定路径结果上传
            self._ui_binder.actionResultUpload.triggered.connect(self.upload_result_report)
        except Exception:
            pass

        try:
            self._ui_binder.actionRelease.triggered.connect(self.about_release)
        except Exception:
            pass

        try:
            self._ui_binder.actionCheckUpdate.triggered.connect(self.about_check_update)
        except Exception:
            pass

        try:
            self._ui_binder.actionHelp.triggered.connect(self.about_help)
        except Exception:
            pass

        try:
            self._ui_binder.actionSOP.triggered.connect(self.about_sop)
        except Exception:
            pass

        try:
            self._ui_binder.actionOneClickUpload.triggered.connect(self.one_click_upload)
        except Exception:
            pass

        try:
            self._ui_binder.open_log_dir.clicked.connect(self.open_last_report_dir)
        except Exception:
            pass

        try:
            self._ui_binder.refreshDeviceButton.clicked.connect(self.on_button_refresh_devices)
        except Exception:
            pass

    def on_button_refresh_devices(self):
        self.statusBar().showMessage(I18n.gen_str("Refreshing device, please wait..", "正在刷新设备，请等待..."), 10000)
        self.window().setEnabled(False)
        self._vm_main.refresh_view()
        self.window().setEnabled(True)
        self.statusBar().showMessage("", 1)

    def _init_logics(self):
        self.statusBar().showMessage(I18n.gen_str("Initializing device, please wait..", "正在初始化设备，请等待..."), 10000)
        self.window().setEnabled(False)

    def _post_init(self):
        self._vm_main.start()
        self.statusBar().showMessage("", 1)
        self.window().setEnabled(True)
        try:
            if self._check_need_start_directly():
                self._ui_binder.startTestButton.click()
        except Exception:
            pass

    def open_last_report_dir(self):
        d = self._vm_runtime.open_log_dir
        if not os.path.exists(d):
            d = None
        if d:
            os.startfile(d)
        else:
            self.statusBar().showMessage(I18n.gen_str("Warning: The report path for the most recent test cannot be found!", "警告：找不到最近一次测试的报告路径！"), 5000)

    def open_config_dir(self):
        d = os.path.join(env.CONFIG_DIR, env.scheme.team, GuiOptions.instance.gui_constants_class.SCHEME_NAME)
        if not os.path.exists(d):
            d = None
        if d:
            os.startfile(d)
        else:
            self.statusBar().showMessage(I18n.gen_str("Warning: Configuration folder path not found", "警告：找不到配置文件夹路径！"), 5000)

    def stop_test(self):
        _a = I18n.gen_str('Please confirm whether to stop testing?', '请确认是否停止测试？')
        _b = I18n.gen_str('Confirm your action', '确认操作')
        _c = (I18n.gen_str('Confirm', '确认'), I18n.gen_str('Cancel', '取消'))

        result = self.show_confirmation_window(_a, message_title=_b, select_name=_c)
        if result:
            self._active_interruption_once = True
            self._vm_main.stop_test()

    def show_error_window(self, error_msg: str, error_title=None):
        if error_title is None:
            error_title = I18n.gen_str(en='Error', zh='错误')

        # 提示窗口异常的最佳实践组合
        self.window().raise_()
        self.window().activateWindow()
        QApplication.alert(self.window(), 0)
        QMessageBox.critical(self.window(), error_title, error_msg)

    def show_message_window(self, message: str, message_title=None):

        if message_title is None:
            message_title = I18n.gen_str('Notice', '提示')

        # 提示窗口异常的最佳实践组合
        self.window().raise_()
        self.window().activateWindow()
        QApplication.alert(self.window(), 0)
        QMessageBox.information(self.window(), message_title, message)

    def show_confirmation_window(self, message=None, message_title=None,
                                 select_name=None):

        if message is None:
            message = I18n.gen_str("", "是否确认执行此操作？")

        if message_title is None:
            message_title = I18n.gen_str("Confirm", "确认")

        if select_name is None:
            select_name = (I18n.gen_str('Continue', '继续'), I18n.gen_str('Cancel', '放弃'))

        # 提示窗口异常的最佳实践组合
        self.window().raise_()
        self.window().activateWindow()
        QApplication.alert(self.window(), 0)

        # 定义消息框
        msg_box = QMessageBox(self.window())
        msg_box.setWindowTitle(message_title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Question)

        no_button = msg_box.addButton(select_name[1], QMessageBox.ButtonRole.RejectRole)
        ok_button = msg_box.addButton(select_name[0], QMessageBox.ButtonRole.AcceptRole)

        # 设置默认按钮为 OK
        msg_box.setDefaultButton(ok_button)

        # 显示消息框并等待用户选择
        msg_box.exec()

        if msg_box.clickedButton() == ok_button:
            return True
        elif msg_box.clickedButton() == no_button:
            return False

    @asyncSlot()
    async def start_test(self):
        try:
            if self._vm_main.is_updating():
                try:
                    self.statusBar().showMessage(I18n.gen_str("Updating in progress, please try again later...","正在更新中，请稍后再试..."),5000)
                except Exception:
                    pass
                return
        except Exception:
            pass
        if not self.check_task_id():
            raise Exception(I18n.gen_str("task_id check failed!","task_id检查不通过！"))

        await self._start_test('')

        # 若处于更新流程（包括点击开始后触发了更新或本就处于更新中），不弹“测试已结束”提示
        try:
            if self._vm_main.is_updating():
                return
        except Exception:
            pass

        if self._active_interruption_once:
            self._active_interruption_once = False
            return
        self.show_message_window(I18n.gen_str("Test ended, please check the test result", "测试已结束，请检查测试结果是否正常"))

    @asyncSlot()
    async def retest_last_report(self):
        """
        槽函数：处理“打开最近一次报告复测”功能。
        """
        # 获取最近一次报告路径
        latest_log_dir = self._vm_runtime.open_log_dir
        if not latest_log_dir:
            self.show_error_window(
                I18n.gen_str(
                    "Could not find the most recent report path, retest is not possible!",
                    "未找到最近一次的报告路径，无法复测!"),
                I18n.gen_str("Path Error","路径错误")
            )
            return

        # taskID校验
        if not self.check_task_id_from(latest_log_dir):
            raise Exception(I18n.gen_str("task_id check failed!","task_id检查不通过！"))

            # 启动测试
        await self._start_test(latest_log_dir)

    @asyncSlot()
    async def retest_customize_report(self):
        """
        槽函数：处理“打开自定义报告复测”功能。
        """
        self.statusBar().setStyleSheet("color: red; font-size: 16px; ")

        from PyQt6.QtWidgets import QFileDialog

        # 获取初始目录，如果 open_log_dir 为 None 则使用当前目录
        initial_dir = ""
        if self._vm_runtime.open_log_dir:
            initial_dir = os.path.dirname(self._vm_runtime.open_log_dir)

        customize_log_dir = QFileDialog.getExistingDirectory(
            self,
            "选择自定义报告路径",
            initial_dir,
            QFileDialog.Option.ShowDirsOnly  # 仅显示目录
        )

        # 自定义选择的文件校验
        result = self.check_customize_log_dir(customize_log_dir)
        if not result:
            raise Exception(I18n.gen_str("Custom path check failed!","自定义路径不通过！"))

        # taskID校验
        if not self.check_task_id_from(customize_log_dir):
            raise Exception(I18n.gen_str("task_id check failed!","task_id检查不通过！"))

        # 启动测试
        await self._start_test(customize_log_dir)

    @asyncSlot()
    async def upload_result_report(self):
        self.statusBar().setStyleSheet("color: red; font-size: 16px; ")

        # 获取初始目录，如果 open_log_dir 为 None 则使用当前目录
        initial_dir = ""
        if self._vm_runtime.open_log_dir:
            initial_dir = os.path.dirname(self._vm_runtime.open_log_dir)

        customize_log_dir = QFileDialog.getExistingDirectory(
            self,
            "选择自定义报告路径",
            initial_dir,
            QFileDialog.Option.ShowDirsOnly  # 仅显示目录
        )

        # 自定义选择的文件校验
        result = self.check_customize_log_dir(customize_log_dir)
        if not result:
            raise Exception(I18n.gen_str("Custom path check failed!","自定义路径不通过！"))

        self._ui_binder.menuRetest.setEnabled(False)
        self._ui_binder.controlBoxGroup.setEnabled(False)

        try:
            # 结果上传
            # self.show_message_window(f"上传结果{customize_log_dir}开始，点击ok刷新UI状态")
            # 获取当前 GUI 绑定的设备号（优先取 VM 记录，回退到共享环境）
            device_id = self._vm_main.user_config.device_id_record or env.get_scheme_shared_kwargs_kv('device_id')
            result = self.show_confirmation_window(
                I18n.gen_str(
                    f"Export {device_id} mobilelog before uploading results?",
                    f"上传结果前是否导出 {device_id} 的 mobilelog 日志？"
                ),
                I18n.gen_str("Export Logs", "导出日志确认"),
                (I18n.gen_str("Export and Upload", "导出并上传"), I18n.gen_str("Upload Without Logs", "不导出日志上传"))
            )

            if result:
                if not device_id or device_id == 'none':
                    raise Exception(I18n.gen_str(f"No DUT selected or connected  {device_id}", f"未选择或未连接测试机 {device_id}"))
                from powertrde.utils.log import mobilelog
                mobilelog.export_logs(device_id, os.path.join(customize_log_dir, 'phone_logs'), export_bug_reports_mode='full')

            reporter = GuiOptions.instance.reporter_class(customize_log_dir, False)
            reporter.parse_reporter_units()
            reporter.write_reporter_excel()
            reporter.generate_utp_data_upload()
            self.show_message_window(I18n.gen_str(
                f"Upload results {customize_log_dir} completed!",
                f"上传结果{customize_log_dir}完成！"
            ))
        except Exception as e:
            t_log.warning(I18n.gen_str(
                f"Error occurred while uploading results: {e}",
                f"结果上传发生错误：{e}"
            ))
            self.show_message_window(I18n.gen_str(
                f"Error occurred while uploading results: {e}",
                f"结果上传发生错误：{e}"
            ), "错误")
        finally:
            self._ui_binder.menuRetest.setEnabled(True)
            self._ui_binder.controlBoxGroup.setEnabled(True)

    def check_customize_log_dir(self, customize_log_dir):
        # 自定义选择的文件校验
        session_process_path = ''
        for root, dirs, files in os.walk(customize_log_dir):
            depth = root[len(customize_log_dir):].count(os.sep)
            if depth >= 2:
                del dirs[:]  # 如果超过两级目录，不再深入 清空 dirs，阻止 os.walk 进一步递归
                continue
            if 'session_process_report.yaml' in files:
                session_process_path = os.path.join(root, 'session_process_report.yaml')
                break
        if session_process_path:
            session_process_dict = yaml_utils.read_yaml(session_process_path)
            if session_process_dict.get('scheme') != GuiOptions.instance.gui_constants_class.SCHEME_NAME:
                self.show_error_window(
                    I18n.gen_str(
                        "Retest model does not match, please select the specified retest model!",
                        "复测模型不对应, 请选择指定复测模型！"
                    ),
                    I18n.gen_str("Path Error","路径错误")
                )
                return
        else:
            self.show_error_window(
                I18n.gen_str(
                    "This is an incomplete session, no session_process_report.yaml file found!",
                    "这是一个非完整的会话, 没有session_process_report.yaml文件！"
                ),
                I18n.gen_str("Path Error","路径错误")
            )
            return

        if not customize_log_dir:
            self.show_error_window(
                I18n.gen_str(
                    "Could not find the custom report path, retest is not possible!",
                    "未找到自定义的报告路径, 无法复测!"
                ),
                I18n.gen_str("Path Error","路径错误")
            )
            return
        else:
            self.statusBar().setStyleSheet("color: black; font-size: 16px; ")
            self.statusBar().showMessage(I18n.gen_str(f"Custom path is: {customize_log_dir}",f"自定义路径是: {customize_log_dir}"))
        return True

    def check_task_id(self):
        if not GuiOptions.instance.gui_constants_class.SUPPORT_TASKID:
            return True
        try:
            if self._ui_binder.disableButton.text() == '启用':
                return True
        except Exception as e:
            t_log.warning(I18n.gen_str(f"An error occurred: {e}",f"发生错误：{e}"))
            ...
        current_task_id = self._ui_binder.taskIDLineEdit.text()
        if current_task_id:
            result = self.show_confirmation_window(
                I18n.gen_str(
                    f"The current task_id is [{current_task_id}], continue?",
                    f"当前task_id为【{current_task_id}】, 是否继续？"
                ),
                I18n.gen_str("Confirm task_id","确认task_id"),
                (I18n.gen_str("Continue", "继续"), I18n.gen_str("Terminate", "终止"))
            )
            return result
        else:
            self.show_message_window(I18n.gen_str(
                "The current task_id is empty, please input task_id or click Disable!",
                "当前task_id为空，请输入task_id或点击禁用！"
            ))
            return False

    def check_task_id_from(self, base_runtime_log_dir):
        if not GuiOptions.instance.gui_constants_class.SUPPORT_TASKID:
            return True
        try:
            if self._ui_binder.disableButton.text() == '启用':
                return True
        except Exception as e:
            t_log.warning(I18n.gen_str(f"An error occurred: {e}",f"发生错误：{e}"))
            ...
        try:
            current_task_id = self._ui_binder.taskIDLineEdit.text()
            if current_task_id:
                result = self.show_confirmation_window(
                    I18n.gen_str(
                        f"The task_id in the current task ID is [{current_task_id}], continue? "
                        f"Otherwise, it will be automatically read from {base_runtime_log_dir}",
                        f"当前任务ID中的task_id为【{current_task_id}】, 是否继续？"
                        f"否则, 将自动从文件{base_runtime_log_dir}读取"
                    ),
                    I18n.gen_str("Confirm task_id","确认task_id"),
                    (I18n.gen_str("Continue", "继续"), I18n.gen_str("Auto Read", "自动读取"))
                )
                if result:
                    return True

            # 检查 原始 meta_report 目录
            base_meta_report_dir = os.path.join(base_runtime_log_dir, 'meta_report')
            base_yaml_path = os.path.join(base_meta_report_dir, 'session_runtime_config.yaml')

            if not os.path.exists(base_meta_report_dir) or not os.path.exists(base_yaml_path):
                self._ui_binder.taskIDLineEdit.setText('')
                result = self.show_confirmation_window(
                    I18n.gen_str(
                        "session_runtime_config.yaml file not found, task_id is empty, continue?",
                        "session_runtime_config.yaml文件不存在, task_id为空, 是否继续？"
                    ),
                    I18n.gen_str("Confirm task_id","确认task_id")
                )
                if result:
                    self._ui_binder.taskIDLineEdit.setText('')
                return result

            base_task_id = yaml_utils.read_yaml(base_yaml_path).get('task_id', '')
            self._ui_binder.taskIDLineEdit.setText(base_task_id)
            # 检查 最新 retest 的 meta_report 目录
            latest_meta_report_dir = self._vm_main.last_runtime_meta_report_dir_from_base(base_runtime_log_dir)
            latest_yaml_path = os.path.join(latest_meta_report_dir, 'session_runtime_config.yaml')

            _text_confirm_task_id = I18n.gen_str(f'Confirm task_id', "确认task_id")

            if not os.path.exists(latest_meta_report_dir) or not os.path.exists(latest_yaml_path):
                result = self.show_confirmation_window(
                    I18n.gen_str(f'Automatically read task_id as: [{base_task_id}]?',
                                 f"自动读取task_id为：【{base_task_id}】？"), _text_confirm_task_id)
                return result

            latest_task_id = yaml_utils.read_yaml(latest_yaml_path).get('task_id', '')

            _text_select = I18n.gen_str(f'Select', "选择")

            # 如果 task_id 不一致，提示用户确认
            if base_task_id != latest_task_id:
                _text_please_select_task_id = I18n.gen_str(
                    f'The task_id in the original report is: [{base_task_id}], and the task_id in the latest retest report is: [{latest_task_id}]. Please select the task_id',
                    f"原始报告中的 task_id 是：【{base_task_id}】, 最新 retest 报告中的 task_id 是：【{latest_task_id}】，请选择task_id")

                result = self.show_confirmation_window(
                    _text_please_select_task_id,
                    _text_confirm_task_id, (f'{_text_select}: ' + base_task_id, f'{_text_select}: ' + latest_task_id)
                )
                if result:
                    self._ui_binder.taskIDLineEdit.setText(base_task_id)
                else:
                    self._ui_binder.taskIDLineEdit.setText(latest_task_id)
                return True
            else:
                # task_id 一致时，直接设置并提示用户
                result = self.show_confirmation_window(
                    I18n.gen_str(f'Automatically read task_id as [{base_task_id}], do you want to continue?',
                                 f'自动读取task_id为：【{base_task_id}】, 是否继续？'),
                    I18n.gen_str('Confirm task_id', "确认task_id"))
                return result

        except Exception as e:
            # 捕获所有异常并提示用户
            self.show_error_window(
                f"{I18n.gen_str('An error occurred while checking task_id', '检查 task_id 时发生错误')}：{str(e)}")

    def about_release(self):
        scheme_name = GuiOptions.instance.gui_constants_class.SCHEME_NAME
        changes_log_path = os.path.join(LAUNCHERS_DIR, 'dzppt', scheme_name, 'change_logs.txt')

        if os.path.exists(changes_log_path):
            with open(changes_log_path, "r", encoding="utf-8") as file:
                content = file.read()

            log_entries = content.strip().split("\n")

            versions = [i for i, line in enumerate(log_entries) if line.startswith("[")]

            # 截取前三个版本信息
            if len(versions) > 3:
                end_index = versions[3]
                log_entries = log_entries[:end_index]

            content = "\n".join(log_entries)
        else:
            content = I18n.gen_str("No version info", "无版本信息")

        self.show_message_window(content, I18n.gen_str('Version Info', '版本信息'))

    def about_check_update(self):
        try:
            if self._vm_main.is_updating():
                try:
                    self.statusBar().showMessage(
                        I18n.gen_str("The update is in progress, please try again later..",
                                     "更新进行中，请稍后再试..."), 5000)
                except Exception:
                    pass
                return
        except Exception:
            pass
        self._vm_main.check_for_updates(show_no_update_message=True, is_manual=True)

    def about_help(self):
        content_zh = ('快温省自动化小组：\n'
                      '郑程鹏：chengpeng.zheng@transsion.com\n'
                      '赵凯：kai.zhao@transsion.com\n'
                      '蒋昊：hao.jiang1@transsion.com\n'
                      '姚婷婷：tingting.yao1@transsion.com\n'
                      '赖科良：keliang.lai@transsion.com\n'
                      '陈兴志：xingzhi.chen@transsion.com\n'
                      '谢凯园：kaiyuan.xie@transsion.com\n'
                      '梁庭嶂：tingzhang.liang@transsion.com\n'
                      '熊婷：ting.xiong@transsion.com\n')
        content_en = ('Basic Experience Automation Team：\n'
                      'chengpeng.zheng@transsion.com\n'
                      'kai.zhao@transsion.com\n'
                      'hao.jiang1@transsion.com\n'
                      'tingting.yao1@transsion.com\n'
                      'keliang.lai@transsion.com\n'
                      'xingzhi.chen@transsion.com\n'
                      'kaiyuan.xie@transsion.com\n'
                      'tingzhang.liang@transsion.com\n'
                      'ting.xiong@transsion.com\n')
        self.show_message_window(I18n.gen_str(content_en, content_zh),
                                 I18n.gen_str('About Us', '关于我们'))

    def about_sop(self):
        sop_info = GuiOptions.instance.gui_constants_class.get_sop_link()
        sop_link = sop_info['link']
        sop_name = f'<div style="text-align: center; font-size: 18px; font-weight: bold; color: green;">{sop_info["name"]}</div>'
        dialog = QDialog(self.window())
        dialog.setWindowTitle(I18n.gen_str(en="SOP Document", zh="SOP文档"))
        dialog.resize(400, 200)
        label = QLabel()
        label.setText(f'<a href="{sop_link}">{sop_name}</a>')
        label.setOpenExternalLinks(True)  # 允许点击打开超链接
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout = QVBoxLayout()
        layout.addWidget(label)
        dialog.setLayout(layout)
        dialog.exec()

    def select_file(self, message=''):
        file_path = QFileDialog.getExistingDirectory(
            self,
            message,
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly
        )
        if not file_path:
            self.show_message_window(I18n.gen_str(en="No file path selected!", zh="未选择文件路径！"), I18n.gen_str(en="Notice", zh="提示"))
        return file_path

    # 反馈信息
    def one_click_upload(self):
        # 第一步：选择待上传的日志文件路径
        log_file_path = self.select_file(I18n.gen_str(en='Select the log file path to upload', zh='选择待上传的日志文件路径'))

        # 第二步：选择上传的目标路径
        # upload_target_path = self.select_file('选择上传的目标路径')

        if not log_file_path:
            return

        # 第三步：确认弹窗
        confirm_message = (f"{I18n.gen_str(en='The log file path you selected is:', zh='您选择的日志文件路径为：')}\n{log_file_path}\n\n"
                           # f"您选择的目标路径为：\n{upload_target_path}\n\n"
                           f"{I18n.gen_str(en='Please confirm whether to start uploading?', zh='请确认是否开始上传？')}")
        confirm = self.show_confirmation_window(confirm_message, select_name=(I18n.gen_str(en='Yes', zh='是'), I18n.gen_str(en='No', zh='否')))
        if not confirm:
            self.show_message_window(I18n.gen_str(en="Upload operation has been cancelled!", zh="已取消上传操作！"), I18n.gen_str(en="Notice", zh="提示"))
            return

        # 第四步：调用 reporter 的上传方法
        try:
            self.statusBar().showMessage(I18n.gen_str(en="Uploading, please wait...", zh="正在上传，请稍候..."))
            time.sleep(3)
            scheme_config = GuiOptions.instance.config_class.get_instance()
            # remote_path = os.path.relpath(upload_target_path, scheme_config.logs_uploader_path)
            upload_target_path = os.path.join('error_logs', datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
            logs_uploader = scheme_config.logs_uploader
            logs_uploader.upload(log_file_path, upload_target_path, False)

            QMessageBox.information(
                self,
                I18n.gen_str(en="Upload Successful", zh="上传成功"),
                f"{I18n.gen_str(en='The log file has been successfully uploaded to the target path!', zh='日志文件已成功上传到目标路径！')}\n\n"
                f"{I18n.gen_str(en='Log path:', zh='日志路径：')}{log_file_path}\n"
                f"{I18n.gen_str(en='Target path:', zh='目标路径：')}{os.path.join(str(scheme_config.logs_uploader_path), upload_target_path)}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                I18n.gen_str(en="Upload Failed", zh="上传失败"),
                f"{I18n.gen_str(en='An error occurred during the upload process!', zh='上传过程中发生错误！')}\n\n"
                f"{I18n.gen_str(en='Error message:', zh='错误信息：')}{e}，{I18n.gen_str(en='Please check the remote NAS disk path!', zh='请检查远端NAS盘路径！')}"
            )
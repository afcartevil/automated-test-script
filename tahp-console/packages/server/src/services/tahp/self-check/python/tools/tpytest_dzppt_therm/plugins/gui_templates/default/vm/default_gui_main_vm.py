import asyncio
import glob
import os

from PyQt6.QtWidgets import QMessageBox
from gui_templates.default.gui_options import GuiOptions

from dataclasses import dataclass, asdict
from functools import cached_property
from typing import List, Optional

from PyQt6.QtCore import pyqtSignal, QObject, QThread
from PyQt6.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton
from powertrde import env
from powertrde.framework.defines import HasHandledException
from powertrde.framework.i18n import I18n
from powertrde.framework.tran_logger import t_log
from powertrde.utils import yaml_utils, collection_utils, misc_utils
from powertrde.utils.trde import adb
from qt_extends.q_view_model import QViewModel
from tpytest.scheme.scheme_test_env import get_scheme_env
from tpytest_extends.utils import tests_utils
from update_version.feishu_updater import FeiShuUpdater
from update_version.updater import GitUpdater


@dataclass
class DefaultGuiMainVMConfig:
    case_set_record: str = ''
    pretest_level_record: int = 0
    app_pretest_record: int = -1
    device_id_record: str = ''
    c_device_id_record: str = ''
    o_device_id_record: str = ''
    task_id_record: str = ''
    powermonitor_num_record: str = ''
    runtime_overwrite_record = None

    def __getstate__(self):
        state = self.__dict__.copy()
        # 跳过不可序列化字段
        if "runtime_overwrite_record" in state:
            del state["runtime_overwrite_record"]
        return state

    def parse(self, merged_config):
        self.case_set_record = merged_config.configured_config_dict.get('case_set_record', '')
        self.pretest_level_record = merged_config.configured_config_dict.get('pretest_level_record', -999)
        self.app_pretest_record = merged_config.configured_config_dict.get('app_pretest_record', -999)
        self.device_id_record = merged_config.configured_config_dict.get('device_id_record', '')
        self.c_device_id_record = merged_config.configured_config_dict.get('c_device_id_record', '')
        self.o_device_id_record = merged_config.configured_config_dict.get('o_device_id_record', '')
        self.task_id_record = merged_config.configured_config_dict.get('task_id_record', '')
        # self.powermonitor_num_record = merged_config.configured_config_dict.get('powermonitor_num_record', '')

    def sync_to_env(self):
        _overwrite_record = self.runtime_overwrite_record

        if _overwrite_record is None:
            _overwrite_record = {}

        _case_set: Optional[str] = _overwrite_record.pop('case_set', None)
        if _case_set is not None:
            self.case_set_record = _case_set

        _pretest_level: Optional[int] = _overwrite_record.pop('pretest_level', None)
        if _pretest_level is not None:
            self.pretest_level_record = _pretest_level

        _app_pretest: Optional[int] = _overwrite_record.pop('app_pretest', None)
        if _app_pretest is not None:
            self.app_pretest_record = _app_pretest

        _device_id: Optional[str] = _overwrite_record.pop('device_id', None)
        if _device_id is not None:
            self.device_id_record = _device_id

        _c_device_id: Optional[str] = _overwrite_record.pop('c_device_id', None)
        if _c_device_id is not None:
            self.c_device_id_record = _c_device_id

        _o_device_id: Optional[str] = _overwrite_record.pop('o_device_id', None)
        if _o_device_id is not None:
            self.o_device_id_record = _o_device_id

        _task_id: Optional[str] = _overwrite_record.pop('task_id', None)
        if _task_id is not None:
            self.task_id_record = _task_id

        _powermonitor_num: Optional[str] = _overwrite_record.pop('powermonitor_num_record', None)
        if _powermonitor_num is not None:
            self.powermonitor_num_record = _powermonitor_num

        env.set_scheme_shared_kwargs_kv('case_set', self.case_set_record)
        if not self.pretest_level_record == -999:
            env.set_scheme_shared_kwargs_kv('pretest_level', self.pretest_level_record)
        if not self.app_pretest_record == -999:
            env.set_scheme_shared_kwargs_kv('app_pretest', self.app_pretest_record)
        env.set_scheme_shared_kwargs_kv('device_id', self.device_id_record)
        env.set_scheme_shared_kwargs_kv('c_device_id', self.c_device_id_record or 'none')
        env.set_scheme_shared_kwargs_kv('o_device_id', self.o_device_id_record or 'none')
        env.set_scheme_shared_kwargs_kv('task_id', self.task_id_record)
        env.set_scheme_shared_kwargs_kv('powermonitor_num', self.powermonitor_num_record or 'none')

        if _overwrite_record:
            env.get_scheme_shared_kwargs().update(_overwrite_record)

    @classmethod
    def parse_from(cls, merged_config):
        ins = cls()
        ins.parse(merged_config)
        return ins


class UpdateWorker(QObject):
    progress = pyqtSignal(str, int, int)  # stage, current, total
    message = pyqtSignal(str)
    finished = pyqtSignal(bool, str)  # success, message
    error = pyqtSignal(str)

    def __init__(self, team: str, name: str, do_backup: bool = True):
        super().__init__()
        self._team = team
        self._name = name
        self._do_backup = do_backup

    def _on_progress(self, stage: str, current: int, total: int):
        # 在工作线程内触发，由Qt自动切回主线程的槽
        try:
            self.progress.emit(stage, current, total)
        except Exception:
            pass

    def run(self):
        try:
            # 尝试使用飞书更新器（配置读取在FeiShuUpdater内部完成）
            feishu_updater = FeiShuUpdater(team=self._team, name=self._name, on_progress=self._on_progress)
            
            if feishu_updater.enabled:
                # 使用飞书更新
                if self._do_backup:
                    self.message.emit(I18n.gen_str("Backing up project...","正在备份项目..."))
                self.message.emit(I18n.gen_str(
                    "Preparing overseas update package..." if feishu_updater.is_overseas else "Preparing to download update package...",
                    "准备海外更新包..." if feishu_updater.is_overseas else "准备下载更新包..."
                ))
                feishu_updater.apply_update(do_backup=self._do_backup, is_overseas=feishu_updater.is_overseas)
                self.finished.emit(True, I18n.gen_str("Update completed, the application will restart.","更新完成，应用即将重启。"))
                return
            
            # 否则使用Git更新
            git_updater = GitUpdater(team=self._team, name=self._name, on_progress=self._on_progress)
            if not git_updater.enabled:
                self.message.emit(I18n.gen_str(
                    "No update method enabled, please check configuration",
                    "未启用任何更新方式，请检查配置"
                ))
                self.finished.emit(False, I18n.gen_str("Update not enabled","更新未启用"))
                return
            
            if self._do_backup:
                self.message.emit(I18n.gen_str("Backing up project...","正在备份项目..."))
                git_updater.backup_project()
            self.message.emit(I18n.gen_str("Preparing to download update package...","准备下载更新包..."))
            git_updater.update_repo()
            self.finished.emit(True, I18n.gen_str("Update completed, the application will restart.","更新完成，应用即将重启。"))
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False, I18n.gen_str(f"Update failed: {e}",f"更新失败: {e}"))


class DefaultGuiMainVM(QViewModel):

    def __init__(self):
        super().__init__()
        self.ui_binder = None
        self.child_process_list = []
        self.user_config = GuiOptions.instance.gui_main_vm_config_class.parse_from(self.merged_config)
        self._case_set_index = 0
        self._pretest_level_index = 3
        self._app_pretest_index = 0
        self._task_id = ''
        self._device_id_index = 0
        self._device_id_component = None
        self._device_id_model_component = None
        self._c_device_id_index = 0
        self._c_device_id_component = None
        self._c_device_id_model_component = None
        self._o_device_id_index = 0
        self._o_device_id_component = None
        self._o_device_id_model_component = None
        self._power_monitor_index = 0
        self._power_monitor_component = None
        self._power_monitor_model_component = None
        self._hvpm = None
        self._device_id_list = None
        self._c_device_id_list = None
        self._o_device_id_list = None
        self._power_monitor_list = None
        self._init_values()
        # 更新相关
        self._update_thread: QThread | None = None
        self._update_worker: UpdateWorker | None = None

    async def _start_test_async(self):
        await GuiOptions.instance.case_scheme_sub_entry_class.main()

    def _get_runtime_vm(self):
        return GuiOptions.instance.gui_runtime_vm_class.get_instance()

    async def start_test(self, retest_target: str, skip_update_check: bool = False):
        """
        启动测试逻辑，支持使用最近一次报告路径。
        """
        _ = self.runtime_vm
        
        # 若当前正在进行更新，直接阻断测试启动
        if self.is_updating():
            t_log.info(I18n.gen_str(
                "Detected an update task in progress, test start has been blocked.",
                "检测到更新任务正在执行，已阻断测试启动。"
            ))
            try:
                self.update_message.emit(I18n.gen_str(
                    "Updating in progress, the test will retry later…",
                    "正在更新中，测试将稍后再试…"
                ))
            except Exception:
                pass
            return
        
        try:
            # 同步用户配置到环境变量
            self.user_config.sync_to_env()

            # 如果有复测路径，将其设置到测试环境中
            env.set_scheme_shared_kwargs_kv('retest_target', retest_target)

            # 在真正开始测试前检查更新；若需要更新则阻断测试
            if not skip_update_check:
                need_block = self.check_for_updates()
                if need_block:
                    # 用户选择更新或强制更新，终止本次测试启动；
                    # 此时会触发 update_started 由窗口层负责禁用控件，这里不做 on_stop_test 以免错误恢复UI
                    return

            # 直到此处才切入测试态，禁用控制区
            self.on_start_test()

            # 启动测试主逻辑
            await self._start_test_async()
        except HasHandledException:
            pass
        except Exception as e:
            t_log.exception(I18n.gen_str(
                f"Failed to start the test: {str(e)}",
                f"启动测试失败：{str(e)}"
            ))
            # 出错时，恢复UI状态并提示
            try:
                self._get_runtime_vm().on_stop_test()
            except Exception:
                pass
            raise e
        finally:
            # 只有真正进入测试流程时 on_start_test 才会被调用；
            # 若前面因更新被阻断并提前 return，则不会执行到这里
            if not self.is_updating():
                # 若并非在更新流程中，恢复UI
                self.on_stop_test()
                await asyncio.sleep(1)

    def stop_test(self):
        try:
            misc_utils.kill_process_tree(env.get_user_env_arg('sub_entry_process').pid)
        except Exception:
            pass
        finally:
            env.set_user_env_arg('sub_entry_process', None)

    def on_start_test(self):
        self.ui_binder.controlBoxGroup.setEnabled(False)
        try:
            self.ui_binder.menuRetest.setEnabled(False)
        except Exception:
            pass
        self.runtime_vm.on_start_test()

    def on_stop_test(self):
        self.ui_binder.controlBoxGroup.setEnabled(True)
        try:
            self.ui_binder.menuRetest.setEnabled(True)
        except Exception:
            pass
        self.runtime_vm.on_stop_test()

    @property
    def runtime_vm(self):
        return self._get_runtime_vm()

    def _init_values(self):
        self.user_config.case_set_record = (self.user_config.case_set_record or self.merged_config.case_set)
        if not self.user_config.case_set_record and self.case_set_list:
            self.user_config.case_set_record = self.case_set_list[0]
        self._case_set_index = collection_utils.index_or_default(self.case_set_list, self.user_config.case_set_record, 0)
        self._pretest_level_index = self.user_config.pretest_level_record + 1 if self.user_config.pretest_level_record != -999 else self.merged_config.pretest_level + 1
        self._app_pretest_index = self.user_config.app_pretest_record + 1 if self.user_config.app_pretest_record != -999 else self.merged_config.app_pretest + 1
        self._task_id = self.user_config.task_id_record
        self._power_monitor_index = collection_utils.index_or_default(self.power_monitor_list, self.user_config.powermonitor_num_record, 0)

    @property
    def scheme_env(self):
        return get_scheme_env()

    @property
    def cache_dir(self):
        return self.scheme_env.scheme_request.cache_dir

    @property
    def user_config_file(self):
        return self.scheme_env.user_config.user_cache_config_file

    @property
    def merged_config(self):
        return self.scheme_env.user_config

    def save_user_config(self):
        yaml_utils.write_yaml(asdict(self.user_config), self.user_config_file, ignore_yaml_error=False)

    @property
    def base_config_dir(self):
        return self.scheme_env.user_config.config_dir

    @cached_property
    def case_set_list(self) -> List[str]:
        search_pattern = os.path.join(self.base_config_dir, 'case_set_*.yaml')
        ret = []
        for file_path in glob.glob(search_pattern):
            ret.append(os.path.basename(file_path)[9:-5])
        return ret

    @property
    def device_id_list(self):
        if self._device_id_list is None or self._c_device_id_list is None or self._o_device_id_list is None:
            self.refresh_device_list()
        return self._device_id_list

    @property
    def c_device_id_list(self):
        if self._device_id_list is None or self._c_device_id_list is None or self._o_device_id_list is None:
            self.refresh_device_list()
        return self._c_device_id_list

    @property
    def o_device_id_list(self):
        if self._device_id_list is None or self._c_device_id_list is None or self._o_device_id_list is None:
            self.refresh_device_list()
        return self._o_device_id_list

    @property
    def power_monitor_list(self):
        if self._power_monitor_list is None:
            self.refresh_power_monitor_list()
        return self._power_monitor_list

    def refresh_device_list(self):
        devices = adb.adb_devices()
        self._device_id_list = []
        self._c_device_id_list = []
        self._o_device_id_list = []
        for d in devices:
            if adb.is_pointer_location_on(d):
                self._c_device_id_list.append(d)
            elif adb.is_fps_show(d):
                self._o_device_id_list.append(d)
            else:
                self._device_id_list.append(d)
        if self._c_device_id_list:
            self._c_device_id_list.append('<None>')
        if self._o_device_id_list:
            self._o_device_id_list.append('<None>')

    def refresh_power_monitor_list(self):
        if GuiOptions.instance.gui_constants_class.SUPPORT_POWER_MONITOR:
            try:
                from pypowertool.union_power_tool import UnionPowerTool
                pm_list = UnionPowerTool.get_pm_sn_list()
                self._power_monitor_list = [f"{sn} ({type})" for sn, type in pm_list]
            except Exception:
                self._power_monitor_list = []
        else:
            self._power_monitor_list = []

    def refresh_view(self, **kwargs):
        self.refresh_device_list()
        self.refresh_power_monitor_list()
        if self.device_id_list:
            self._device_id_index = collection_utils.index_or_default(self.device_id_list, self.merged_config.device_id,
                                                                      0)
        else:
            self._device_id_index = -1

        if self.c_device_id_list:
            self._c_device_id_index = collection_utils.index_or_default(self.c_device_id_list,
                                                                        self.merged_config.c_device_id, 0)
        else:
            self._c_device_id_index = -1

        if self.o_device_id_list:
            self._o_device_id_index = collection_utils.index_or_default(self.o_device_id_list,
                                                                        self.merged_config.o_device_id,
                                                                        0)
        else:
            self._o_device_id_index = -1

        if self.power_monitor_list:
            self._power_monitor_index = collection_utils.index_or_default(self.power_monitor_list, self.user_config.powermonitor_num_record, 0)
        else:
            self._power_monitor_index = -1

        try:
            self.refresh_device_id()
        except Exception:
            pass
        try:
            self.refresh_c_device_id()
        except Exception:
            pass
        try:
            self.refresh_o_device_id()
        except Exception:
            pass
        try:
            self.refresh_power_monitor()
        except Exception:
            pass

    def start(self):
        self.refresh_view()

    # --------------------------------------------------------------------------------------

    case_set_index_signal_changed = pyqtSignal(int)

    @property
    def case_set_index(self) -> int:
        return self._case_set_index

    @case_set_index.setter
    def case_set_index(self, v: int):
        if self._set_case_set_index(v):
            self.case_set_index_signal_changed.emit(v)

    def _set_case_set_index(self, v: int):
        if self._case_set_index != v:
            self._case_set_index = v
            self.user_config.case_set_record = self.case_set_list[self._case_set_index]
            return True
        return False

    def bind_case_set(self, q: QComboBox):
        q.clear()
        q.addItems(self.case_set_list)

        q.currentIndexChanged.connect(self._set_case_set_index)
        self.case_set_index_signal_changed.connect(q.setCurrentIndex)
        self.case_set_index_signal_changed.emit(self.case_set_index)

    # --------------------------------------------------------------------------------------

    pretest_level_index_signal_changed = pyqtSignal(int)

    @property
    def pretest_level_index(self) -> int:
        return self._pretest_level_index

    @pretest_level_index.setter
    def pretest_level_index(self, v: int):
        if self._set_pretest_level_index(v):
            self.pretest_level_index_signal_changed.emit(v)

    def _set_pretest_level_index(self, v: int):
        if self._pretest_level_index != v:
            self._pretest_level_index = v
            self.user_config.pretest_level_record = v - 1
            return True
        return False

    def bind_pretest_level(self, q: QComboBox):
        q.clear()
        _a = I18n.gen_str(en='No Pretest', zh='不测')
        _b = I18n.gen_str(en='State Resume', zh='状态恢复')
        _c = I18n.gen_str(en='Basic', zh='基础')
        _d = I18n.gen_str(en='Full', zh='完整')
        q.addItems([_a, _b, _c, _d])

        q.currentIndexChanged.connect(self._set_pretest_level_index)
        self.pretest_level_index_signal_changed.connect(q.setCurrentIndex)
        self.pretest_level_index_signal_changed.emit(self.pretest_level_index)

    # --------------------------------------------------------------------------------------

    app_pretest_index_signal_changed = pyqtSignal(int)

    @property
    def app_pretest_index(self) -> int:
        return self._app_pretest_index

    @app_pretest_index.setter
    def app_pretest_index(self, v: int):
        if self._set_app_pretest_index(v):
            self.app_pretest_index_signal_changed.emit(v)

    def _set_app_pretest_index(self, v: int):
        if self._app_pretest_index != v:
            self._app_pretest_index = v
            self.user_config.app_pretest_record = v - 1
            return True
        return False

    def bind_app_pretest(self, q: QComboBox):
        q.clear()
        _a = I18n.gen_str(en='Run for Only Full-pretest', zh='完整预测试才跑')
        _b = I18n.gen_str(en='Not Run', zh='不跑')
        _c = I18n.gen_str(en='Run on Any Pretest', zh='凡是预测试就跑')
        q.addItems([_a, _b, _c])

        q.currentIndexChanged.connect(self._set_app_pretest_index)
        self.app_pretest_index_signal_changed.connect(q.setCurrentIndex)
        self.app_pretest_index_signal_changed.emit(self.app_pretest_index)

    # --------------------------------------------------------------------------------------

    device_id_index_signal_changed = pyqtSignal(int)

    @property
    def device_id_index(self) -> int:
        return self._device_id_index

    @device_id_index.setter
    def device_id_index(self, v: int):
        if self._set_device_id_index(v):
            self.device_id_index_signal_changed.emit(v)

    def _set_device_id_index(self, v: int):
        if self._device_id_index != v:
            self._device_id_index = v
            if self._device_id_index >= 0:
                self.user_config.device_id_record = self.device_id_list[self._device_id_index]
                if self.user_config.device_id_record == '<None>':
                    self.user_config.device_id_record = 'none'
                model = adb.device_model_simple(self.user_config.device_id_record)
                self._device_id_model_component.setText(I18n.gen_str(f'DUT[{model}]', f'测试机[{model}]'))
            else:
                self.user_config.device_id_record = ''
                self._device_id_model_component.setText(I18n.gen_str('DUT', f'测试机'))
            return True
        return False

    def bind_device_id(self, q: QComboBox, q_label: QLabel):
        self._device_id_component = q
        self._device_id_model_component = q_label
        q.currentIndexChanged.connect(self._set_device_id_index)
        self.device_id_index_signal_changed.connect(q.setCurrentIndex)
        self.device_id_index_signal_changed.emit(self.device_id_index)

    def refresh_device_id(self):
        self._device_id_component.clear()
        self._device_id_component.addItems(self.device_id_list)
        target_index = self._device_id_index
        self._device_id_index = -2
        self.device_id_index = target_index

    # --------------------------------------------------------------------------------------

    c_device_id_index_signal_changed = pyqtSignal(int)

    @property
    def c_device_id_index(self) -> int:
        return self._c_device_id_index

    @c_device_id_index.setter
    def c_device_id_index(self, v: int):
        if self._set_c_device_id_index(v):
            self.c_device_id_index_signal_changed.emit(v)

    def _set_c_device_id_index(self, v: int):
        if self._c_device_id_index != v:
            self._c_device_id_index = v
            if self._c_device_id_index >= 0:
                self.user_config.c_device_id_record = self.c_device_id_list[self._c_device_id_index]
                if self.user_config.c_device_id_record == '<None>':
                    self.user_config.c_device_id_record = 'none'
                    self._c_device_id_model_component.setText(I18n.gen_str(f'AUX', f'辅助机'))
                else:
                    c_model = adb.device_model_simple(self.user_config.c_device_id_record)
                    self._c_device_id_model_component.setText(I18n.gen_str(f'AUX[{c_model}]', f'辅助机[{c_model}]'))
            else:
                self.user_config.c_device_id_record = ''
                self._c_device_id_model_component.setText(I18n.gen_str(f'AUX', f'辅助机'))
            return True
        return False

    def bind_c_device_id(self, q: QComboBox, q_label: QLabel):
        self._c_device_id_component = q
        self._c_device_id_model_component = q_label
        q.currentIndexChanged.connect(self._set_c_device_id_index)
        self.c_device_id_index_signal_changed.connect(q.setCurrentIndex)
        self.c_device_id_index_signal_changed.emit(self.c_device_id_index)

    def refresh_c_device_id(self):
        self._c_device_id_component.clear()
        self._c_device_id_component.addItems(self.c_device_id_list)
        target_index = self._c_device_id_index
        self._c_device_id_index = -2
        self.c_device_id_index = target_index

    # ----------------------------------------------------
    o_device_id_index_signal_changed = pyqtSignal(int)

    @property
    def o_device_id_index(self) -> int:
        return self._o_device_id_index

    @o_device_id_index.setter
    def o_device_id_index(self, v: int):
        if self._set_o_device_id_index(v):
            self.o_device_id_index_signal_changed.emit(v)

    def _set_o_device_id_index(self, v: int):
        if self._o_device_id_index != v:
            self._o_device_id_index = v
            if self._o_device_id_index >= 0:
                self.user_config.o_device_id_record = self.o_device_id_list[self._o_device_id_index]
                if self.user_config.o_device_id_record == '<None>':
                    self.user_config.o_device_id_record = 'none'
                    self._o_device_id_model_component.setText(I18n.gen_str(f'OBSV', f'观测机'))
                else:
                    o_model = adb.device_model_simple(self.user_config.o_device_id_record)
                    self._o_device_id_model_component.setText(I18n.gen_str(f'OBSV[{o_model}]', f'观测机[{o_model}]'))
            else:
                self.user_config.o_device_id_record = ''
                self._o_device_id_model_component.setText(I18n.gen_str(f'OBSV', f'观测机'))
            return True
        return False

    def bind_o_device_id(self, q: QComboBox, q_label: QLabel):
        self._o_device_id_component = q
        self._o_device_id_model_component = q_label
        q.currentIndexChanged.connect(self._set_o_device_id_index)
        self.o_device_id_index_signal_changed.connect(q.setCurrentIndex)
        self.o_device_id_index_signal_changed.emit(self.o_device_id_index)

    def refresh_o_device_id(self):
        self._o_device_id_component.clear()
        self._o_device_id_component.addItems(self.o_device_id_list)
        target_index = self._o_device_id_index
        self._o_device_id_index = -2
        self.o_device_id_index = target_index

    # --------------------------------------------------------------------------------------

    task_id_signal_changed = pyqtSignal(str)

    @property
    def task_id(self) -> str:
        return self._task_id

    @task_id.setter
    def task_id(self, v: str):
        if self._set_task_id(v):
            self.task_id_signal_changed.emit(v)

    def _set_task_id(self, v: str):
        if self._task_id != v:
            self._task_id = v
            self.user_config.task_id_record = v
            return True
        return False

    def bind_task_id(self, q: QLineEdit):
        # 设置当前文本框中的值为当前的 task_id
        q.setText(self.task_id)

        # 当文本框内容发生变化时，更新 task_id
        def on_text_changed(text):
            self.task_id = text

        q.textChanged.connect(on_text_changed)

        # 当 task_id 属性发生变化时，更新文本框中的值
        self.task_id_signal_changed.connect(lambda v: q.setText(v))

        # 初始化时同步信号
        self.task_id_signal_changed.emit(self.task_id)

    # --------------------------------------------------------------------------------------

    update_started = pyqtSignal()
    update_message = pyqtSignal(str)
    update_progress = pyqtSignal(str, int, int)
    update_finished = pyqtSignal(bool, str)
    update_no_update = pyqtSignal(str)

    def check_for_updates(self, show_no_update_message: bool = False, is_manual: bool = False):
        """
        检查更新，优先检查飞书更新（仅odm/overseas模式），否则使用Git更新。
        """
        if self.is_updating():
            t_log.info(I18n.gen_str(
                "Update in progress, ignoring manual check request.",
                "更新进行中，忽略手动检查请求。"
            ))
            try:
                self.update_message.emit(I18n.gen_str(
                    "Updating in progress, please try again later…",
                    "正在更新中，请稍后再试…"
                ))
            except Exception:
                pass
            return False

        try:
            # 获取发布模式
            publish_mode = getattr(env, 'PUBLISH_MODE', '')
            
            # 定义进度回调函数（仅在手动检查时使用）
            def progress_callback(stage: str, current: int, total: int):
                try:
                    self.update_progress.emit(stage, current, total)
                except Exception:
                    pass
            
            # 飞书更新仅在 odm 或 overseas 模式下可用
            if publish_mode in ('odm', 'overseas'):
                # 仅在手动检查时传入进度回调，自动检查时不传入（避免显示进度条）
                on_progress = progress_callback if is_manual else None
                feishu_updater = FeiShuUpdater(team=env.scheme.team, name=env.scheme.name, on_progress=on_progress)
                
                if feishu_updater.enabled:
                    # 使用飞书更新
                    return self._handle_feishu_update(feishu_updater, show_no_update_message, is_manual)
                else:
                    t_log.warning(I18n.gen_str(
                        f"PUBLISH_MODE is '{publish_mode}' but feishu_updater is not enabled",
                        f"发布模式为 '{publish_mode}' 但飞书更新未启用"
                    ))
            
            # 使用Git更新器（同样只在手动检查时传入进度回调）
            on_progress = progress_callback if is_manual else None
            git_updater = GitUpdater(team=env.scheme.team, name=env.scheme.name, on_progress=on_progress)
            
            if not git_updater.enabled:
                # 两个更新器都未启用，直接提示用户
                t_log.warning(I18n.gen_str(
                    "No update method enabled, please check configuration",
                    "未启用任何更新方式，请检查配置"
                ))
                if is_manual:
                    # 手动检查时，弹出提示
                    self.update_no_update.emit(I18n.gen_str(
                        "No update method enabled.\nPlease check git_updater or feishu_updater configuration in base_config.yaml",
                        "未启用任何更新方式\n请检查 base_config.yaml 中的 git_updater 或 feishu_updater 配置"
                    ))
                return False
            
            return self._handle_git_update(git_updater, show_no_update_message, is_manual)
            
        except Exception as e:
            t_log.exception(I18n.gen_str(f"Update check failed: {e}", f"更新检查失败: {e}"))
            return False

    # -------------------- FeiShuUpdater 处理逻辑 -------------------- #
    def _handle_feishu_update(self, updater, show_no_update_message, is_manual):
        try:
            # 下载元数据（如果传入了on_progress回调，会自动显示进度）
            try:
                updater._progress_stage = "meta"
                meta = updater.get_remote_Specify_version()
            finally:
                try:
                    updater._progress_stage = None
                except Exception:
                    pass
            remote_v = str(meta.get("version", "0.0.0"))
            update_level = int(meta.get("update_level", 0))
            notes = meta.get("release_notes")
            remote_weight = int(meta.get("total_update_level_weight", 0))
            local_weight = self._get_local_weight(updater)
            if remote_weight - local_weight >= 10000:
                update_level = 2
            note_text = self._format_notes(notes)
            if updater.has_update():
                pm = getattr(env, 'PUBLISH_MODE', '')
                if update_level >= 2:
                    self.update_message.emit(I18n.gen_str(
                        f"Mandatory update found v{remote_v}, preparing to download update package...",
                        f"发现必须更新 v{remote_v}，准备下载更新包..."
                    ))
                    self._start_update_thread(do_backup=True)
                    return True
                if update_level == 1:
                    return self._prompt_update(remote_v, note_text)
                if is_manual:
                    return self._prompt_update(remote_v, note_text)
                t_log.info(I18n.gen_str(
                    "Normal update (auto detection), no popup, continue execution.",
                    "普通更新（自动检测），不弹窗，继续执行。"
                ))
                return False
            else:
                t_log.info(I18n.gen_str("Already the latest version ✅", "已是最新版本 ✅"))
                if show_no_update_message:
                    self.update_no_update.emit(I18n.gen_str("Already the latest version", "已是最新版本"))
                return False
        except Exception as e:
            t_log.warning(I18n.gen_str(f"FeiShu update check failed: {e}", f"FeiShu 更新检查失败: {e}"))
            return False

    # -------------------- GitUpdater 处理逻辑 -------------------- #
    def _handle_git_update(self, updater, show_no_update_message, is_manual):
        try:
            meta = updater.get_remote_meta()
            remote_v = str(meta.get("version", "0.0.0"))
            update_level = int(meta.get("update_level", 0))
            notes = meta.get("release_notes")

            note_text = self._format_notes(notes)

            if updater.has_update():
                return self._process_update(remote_v, update_level, note_text, is_manual)
            else:
                t_log.info(I18n.gen_str("Already the latest version ✅", "已是最新版本 ✅"))
                if show_no_update_message:
                    self.update_no_update.emit(I18n.gen_str("Already the latest version", "已是最新版本"))
                return False
        except Exception as e:
            t_log.warning(I18n.gen_str(f"Git update check failed: {e}", f"Git 更新检查失败: {e}"))
            return False

    # -------------------- 公共处理逻辑 -------------------- #
    def _process_update(self, remote_v, update_level, note_text, is_manual):
        """统一处理更新策略和弹窗逻辑"""
        if update_level >= 2:
            # 强制更新
            self.update_message.emit(I18n.gen_str(
                f"Mandatory update found v{remote_v}, preparing to download update package...",
                f"发现必须更新 v{remote_v}，准备下载更新包..."
            ))
            self._start_update_thread(do_backup=True)
            return True

        # 推荐更新
        if update_level == 1:
            return self._prompt_update(remote_v, note_text)

        # 普通更新：手动弹框，自动检测不弹
        if is_manual:
            return self._prompt_update(remote_v, note_text)

        t_log.info(I18n.gen_str(
            "Normal update (auto detection), no popup, continue execution.",
            "普通更新（自动检测），不弹窗，继续执行。"
        ))
        return False

    def _get_local_weight(self, updater):
        """获取 FeiShuUpdater 本地 total_update_level_weight"""
        local_weight = 0
        try:
            name = getattr(env.scheme, 'name', None)
            if name:
                local_yaml = os.path.join(env.PROJ_DIR, f"{name}_version.yaml")
                if os.path.exists(local_yaml):
                    data = yaml_utils.read_yaml(local_yaml, ignore_yaml_error=False)
                    lw = data.get("total_update_level_weight")
                    if lw is not None:
                        local_weight = int(lw)
        except Exception:
            pass

        if local_weight == 0:
            try:
                local_ver = updater.get_local_version()
                local_meta = updater.get_remote_Specify_version(local_ver)
                local_weight = int(local_meta.get("total_update_level_weight", 0))
            except Exception:
                pass
        return local_weight

    def _format_notes(self, notes):
        """格式化更新说明"""
        if not notes:
            return ""
        if isinstance(notes, list):
            return I18n.gen_str("\n\nUpdate Notes:\n- " + "\n- ".join(str(x) for x in notes),
                                "\n\n更新说明：\n- " + "\n- ".join(str(x) for x in notes))
        return I18n.gen_str(f"\n\nUpdate Notes:\n{notes}", f"\n\n更新说明：\n{notes}")

    def _prompt_update(self, remote_v, note_text):
        """弹窗提示更新"""
        from PyQt6.QtWidgets import QMessageBox as _QMB
        reply = _QMB.question(
            None,
            I18n.gen_str("New Version Found", "发现新版本"),
            I18n.gen_str(
                f"Detected new version v{remote_v}, update and restart now?\n"
                "(The application will exit and restart after download is complete)"
                f"{note_text}",
                f"检测到新版本 v{remote_v}，是否立即更新并重启？\n"
                "（下载完成后应用将自动退出并重启）"
                f"{note_text}"
            ),
            _QMB.StandardButton.Yes | _QMB.StandardButton.No,
            _QMB.StandardButton.Yes
        )
        if reply == _QMB.StandardButton.Yes:
            self.update_message.emit(I18n.gen_str(
                "Preparing to download update package...",
                "准备下载更新包..."
            ))
            self._start_update_thread(do_backup=True)
            return True
        else:
            # 用户取消更新，触发完成信号以关闭进度条
            try:
                self.update_finished.emit(False, I18n.gen_str(
                    "Update cancelled by user",
                    "用户取消更新"
                ))
            except Exception:
                pass
            return False

    def is_updating(self) -> bool:
        """当前是否有更新任务在进行中"""
        return self._update_thread is not None

    def _start_update_thread(self, do_backup: bool = True):
        try:
            if self._update_thread is not None:
                # 已有更新任务在执行，避免重复启动
                t_log.warning(I18n.gen_str(
                    "An update task is already running, ignoring new start request.",
                    "已有更新任务在执行，忽略新的启动请求。"
                ))
                return

            worker = UpdateWorker(env.scheme.team, env.scheme.name, do_backup=do_backup)
            thread = QThread()
            worker.moveToThread(thread)

            # 透传工作线程信号到VM信号
            worker.progress.connect(self.update_progress)
            worker.message.connect(self.update_message)

            def _on_finished(success: bool, msg: str):
                # 转发并清理
                try:
                    self.update_finished.emit(success, msg)
                finally:
                    try:
                        thread.quit()
                        thread.wait(2000)
                    except Exception:
                        pass
                    self._update_thread = None
                    self._update_worker = None

            worker.finished.connect(_on_finished)
            worker.error.connect(
                lambda m: self.update_message.emit(I18n.gen_str(f"Update failed: {m}",f"更新失败: {m}")))
            thread.started.connect(worker.run)

            # 启动
            self._update_thread = thread
            self._update_worker = worker
            self.update_started.emit()
            thread.start()
        except Exception as e:
            t_log.exception(I18n.gen_str(f"Failed to start update thread: {e}",f"启动更新线程失败: {e}"))

    # --------------------------------------------------------------------------------------

    @property
    def base_last_runtime_log_dir(self):
        return tests_utils.get_last_runtime_log_dir(GuiOptions.instance.gui_constants_class.SCHEME_NAME)

    @property
    def last_runtime_log_dir(self):
        return self.last_runtime_log_dir_from_base(self.base_last_runtime_log_dir)

    @property
    def last_runtime_meta_report_dir(self):
        return self.last_runtime_meta_report_dir_from_base(self.base_last_runtime_log_dir)

    # 区别retests里面的最新文件
    def last_runtime_log_dir_from_base(self, base_runtime_log_dir):
        # 检查是否存在 retests 文件夹
        retests_dir = os.path.join(base_runtime_log_dir, "retests")
        if os.path.exists(retests_dir):
            subdirs = [os.path.join(retests_dir, d) for d in os.listdir(retests_dir)]
            if subdirs:
                # 按目录名称中时间戳排序，获取最新目录
                latest_subdir = max(subdirs, key=lambda d: os.path.basename(d))
                return latest_subdir
        return base_runtime_log_dir

    def last_runtime_meta_report_dir_from_base(self, base_runtime_log_dir):
        return os.path.join(self.last_runtime_log_dir_from_base(base_runtime_log_dir), 'meta_report')

    def bind_fill_last_task_id(self, fillLast_button: QPushButton, task_id_input: QLineEdit):
        def fill_task_id_from_log():
            session_runtime_config_path = os.path.join(self.last_runtime_meta_report_dir, "session_runtime_config.yaml")

            if not os.path.exists(session_runtime_config_path):
                QMessageBox.warning(
                    None,
                    I18n.gen_str("File Not Found", "文件不存在"),
                    I18n.gen_str(f"File not found: {session_runtime_config_path}",
                                 f"未找到文件: {session_runtime_config_path}")
                )
                return
            try:
                data = yaml_utils.read_yaml(session_runtime_config_path)
                task_id = data.get('task_id', '')
                if not task_id:
                    task_id_input.setText('')
                    QMessageBox.warning(
                        None,
                        I18n.gen_str("task_id Not Found", "task_id 不存在"),
                        I18n.gen_str(
                            f"No 'task_id' found in file: {session_runtime_config_path}",
                            f"{session_runtime_config_path} 文件中未找到 'task_id'"
                        )
                    )
                    return
                task_id_input.setText(task_id)
                self.task_id = task_id
                QMessageBox.information(
                    None,
                    I18n.gen_str("Fill Successful", "填充成功"),
                    I18n.gen_str(f"Successfully filled task ID: {task_id}", f"已成功填充任务ID: {task_id}")
                )
            except Exception as e:
                task_id_input.setText('')
                QMessageBox.critical(
                    None,
                    I18n.gen_str("Read Failed", "读取失败"),
                    I18n.gen_str(f"Error occurred while reading file: {str(e)}", f"读取文件时发生错误: {str(e)}")
                )

        fillLast_button.clicked.connect(fill_task_id_from_log)

    def bind_disable_button_task_id(self, disable_button: QPushButton, fillLast_button: QPushButton, task_id_input: QLineEdit):
        def update_state():
            if disable_button.text() == '禁用':
                # 设置 fillLast_button 和 task_id_input 为不可用
                fillLast_button.setEnabled(False)
                task_id_input.setEnabled(False)
                disable_button.setText(I18n.gen_str("Enable", "启用"))
            else:
                # 恢复 fillLast_button 和 task_id_input 的可用状态
                fillLast_button.setEnabled(True)
                task_id_input.setEnabled(True)
                disable_button.setText(I18n.gen_str("Disable", "禁用"))

        disable_button.clicked.connect(update_state)  # 点击触发

    # --------------------------------------------------------------------------------------

    power_monitor_index_signal_changed = pyqtSignal(int)

    @property
    def power_monitor_index(self) -> int:
        return self._power_monitor_index

    @power_monitor_index.setter
    def power_monitor_index(self, v: int):
        if self._set_power_monitor_index(v):
            self.power_monitor_index_signal_changed.emit(v)

    def _set_power_monitor_index(self, v: int):
        if self._power_monitor_index != v:
            self._power_monitor_index = v
            if self._power_monitor_index >= 0:
                # 从显示文本中提取sn，例如"123456（hvpm）" -> "123456"
                display_text = self.power_monitor_list[self._power_monitor_index]
                sn = display_text.split(" ")[0]
                self.user_config.powermonitor_num_record = sn
                env.set_scheme_shared_kwargs_kv('power_monitor', sn)
            else:
                self.user_config.powermonitor_num_record = ''
                env.set_scheme_shared_kwargs_kv('power_monitor', '')
            return True
        return False

    def bind_power_monitor(self, q: QComboBox, q_label: QLabel):
        self._power_monitor_component = q
        self._power_monitor_model_component = q_label
        q.currentIndexChanged.connect(self._set_power_monitor_index)
        self.power_monitor_index_signal_changed.connect(q.setCurrentIndex)
        self.power_monitor_index_signal_changed.emit(self.power_monitor_index)

    def refresh_power_monitor(self):
        self._power_monitor_component.clear()
        self._power_monitor_component.addItems(self.power_monitor_list)
        target_index = self._power_monitor_index
        self._power_monitor_index = -2
        self.power_monitor_index = target_index

    # --------------------------------------------------------------------------------------

    hvpm_signal_changed = pyqtSignal(str)

    @property
    def hvpm(self) -> str:
        return self._hvpm

    @hvpm.setter
    def hvpm(self, v: str):
        if self._set_hvpm(v):
            self.hvpm_signal_changed.emit(v)

    def _set_hvpm(self, v: str):
        if self._hvpm != v:
            self._hvpm = v
            self.user_config.powermonitor_num_record = v
            return True
        return False

    def bind_hvpm(self, q: QLineEdit):
        # 设置当前文本框中的值为当前的 hvpm
        q.textChanged.connect(self._set_hvpm)

        # 当 hvpm 属性发生变化时，更新文本框中的值
        self.hvpm_signal_changed.connect(q.setText)

        # 发送初始值给绑定框体
        self.hvpm_signal_changed.emit(self.hvpm)

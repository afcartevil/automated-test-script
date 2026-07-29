import os
import time

from tpytest.scheme.scheme_test_env import SchemeTestEnv, get_scheme_env
from tpy_aw.u2d_test_helper import U2DTestHelper
from tpytest.scheme.scheme_user_config import SchemeUserConfig
from tpytest_extends.scheme.accounts_static_info import AccountsStaticInfo
from tpytest_extends.utils import tests_utils


def _get_account_dict(_accounts_bundle: str):
    account_info = AccountsStaticInfo.get_default_table().get_info_with_default(_accounts_bundle, None)
    assert account_info, f'Unable to find the account bundle named "{_accounts_bundle}" in the online account registry!'
    return account_info.account_dict


class SchemeExtendTestEnv(SchemeTestEnv):
    def __init__(self):
        SchemeUserConfig.option_accounts_bundle_provider = _get_account_dict
        self._retest_target_to_normalized_target_pair = None
        self._txn_status_dispatcher = None
        self._video_monitor_save_dir = None
        super().__init__()

    @property
    def u2d_helper(self) -> U2DTestHelper:
        return super().u2d_helper

    @property
    def c_u2d_helper(self) -> U2DTestHelper:
        return super().c_u2d_helper

    def get_retest_target_normalized(self):
        _rt = self.user_config.retest_target
        if not _rt:
            return None
        if self._retest_target_to_normalized_target_pair and self._retest_target_to_normalized_target_pair[0] == _rt:
            return self._retest_target_to_normalized_target_pair[1]
        if not os.path.exists(_rt):
            return None
        _new_dir, _, _ = tests_utils.check_to_correct_retest_root_dir(_rt)
        self._retest_target_to_normalized_target_pair = (_rt, _new_dir)
        return _new_dir

    def try_start_txn_status_dispatcher(self):
        if self._txn_status_dispatcher or not self.device_id:
            return
        if self.user_config.txn_status_server_port > 0:
            from tpytest_extends.txn_support.txn_status_dispatcher import TxnStatusDispatcher
            self._txn_status_dispatcher = TxnStatusDispatcher(self.team_name, self.scheme_name, self.device_id, bool(self.user_config.retest_target), ('tcp', '127.0.0.1', self.user_config.txn_status_server_port))
            self._txn_status_dispatcher.start()

    def try_stop_txn_status_dispatcher(self):
        if self._txn_status_dispatcher:
            self._txn_status_dispatcher.stop()
            self._txn_status_dispatcher = None

    def start_video_monitor(self, custom_dir=None):
        if self._video_monitor_save_dir:
            raise Exception('The video monitor is already recording!')
        target_dir = custom_dir or self.get_session_video_logs_dir()
        try:
            params = {
                'save_own_copy': True,  # 关键: 启用专属副本
                'copy_to_dir': target_dir,  # 自定义文件夹名
            }
            from video_recorder.camera_service_manager import CameraServiceManager
            CameraServiceManager.get_instance().ensure_service_running(params)
            _pool = self.get_resource_lock_pool_by_group_id('VideoMonitor')
            _pool.join_shared_resource('摄像头', params)
            if CameraServiceManager.get_instance().wait_for_recording_active():
                self.logger.info("录像已确认开始，执行关键操作...", ext_event=True)
                # 执行您的操作
            else:
                self.logger.warning("等待录像启动超时!", ext_event=True)
        except Exception:
            self.logger.warning('Unable to import video_monitor module, please make sure that the video_monitor module is installed!', ext_event=True)
            return

        self._video_monitor_save_dir = target_dir

    def stop_video_monitor(self):
        if not self._video_monitor_save_dir:
            return None
        target_dir = self._video_monitor_save_dir
        self._video_monitor_save_dir = None

        target_done_file = os.path.join(target_dir, '.copy_completed')
        timeout = 180

        try:
            _pool = self.get_resource_lock_pool_by_group_id('VideoMonitor')
            _pool.leave_shared_resource('摄像头')
        except Exception:
            self.logger.warning('Unable to import video_monitor module, please make sure that the video_monitor module is installed!', ext_event=True)
            return None

        # 在 timeout 秒内，等待 target_done_file 创建
        while timeout > 0:
            if os.path.exists(target_done_file):
                break
            timeout -= 1
            time.sleep(1)
        else:
            return None

        # 读取 target_done_file，获取视频保存路径（一组）
        video_paths = [line.strip() for line in open(target_done_file, 'r', encoding='utf-8').readlines()]
        # 删除 target_done_file
        os.remove(target_done_file)
        return [os.path.join(target_dir, os.path.basename(video_path)) for video_path in video_paths]

# ------------------------------------------------------------------------


def get_scheme_extend_env() -> SchemeExtendTestEnv:
    env_ins = get_scheme_env()
    if not isinstance(env_ins, SchemeExtendTestEnv):
        raise Exception(
            f'Current scheme env class is {env_ins.__class__.__name__} but not {SchemeExtendTestEnv.__name__}')
    return env_ins

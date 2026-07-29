"""
摄像头服务进程 - 基于 LazySharedPool 共享资源机制
职责:
1. 心跳检测共享资源使用者列表
2. 根据使用者数量自动开始/停止录制
3. 使用者数量变化时主动分割视频
4. 使用者退出时复制其使用期间的录像文件
"""
import os
import sys
import time
import shutil
import glob
from typing import Dict

# 确保可以导入项目模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from powertrde.framework.tran_logger import t_log
from powertrde import env
from powertrde.utils.lazy_shared_pool import LazySharedPool
from plugins.video_recorder.video_recorder_helper import VideoRecorderHelper

# 服务进程互斥锁名称
CAMERA_SERVICE_MUTEX = "Global\\CameraServiceServer_V1_20260106"


class CameraServiceServer:
    """摄像头服务进程 - 参考 _main6_server() 实现"""

    def __init__(self, db_path: str, save_dir: str, check_interval: float = 1.0):
        """
        初始化摄像头服务进程
        
        Args:
            db_path: LazySharedPool 数据库路径(与 env.get_lazy_shared_pool() 相同)
            save_dir: 视频保存目录
            check_interval: 心跳检查间隔(秒)
        """
        # 创建互斥锁(防止重复启动)
        self.mutex = None
        if env.is_run_on_windows():
            try:
                import win32event
                import win32api
                import winerror

                self.mutex = win32event.CreateEvent(None, True, False, CAMERA_SERVICE_MUTEX)
                last_error = win32api.GetLastError()
                if last_error == winerror.ERROR_ALREADY_EXISTS:
                    t_log.warning("[CameraService] 服务进程已存在,退出")
                    if self.mutex:
                        win32api.CloseHandle(self.mutex)
                    sys.exit(0)

                t_log.info("[CameraService] ✓ 互斥锁创建成功")
            except Exception as e:
                t_log.error(f"[CameraService] 创建互斥锁失败: {e}")

        self.db_path = db_path
        self.save_dir = save_dir
        self.check_interval = check_interval

        # 创建独立的 pool 实例用于服务进程
        self.pool = LazySharedPool(
            db_path=db_path,
            group_id="camera-service-server",
            stale_ttl=10.0
        )

        # 录制状态
        self.is_recording = False
        self.last_user_count = 0
        self.video_helper = VideoRecorderHelper.get_instance()

        # 使用者时间段追踪 {group_id: {'join_time': float, 'params': dict}}
        self.user_sessions: Dict[str, dict] = {}

        # 心跳续期配置
        self.heartbeat_interval = 60 * 30  # 每30分钟续期一次
        self.last_heartbeat_time = 0
        self.recording_duration = 60 * 60 * 24  # 1天

        # 自动清理配置 (默认保留2天)
        self.auto_clean_days = 7
        self.cleanup_interval = 60 * 60  # 每小时检查一次
        self.last_cleanup_time = 0


        # 摄像头硬件检测配置
        self.check_camera_interval = 5.0  # 每5秒检查一次
        self.last_check_camera_time = 0
        self.is_camera_connected = True  # 默认为True,首次检查会更新
        self.camera_disconnect_time = 0  # 记录断线时间点

        # 自动退出配置 (5分钟空闲自动退出)
        self.MAX_IDLE_SECONDS = 300
        self.last_idle_time = 0  # 记录空闲开始的时间戳

        t_log.info("[CameraService] " + "=" * 60)
        t_log.info("[CameraService] 摄像头服务进程已启动")
        t_log.info(f"[CameraService] 数据库路径: {db_path}")
        t_log.info(f"[CameraService] 视频保存目录: {save_dir}")
        t_log.info("[CameraService] " + "=" * 60)

    def __del__(self):
        """释放互斥锁"""
        if self.mutex:
            try:
                import win32api
                win32api.CloseHandle(self.mutex)
                t_log.debug("[CameraService] 互斥锁已释放")
            except:
                pass

    def _get_camera_users(self) -> dict:
        """
        获取摄像头共享资源的使用者列表
        
        Returns:
            dict: { group_id: {"joined_at": float, "params": Any, "member_count": int, "last_heartbeat": float} }
        """
        try:
            users = self.pool.list_shared_resource_users('摄像头')
            return users
        except Exception as e:
            t_log.error(f"[CameraService] 获取使用者列表失败: {e}")
            return {}

    def _start_recording(self):
        """启动摄像头录制"""
        if self.is_recording:
            return

        try:
            t_log.info(f"[CameraService] 启动录制 -> 保存目录: {self.save_dir}")

            # 孤儿进程检测与恢复
            # 如果 service 刚启动(is_recording=False)，但 video_recorder.exe 已经在跑
            # 说明这是上次服务意外退出遗留的"孤儿录像"。
            # 为了防止新用户继承到这个已经跑了很久、时间戳很早的录像文件(导致拷贝时被时间过滤掉)，
            # 必须强制分割一下，让新用户从一个全新的、时间戳当前的文件开始。
            from powertrde.utils import misc_utils
            if misc_utils.is_process_running('video_recorder.exe'):
                t_log.warning("[CameraService] 检测到孤儿录像进程在运行, 执行强制分割以重置时间戳...")
                # 尝试分割
                if self.video_helper.split_video():
                    t_log.info("[CameraService] ✓ 孤儿录像已封存, 新录像文件已生成")
                    # 稍微等待文件系统
                    time.sleep(1.0)
                else:
                    t_log.warning("[CameraService] ! 孤儿录像分割失败, 将尝试直接 Update 续期")

            # 使用 VideoRecorderHelper.update_record_from_server() 启动录制
            self.video_helper.update_record_from_server(
                record_duration_in_second=self.recording_duration,
                change_save_dir=self.save_dir
            )

            self.is_recording = True
            t_log.info("[CameraService] ✓ 录制已启动")

        except Exception as e:
            t_log.error(f"[CameraService] 启动录制失败: {e}")

    def _stop_recording(self):
        """停止摄像头录制"""
        if not self.is_recording:
            return

        try:
            t_log.info("[CameraService] 停止录制")

            # 使用 VideoRecorderHelper.stop_record_from_server() 停止录制
            self.video_helper.stop_record_from_server(wait_for_stop=True)

            self.is_recording = False
            t_log.info("[CameraService] ✓ 录制已停止")

        except Exception as e:
            t_log.error(f"[CameraService] 停止录制失败: {e}")

    def _split_video(self):
        """主动触发视频分割"""
        if not self.is_recording:
            return

        try:
            t_log.info("[CameraService] 触发视频分割")

            # 使用 VideoRecorderHelper.split_video() 分割视频
            success = self.video_helper.split_video()

            if success:
                t_log.info("[CameraService] ✓ 视频已分割")
            else:
                t_log.warning("[CameraService] ! 视频分割失败")

        except Exception as e:
            t_log.error(f"[CameraService] 视频分割异常: {e}")

    def _parse_video_timestamp(self, filename: str) -> float:
        """从视频文件名中解析时间戳

        Args:
            filename: 文件名，如 'recording_20251230_192309.avi'

        Returns:
            时间戳(秒)，解析失败返回 0
        """
        import re
        # 匹配文件名中的时间戳: recording_YYYYMMDD_HHMMSS.avi
        match = re.search(r'recording_(\d{8})_(\d{6})', filename)
        if match:
            date_str = match.group(1)  # YYYYMMDD
            time_str = match.group(2)  # HHMMSS
            try:
                # 构造时间字符串: YYYY-MM-DD HH:MM:SS
                datetime_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                # 转换为时间戳
                import datetime
                dt = datetime.datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                return dt.timestamp()
            except Exception:
                return 0
        return 0

    def _copy_user_videos(self, group_id: str, user_info: dict):
        """复制使用者使用期间的视频文件到专属文件夹"""
        try:
            params = user_info.get('params') or {}

            # 检查是否需要保存专属副本
            save_own_copy = params.get('save_own_copy', False)
            if not save_own_copy:
                return

            # 获取使用者的时间段
            join_time = user_info.get('join_time')
            leave_time = time.time()

            if join_time is None:
                t_log.warning(f"[CameraService] 使用者 {group_id[:20]}... 没有加入时间记录,跳过复制")
                return

            # 获取目标文件夹路径（绝对路径）
            copy_to_dir = params.get('copy_to_dir')
            if not copy_to_dir:
                t_log.warning(f"[CameraService] 使用者 {group_id[:20]}... 未指定copy_to_dir参数,跳过复制")
                return

            # 确保目标目录存在
            os.makedirs(copy_to_dir, exist_ok=True)

            t_log.info(f"[CameraService] 开始复制使用者视频到: {copy_to_dir}")
            t_log.info(f"[CameraService]   时间段: {time.strftime('%H:%M:%S', time.localtime(join_time))} - {time.strftime('%H:%M:%S', time.localtime(leave_time))}")

            # 直接扫描保存目录中的所有视频文件
            # 这样可以确保包含所有视频，无论是主动分割还是自动1小时分割
            pattern = os.path.join(self.save_dir, 'recording_*.avi')
            all_video_files = glob.glob(pattern)

            t_log.info(f"[CameraService]   扫描到 {len(all_video_files)} 个视频文件")

            # 筛选时间段内的视频文件（根据文件名中的时间戳）
            copied_count = 0
            copied_filenames = []
            for video_file in all_video_files:
                if not os.path.exists(video_file):
                    continue

                # 从文件名中解析视频开始录制的时间戳
                filename = os.path.basename(video_file)
                video_start_time = self._parse_video_timestamp(filename)

                if video_start_time == 0:
                    t_log.warning(f"[CameraService]   ! 无法解析文件名时间戳: {filename}")
                    continue

                # 判断视频开始时间是否在使用者的时间段内
                # 视频开始时间在加入之后（或稍早一点），且在退出之前（考虑容错）
                # 关键：video_start_time >= join_time 表示这个视频是在使用者加入后才开始录制的
                # 修正: leave_time - 3 是为了过滤掉因本次退出而触发分割产生的新视频文件(通常是0KB)
                # 分割流程: 退出 -> 分割(产生新文件) -> sleep(2) -> 记录leave_time. 新文件start约等于leave_time-2.
                if join_time - 5 <= video_start_time <= leave_time - 5:
                    target_file = os.path.join(copy_to_dir, filename)
                    shutil.copy2(video_file, target_file)
                    copied_count += 1
                    copied_filenames.append(filename)
                    video_time_str = time.strftime('%H:%M:%S', time.localtime(video_start_time))
                    t_log.info(f"[CameraService]   ✓ 复制: {filename} (开始时间: {video_time_str})")

            if copied_count > 0:
                t_log.info(f"[CameraService] ✓ 共复制 {copied_count} 个视频文件到: {copy_to_dir}")
            else:
                t_log.warning(f"[CameraService] ! 没有找到该时间段内的视频文件")

            # 创建拷贝完成标记文件
            marker_file = os.path.join(copy_to_dir, '.copy_completed')
            try:
                with open(marker_file, 'w', encoding='utf-8') as f:
                    for file_name in copied_filenames:
                        f.write(f"{file_name}\n")
                t_log.info(f"[CameraService] ✓ 创建完成标记: {marker_file}")
            except Exception as e:
                t_log.warning(f"[CameraService] 创建完成标记失败: {e}")

        except Exception as e:
            t_log.error(f"[CameraService] 复制使用者视频失败: {e}")
            import traceback
            t_log.error(f"[CameraService] {traceback.format_exc()}")

    def _update_user_sessions(self, current_users: dict):
        """更新使用者会话追踪,检测新加入和退出的使用者"""
        current_group_ids = set(current_users.keys())
        tracked_group_ids = set(self.user_sessions.keys())

        # 检测新加入的使用者
        new_users = current_group_ids - tracked_group_ids
        for group_id in new_users:
            user_info = current_users[group_id]
            self.user_sessions[group_id] = {
                'join_time': time.time(),
                'params': user_info.get('params')
            }
            t_log.info(f"[CameraService] 记录新使用者加入: {group_id[:30]}...")

        # 检测退出的使用者
        left_users = tracked_group_ids - current_group_ids
        for group_id in left_users:
            user_info = self.user_sessions[group_id]
            t_log.info(f"[CameraService] 检测到使用者退出: {group_id[:30]}...")

            # 触发视频复制
            self._copy_user_videos(group_id, user_info)

            # 移除会话记录
            del self.user_sessions[group_id]

    def _heartbeat_renew_recording(self):
        """
        心跳续期录像时间
        只要有使用者存在,就定期刷新 close_delay_time
        """
        if not self.is_recording:
            return

        now = time.time()
        if now - self.last_heartbeat_time < self.heartbeat_interval:
            return

        try:
            t_log.debug("[CameraService] 执行心跳续期")

            # 刷新录像时间(重新调用 update_record_from_server)
            self.video_helper.update_record_from_server(
                record_duration_in_second=self.recording_duration,
                change_save_dir=self.save_dir
            )

            self.last_heartbeat_time = now
            t_log.debug("[CameraService] ✓ 心跳续期成功")

        except Exception as e:
            t_log.warning(f"[CameraService] 心跳续期失败: {e}")

    def _cleanup_old_videos(self):
        """清理过期的视频文件
        
        策略:
        1. 默认清理超过 auto_clean_days (2天) 的文件
        2. 如果有长时间运行的使用者(超过2天),则保护其加入之后的所有视频文件不被删除
        """
        now = time.time()
        if now - self.last_cleanup_time < self.cleanup_interval:
            return

        try:
            t_log.debug("[CameraService] 开始检查过期视频文件...")

            # 1. 计算基础过期时间 (如2天前)
            default_expiration_time = now - (self.auto_clean_days * 24 * 60 * 60)

            # 2. 计算"保护时间点"
            # 如果有使用者正在运行,找出最早加入的时间
            # 我们不能删除(最早加入时间 - 1小时)之后的任何文件,以确保该使用者退出时能拷贝到完整的视频
            earliest_join_time = now
            if self.user_sessions:
                times = [info['join_time'] for info in self.user_sessions.values()]
                earliest_join_time = min(times)
                # 留1小时缓冲
                earliest_join_time -= 3600

            # 3. 最终过期时间 = min(默认过期时间, 最早使用者保护时间)
            # 举例:
            # - 场景A(正常): 默认过期时间是48小时前, 最早使用者是1小时前加入. min=48小时前. -> 清理48小时前的文件.
            # - 场景B(长任务): 默认过期时间是48小时前, 使用者是100小时前加入. min=100小时前. -> 清理100小时前的文件(保留最近100小时的).
            final_expiration_time = min(default_expiration_time, earliest_join_time)

            t_log.debug(f"[CameraService] 清理策略: 默认保留{self.auto_clean_days}天, 当前活跃任务保护至 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(earliest_join_time))}")

            pattern = os.path.join(self.save_dir, 'recording_*.avi')
            all_files = glob.glob(pattern)

            deleted_count = 0
            for file_path in all_files:
                try:
                    filename = os.path.basename(file_path)

                    # 使用文件名中的时间戳而不是文件修改时间
                    # 这样更准确，因为文件名代表了录像实际开始的时间
                    video_start_time = self._parse_video_timestamp(filename)

                    if video_start_time == 0:
                        t_log.debug(f"[CameraService] 无法解析文件名时间戳, 跳过: {filename}")
                        continue

                    if video_start_time < final_expiration_time:
                        os.remove(file_path)
                        deleted_count += 1
                        t_log.info(f"[CameraService] 删除过期视频: {filename} (时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(video_start_time))})")
                except Exception as e:
                    t_log.warning(f"[CameraService] 删除文件失败 {file_path}: {e}")

            if deleted_count > 0:
                t_log.info(f"[CameraService] ✓ 清理完成: 删除了 {deleted_count} 个过期文件")
            else:
                t_log.debug("[CameraService] 没有发现需要清理的文件")

            self.last_cleanup_time = now

        except Exception as e:
            t_log.error(f"[CameraService] 视频清理检查失败: {e}")

    def _check_and_handle_camera_status(self, current_user_count: int):
        """检查摄像头硬件连接状态并处理异常"""
        now = time.time()
        if now - self.last_check_camera_time < self.check_camera_interval:
            return

        self.last_check_camera_time = now

        # 1. 执行硬件检测
        is_connected = self.video_helper.check_camera_hardware()

        # 2. 状态变化处理
        if is_connected != self.is_camera_connected:
            if not is_connected:
                # 状态: 连接 -> 断开
                t_log.warning("[CameraService] ⚠️ 警告: 检测到摄像头硬件断开!")
                self.is_camera_connected = False
                self.camera_disconnect_time = now

            else:
                # 状态: 断开 -> 连接
                t_log.info("[CameraService] ✓ 摄像头硬件已重新连接")
                self.is_camera_connected = True
                self.camera_disconnect_time = 0

                # 如果有用户,自动恢复录像
                if current_user_count > 0:
                    t_log.info("[CameraService] 检测到有活跃用户,尝试自动恢复录像...")
                    # 所以必须重置标志位,允许重新启动
                    self.is_recording = False
                    self._start_recording()

        # 3. 补录机制 (状态未变,但逻辑不一致)
        # 场景: 摄像头是好的,有用户,但不知为何没在录像 (可能是启动失败,或被意外杀掉)
        elif is_connected and current_user_count > 0 and not self.is_recording:
            # 只有在连接状态稳定(>10秒)的情况下才尝试补录,避免刚连上时的不稳定
            if self.camera_disconnect_time == 0 or (now - self.camera_disconnect_time > 10):
                t_log.warning("[CameraService] 发现状态不一致(设备在线+有用户+未录像), 触发补录机制")
                self._start_recording()

    def run(self):
        """运行服务主循环 - 心跳检测"""
        t_log.info("[CameraService] 开始心跳检测循环...")

        try:
            while True:
                # 获取当前使用者列表(参考 _main6_server)
                users = self._get_camera_users()
                current_count = len(users)

                # 1. 优先检测使用者数量变化并调整录像状态
                # 关键: 如果是最后一个使用者退出(1->0),必须先停止录像,确保存盘完毕,然后再执行复制!
                if current_count != self.last_user_count:
                    t_log.info(f"[CameraService] 使用者数量变化: {self.last_user_count} → {current_count}")

                    # 打印使用者详情
                    if current_count > 0:
                        self.last_idle_time = 0  # 重置空闲计时
                        t_log.info(f"[CameraService] 当前使用者列表:")
                        for group_id, info in users.items():
                            params = info.get('params')
                            member_count = info.get('member_count', 0)
                            t_log.info(f"[CameraService]   - group_id: {group_id[:50]}... | 成员数: {member_count} | params: {params}")

                    # 判断是否需要分割视频
                    if self.last_user_count == 0 and current_count == 1:
                        # 0→1: 只开启录像,不分割
                        t_log.info("[CameraService] 首个使用者加入,开启录像")
                        self._start_recording()
                    elif self.last_user_count == 1 and current_count == 0:
                        # 1→0: 只关闭录像,不分割
                        t_log.info("[CameraService] 最后一个使用者退出,关闭录像")
                        self._stop_recording()
                        time.sleep(10)
                        self.last_idle_time = time.time()  # 开始空闲计时
                    elif current_count > 0:
                        # 中间数量变化: 触发分割
                        if self.last_user_count > 0:
                            t_log.info(f"[CameraService] 使用者数量中间变化({self.last_user_count}→{current_count}),触发分割")
                            self._split_video()
                            # 稍微等待一下分割生效,虽然不是绝对保证,但有助于减少文件占用冲突
                            time.sleep(0.5)
                        else:
                            # last_user_count=0, current_count>1: 异常情况,直接开启录像
                            t_log.info(f"[CameraService] 使用者数量从0跳变为{current_count},开启录像")
                            self._start_recording()
                    elif current_count == 0 and self.last_user_count > 1:
                        # 从多个使用者直接降为0: 关闭录像
                        t_log.info(f"[CameraService] 使用者数量从{self.last_user_count}降为0,关闭录像")
                        self._stop_recording()
                        self.last_idle_time = time.time()  # 开始空闲计时

                # 2. 空闲自动退出检查
                if current_count == 0:
                     if self.last_idle_time > 0 and (time.time() - self.last_idle_time > self.MAX_IDLE_SECONDS):
                        t_log.info(f"[CameraService] 服务已空闲超过 {self.MAX_IDLE_SECONDS} 秒, 自动退出以节省资源")
                        break # 跳出循环, 结束进程
                
                # 3. 更新使用者会话追踪 (检测退出并复制视频)
                # 此时如果是退出场景,录像应该已经停止或分割,文件相对安全
                self._update_user_sessions(users)

                self.last_user_count = current_count

                # 心跳续期
                if current_count > 0:
                    self._heartbeat_renew_recording()

                # 定时清理
                self._cleanup_old_videos()

                # 摄像头硬件心跳与状态维护
                self._check_and_handle_camera_status(current_count)

                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            t_log.info("[CameraService] 收到中断信号,正在退出...")
        except Exception as e:
            t_log.error(f"[CameraService] 服务异常: {e}")
            import traceback
            t_log.error(f"[CameraService] {traceback.format_exc()}")
        finally:
            if self.is_recording:
                t_log.info("[CameraService] 清理: 停止录制")
                self._stop_recording()
            t_log.info("[CameraService] 摄像头服务进程已退出")


def start_camera_service(db_path: str, save_dir: str):
    """启动摄像头服务"""
    server = CameraServiceServer(db_path, save_dir)
    server.run()


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python camera_service_server.py <db_path> <save_dir>")
        print("\n示例:")
        print(f"  python camera_service_server.py D:/cache/powertrde_shared_pool.db E:/videos")
        sys.exit(1)

    db_path = sys.argv[1]
    save_dir = sys.argv[2]
    # db_path = r'D:\dz_auto_env_configs\shared\powertrde_shared_pool.db'
    # save_dir = r'E:\Desktop\camera_video_logs'
    #
    # t_log.info(f"[CameraService] 启动参数:")
    # t_log.info(f"[CameraService]   db_path: {db_path}")
    # t_log.info(f"[CameraService]   save_dir: {save_dir}")
    #
    # print(f"启动摄像头服务进程:")
    # print(f"  DB路径: {db_path}")
    # print(f"  保存目录: {save_dir}")
    # print()

    start_camera_service(db_path, save_dir)

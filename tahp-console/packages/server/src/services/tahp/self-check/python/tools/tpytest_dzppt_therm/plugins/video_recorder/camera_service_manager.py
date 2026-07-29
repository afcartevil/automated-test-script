"""
摄像头服务懒加载管理器
职责:
1. 检测服务进程是否运行
2. 按需启动服务进程
3. 从 params 提取配置并传递
"""
import os
import sys
import time
from typing import Optional, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from powertrde import env
from powertrde.framework.tran_logger import t_log
from powertrde.utils import misc_utils

# 服务进程互斥锁名称
CAMERA_SERVICE_MUTEX = "Global\\CameraServiceServer_V1_20260106"


class CameraServiceManager:
    """摄像头服务管理器(单例)"""
    
    _instance = None
    
    def __init__(self):
        self._last_check_time = 0
        self._check_interval = 5.0  # 检查间隔(秒)
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def is_service_running(self) -> bool:
        """
        检测摄像头服务进程是否运行
        
        Returns:
            bool: True=运行中, False=未运行
        """
        if not env.is_run_on_windows():
            return False
        
        try:
            import win32event
            import win32api
            
            # 尝试打开互斥锁
            mutex = win32event.OpenEvent(win32event.SYNCHRONIZE, False, CAMERA_SERVICE_MUTEX)
            if mutex:
                win32api.CloseHandle(mutex)
                return True
        except:
            pass
        
        return False
    
    def ensure_service_running(self, params: Optional[Dict[str, Any]] = None) -> bool:
        """
        确保摄像头服务进程运行,如果未运行则启动
        
        Args:
            params: 使用者参数,可包含:
                - db_path: 数据库路径(可选,默认使用 env.get_lazy_shared_pool().db_path)
                - save_dir: 视频保存目录(可选,默认使用配置)
                
        Returns:
            bool: True=服务已运行或启动成功, False=启动失败
        """
        if not env.is_run_on_windows():
            t_log.warning('[CameraServiceManager] 非 Windows 系统,摄像头服务不可用')
            return False
        
        # 限流检查(避免频繁检测)
        now = time.time()
        if now - self._last_check_time < self._check_interval:
            # 距离上次检查不到5秒,直接返回
            return self.is_service_running()
        self._last_check_time = now
        
        # 检查是否已运行
        if self.is_service_running():
            t_log.debug('[CameraServiceManager] 摄像头服务进程已运行')
            return True
        
        # 提取配置
        params = params or {}
        db_path = params.get('db_path') or env.get_lazy_shared_pool().db_path
        save_dir = params.get('save_dir') or self._get_default_save_dir()
        
        # 启动服务进程
        return self._start_service(db_path, save_dir)
    
    def _get_default_save_dir(self) -> str:
        """获取默认视频保存目录"""
        # 使用默认的 D 盘目录
        default_path = r'D:\camera_service_videos'
        if not os.path.exists(default_path):
            try:
                os.makedirs(default_path, exist_ok=True)
            except Exception:
                # 如果 D 盘不存在或无法创建,回退到临时目录
                import tempfile
                default_path = os.path.join(tempfile.gettempdir(), 'camera_videos')
        
        return default_path
    
    def _start_service(self, db_path: str, save_dir: str) -> bool:
        """
        启动服务进程
        
        Args:
            db_path: 数据库路径
            save_dir: 视频保存目录
            
        Returns:
            bool: True=启动成功, False=启动失败
        """
        try:
            t_log.info(f'[CameraServiceManager] 启动摄像头服务进程')
            t_log.info(f'[CameraServiceManager]   db_path: {db_path}')
            t_log.info(f'[CameraServiceManager]   save_dir: {save_dir}')
            
            # 构造启动命令
            script_path = os.path.join(
                os.path.dirname(__file__),
                'camera_service_server.py'
            )
            
            # 使用 python.exe (不是 pythonw.exe) 以显示终端窗口
            python_exe = sys.executable
            
            # 构造 CMD 命令,在新窗口中启动服务
            # title 设置窗口标题,便于识别
            # /k 保持窗口打开,关闭窗口时自动结束进程
            # /min 最小化启动，不干扰用户视线
            window_title = "摄像头服务进程 - Camera Service"
            cmd = f'start "{window_title}" /min cmd /k ""{python_exe}" "{script_path}" "{db_path}" "{save_dir}""'
            
            t_log.info(f'[CameraServiceManager] 终端窗口标题: {window_title}')
            
            # 使用 shell=True 执行 start 命令
            misc_utils.run_command_detached(cmd, shell=True)
            
            # 等待启动(最多3秒)
            for i in range(6):
                time.sleep(0.5)
                if self.is_service_running():
                    t_log.info('[CameraServiceManager] ✓ 摄像头服务进程启动成功')
                    t_log.info('[CameraServiceManager] 提示: 关闭终端窗口将自动停止服务')
                    return True
            
            t_log.warning('[CameraServiceManager] ! 摄像头服务进程启动超时')
            return False
            
        except Exception as e:
            t_log.error(f'[CameraServiceManager] 启动摄像头服务进程失败: {e}')
            import traceback
            t_log.error(traceback.format_exc())
            return False


    
    def wait_for_recording_active(self, save_dir: str = None, timeout: float = 30.0) -> bool:
        """
        等待摄像头录像真正开始(进程已启动且检测到新视频文件生成)
        
        Args:
            save_dir: 视频保存目录(如果不传则尝试获取默认)
            timeout: 超时时间(秒)
            
        Returns:
            bool: True=录像已激活, False=超时未检测到
        """
        if not env.is_run_on_windows():
            return True
        
        t_log.info(f'[CameraServiceManager] 等待录像激活 (超时: {timeout}s)...')
        start_time = time.time()
        
        # 确定检测目录
        if not save_dir:
            save_dir = self._get_default_save_dir()
            
        # 记录当前的最新文件时间,作为基准
        import glob
        pattern = os.path.join(save_dir, 'recording_*.avi')
        existing_files = set(glob.glob(pattern))
        
        while time.time() - start_time < timeout:
            # 1. 检查录像进程是否运行
            if not misc_utils.is_process_running('video_recorder.exe'):
                time.sleep(0.5)
                continue
            
            # 2. 检查是否有新文件生成
            current_files = set(glob.glob(pattern))
            new_files = current_files - existing_files
            
            if new_files:
                # 找到新文件!
                latest_new_file = list(new_files)[0] # 简单取一个
                t_log.info(f'[CameraServiceManager] ✓ 检测到新录像文件生成: {os.path.basename(latest_new_file)}')
                return True
                
            # 3. 如果没新文件,但也可能是刚才已经开始录了(文件大小增长?),这里简单点只看新文件
            # 或者如果目录本来是空的,现在有文件了也可以
            if not existing_files and current_files:
                t_log.info(f'[CameraServiceManager] ✓ 检测到录像文件生成')
                return True
                
            time.sleep(1.0)
            
        t_log.warning(f'[CameraServiceManager] ! 等待录像激活超时 (虽然进程可能在运行,但未检测到新文件)')
        return False


# 便捷函数
def ensure_camera_service(params: Optional[Dict[str, Any]] = None) -> bool:
    """
    确保摄像头服务运行(便捷函数)
    
    Args:
        params: 使用者参数
        
    Returns:
        bool: True=服务已运行或启动成功
        
    Example:
        #>>> from plugins.video_recorder.camera_service_manager import ensure_camera_service
        #>>> params = {'save_dir': r'E:\Videos'}
        #>>> ensure_camera_service(params)
    """
    return CameraServiceManager.get_instance().ensure_service_running(params)


if __name__ == '__main__':
    ensure_camera_service()
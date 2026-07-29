#!/usr/bin/env python3
"""
monkey_commander.py

基于 ADB 重新实现的 Monkey 命令工具
模拟 Android 原生 monkey 命令的核心功能，提供更灵活的控制和扩展能力

特性：
- 支持多种事件类型：触摸、滑动、按键、手势等
- 包名过滤和前台应用守护
- 事件类型比例控制
- 节流和种子控制
- 崩溃/超时处理
- 完全基于 ADB 实现，无需设备端 monkey 支持
"""
import random
import time
import subprocess
import threading
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass
from enum import Enum
import re

from powertrde.env import ADB_EXE


class EventType(Enum):
    """事件类型枚举"""
    TOUCH = "touch"              # 触摸事件
    MOTION = "motion"            # 移动/拖拽事件
    TRACKBALL = "trackball"      # 轨迹球事件（已过时，保留兼容）
    NAV = "nav"                  # 导航事件（方向键）
    MAJOR_NAV = "majornav"       # 主要导航（Home、Back、Menu等）
    SYSKEYS = "syskeys"          # 系统按键
    APPSWITCH = "appswitch"      # 应用切换
    FLIP = "flip"                # 屏幕旋转
    ANYEVENT = "anyevent"        # 其他事件


@dataclass
class MonkeyConfig:
    """Monkey 配置参数"""
    # 基本参数
    package: str                              # 目标包名
    event_count: Optional[int] = None         # 事件总数（与 duration_seconds 二选一）
    duration_seconds: Optional[int] = None    # 运行时长（秒）（与 event_count 二选一）
    throttle_ms: int = 100                    # 事件间隔（毫秒）
    seed: Optional[int] = None                # 随机种子
    
    # 事件类型比例（百分比，总和应为100）
    pct_touch: int = 30                       # 触摸事件比例
    pct_motion: int = 25                      # 移动/拖拽比例
    pct_trackball: int = 0                    # 轨迹球比例（一般为0）
    pct_nav: int = 5                          # 方向键比例
    pct_majornav: int = 10                    # 主要导航比例
    pct_syskeys: int = 2                      # 系统按键比例
    pct_appswitch: int = 2                    # 应用切换比例
    pct_flip: int = 0                         # 屏幕旋转比例（一般为0）
    pct_anyevent: int = 26                    # 其他事件比例（补足100）
    
    # 行为控制
    ignore_crashes: bool = True               # 忽略崩溃
    ignore_timeouts: bool = True              # 忽略超时
    ignore_security_exceptions: bool = True   # 忽略安全异常
    monitor_native_crashes: bool = False      # 监控 Native 崩溃
    kill_process_after_error: bool = False    # 错误后杀进程
    
    # 前台守护
    keep_app_foreground: bool = True          # 保持应用在前台
    foreground_check_interval: int = 50       # 每N个事件检查一次前台（当 strict_foreground=False 时有效）
    strict_foreground: bool = True           # 严格前台模式：每次操作前都检查，确保不在其他应用执行任何操作
    
    # 屏幕边界
    margin_ratio: float = 0.05                # 屏幕边距比例（避免误触边缘）
    
    # 调试
    verbosity: int = 1                        # 日志级别 0-3
    
    def validate(self):
        """验证配置参数"""
        # 验证事件计数或时长至少指定一个
        if self.event_count is None and self.duration_seconds is None:
            raise ValueError("必须指定 event_count 或 duration_seconds 其中之一")
        if self.event_count is not None and self.duration_seconds is not None:
            raise ValueError("event_count 和 duration_seconds 不能同时指定，请只选择一个")
        
        # 验证事件类型比例
        total_pct = (self.pct_touch + self.pct_motion + self.pct_trackball + 
                    self.pct_nav + self.pct_majornav + self.pct_syskeys + 
                    self.pct_appswitch + self.pct_flip + self.pct_anyevent)
        if total_pct != 100:
            raise ValueError(f"事件类型比例总和必须为100，当前为{total_pct}")


class MonkeyCommander:
    """基于 ADB 的 Monkey 命令实现"""
    
    # 系统按键码
    KEYCODE_HOME = 3
    KEYCODE_BACK = 4
    KEYCODE_MENU = 82
    KEYCODE_SEARCH = 84
    KEYCODE_DPAD_UP = 19
    KEYCODE_DPAD_DOWN = 20
    KEYCODE_DPAD_LEFT = 21
    KEYCODE_DPAD_RIGHT = 22
    KEYCODE_DPAD_CENTER = 23
    KEYCODE_VOLUME_UP = 24
    KEYCODE_VOLUME_DOWN = 25
    KEYCODE_POWER = 26
    KEYCODE_CAMERA = 27
    KEYCODE_APP_SWITCH = 187
    
    # 系统弹窗/分享界面白名单（这些包名出现时不认为离开了目标应用）
    SYSTEM_OVERLAY_PACKAGES = [
        "com.android.systemui",              # 系统UI（分享面板、通知等）
        "com.google.android.apps.photos",    # Google相册分享
        "com.android.packageinstaller",      # 安装器
        "com.google.android.permissioncontroller",  # 权限控制器
        "com.android.permissioncontroller",  # 权限控制器（非Google版本）
        "com.google.android.gms",            # Google服务（可能弹出登录等）
        # 新增：
        "com.miui.securitycenter",        # 小米权限
        "com.huawei.systemmanager",       # 华为管家
        "com.coloros.safecenter",         # OPPO安全
        "com.google.android.inputmethod", # 输入法
        "com.sohu.inputmethod.sogou",     # 搜狗输入法
        "com.baidu.input",                # 百度输入法
    ]
    
    def __init__(self, config: MonkeyConfig, adb_serial: Optional[str] = None):
        """
        初始化 MonkeyCommander
        
        :param config: Monkey 配置
        :param adb_serial: 设备序列号
        """
        config.validate()
        self.config = config
        self.adb_serial = adb_serial
        
        # 运行状态
        self._running = False
        self._stop_requested = False
        self._event_count = 0
        self._error_count = 0
        self._start_time = 0.0
        self._elapsed_time = 0.0
        
        # 屏幕信息
        self._screen_width = 0
        self._screen_height = 0
        self._bounds = None  # (minx, maxx, miny, maxy)
        
        # 随机数生成器
        if config.seed is not None:
            random.seed(config.seed)
        
        # 事件类型权重列表（用于加权随机）
        self._event_weights = self._build_event_weights()
    
    def _build_event_weights(self) -> List[Tuple[EventType, int]]:
        """构建事件类型权重列表"""
        weights = []
        if self.config.pct_touch > 0:
            weights.append((EventType.TOUCH, self.config.pct_touch))
        if self.config.pct_motion > 0:
            weights.append((EventType.MOTION, self.config.pct_motion))
        if self.config.pct_trackball > 0:
            weights.append((EventType.TRACKBALL, self.config.pct_trackball))
        if self.config.pct_nav > 0:
            weights.append((EventType.NAV, self.config.pct_nav))
        if self.config.pct_majornav > 0:
            weights.append((EventType.MAJOR_NAV, self.config.pct_majornav))
        if self.config.pct_syskeys > 0:
            weights.append((EventType.SYSKEYS, self.config.pct_syskeys))
        if self.config.pct_appswitch > 0:
            weights.append((EventType.APPSWITCH, self.config.pct_appswitch))
        if self.config.pct_flip > 0:
            weights.append((EventType.FLIP, self.config.pct_flip))
        if self.config.pct_anyevent > 0:
            weights.append((EventType.ANYEVENT, self.config.pct_anyevent))
        return weights
    
    def _adb_prefix(self) -> List[str]:
        """构建 ADB 命令前缀"""
        cmd = [ADB_EXE]
        if self.adb_serial:
            cmd += ["-s", self.adb_serial]
        return cmd
    
    def _run_adb(self, args: List[str], timeout: float = 5.0) -> Tuple[int, str]:
        """执行 ADB 命令"""
        full_cmd = self._adb_prefix() + args
        try:
            result = subprocess.run(
                full_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                timeout=timeout,
                text=True
            )
            return result.returncode, result.stdout
        except subprocess.TimeoutExpired:
            return -1, ""
        except Exception as e:
            return -1, str(e)
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕尺寸"""
        rc, out = self._run_adb(["shell", "wm", "size"], timeout=2.0)
        if rc == 0 and out:
            m = re.search(r"Physical size:\s*(\d+)x(\d+)|(\d+)x(\d+)", out)
            if m:
                if m.group(1) and m.group(2):
                    return int(m.group(1)), int(m.group(2))
                else:
                    return int(m.group(3)), int(m.group(4))
        return 1080, 1920  # 默认分辨率
    
    def _init_screen_bounds(self):
        """初始化屏幕边界"""
        self._screen_width, self._screen_height = self._get_screen_size()
        margin = self.config.margin_ratio
        minx = int(self._screen_width * margin)
        maxx = int(self._screen_width * (1.0 - margin))
        miny = int(self._screen_height * margin)
        maxy = int(self._screen_height * (1.0 - margin))
        self._bounds = (minx, maxx, miny, maxy)
        
        if self.config.verbosity >= 1:
            print(f"[Monkey] Screen: {self._screen_width}x{self._screen_height}, "
                  f"Bounds: ({minx},{miny})-({maxx},{maxy})")
    
    def _get_random_point(self) -> Tuple[int, int]:
        """获取随机屏幕坐标"""
        minx, maxx, miny, maxy = self._bounds
        x = random.randint(minx, maxx)
        y = random.randint(miny, maxy)
        return x, y
    
    def _get_foreground_package(self) -> Optional[str]:
        """获取前台应用包名"""
        candidates = [
            "dumpsys activity activities | grep -E 'mFocusedActivity|mFocusedWindow' -m 1",
            "dumpsys window windows | grep -m 1 mCurrentFocus"
        ]
        for cmd in candidates:
            rc, out = self._run_adb(["shell", cmd], timeout=2.0)
            if rc == 0 and out:
                # 提取包名
                m = re.search(r'([a-z][a-z0-9_]*(\.[a-z0-9_]+)+)', out)
                if m:
                    return m.group(1)
        return None
    
    def _is_system_overlay(self, package: str) -> bool:
        """判断是否是系统弹窗/分享界面等覆盖层
        
        :param package: 包名
        :return: 是否是系统覆盖层
        """
        if not package:
            return False
        for overlay_pkg in self.SYSTEM_OVERLAY_PACKAGES:
            if package.startswith(overlay_pkg):
                return True
        return False
    
    def _ensure_app_foreground(self, quick_check: bool = False) -> bool:
        """确保目标应用在前台
        
        :param quick_check: 快速检查模式，如果不在前台立即返回 False，不尝试启动
        :return: 是否在前台
        """
        fg = self._get_foreground_package()
        
        # 情况1：目标应用在前台
        if fg and fg.startswith(self.config.package):
            return True
        
        # 情况2：系统弹窗/分享界面（认为应用还在，只是被覆盖了）
        if fg and self._is_system_overlay(fg):
            if self.config.verbosity >= 2:
                print(f"[Monkey] System overlay detected ({fg}), treating as foreground")
            return True
        
        # 快速检查模式：不在前台直接返回
        if quick_check:
            return False
        
        # 非快速模式：进行多次重试拉起应用（三层渐进式恢复策略）
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            if self.config.verbosity >= 1:
                print(f"[Monkey] App not foreground (current: {fg}), recovering... (attempt {attempt}/{max_retries})")
            
            # 策略1：第1次尝试温和恢复（连续按多次BACK键，处理多层弹窗）
            if attempt == 1:
                if self.config.verbosity >= 2:
                    print(f"[Monkey] Strategy 1: Trying BACK key to dismiss overlay/dialog (multiple attempts)")
                
                # 连续按最多5次BACK键，处理多层嵌套弹窗
                max_back_presses = 5
                for back_count in range(1, max_back_presses + 1):
                    self._run_adb(["shell", "input", "keyevent", str(self.KEYCODE_BACK)], timeout=2.0)
                    time.sleep(0.4)  # 每次BACK后短暂等待
                    
                    # 每次BACK后都检查是否已回到目标应用
                    fg = self._get_foreground_package()
                    if fg and (fg.startswith(self.config.package) or self._is_system_overlay(fg)):
                        if self.config.verbosity >= 1:
                            print(f"[Monkey] BACK key worked after {back_count} press(es), app is now accessible (fg: {fg})")
                        return True
                    
                    if self.config.verbosity >= 2:
                        print(f"[Monkey] BACK press {back_count}/{max_back_presses}, current fg: {fg}")
            
            # 策略2：第2-3次尝试彻底恢复（强制杀死进程 + 重新启动）
            else:
                if self.config.verbosity >= 2:
                    print(f"[Monkey] Strategy 2: Force-stop and restart app")
                
                # 强制停止应用（杀死进程）
                self._run_adb(["shell", "am", "force-stop", self.config.package], timeout=3.0)
                for _ in range(3):
                    self._run_adb(["shell", "input", "keyevent", str(self.KEYCODE_HOME)], timeout=2.0)
                time.sleep(0.3)
                
                # 重新启动应用
                self._run_adb([
                    "shell", "monkey", "-p", self.config.package,
                    "-c", "android.intent.category.LAUNCHER", "1"
                ], timeout=5.0)
                time.sleep(1.0)  # 给冷启动更多时间
                
                # 检查前台应用
                fg = self._get_foreground_package()
                if fg and (fg.startswith(self.config.package) or self._is_system_overlay(fg)):
                    if self.config.verbosity >= 1:
                        print(f"[Monkey] App restarted successfully (fg: {fg})")
                    return True
        
        # 多次重试后仍未在前台
        if self.config.verbosity >= 1:
            print(f"[Monkey] Failed to bring {self.config.package} to foreground after {max_retries} attempts (current: {fg})")
        return False
    
    def _select_event_type(self) -> EventType:
        """根据权重随机选择事件类型"""
        total_weight = sum(w for _, w in self._event_weights)
        r = random.randint(1, total_weight)
        cumulative = 0
        for event_type, weight in self._event_weights:
            cumulative += weight
            if r <= cumulative:
                return event_type
        return EventType.TOUCH  # fallback
    
    def _execute_touch_event(self):
        """执行触摸事件"""
        x, y = self._get_random_point()
        self._run_adb(["shell", "input", "tap", str(x), str(y)], timeout=2.0)
        if self.config.verbosity >= 3:
            print(f"[Monkey] Touch at ({x},{y})")
    
    def _execute_motion_event(self):
        """执行移动/拖拽事件"""
        x1, y1 = self._get_random_point()
        x2, y2 = self._get_random_point()
        duration = random.randint(200, 800)
        self._run_adb(["shell", "input", "swipe", 
                      str(x1), str(y1), str(x2), str(y2), str(duration)], timeout=3.0)
        if self.config.verbosity >= 3:
            print(f"[Monkey] Swipe from ({x1},{y1}) to ({x2},{y2})")
    
    def _execute_nav_event(self):
        """执行导航事件（方向键）"""
        nav_keys = [
            self.KEYCODE_DPAD_UP,
            self.KEYCODE_DPAD_DOWN,
            self.KEYCODE_DPAD_LEFT,
            self.KEYCODE_DPAD_RIGHT,
            self.KEYCODE_DPAD_CENTER
        ]
        keycode = random.choice(nav_keys)
        self._run_adb(["shell", "input", "keyevent", str(keycode)], timeout=2.0)
        if self.config.verbosity >= 3:
            print(f"[Monkey] Nav key: {keycode}")
    
    def _execute_majornav_event(self):
        """执行主要导航事件（Home、Back、Menu等）"""
        # 注意：避免频繁使用 Home 键导致退出应用
        major_keys = [
            self.KEYCODE_BACK,
            # self.KEYCODE_MENU,
            # self.KEYCODE_SEARCH,
        ]
        # 低概率加入 Home 键
        # if random.random() < 0.1:
        #     major_keys.append(self.KEYCODE_HOME)
        
        keycode = random.choice(major_keys)
        self._run_adb(["shell", "input", "keyevent", str(keycode)], timeout=2.0)
        if self.config.verbosity >= 3:
            print(f"[Monkey] Major nav key: {keycode}")
    
    def _execute_syskeys_event(self):
        """执行系统按键事件"""
        sys_keys = [
            self.KEYCODE_VOLUME_UP,
            self.KEYCODE_VOLUME_DOWN,
        ]
        keycode = random.choice(sys_keys)
        self._run_adb(["shell", "input", "keyevent", str(keycode)], timeout=2.0)
        if self.config.verbosity >= 3:
            print(f"[Monkey] System key: {keycode}")
    
    def _execute_appswitch_event(self):
        """执行应用切换事件"""
        self._run_adb(["shell", "input", "keyevent", str(self.KEYCODE_APP_SWITCH)], timeout=2.0)
        if self.config.verbosity >= 3:
            print(f"[Monkey] App switch")
    
    def _execute_flip_event(self):
        """执行屏幕旋转事件（慎用）"""
        # 这个操作比较危险，暂时用快速旋转模拟
        pass
    
    def _execute_anyevent(self):
        """执行其他随机事件"""
        # 随机选择一个简单事件
        actions = [
            self._execute_touch_event,
            self._execute_motion_event,
            self._execute_nav_event,
        ]
        random.choice(actions)()
    
    def _execute_event(self, event_type: EventType) -> bool:
        """执行指定类型的事件
        
        :return: 是否成功执行（如果因为前台检查失败返回 False）
        """
        # 严格前台模式：每次操作前都检查
        if self.config.strict_foreground and self.config.keep_app_foreground:
            if not self._ensure_app_foreground(quick_check=True):
                if self.config.verbosity >= 2:
                    fg = self._get_foreground_package()
                    print(f"[Monkey] Skipping event, app not foreground (current: {fg})")
                return False
        
        try:
            if event_type == EventType.TOUCH:
                self._execute_touch_event()
            elif event_type == EventType.MOTION:
                self._execute_motion_event()
            elif event_type == EventType.NAV:
                self._execute_nav_event()
            elif event_type == EventType.MAJOR_NAV:
                self._execute_majornav_event()
            elif event_type == EventType.SYSKEYS:
                self._execute_syskeys_event()
            elif event_type == EventType.APPSWITCH:
                self._execute_appswitch_event()
            elif event_type == EventType.FLIP:
                self._execute_flip_event()
            elif event_type == EventType.ANYEVENT:
                self._execute_anyevent()
            return True
        except Exception as e:
            self._error_count += 1
            if self.config.verbosity >= 2:
                print(f"[Monkey] Event execution error: {e}")
            if not self.config.ignore_crashes:
                raise
            return False
    
    def start(self, background: bool = False):
        """
        启动 Monkey 测试
        
        :param background: 是否在后台运行（默认前台阻塞）
        """
        if self._running:
            raise RuntimeError("Monkey is already running")
        
        self._running = True
        self._stop_requested = False
        self._event_count = 0
        self._error_count = 0
        self._start_time = time.time()
        self._elapsed_time = 0.0
        
        if background:
            thread = threading.Thread(target=self._run_loop, daemon=True)
            thread.start()
        else:
            self._run_loop()
    
    def _run_loop(self):
        """主运行循环"""
        # 初始化
        self._init_screen_bounds()
        
        if self.config.verbosity >= 1:
            print(f"[Monkey] Starting monkey test for {self.config.package}")
            if self.config.event_count is not None:
                print(f"[Monkey] Target events: {self.config.event_count}, "
                      f"Throttle: {self.config.throttle_ms}ms, Seed: {self.config.seed}")
            else:
                print(f"[Monkey] Duration: {self.config.duration_seconds}s, "
                      f"Throttle: {self.config.throttle_ms}ms, Seed: {self.config.seed}")
        
        # 确保应用在前台
        if self.config.keep_app_foreground:
            if not self._ensure_app_foreground():
                print(f"[Monkey] Failed to bring {self.config.package} to foreground")
                self._running = False
                return
        
        # 确定硬超时时间（仅在按时长运行时启用）
        hard_stop_time = None
        if self.config.duration_seconds is not None:
            # 使用 _start_time + duration_seconds 作为目标时间，并预留少量缓冲
            hard_stop_time = self._start_time + self.config.duration_seconds + 5
        
        # 主循环
        try:
            while self._running and not self._stop_requested:
                # 时间防护：无论内部逻辑如何，一旦超过硬超时时间就强制停止
                if hard_stop_time is not None and time.time() >= hard_stop_time:
                    if self.config.verbosity >= 1:
                        print(f"[Monkey] Hard timeout reached (duration={self.config.duration_seconds}s), stopping by guard")
                    break
                
                # 检查停止条件
                if self.config.event_count is not None:
                    # 按事件数量停止
                    if self._event_count >= self.config.event_count:
                        break
                else:
                    # 按时间停止
                    self._elapsed_time = time.time() - self._start_time
                    if self._elapsed_time >= self.config.duration_seconds:
                        break
                
                # 选择事件类型
                event_type = self._select_event_type()
                
                # 执行事件（严格模式下会在内部检查前台）
                executed = self._execute_event(event_type)
                
                # 如果因为前台检查失败而跳过，尝试恢复
                if not executed and self.config.strict_foreground:
                    if self.config.verbosity >= 1:
                        print(f"[Monkey] App left foreground, recovering...")
                    # 尝试恢复到前台
                    if not self._ensure_app_foreground(quick_check=False):
                        if self.config.verbosity >= 1:
                            print(f"[Monkey] Cannot recover app to foreground, stopping...")
                        break
                    # 恢复成功，继续下一次循环（不增加事件计数）
                    continue
                
                # 非严格模式：定期检查前台
                if (not self.config.strict_foreground and self.config.keep_app_foreground and 
                    self._event_count % self.config.foreground_check_interval == 0):
                    if not self._ensure_app_foreground():
                        if self.config.verbosity >= 1:
                            print(f"[Monkey] Cannot keep app foreground, stopping...")
                        break
                
                # 成功执行事件，计数+1
                if executed:
                    self._event_count += 1
                
                # 进度输出
                if self.config.verbosity >= 1 and self._event_count % 100 == 0:
                    self._elapsed_time = time.time() - self._start_time
                    if self.config.event_count is not None:
                        progress = (self._event_count / self.config.event_count) * 100
                        print(f"[Monkey] Progress: {self._event_count}/{self.config.event_count} "
                              f"({progress:.1f}%), Elapsed: {self._elapsed_time:.1f}s, Errors: {self._error_count}")
                    else:
                        progress = (self._elapsed_time / self.config.duration_seconds) * 100
                        print(f"[Monkey] Progress: {self._elapsed_time:.1f}s/{self.config.duration_seconds}s "
                              f"({progress:.1f}%), Events: {self._event_count}, Errors: {self._error_count}")
                
                # 节流
                if self.config.throttle_ms > 0:
                    time.sleep(self.config.throttle_ms / 1000.0)
        
        except KeyboardInterrupt:
            if self.config.verbosity >= 1:
                print(f"[Monkey] Interrupted by user")
        except Exception as e:
            if self.config.verbosity >= 1:
                print(f"[Monkey] Fatal error: {e}")
        finally:
            self._running = False
            self._elapsed_time = time.time() - self._start_time
            if self.config.verbosity >= 1:
                print(f"[Monkey] Test completed: {self._event_count} events, "
                      f"Duration: {self._elapsed_time:.1f}s, Errors: {self._error_count}")
    
    def stop(self):
        """停止 Monkey 测试"""
        if self._running:
            self._stop_requested = True
            if self.config.verbosity >= 1:
                print(f"[Monkey] Stop requested")


# ===== 命令行接口和便捷函数 =====

def create_simple_monkey(
    package: str,
    event_count: Optional[int] = None,
    duration_seconds: Optional[int] = None,
    throttle_ms: int = 100,
    adb_serial: Optional[str] = None,
    keep_foreground: bool = True,
    verbosity: int = 1
) -> MonkeyCommander:
    """
    创建简单配置的 Monkey
    
    :param package: 目标包名
    :param event_count: 事件总数（与 duration_seconds 二选一）
    :param duration_seconds: 运行时长（秒）（与 event_count 二选一）
    :param throttle_ms: 事件间隔（毫秒）
    :param adb_serial: 设备序列号
    :param keep_foreground: 保持应用在前台
    :param verbosity: 日志级别
    :return: MonkeyCommander 实例
    """
    # 默认值处理
    if event_count is None and duration_seconds is None:
        event_count = 1000  # 默认 1000 个事件
    
    config = MonkeyConfig(
        package=package,
        event_count=event_count,
        duration_seconds=duration_seconds,
        throttle_ms=throttle_ms,
        keep_app_foreground=keep_foreground,
        verbosity=verbosity
    )
    return MonkeyCommander(config, adb_serial)


def create_safe_monkey(
    package: str,
    event_count: Optional[int] = None,
    duration_seconds: Optional[int] = None,
    adb_serial: Optional[str] = None
) -> MonkeyCommander:
    """
    创建安全配置的 Monkey（避免系统按键和应用切换）

    :param package: 目标包名
    :param event_count: 事件总数（与 duration_seconds 二选一）
    :param duration_seconds: 运行时长（秒）（与 event_count 二选一）
    :param adb_serial: 设备序列号
    :return: MonkeyCommander 实例
    """
    # 默认值处理
    if event_count is None and duration_seconds is None:
        event_count = 1000  # 默认 1000 个事件
    
    config = MonkeyConfig(
        package=package,
        event_count=event_count,
        duration_seconds=duration_seconds,
        throttle_ms=200,
        pct_touch=50,
        pct_motion=45,
        pct_trackball=0,
        pct_nav=0,
        pct_majornav=5,
        pct_syskeys=0,
        pct_appswitch=0,
        pct_flip=0,
        pct_anyevent=0,
        keep_app_foreground=True,
        margin_ratio=0.05,
        verbosity=3
    )
    return MonkeyCommander(config, adb_serial)


def create_strict_monkey(
    package: str,
    event_count: Optional[int] = None,
    duration_seconds: Optional[int] = None,
    adb_serial: Optional[str] = None,
    verbosity: int = 1
) -> MonkeyCommander:
    """
    创建严格前台守护的 Monkey（确保不在其他应用执行任何操作）
    
    特性：
    - 每次操作前都检查前台应用
    - 一旦检测到离开目标应用，立即停止操作并恢复
    - 不使用系统按键和应用切换
    - 适合长时间稳定性测试
    
    :param package: 目标包名
    :param event_count: 事件总数（与 duration_seconds 二选一）
    :param duration_seconds: 运行时长（秒）（与 event_count 二选一）
    :param adb_serial: 设备序列号
    :param verbosity: 日志级别
    :return: MonkeyCommander 实例
    """
    # 默认值处理
    if event_count is None and duration_seconds is None:
        event_count = 1000  # 默认 1000 个事件
    
    config = MonkeyConfig(
        package=package,
        event_count=event_count,
        duration_seconds=duration_seconds,
        throttle_ms=200,
        pct_touch=45,
        pct_motion=35,
        pct_nav=10,
        pct_majornav=10,      # 允许少量 Back/Menu
        pct_syskeys=0,        # 不使用系统按键
        pct_appswitch=0,      # 不切换应用
        pct_anyevent=0,
        keep_app_foreground=True,
        strict_foreground=True,  # 启用严格前台模式
        margin_ratio=0.08,
        verbosity=verbosity
    )
    return MonkeyCommander(config, adb_serial)


# ===== 示例用法 =====

if __name__ == "__main__":
    create_safe_monkey(
        package="com.facebook.katana",
        duration_seconds=6000,
        adb_serial="1410925519000179",
    ).start()

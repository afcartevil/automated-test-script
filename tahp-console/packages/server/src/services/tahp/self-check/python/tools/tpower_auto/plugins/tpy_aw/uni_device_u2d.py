import datetime
import math
import os
import time
from typing import Optional, Tuple

import numpy as np
import uiautomator2
from PIL.Image import Resampling

from cv_utils import cv_utils
from powertrde.utils.cv_extends.cv_defines import TemplateMatchResult, TemplateMatchError
from powertrde.framework.logs_protocol import logs_p
from powertrde.utils.trde import adb
from powertrde.framework.uni_device import UniDevice


class UniDeviceU2D(UniDevice):
    def __init__(self, u2d: uiautomator2.Device):
        super().__init__()
        self.u2d = u2d
        s = self.u2d.window_size()
        if self.is_landscape:
            self.width = s[1]
            self.height = s[0]
        else:
            self.width = s[0]
            self.height = s[1]

    @property
    def is_landscape(self):
        return self.u2d.orientation in ['left', 'right']

    def _to_absolute(self, fx: float, fy: float):
        fx, fy, changed = self.pos_convert_to_landscape(fx, fy, self.u2d.orientation)
        if changed:
            return fx * self.height, fy * self.width
        return fx * self.width, fy * self.height

    def click(self, fx: float, fy: float, times: int = 1, interval: float = 0.5, z_delta: float = 0.0):
        x, y = self._to_absolute(fx, fy)
        for i in range(times):
            if i > 0:
                time.sleep(interval)
            self.u2d.click(x, y)

    def swipe(self, fx_from: float, fy_from: float, fx_to: float, fy_to: float, speed: int = 200):
        x1, y1 = self._to_absolute(fx_from, fy_from)
        x2, y2 = self._to_absolute(fx_to, fy_to)
        # 计算两点之间的距离（像素）
        distance = math.hypot(x2 - x1, y2 - y1)
        # duration = 距离 / speed (speed 单位：像素/秒)，duration 单位为秒
        duration = distance / 50 / speed if speed > 0 else 0.5
        self.u2d.swipe(x1, y1, x2, y2, duration=duration)

    def long_press(self, fx: float, fy: float, hold_time: float = 1, z_delta: float = 0.0):
        x, y = self._to_absolute(fx, fy)
        self.u2d.drag(x, y, x, y, duration=hold_time)

    def _bottom_key_coords(self, key: str):
        """
        计算下方三键中对应按键的相对坐标，
        默认排列顺序：menu, home, back。
        """
        key = key.lower()
        if key not in self.BOTTOM_KEYS:
            raise ValueError(f"不支持的按键: {key}")
        return self.BOTTOM_KEYS[key]

    def click_menu(self, times: int = 1, interval: float = 0.5):
        x, y = self._bottom_key_coords("menu")
        self.click(x, y, times, interval)

    def click_home(self, times: int = 1, interval: float = 0.5):
        x, y = self._bottom_key_coords("home")
        self.click(x, y, times, interval)

    def click_back(self, times: int = 1, interval: float = 0.5):
        x, y = self._bottom_key_coords("back")
        self.click(x, y, times, interval)

    def click_power(self, times: int = 1, interval: float = 0.5):
        # power 键操作直接调用按键
        for i in range(times):
            if i > 0:
                time.sleep(interval)
            self.u2d.press("power")

    def long_press_power(self, hold_time: float = 2):
        self.u2d.long_press("power")
        # 此处无需额外 sleep，因为 long_press 内部已实现

    def home_axes(self, fast_mode: bool = True):
        # U2D 模式无需回轴
        pass

    def match_template(self, template_input, target_score=0.7, match_times=1, match_interval=1.0,
                       limit_area: Optional[Tuple[float, float, float, float]] = None,
                       match_method: str = 'normal', raise_on_match_failed=False, show_log=True) -> TemplateMatchResult:
        super().match_template(template_input, target_score, match_times, match_interval,
                               limit_area, match_method, raise_on_match_failed, show_log)
        resized = None
        for i in range(match_times):
            if i > 0:
                time.sleep(match_interval)
            # 1. 截屏
            screenshot = self.u2d.screenshot()

            # 2. 归一化尺寸：短边固定为720像素
            orig_width, orig_height = screenshot.size
            if orig_width < orig_height:
                scale = 720 / orig_width
                new_width = 720
                new_height = int(orig_height * scale)
            else:
                scale = 720 / orig_height
                new_height = 720
                new_width = int(orig_width * scale)
            resized = screenshot.resize((new_width, new_height), Resampling.LANCZOS)

            # 如果是横屏，则进行翻转
            orientation = self.u2d.orientation
            if orientation == 'left':
                resized = resized.rotate(270, expand=True)
            elif orientation == 'right':
                resized = resized.rotate(90, expand=True)

            # 4. 将 PIL.Image 转换为灰度的 numpy 数组
            target_np = np.array(resized.convert('L'))

            # 5. 调用cv工具的灰度模板匹配，传入 template_path（可以是 PathLike）和 target_np
            match_result = cv_utils.template_match_gray_ext(template_input, target_np,
                                                            limit_area=limit_area,
                                                            match_threshold=target_score,
                                                            raise_on_match_failed=False,
                                                            scale_range=(0.99, 1.01))
            if match_result.success:
                break
        result_text = 'success' if match_result.success else 'fail'
        if isinstance(template_input, (str, os.PathLike)):
            message = f'[U2D Match template {result_text}] ({os.path.basename(os.path.dirname(template_input))}/{os.path.basename(template_input)}) score: {match_result.score:.1%} | target score: {match_result.target_score:.1%}'
            if not match_result.success and raise_on_match_failed and resized:
                message = self.save_match_pic(resized, template_input, message)
        else:
            message = f'[U2D Match template {result_text}] score: {match_result.score:.1%} | target score: {match_result.target_score:.1%}'
            if not match_result.success and raise_on_match_failed and resized:
                message = self.save_match_pic(resized, '', message)

        if show_log:
            logs_p().log(message)
        if raise_on_match_failed and not match_result.success:
            raise TemplateMatchError(message, match_result)
        return match_result

    def match_text(self, template_input, target_score=0.7, match_times=1, match_interval=1.0, match_lang="eng",
                   limit_area: Optional[Tuple[float, float, float, float]] = None, case_sensitive: bool = True,
                   match_method: str = 'normal', raise_on_match_failed=False, show_log=True) -> TemplateMatchResult:
        super().match_text(template_input, target_score, match_times, match_interval, match_lang,
                           limit_area, case_sensitive, match_method, raise_on_match_failed, show_log)
        match_result = None
        resized = None
        for i in range(match_times):
            if i > 0:
                time.sleep(match_interval)
            # 1. 截屏
            screenshot = self.u2d.screenshot()

            # 2. 归一化尺寸：短边固定为720像素
            orig_width, orig_height = screenshot.size
            if orig_width < orig_height:
                scale = 720 / orig_width
                new_width = 720
                new_height = int(orig_height * scale)
            else:
                scale = 720 / orig_height
                new_height = 720
                new_width = int(orig_width * scale)
            resized = screenshot.resize((new_width, new_height), Resampling.LANCZOS)

            # 如果是横屏，则进行翻转
            orientation = self.u2d.orientation
            if orientation == 'left':
                resized = resized.rotate(270, expand=True)
            elif orientation == 'right':
                resized = resized.rotate(90, expand=True)

            # 4. 将 PIL.Image 转换为灰度的 numpy 数组
            target_np = np.array(resized.convert('L'))

            # 4. 调用cv工具的灰度模板匹配，传入 text
            match_result = cv_utils.ocr_match(template_input, target_np,
                                              limit_area=limit_area,
                                              match_lang="eng",
                                              scale_factor=3,
                                              match_threshold=target_score,
                                              case_sensitive=case_sensitive,
                                              raise_on_match_failed=False)
            if match_result.success:
                break
        result_text = 'success' if match_result.success else 'fail'
        _path = os.path.join(logs_p().get_log_dir(), f'{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
        if isinstance(template_input, (str, os.PathLike)):
            message = f'[DZ Match text {result_text}] ({os.path.basename(os.path.dirname(template_input))}/{os.path.basename(template_input)}) score: {match_result.score:.1%} | target score: {match_result.target_score:.1%}'
            if not match_result.success and raise_on_match_failed and resized:
                message = self.save_match_pic(resized, template_input, message)
        else:
            message = f'[DZ Match text {result_text}] score: {match_result.score:.1%} | target score: {match_result.target_score:.1%}'
            if not match_result.success and raise_on_match_failed and resized:
                message = self.save_match_pic(resized, '', message)
        if show_log:
            logs_p().log(message)
        if raise_on_match_failed and not match_result.success:
            raise TemplateMatchError(message, match_result)
        return match_result

    def save_match_pic(self, resized, template_input: str, message):
        base_path = os.path.join(logs_p().get_log_dir(), 'match_pic')
        if not os.path.exists(base_path):
            os.makedirs(base_path, True)
        _path_screen = os.path.join(base_path, f'{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
        resized.save(_path_screen)
        message = message + f' | screen: {_path_screen}, template: {template_input}'
        return message

    def detect_black_screen(self, threshold_mean: float = 1, threshold_std: float = 1) -> bool:
        return not adb.is_screen_on(self.u2d.serial)

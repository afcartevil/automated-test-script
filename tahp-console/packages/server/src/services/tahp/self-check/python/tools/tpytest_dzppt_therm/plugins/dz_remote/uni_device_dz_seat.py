import datetime
import os
import tempfile
import time
from typing import Optional, Callable, Tuple

import numpy as np
from PIL import Image
from PIL.Image import Resampling

from cv_utils import cv_utils
from powertrde.utils.cv_extends.cv_defines import TemplateMatchResult, TemplateMatchError
from dz_remote.dz_seat import DzSeat
from powertrde.framework.logs_protocol import logs_p
from powertrde.framework.uni_device import UniDevice


class UniDeviceDzSeat(UniDevice):
    def __init__(self, dz_seat: DzSeat):
        super().__init__()
        self.dz_seat = dz_seat
        # 从 dz_seat 获取屏幕范围信息：X, Y, Width, Height
        self.screen_rect = dz_seat.screen_rect
        self.on_custom_z_delta: Optional[Callable[[float, float, float], float]] = None

    def _to_absolute(self, fx: float, fy: float):
        # 注意：这里我们假定传入的相对坐标已经不包含屏幕偏移（X、Y）
        # 如果需要考虑屏幕左上角偏移，可按需求调整
        abs_x = fx * self.screen_rect['Width']
        abs_y = fy * self.screen_rect['Height']
        return abs_x, abs_y

    def click(self, fx: float, fy: float, times: int = 1, interval: float = 0.5, z_delta: float = 0.0):
        x, y = self._to_absolute(fx, fy)
        if self.on_custom_z_delta:
            z_delta = self.on_custom_z_delta(z_delta, fx, fy)
        self.dz_seat.continuous_click_screen(x, y, z_delta, times, int(interval * 1000) if times > 1 else 0)
        # for i in range(times):
        #     if i > 0:
        #         time.sleep(interval)
        #     self.dz_seat.click_screen(x, y, click_type=0, timeout=0)

    def swipe(self, fx_from: float, fy_from: float, fx_to: float, fy_to: float, speed: int = 200):
        x1, y1 = self._to_absolute(fx_from, fy_from)
        x2, y2 = self._to_absolute(fx_to, fy_to)
        # 对于机械手，我们假定传入的 speed 参数表示滑动耗时（单位：毫秒）
        # 这里可直接调用 dz_seat 提供的 swipe_screen 方法
        self.dz_seat.swipe_screen(x1, y1, x2, y2, speed)

    def long_press(self, fx: float, fy: float, hold_time: float = 1, z_delta: float = 0.0):
        x, y = self._to_absolute(fx, fy)
        if self.on_custom_z_delta:
            z_delta = self.on_custom_z_delta(z_delta, fx, fy)
        # HACK: 未实现长按z轴增量，如果后续需要用到再想办法
        self.dz_seat.click_screen(x, y, click_type=2, timeout=int(hold_time * 1000))

    def click_back(self, times: int = 1, interval: float = 0.5):
        for i in range(times):
            if i > 0:
                time.sleep(interval)
            self.dz_seat.click_key("Back")

    def click_home(self, times: int = 1, interval: float = 0.5):
        for i in range(times):
            if i > 0:
                time.sleep(interval)
            self.dz_seat.click_key("Home")

    def click_menu(self, times: int = 1, interval: float = 0.5):
        for i in range(times):
            if i > 0:
                time.sleep(interval)
            self.dz_seat.click_key("Menu")

    def click_power(self, times: int = 1, interval: float = 0.5):
        for i in range(times):
            if i > 0:
                time.sleep(interval)
            self.dz_seat.click_key("Power")

    def long_press_power(self, hold_time: float = 2):
        self.dz_seat.click_key("Power", click_type=2, pause_time=int(hold_time * 1000))

    def home_axes(self, fast_mode: bool = True):
        self.dz_seat.home_axes(fast_mode)

    def match_template(self, template_input, target_score=0.7, match_times=1, match_interval=1.0,
                       limit_area: Optional[Tuple[float, float, float, float]] = None,
                       match_method: str = 'normal', raise_on_match_failed=False, show_log=True) -> TemplateMatchResult:
        super().match_template(template_input, target_score, match_times, match_interval,
                               limit_area, match_method, raise_on_match_failed, show_log)
        match_result = None
        resized = None
        for i in range(match_times):
            if i > 0:
                time.sleep(match_interval)
            # 1. 东舟工位截屏
            screenshot_file = os.path.join(tempfile.gettempdir(), "dz_seat_temp_screenshot.png")
            if os.path.exists(screenshot_file):
                os.remove(screenshot_file)
            capture_result = self.dz_seat.capture_screen(screenshot_file)
            if not os.path.exists(screenshot_file):
                raise Exception(
                    f'Can not capture screen from dz seat index {self.dz_seat.seat_index}, capture result is: {capture_result}')
            screenshot = Image.open(screenshot_file)

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

            # 3. 将 PIL.Image 转换为灰度的 numpy 数组
            target_np = np.array(resized.convert('L'))

            # 4. 调用cv工具的灰度模板匹配，传入 template_path（可以是 PathLike）和 target_np
            match_result = cv_utils.template_match_gray_ext(template_input, target_np,
                                                            limit_area=limit_area,
                                                            match_threshold=target_score,
                                                            raise_on_match_failed=False,
                                                            scale_range=(0.95, 1.05))
            if match_result.success:
                break
        result_text = 'success' if match_result.success else 'fail'
        _path = os.path.join(logs_p().get_log_dir(), f'{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
        if isinstance(template_input, (str, os.PathLike)):
            message = f'[DZ Match template {result_text}] ({os.path.basename(os.path.dirname(template_input))}/{os.path.basename(template_input)}) score: {match_result.score:.1%} | target score: {match_result.target_score:.1%}'
            if not match_result.success and raise_on_match_failed and resized:
                message = self.save_match_pic(resized, template_input, message)
        else:
            message = f'[DZ Match template {result_text}] score: {match_result.score:.1%} | target score: {match_result.target_score:.1%}'
            if not match_result.success and raise_on_match_failed and resized:
                message = self.save_match_pic(resized, '', message)
        if show_log:
            logs_p().log(message)
        if raise_on_match_failed and not match_result.success:
            raise TemplateMatchError(message, match_result)
        return match_result

    def match_text(self, template_input, target_score=0.7, match_times=1, match_interval=1.0, match_lang="eng",
                   limit_area: Optional[Tuple[float, float, float, float]] = None, case_sensitive: bool = True,
                   match_method: str = 'normal', scale_factor=2.0, raise_on_match_failed=False, show_log=True) -> TemplateMatchResult:

        super().match_text(template_input, target_score, match_times, match_interval, match_lang,
                           limit_area, case_sensitive, scale_factor, raise_on_match_failed, show_log)
        match_result = None
        proc_img = None
        for i in range(match_times):
            if i > 0:
                time.sleep(match_interval)
            # 1. 东舟工位截屏
            screenshot_file = os.path.join(tempfile.gettempdir(), "dz_seat_temp_screenshot.png")
            if os.path.exists(screenshot_file):
                os.remove(screenshot_file)
            capture_result = self.dz_seat.capture_screen(screenshot_file)
            if not os.path.exists(screenshot_file):
                raise Exception(
                    f'Can not capture screen from dz seat index {self.dz_seat.seat_index}, capture result is: {capture_result}')
            screenshot = Image.open(screenshot_file)

            proc_img = screenshot

            # 2. 将 PIL.Image 转换为灰度的 numpy 数组（原始分辨率）
            target_np = np.array(proc_img.convert('L'))

            # 4. 调用cv工具的 OCR 匹配
            match_result = cv_utils.ocr_match(template_input, target_np,
                                              limit_area=limit_area,
                                              match_lang=match_lang,
                                              scale_factor=scale_factor,
                                              match_threshold=target_score,
                                              case_sensitive=case_sensitive,
                                              raise_on_match_failed=False)
            if match_result.success:
                break
        result_text = 'success' if match_result.success else 'fail'
        _path = os.path.join(logs_p().get_log_dir(), f'{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
        if isinstance(template_input, (str, os.PathLike)):
            message = f'[DZ Match text {result_text}] ({template_input}) score: {match_result.score:.1%} | target score: {match_result.target_score:.1%}'
            if not match_result.success and raise_on_match_failed and proc_img:
                message = self.save_match_pic(proc_img, template_input, message)
        else:
            message = f'[DZ Match text {result_text}] score: {match_result.score:.1%} | target score: {match_result.target_score:.1%}'
            if not match_result.success and raise_on_match_failed and proc_img:
                message = self.save_match_pic(proc_img, '', message)
        if show_log:
            logs_p().log(message)
        if raise_on_match_failed and not match_result.success:
            raise TemplateMatchError(message, match_result)
        return match_result

    def save_match_pic(self, resized, template_input: str, message):
        base_path = os.path.join(logs_p().get_log_dir(), 'match_pic')
        if not os.path.exists(base_path):
            os.makedirs(base_path)
        _path_screen = os.path.join(base_path, f'{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
        resized.save(_path_screen)
        message = message + f' | screen: {_path_screen}, template: {template_input}'
        return message

    def detect_black_screen(self, threshold_mean: float = 3, threshold_std: float = 6) -> bool:
        """
        更精准的黑屏检测算法，通过图像的均值和标准差判断屏幕是否为黑屏。
        :param threshold_mean: 判断黑屏的均值阈值，默认为10。
        :param threshold_std: 判断黑屏的标准差阈值，默认为10。
        :return: 返回True表示黑屏，False表示不是黑屏。
        """
        # 1. 使用东舟设备截图
        screenshot_file = os.path.join(tempfile.gettempdir(), "dz_seat_temp_screenshot.png")
        if os.path.exists(screenshot_file):
            os.remove(screenshot_file)
        capture_result = self.dz_seat.capture_screen(screenshot_file)

        # 检查截图是否成功
        if not os.path.exists(screenshot_file):
            raise Exception(
                f"无法从东舟设备（工位 {self.dz_seat.seat_index}）截取屏幕，捕获结果为: {capture_result}"
            )
        screenshot = Image.open(screenshot_file)

        # 2. 将截图转换为灰度图像
        gray_screenshot = screenshot.convert('L')  # 转为灰度图，'L'表示亮度通道
        screenshot_np = np.array(gray_screenshot)

        # 3. 计算图像的均值和标准差
        mean_pixel_value = np.mean(screenshot_np)
        std_pixel_value = np.std(screenshot_np)
        print(mean_pixel_value, std_pixel_value)

        # 4. 判断黑屏条件
        if mean_pixel_value < threshold_mean and std_pixel_value < threshold_std:
            return True  # 屏幕是黑屏

        return False

import time
from typing import Tuple, Optional

from powertrde.utils.cv_extends.cv_defines import TemplateMatchResult


class UniDevice:
    CENTER = (0.5, 0.5)
    # 底部三键坐标，分别为 (menu, home, back)
    BOTTOM_KEYS = {
        "menu": (1.3 / 6, 0.98),
        "home": (0.5, 0.98),
        "back": (4.7 / 6, 0.98),
    }

    # edge_swipe预设起点（相对坐标）及滑动方向
    EDGE_PRESETS = {
        "bottom": {"start": (0.5, 1), "end_delta": (0, -1)},  # 从屏幕底部向上滑动 distance_ratio
        "top": {"start": (0.5, 0), "end_delta": (0, 1)},  # 从屏幕顶部向下滑动
        "left": {"start": (0, 0.5), "end_delta": (1, 0)},  # 从屏幕左侧向右滑动
        "right": {"start": (1, 0.5), "end_delta": (-1, 0)},  # 从屏幕右侧向左滑动
        "top_left": {"start": (0.25, 0), "end_delta": (0, 1)},  # 从左上角向下滑动
        "top_right": {"start": (0.75, 0), "end_delta": (0, 1)},  # 从右上角向下滑动
    }

    @staticmethod
    def pos_convert_to_landscape(x_prime, y_prime, direction):
        if direction == 'left':
            # 转换到左旋转横屏
            x = y_prime
            y = 1 - x_prime
        elif direction == 'right':
            # 转换到右旋转横屏
            x = 1 - y_prime
            y = x_prime
        else:
            return x_prime, y_prime, False
        return x, y, True

    def __init__(self):
        self.user_args = {}

    def click(self, fx: float, fy: float, times: int = 1, interval: float = 0.5, z_delta: float = 0.0):
        ...

    def click_tuple(self, pos: Tuple[float, float], times: int = 1, interval: float = 0.5,
                    z_delta: float = 0.0):
        self.click(pos[0], pos[1], times, interval, z_delta)

    def swipe(self, fx_from: float, fy_from: float, fx_to: float, fy_to: float, speed: int = 200):
        ...

    def swipe_tuple(self, pos_from: Tuple[float, float], pos_to: Tuple[float, float], speed: int = 200):
        self.swipe(pos_from[0], pos_from[1], pos_to[0], pos_to[1], speed)

    def long_press(self, fx: float, fy: float, hold_time: float = 1, z_delta: float = 0.0):
        ...

    def long_press_tuple(self, pos: Tuple[float, float], hold_time: float = 1, z_delta: float = 0.0):
        self.long_press(pos[0], pos[1], hold_time, z_delta)

    def click_back(self, times: int = 1, interval: float = 0.5):
        ...

    def click_home(self, times: int = 1, interval: float = 0.5):
        ...

    def home_axes(self, fast_mode: bool = True):
        ...

    def click_menu(self, times: int = 1, interval: float = 0.5):
        ...

    def click_power(self, times: int = 1, interval: float = 0.5):
        ...

    def long_press_power(self, hold_time: float = 2):
        ...

    def match_template(self, template_input, target_score=0.7, match_times=1, match_interval=1.0,
                       limit_area: Optional[Tuple[float, float, float, float]] = None,
                       match_method: str = 'normal', raise_on_match_failed=False, show_log=True) -> TemplateMatchResult:
        """
        template_input可以回退到(float, float)，这意味着传递的是一个占比坐标，当等待适当的时间后（来自match_interval和match_times），会直接返回该坐标
        """
        if match_times < 1:
            raise ValueError('The Match times parameter cannot be less than 1.')

        # for debug fallback
        if isinstance(template_input, tuple):
            time.sleep(match_interval * (match_times - 1) * 0.6)
            return TemplateMatchResult(target_score=target_score, score=2, bounds=(
                template_input[0], template_input[1], template_input[0], template_input[1]), result_code=0)
        ...

    def match_text(self, template_input, target_score=0.7, match_times=1, match_interval=1.0, match_lang="eng",
                   limit_area: Optional[Tuple[float, float, float, float]] = None, case_sensitive: bool = True,
                   match_method: str = 'normal', raise_on_match_failed=False, show_log=True) -> TemplateMatchResult:
        """
        template_input可以回退到(float, float)，这意味着传递的是一个占比坐标，当等待适当的时间后（来自match_interval和match_times），会直接返回该坐标
        """
        if match_times < 1:
            raise ValueError('The Match times parameter cannot be less than 1.')

        # for debug fallback
        if isinstance(template_input, tuple):
            time.sleep(match_interval * (match_times - 1) * 0.6)
            return TemplateMatchResult(target_score=target_score, score=2, bounds=(
                template_input[0], template_input[1], template_input[0], template_input[1]), result_code=0)
        ...

    def click_match_template(self, template_input, target_score=0.7, match_times=1, match_interval=1.0,
                             limit_area: Optional[Tuple[float, float, float, float]] = None,
                             match_method: str = 'normal', pos_offset=(0.0, 0.0),
                             click_times=1, click_interval=0.5, z_delta: float = 0.0) -> TemplateMatchResult:
        """
        template_input可以回退到(float, float)，这意味着传递的是一个占比坐标，当等待适当的时间后（来自match_interval和match_times），会直接点击该坐标
        """
        # for debug fallback
        if isinstance(template_input, tuple):
            time.sleep(match_interval * (match_times - 1) * 0.6)
            self.click(template_input[0], template_input[1], click_times, click_interval, z_delta)
            return TemplateMatchResult(target_score=target_score, score=2, bounds=(
                template_input[0], template_input[1], template_input[0], template_input[1]), result_code=0)

        match_result = self.match_template(template_input, target_score, match_times, match_interval, limit_area,
                                           match_method, True)
        click_pos = match_result.center
        size = match_result.size
        click_pos = (click_pos[0] + pos_offset[0] * size[0], click_pos[1] + pos_offset[1] * size[1])
        assert 0 <= click_pos[0] <= 1 and 0 <= click_pos[1] <= 1
        self.click_tuple(click_pos, click_times, click_interval, z_delta)
        return match_result

    def click_match_text(self, template_input, target_score=0.7, match_times=1, match_interval=1.0, match_lang="eng",
                         limit_area: Optional[Tuple[float, float, float, float]] = None,
                         match_method: str = 'normal', pos_offset=(0.0, 0.0), case_sensitive: bool = True,
                         click_times=1, click_interval=0.5, z_delta: float = 0.0) -> TemplateMatchResult:
        """
        template_input可以回退到(float, float)，这意味着传递的是一个占比坐标，当等待适当的时间后（来自match_interval和match_times），会直接点击该坐标
        """
        # for debug fallback
        if isinstance(template_input, tuple):
            time.sleep(match_interval * (match_times - 1) * 0.6)
            self.click(template_input[0], template_input[1], click_times, click_interval, z_delta)
            return TemplateMatchResult(target_score=target_score, score=2, bounds=(
                template_input[0], template_input[1], template_input[0], template_input[1]), result_code=0)

        match_result = self.match_text(template_input, target_score, match_times, match_interval, match_lang,
                                       limit_area, case_sensitive, match_method, True)
        click_pos = match_result.center
        click_pos = (click_pos[0] + pos_offset[0], click_pos[1] + pos_offset[1])
        assert 0 <= click_pos[0] <= 1 and 0 <= click_pos[1] <= 1
        self.click_tuple(click_pos, click_times, click_interval, z_delta)
        return match_result

    def assert_match_template(self, template_input, target_score=0.7, match_times=1, match_interval=1.0,
                              limit_area: Optional[Tuple[float, float, float, float]] = None,
                              match_method: str = 'normal') -> TemplateMatchResult:
        """
        template_input可以回退到(float, float)，这意味着传递的是一个占比坐标，当等待适当的时间后（来自match_interval和match_times），会直接返回该坐标
        """
        match_result = self.match_template(template_input, target_score, match_times, match_interval, limit_area,
                                           match_method, True)
        return match_result

    def assert_match_text(self, template_input, target_score=0.7, match_times=1, match_interval=1.0, match_lang="eng",
                          limit_area: Optional[Tuple[float, float, float, float]] = None,
                          case_sensitive: bool = True, match_method: str = 'normal') -> TemplateMatchResult:
        """
        template_input可以回退到(float, float)，这意味着传递的是一个占比坐标，当等待适当的时间后（来自match_interval和match_times），会直接返回该坐标
        """
        match_result = self.match_text(template_input, target_score, match_times, match_interval, match_lang,
                                       limit_area, case_sensitive, match_method, True)
        return match_result

    def swipe_direction(self, direction: str, distance_ratio: float = 0.5, speed: int = 200):
        """
        从屏幕中心出发，根据方向前后加减一半 distance_ratio，
        然后按 speed 滑动。
        支持的 direction: up, down, left, right
        """
        cx, cy = self.CENTER
        d = distance_ratio / 2.0
        direction = direction.lower()
        if direction == "up":
            start = (cx, cy + d)
            end = (cx, cy - d)
        elif direction == "down":
            start = (cx, cy - d)
            end = (cx, cy + d)
        elif direction == "left":
            start = (cx + d, cy)
            end = (cx - d, cy)
        elif direction == "right":
            start = (cx - d, cy)
            end = (cx + d, cy)
        else:
            raise ValueError(f"不支持的方向: {direction}")
        self.swipe(start[0], start[1], end[0], end[1], speed)

    def edge_swipe(self, edge: str = 'bottom', distance_ratio: float = 0.2, speed: int = 200):
        """
        从边缘向内滑动。
        edge 支持的值: bottom, left, right, top, top_left, top_right
        对于 top_left 和 top_right，起点分别为 (0.25, 0.02) 和 (0.75, 0.02)，均向下滑动。
        滑动距离为 distance_ratio。
        """
        edge = edge.lower()
        if edge not in self.EDGE_PRESETS:
            raise ValueError(f"不支持的边缘: {edge}")
        preset = self.EDGE_PRESETS[edge]
        sx, sy = preset["start"]
        dx, dy = preset["end_delta"]
        ex = sx + dx * distance_ratio
        ey = sy + dy * distance_ratio
        self.swipe(sx, sy, ex, ey, speed)

    def detect_black_screen(self, threshold_mean: float = 1, threshold_std: float = 1) -> bool:
        ...

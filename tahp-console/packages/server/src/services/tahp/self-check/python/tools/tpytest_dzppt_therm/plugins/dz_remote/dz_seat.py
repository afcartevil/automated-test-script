import json
import time
from typing import Tuple, Optional, Callable

from dz_remote.dz_api_error import TestExecutionError, TestExecutionFailed
from dz_remote.dz_client import DzClient
from dz_remote.dz_rect import DzRect
from dz_remote.dz_remote_utils import dz_result_to_dict
from powertrde.framework.logs_protocol import logs_p
from powertrde.utils import misc_utils


class DzSeat:
    def __init__(self, dz_client: DzClient, seat_index: int):
        self.dz_client = dz_client
        self.seat_index = seat_index
        self.screen_rect = None  # {'X':0, 'Y':0, 'Width':1920, 'Height':1080}
        self._keys = []  # 工位可用按键列表
        self._setup_seat()
        self.user_args = {}

    def _setup_seat(self):
        """初始化工位参数"""
        devices = self.dz_client.get_device_info()
        if not devices:
            raise ValueError("未找到可用工位信息")

        target = next((d for d in devices if d['DeviceNo'] == self.seat_index), None)
        if not target:
            raise ValueError(f"工位{self.seat_index}不存在")

        # 解析屏幕范围
        rect_str = target.get('RecByCamera', '{X=0,Y=0,Width=0,Height=0}')[1:-1]
        self.screen_rect = {
            k: float(v) for item in rect_str.split(',')
            for k, v in [item.strip().split('=')]
        }

        # 解析按键配置
        self._keys = [key['Name'] for key in target.get('Keys', [])]

    # def validate_coordinate(self, x: float, y: float):
    #     """验证坐标是否在屏幕范围内"""
    #     if not (self.screen_rect['X'] <= x <= self.screen_rect['X'] + self.screen_rect['Width']):
    #         raise ValueError(
    #             f"X坐标{x}超出屏幕范围[{self.screen_rect['X']}-{self.screen_rect['X'] + self.screen_rect['Width']}]")
    #     if not (self.screen_rect['Y'] <= y <= self.screen_rect['Y'] + self.screen_rect['Height']):
    #         raise ValueError(
    #             f"Y坐标{y}超出屏幕范围[{self.screen_rect['Y']}-{self.screen_rect['Y'] + self.screen_rect['Height']}]")

    def execute_test_case(self, case_path: str, timeout_seconds: float = 1200, delete_task_on_finish=True,
                          on_task_end: Optional[Callable[[int, Optional[dict], Optional[Exception]], None]] = None):
        """
        执行测试用例并等待完成

        返回的格式举例如下：
        {"TestExecutionLogs":[{"Id":18567,"TaskId":99,"SetId":66,"CaseId":1136,"CaseName":"DOU3_Facebook_Video_1",
        "StartTime":"2025-02-12T17:15:38.103","FinishTime":"2025-02-12T17:15:43.393","ExeResult":false,"ExeResultNew":0,
        "ExeTimeSapn":5290,"CustomLogs":null,"ResultDetail":null,"MarkTimeSpan":0,
        "WorkFolder":"D:\DZSOFT\exe\V2.2024.1213.1820_RELEASE\Release\logs\Robot\taskLogs\99\1136\20250212171538103"}],
        "ret":true,"error":null}
        """
        state = self.dz_client.safe_call(self.dz_client.rpc_client.GetTaskExecuteState)
        if state:
            logs_p().log('发现DZ任务正在执行中，无法执行下个任务，准备查找正在执行的任务ID...')
            task_info = self.dz_client.rpc_client.GetAllTasks()
            parsed_data = json.loads(task_info)
            task_ids = [execution["TaskId"] for task_set in parsed_data for execution in task_set["Executions"]]
            task_ids = list(set(task_ids))
            task_ids.sort()
            logs_p().log('已经执行过的任务ID集合是：' + str(task_ids))
            if task_ids:
                last_id = task_ids[-1]
                for i in range(6):
                    task_ids.append(last_id - i - 1)
                    task_ids.append(last_id + i + 1)
            for task_id in task_ids:
                task_id_state = self.dz_client.safe_call(self.dz_client.rpc_client.GetTaskState, task_id)
                if task_id_state == 'Running':
                    self.dz_client.stop_task(task_id)
                    time.sleep(0.2)
                    logs_p().log(
                        f'DZ任务ID {task_id} 正在执行并已尝试停止，当前此任务的状态为 {self.dz_client.safe_call(self.dz_client.rpc_client.GetTaskState, task_id)}')

            self.home_axes()
            time.sleep(0.5)

        task_id = 0
        result_json = None
        exc = None
        try:
            try:
                task_id = self.dz_client.safe_call(
                    self.dz_client.rpc_client.ExecCase,
                    case_path, self.seat_index
                )
            except Exception as e:
                logs_p().log_error(f'DZ任务执行时发生错误，原因为：{e}\n将等待一会儿重试一次！')
                for i in range(6):
                    time.sleep(1)
                    if not self.dz_client.safe_call(self.dz_client.rpc_client.GetTaskExecuteState):
                        break
                task_id = self.dz_client.safe_call(
                    self.dz_client.rpc_client.ExecCase,
                    case_path, self.seat_index
                )

            start_time = time.time()
            retry_get_result_count = 0
            while time.time() - start_time < timeout_seconds:
                state = self.dz_client.safe_call(
                    self.dz_client.rpc_client.GetTaskState,
                    task_id
                )
                if state == "Finish":
                    time.sleep(0.5)

                    try:
                        dz_result = self.dz_client.get_task_result(task_id)
                    except Exception as e:
                        time.sleep(0.5)
                        retry_get_result_count += 1
                        if retry_get_result_count < 10:
                            logs_p().log(
                                f'DZ任务ID {task_id} 已经Finish，但是无法获取其运行结果，将重试，错误详情：{e}')
                            continue
                        else:
                            raise

                    def _retry_get_result():
                        nonlocal dz_result
                        dz_result = self.dz_client.get_task_result(task_id)

                    misc_utils.retry_func(_retry_get_result, attempts=10, on_exception=lambda _e, _i: time.sleep(1))

                    result_json = dz_result_to_dict(dz_result)['TestExecutionLogs'][0]
                    exec_result = result_json['ExeResult']
                    if not exec_result:
                        raise TestExecutionFailed(f"Case Task '{case_path}' Fail", result_json)
                    return result_json
                elif state == "Error":
                    time.sleep(0.5)
                    raise TestExecutionError(f"Case Task '{case_path}' Error")
                time.sleep(1)

            try:
                self.dz_client.stop_task(task_id)
            except Exception:
                pass
            raise TimeoutError(f"Case Task '{case_path}' Timeout, expect {timeout_seconds:.1f}s")
        except Exception as e:
            exc = e
            raise
        finally:
            if task_id:
                if on_task_end:
                    on_task_end(task_id, result_json, exc)

                if delete_task_on_finish:
                    self.dz_client.safe_call(
                        self.dz_client.rpc_client.DeleteTaskById,
                        task_id
                    )

    def delete_task(self, task_id: int):
        return self.dz_client.delete_task(task_id)

    @property
    def available_keys(self):
        """返回工位支持的物理按键列表"""
        return self._keys.copy()

    def __repr__(self):
        return f"<DzSeat {self.seat_index} | Screen: {self.screen_rect['Width']}x{self.screen_rect['Height']}>"

    class GesturePreset:
        """手势预设定位系统"""
        CENTER = (0.5, 0.5)
        TOP_CENTER = (0.5, 0.1)
        BOTTOM_CENTER = (0.5, 0.9)
        LEFT_CENTER = (0.1, 0.5)
        RIGHT_CENTER = (0.9, 0.5)
        TOP_LEFT = (0.1, 0.1)
        TOP_RIGHT = (0.9, 0.1)
        BOTTOM_LEFT = (0.1, 0.9)
        BOTTOM_RIGHT = (0.9, 0.9)

    @property
    def to_screen_ratio_x(self) -> float:
        """屏幕宽度转换比例"""
        return self.screen_rect['Width']

    @property
    def to_screen_ratio_y(self) -> float:
        """屏幕宽度转换比例"""
        return self.screen_rect['Height']

    def _rel_to_abs(self, rel_x: float, rel_y: float) -> Tuple[float, float]:
        """将相对坐标转换为绝对坐标"""
        return (
            rel_x * self.screen_rect['Width'],
            rel_y * self.screen_rect['Height']
        )

    # ---------- 核心交互操作 ----------
    def click_relative(self, rel_x: float, rel_y: float, click_type: int = 0, timeout: int = 0):
        """相对坐标点击（0-1范围）"""
        x, y = self._rel_to_abs(rel_x, rel_y)
        return self.click_screen(x, y, click_type, timeout)

    def swipe_relative(self,
                       start_rel: Tuple[float, float],
                       end_rel: Tuple[float, float],
                       speed: int = 200,
                       curve: bool = False):
        """相对坐标滑动"""
        start_x, start_y = self._rel_to_abs(*start_rel)
        end_x, end_y = self._rel_to_abs(*end_rel)
        if curve:
            return self.dz_client.safe_call(
                self.dz_client.rpc_client.CurveSwipe,
                self.seat_index, start_x, start_y, end_x, end_y, speed
            )
        else:
            return self.dz_client.safe_call(
                self.dz_client.rpc_client.Swipe,
                self.seat_index, start_x, start_y, end_x, end_y, speed
            )

    # ---------- 智能手势库 ----------
    def swipe_direction(self,
                        direction: str,
                        distance_ratio: float = 0.5,
                        speed: int = 200):
        """
        方向滑动（上下左右）
        :param direction: up/down/left/right
        :param distance_ratio: 滑动距离占屏幕比例
        :param speed: 速度在1-500
        """
        direction = direction.lower()
        base_x, base_y = self.GesturePreset.CENTER

        direction_map = {
            'up': (base_x, base_y + distance_ratio / 2, base_x, base_y - distance_ratio / 2),
            'down': (base_x, base_y - distance_ratio / 2, base_x, base_y + distance_ratio / 2),
            'left': (base_x + distance_ratio / 2, base_y, base_x - distance_ratio / 2, base_y),
            'right': (base_x - distance_ratio / 2, base_y, base_x + distance_ratio / 2, base_y)
        }

        if direction not in direction_map:
            raise ValueError(f"无效方向{direction}，支持: up/down/left/right")

        return self.swipe_relative(
            start_rel=direction_map[direction][:2],
            end_rel=direction_map[direction][2:],
            speed=speed
        )

    def edge_swipe(self,
                   edge: str = 'bottom',
                   distance_ratio: float = 0.3,
                   speed: int = 200):
        """
        边缘手势（调出系统UI）
        :param edge: top/bottom/left/right
        :param distance_ratio: 滑动距离比例
        :param speed: 滑动速度
        """
        edge = edge.lower()
        coord_map = {
            'top': ((0.5, 0.02), (0.5, 0.02 + distance_ratio)),
            'bottom': ((0.5, 0.98), (0.5, 0.98 - distance_ratio)),
            'left': ((0.02, 0.5), (0.02 + distance_ratio, 0.5)),
            'right': ((0.98, 0.5), (0.98 - distance_ratio, 0.5))
        }

        if edge not in coord_map:
            raise ValueError(f"无效边缘方向{edge}")

        return self.swipe_relative(*coord_map[edge], speed=speed)

    # ---------- 工位封装 ----------
    def click_key(self, key_name: str, click_type: int = 0, pause_time: int = 0):
        """
        按键点击操作（工位封装）

        :param key_name: str 按键名称，如'Home', 'Back'等
        :param click_type: int 点击类型，0表示单击，1表示双击，2表示长按
        :param pause_time: int 长按时间，仅当click_type为2时有效，单位为毫秒
        :return: 操作结果
        """
        if key_name not in self._keys:
            raise NotImplementedError(f"该工位{self.seat_index}未配置{key_name}键")
        return self.dz_client.click_key(self.seat_index, key_name, click_type, pause_time)

    def click_screen(self, x: float, y: float, click_type: int = 0, timeout: int = 0):
        """
        屏幕点击操作（工位封装）

        :param x: float 屏幕X坐标
        :param y: float 屏幕Y坐标
        :param click_type: int 点击类型，0表示单击，1表示双击，2表示长按
        :param timeout: int 长按超时时间，仅当click_type为2时有效
        :return: 操作结果
        """
        # self.validate_coordinate(x, y)
        return self.dz_client.click_screen(self.seat_index, x, y, click_type, timeout)

    def continuous_click_screen(self, x: float, y: float, z_delta: float = 0, times: int = 1, interval: int = 1000):
        """
        屏幕坐标连续点击

        :param x: float 屏幕X坐标
        :param y: float 屏幕Y坐标
        :param z_delta: float z轴增量
        :param times: int 连续点击次数
        :param interval: int 连续点击间隔（毫秒）
        :return: 操作结果
        """
        return self.dz_client.continuous_click_screen(self.seat_index, x, y, z_delta, times, interval)

    def swipe_screen(self, x1: float, y1: float, x2: float, y2: float, speed: int = 200):
        """
        屏幕滑动操作（工位封装）

        :param x1: float 起始点X坐标
        :param y1: float 起始点Y坐标
        :param x2: float 结束点X坐标
        :param y2: float 结束点Y坐标
        :param speed: int 滑动速度
        :return: 操作结果
        """
        return self.dz_client.swipe_screen(self.seat_index, x1, y1, x2, y2, speed)

    def curve_swipe_screen(self, x1: float, y1: float, x2: float, y2: float, speed: int = 200):
        """
        曲线滑动操作（工位封装）

        :param x1: float 起始点X坐标
        :param y1: float 起始点Y坐标
        :param x2: float 结束点X坐标
        :param y2: float 结束点Y坐标
        :param speed: int 滑动速度
        :return: 操作结果
        """
        return self.dz_client.curve_swipe_screen(self.seat_index, x1, y1, x2, y2, speed)

    def set_exposure_time(self, exposure_time: int):
        """
        设置相机曝光时间
        参数：exposure_time 曝光时间
        返回值：无
        """
        return self.dz_client.set_exposure_time(self.seat_index, exposure_time)

    def capture_screen(self, save_file: str):
        """
        屏幕截图（工位封装）

        :param save_file: str 保存截图的文件路径
        :return: 操作结果
        """
        return self.dz_client.capture_screen(self.seat_index, save_file)

    def match_template(self, image_file: str, exhaustive: float = 0.75, icon_type: str = "Normal",
                       rect_limit: Optional[DzRect] = None):
        """
        模板匹配识别（工位封装）

        :param image_file: str 模板图像文件路径
        :param exhaustive: float 匹配阈值，范围0.1到1.0
        :param icon_type: str 图标类型，Normal, Transparent, Feature
        :param rect_limit: DzRect 识别区域限制，可选参数，用于限制模板匹配的区域
        :return: 匹配结果，包括最佳匹配值、位置和尺寸
        """
        return self.dz_client.match_template(self.seat_index, image_file, exhaustive, icon_type,
                                             '' if not rect_limit else rect_limit.to_str())

    def ocr_text(self, rect_limit: Optional[DzRect] = None, angle: int = 0):
        """
        光学字符识别（OCR）（工位封装）

        :param rect_limit: DzRect 识别区域限制，可选参数，用于限制OCR识别的区域
        :param angle: int 文本旋转角度，支持0, 90, 180, 270
        :return: 识别结果，包括识别的文本列表及其位置和置信度
        """
        return self.dz_client.ocr_text(self.seat_index, '' if not rect_limit else rect_limit.to_str(), angle)

    def home_axes(self, fast: bool = True):
        """
        全轴回零操作 （工位封装）

        :param fast: 是否快速回零模式
        :return: 操作是否成功
        """
        return self.dz_client.home_axes(self.seat_index, fast)

    # ---------- 系统级操作 ----------

    def press_home(self):
        """Home键操作"""
        return self.click_key('Home')

    def long_press_home(self, hold_time: int = 1000):
        """Home键长按"""
        return self.click_key('Home', click_type=2, pause_time=hold_time)

    def double_press_home(self):
        """双击Home键"""
        return self.click_key('Home', click_type=1)

    def triple_press_home(self):
        """三击Home键"""
        self.click_key('Home', click_type=1)
        self.click_key('Home')

    def press_back(self):
        """返回键"""
        self.click_key('Back')

    def press_menu(self):
        """菜单键"""
        self.click_key('Menu')

    def long_press_power(self, hold_time: int = 2000):
        """Power键长按"""
        self.click_key('Power', click_type=2, pause_time=hold_time)

    def open_notification(self, from_edge: str = 'top_left'):
        """打开通知中心（兼容不同机型）"""
        coord_strategy = {
            'top_left': ((0.1, 0.05), (0.1, 0.3)),
            'top_center': (self.GesturePreset.TOP_CENTER, self.GesturePreset.BOTTOM_CENTER)
        }
        return self.swipe_relative(*coord_strategy[from_edge], speed=200)

    def open_control_center(self, from_edge: str = 'top_right'):
        """打开控制中心"""
        coord_strategy = {
            'top_right': ((0.9, 0.05), (0.9, 0.3)),
            'bottom_up': (self.GesturePreset.BOTTOM_RIGHT, self.GesturePreset.TOP_RIGHT)
        }
        return self.swipe_relative(*coord_strategy[from_edge], speed=200)

    # ---------- 快速访问方法 ----------
    @property
    def display_center(self) -> Tuple[float, float]:
        return self._rel_to_abs(*self.GesturePreset.CENTER)

    def tap_center(self):
        """点击屏幕中心"""
        return self.click_relative(*self.GesturePreset.CENTER)

    # --------- 进阶方法 --------------

    # --------- 续航温升方法 --------------
    def get_flir_history(self, flir_id: int):
        """
        获取指定热像仪的全部选区温度记录集合
        参数：
            flir_id: 热像仪的指定ID（需要查看配置文件的热像仪对应ID）
        返回值：指定热像仪的全部选区温度记录集合的数据（JSON）
        """
        return self.dz_client.get_flir_history(flir_id)

    def get_flir_one_history(self, flir_id: int, area_name: str):
        """
        获取指定热像仪某一选区的温度记录集合
        参数：
            flir_id: 热像仪的指定ID
            area_name: 选区的名称
        返回值：指定热像仪的指定选区温度集合的数据（JSON）
        """
        return self.dz_client.get_flir_one_history(flir_id, area_name)

    def get_flir_current_temp_value(self, flir_id: int):
        """
        获取指定热像仪的当前温度
        参数：
            flir_id: 热像仪的指定ID
        返回值：热像仪的当前温度值（double）
        """
        return self.dz_client.get_flir_current_temp_value(flir_id)

    def open_temperature_box(self, temperature_value: float, timeout: float, wait_time: int):
        """
        打开温箱，并设置目标温度
        参数：
            temperature_value: 要设置的恒温箱温度值
            timeout: 等待达到指定温度的超时时间，默认为0（立即返回）
            wait_time: 达到指定温度后等待的时间，单位为毫秒，默认为0（立即返回）
        返回值：True（成功）或 False（失败）
        """
        return self.dz_client.open_temperature_box(temperature_value, timeout, wait_time)

    def close_temperature_box(self):
        """
        关闭温箱
        返回值：True（成功）或 False（失败）
        """
        return self.dz_client.close_temperature_box()

    def get_current_temperature(self):
        """
        查询当前环境温度
        返回值：当前环境温度（double）
        """
        return self.dz_client.get_current_temperature()

    def open_fan(self, group_id: int):
        """
        打开指定风扇组
        参数：
            group_id: 风扇组ID（1-4）
        返回值：True（成功）或 False（失败）
        """
        return self.dz_client.open_fan(group_id)

    def open_fan_with_wind(self, group_id: int, wind: int):
        """
        打开指定风扇组并设置风力
        参数：
            group_id: 风扇组ID（1-4）
            wind: 风力（0-99）
        返回值：True（成功）或 False（失败）
        """
        return self.dz_client.open_fan_with_wind(group_id, wind)

    def close_fan(self, group_id: int):
        """
        关闭指定风扇组
        参数：
            group_id: 风扇组ID（1-4）
        返回值：True（成功）或 False（失败）
        """
        return self.dz_client.close_fan(group_id)

    def open_air_conditioner(self):
        """
        打开空调
        返回值：True（成功）或 False（失败）
        """
        return self.dz_client.open_air_conditioner()

    def close_air_conditioner(self):
        """
        关闭空调
        返回值：True（成功）或 False（失败）
        """
        return self.dz_client.close_air_conditioner()

    def change_power_status(self, channel_no: int, on_off_status: int):
        """
        控制程控电源指定通道的电源通断
        参数：
            channel_no: 通道号（从1开始）
            on_off_status: 开关状态（0：关，1：开）
        返回值：无
        """
        return self.dz_client.change_power_status(channel_no, on_off_status)

    def usb_charge_control(self, channel_no: int, control_type: str):
        """
        USB切换控制
        参数：
            channel_no: 通道号（从1开始）
            control_type: 控制类型（如“快充”、“浮地”、“接地”、“OTG”、“接通USB”、“断开USB”）
        返回值：无
        """
        return self.dz_client.usb_charge_control(channel_no, control_type)

    def open_usb(self, model: str) -> bool:
        """
        切换USB模式

        :param model: str USB模式
        :return: bool 操作结果
        """
        return self.dz_client.open_usb(self.seat_index, model)

    def close_usb(self) -> bool:
        """
        断开USB连接

        :return: bool 操作结果
        """
        return self.dz_client.close_usb(self.seat_index)

    def check_temperature(self, temperature_value: float, condition: str) -> bool:
        """
        检查温度是否符合给定条件

        :param condition: str 条件（GreatThan、Equal、LessThan）
        :return: bool 判断结果
        """
        return self.dz_client.check_temperature(temperature_value, condition)



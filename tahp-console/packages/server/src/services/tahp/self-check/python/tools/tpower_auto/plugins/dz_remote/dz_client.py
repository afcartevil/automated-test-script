import json
import time
from typing import Optional, List, Dict


from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol

from dz_remote.DONGZHOU.Device.Server.ActionProvider import Client
from dz_remote.dz_api_error import DzApiError
from powertrde.framework.logs_protocol import logs_p


class DzClient:
    def __init__(self):
        self.rpc_client: Optional[Client] = None
        self._transport: Optional[TTransport.TBufferedTransport] = None
        # self.logger = logging.getLogger(__name__)
        self._hw_status_cache = {}  # 硬件状态缓存
        self._seats = {}
        self.selected_seat_index = 1

    @property
    def seat(self):
        from dz_remote.dz_seat import DzSeat
        exist_seat = self._seats.get(self.selected_seat_index)
        if not exist_seat:
            exist_seat = DzSeat(self, self.selected_seat_index)
            self._seats[self.selected_seat_index] = exist_seat
        return exist_seat

    def connect_dz(self, to_remote_mode=True):
        """连接机械臂"""
        try:
            self._transport = TTransport.TBufferedTransport(
                TSocket.TSocket('127.0.0.1', 9300)
            )
            protocol = TBinaryProtocol.TBinaryProtocol(self._transport)
            self.rpc_client = Client(protocol)
            self._transport.open()
            if to_remote_mode:
                try:
                    self.rpc_client.GetDevices()
                except:
                    self._transport.close()
                    self._transport.open()
                    self.to_remote_mode()
                    time.sleep(0.3)
                    self.rpc_client.GoHome(1, '主手')
                    time.sleep(0.3)
            logs_p().log("成功连接东舟控制服务")
            return
        except TTransport.TTransportException as e:
            logs_p().log_error(f"连接失败，错误：{e}")
            time.sleep(1)
        raise ConnectionError("无法连接到东舟服务")

    def safe_call(self, func, *args, **kwargs):
        """带异常处理的统一调用方法"""
        try:
            if not self._transport.isOpen():
                self.connect_dz()
            result = func(*args, **kwargs)
            return result
        except TTransport.TTransportException as e:
            logs_p().log_error(f"RPC调用失败：{e}")
            self.update_hw_status()  # 更新硬件状态
            raise DzApiError(str(e)) from e

    def update_hw_status(self):
        """更新硬件状态缓存"""
        try:
            result = json.loads(self.rpc_client.GetHWStatus())
            self._hw_status_cache = {item['Type']: item for item in result}
        except Exception as e:
            logs_p().log(f"硬件状态更新失败：{e}")

    def get_device_info(self) -> List[Dict]:
        """获取所有工位结构化数据"""
        devices_json = self.safe_call(self.rpc_client.GetDevices)
        return json.loads(devices_json).get("Devices", [])

    @property
    def is_connected(self):
        return self._transport and self._transport.isOpen()

    def __enter__(self):
        self.connect_dz()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._transport.close()

    def to_remote_mode(self):
        self.rpc_client.SetModel('remote')

    def to_local_mode(self):
        self.rpc_client.SetModel('local')

    # ---------- 常用API封装 ----------
    def click_key(self, device_no: int, key_name: str, click_type: int = 0, pause_time: int = 0):
        """
        按键点击操作

        :param device_no: int 工位编号，指定在哪个工位进行操作
        :param key_name: str 按键名称，如'Home', 'Back'等
        :param click_type: int 点击类型，0表示单击，1表示双击，2表示长按
        :param pause_time: int 长按时间，仅当click_type为2时有效，单位为毫秒
        :return: 操作结果，成功或失败及错误信息
        """
        return self.safe_call(
            self.rpc_client.ClickKey,
            device_no, key_name, click_type, pause_time
        )

    def click_home(self, device_no: int, long_press: bool = False):
        """
        Home键点击操作

        :param device_no: int 工位编号
        :param long_press: bool 是否长按Home键
        :return: 操作结果
        """
        return self.click_key(device_no, 'Home', click_type=2 if long_press else 0,
                              pause_time=1000 if long_press else 0)

    def click_back(self, device_no: int):
        """
        返回键点击操作

        :param device_no: int 工位编号
        :return: 操作结果
        """
        return self.click_key(device_no, 'Back')

    def click_menu(self, device_no: int):
        """
        Menu键点击操作

        :param device_no: int 工位编号
        :return: 操作结果
        """
        return self.click_key(device_no, 'Menu')

    def adjust_volume(self, device_no: int, up: bool = True):
        """
        音量调整

        :param device_no: int 工位编号
        :param up: bool True表示音量增加，False表示音量减小
        :return: 操作结果
        """
        key = 'VolUp' if up else 'VolDown'
        return self.click_key(device_no, key)

    def long_press_power(self, device_no: int, duration: int = 2000):
        """
        长按Power键

        :param device_no: int 工位编号
        :param duration: int 长按持续时间，单位为毫秒
        :return: 操作结果
        """
        return self.click_key(device_no, 'Power', click_type=2, pause_time=duration)

    # ---------- 屏幕操作封装 ----------
    def click_screen(self, device_no: int, x: float, y: float, click_type: int = 0, timeout: int = 0):
        """
        屏幕坐标点击

        :param device_no: int 工位编号
        :param x: float 屏幕X坐标
        :param y: float 屏幕Y坐标
        :param click_type: int 点击类型，0表示单击，1表示双击，2表示长按
        :param timeout: int 长按超时时间，仅当click_type为2时有效
        :return: 操作结果
        """
        return self.safe_call(
            self.rpc_client.Click,
            device_no, x, y, click_type, timeout
        )

    def continuous_click_screen(self, device_no: int, x: float, y: float, z_delta: float = 0, times: int = 1, interval: int = 1000):
        """
        屏幕坐标点击

        :param device_no: int 工位编号
        :param x: float 屏幕X坐标
        :param y: float 屏幕Y坐标
        :param z_delta: float z轴增量
        :param times: int 连续点击次数
        :param interval: int 连续点击间隔（毫秒）
        :return: 操作结果
        """
        return self.safe_call(
            self.rpc_client.GetContinuousClick,
            x, y, device_no, z_delta, times, interval, False
        )

    def swipe_screen(self, device_no: int, x1: float, y1: float, x2: float, y2: float, speed: int = 200):
        """
        屏幕滑动操作

        :param device_no: int 工位编号
        :param x1: float 起始点X坐标
        :param y1: float 起始点Y坐标
        :param x2: float 结束点X坐标
        :param y2: float 结束点Y坐标
        :param speed: int 滑动速度
        :return: 操作结果
        """
        return self.safe_call(
            self.rpc_client.Swipe,
            device_no, x1, y1, x2, y2, speed
        )

    def curve_swipe_screen(self, device_no: int, x1: float, y1: float, x2: float, y2: float, speed: int = 200):
        """
        曲线滑动操作

        :param device_no: int 工位编号
        :param x1: float 起始点X坐标
        :param y1: float 起始点Y坐标
        :param x2: float 结束点X坐标
        :param y2: float 结束点Y坐标
        :param speed: int 滑动速度
        :return: 操作结果
        """
        return self.safe_call(
            self.rpc_client.CurveSwipe,
            device_no, x1, y1, x2, y2, speed
        )

    # ---------- 任务执行相关 ----------
    def exec_case(self, case_name: str, device_no: int):
        """
        执行用例

        :param case_name: str 用例名称，路径格式支持节点结构
        :param device_no: int 工位编号
        :return: int 任务ID
        """
        return self.safe_call(self.rpc_client.ExecCase, case_name, device_no)

    def check_task_state(self, task_id: int):
        """
        检查任务执行状态

        :param task_id: int 任务ID
        :return: str 任务状态（Running, Finish, Error等）
        """
        return self.safe_call(self.rpc_client.GetTaskState, task_id)

    def get_task_result(self, task_id: int):
        """
        获取任务执行结果

        :param task_id: int 任务ID
        :return: dict 任务结果信息，包含执行日志和细节
        """
        return self.safe_call(self.rpc_client.GetTaskResult, task_id)

    def get_task_detail(self, task_id: int):
        """
        获取任务执行结果

        :param task_id: int 任务ID
        :return: dict 任务的执行细节
        """
        return self.safe_call(self.rpc_client.GetTaskDetail, task_id)

    def stop_task(self, task_id: int):
        """
        停止任务

        :param task_id: int 任务ID
        :return: 操作结果
        """
        return self.safe_call(self.rpc_client.StopTask, task_id)

    def delete_task(self, task_id: int):
        """
        删除任务

        :param task_id: int 任务ID
        :return: 操作结果
        """
        return self.safe_call(self.rpc_client.DeleteTaskById, task_id)

    # ---------- 设备状态检查 ----------
    def get_device_status(self):
        """
        获取设备硬件状态

        :return: list 设备状态列表，包括每个设备的类型、ID、活动状态及错误消息
        """
        return self.safe_call(self.rpc_client.GetHWStatus)

    def is_device_active(self, device_type: str):
        """
        检查特定设备是否正常工作

        :param device_type: str 设备类型，例如'Camera', 'Robot'
        :return: bool 设备是否正常
        """
        status = self.get_device_status()
        for device in status:
            if device['Type'] == device_type:
                return device['Active']
        return False

    # ---------- 图像识别相关 ----------
    def match_template(self, device_no: int, image_file: str, exhaustive: float = 0.75, icon_type: str = "Normal",
                       rect_limit: str = ""):
        """
        模板匹配识别

        :param device_no: int 工位编号
        :param image_file: str 模板图像文件路径
        :param exhaustive: float 匹配阈值，范围0.1到1.0
        :param icon_type: str 图标类型，Normal, Transparent, Feature
        :param rect_limit: str 限制区域，格式"x,y,width,height"，空字符串表示全图
        :return: dict 匹配结果，包括最佳匹配值、位置和尺寸
        """
        return self.safe_call(
            self.rpc_client.MatchTemplate,
            device_no, image_file, exhaustive, icon_type, rect_limit
        )

    def ocr_text(self, device_no: int, rect_limit: str = "", angle: int = 0):
        """
        光学字符识别（OCR）

        :param device_no: int 工位编号
        :param rect_limit: str 限制区域，空字符串表示全图识别
        :param angle: int 文本旋转角度，支持0, 90, 180, 270
        :return: dict 识别结果，包括识别的文本列表及其位置和置信度
        """
        return self.safe_call(
            self.rpc_client.OCR,
            device_no, rect_limit, angle
        )

    def capture_screen(self, device_no: int, save_file: str):
        """
        屏幕截图

        :param device_no: int 工位编号
        :param save_file: str 保存截图的文件路径
        :return: 操作结果
        """
        return self.safe_call(
            self.rpc_client.ScreenShot,
            device_no, save_file
        )

    def start_image_grab(self, camera_index: int, save_path: str):
        """
        开始图像采集

        :param camera_index: int 相机索引编号
        :param save_path: str 图像保存路径
        :return: 操作结果
        """
        return self.safe_call(
            self.rpc_client.StartImageGrab,
            camera_index, save_path
        )

    def stop_image_grab(self, camera_index: int):
        """
        停止图像采集

        :param camera_index: int 相机索引编号
        :return: 操作结果
        """
        return self.safe_call(
            self.rpc_client.StopImageGrab,
            camera_index
        )

    def get_single_image(self, camera_index: int, save_file: str):
        """
        获取相机单张图像

        :param camera_index: int 相机索引编号
        :param save_file: str 保存图像的文件路径
        :return: 操作结果
        """
        return self.safe_call(
            self.rpc_client.GetOneImage,
            camera_index, save_file
        )

    def set_exposure_time(self, device_no: int, exposure_time: int):
        """
        设置相机曝光时间
        参数：exposure_time 曝光时间，deviceNo 工位号
        返回值：无
        """
        return self.safe_call(
            self.rpc_client.SetExposureTime,
            exposure_time, device_no, False
        )

    def home_axes(self, device_no: int, fast: bool = True):
        """
        全轴回零操作 (DOC 2.1-2.2节)

        :param device_no: 通过GetDevices验证的工位编号
        :param fast: 是否快速回零模式
        :return: 操作是否成功
        """
        # 快速回零可能有问题
        # method = self.rpc_client.FastGoHome if fast else self.rpc_client.GoHome
        method = self.rpc_client.GoHome
        return self.safe_call(method, device_no, '主手')

    # ---------- 续航温升相关 ----------
    def get_flir_history(self, flir_id: int):
        """
        获取指定热像仪的全部选区温度记录集合
        参数：
            flir_id: 热像仪的指定ID（需要查看配置文件的热像仪对应ID）
        返回值：指定热像仪的全部选区温度记录集合的数据（JSON）
        """
        return self.safe_call(
            self.rpc_client.GetFlirHistory,
            flir_id
        )

    def get_flir_one_history(self, flir_id: int, area_name: str):
        """
        获取指定热像仪某一选区的温度记录集合
        参数：
            flir_id: 热像仪的指定ID
            area_name: 选区的名称
        返回值：指定热像仪的指定选区温度集合的数据（JSON）
        """
        return self.safe_call(
            self.rpc_client.GetFlirOneHistory,
            flir_id, area_name
        )

    def get_flir_current_temp_value(self, flir_id: int):
        """
        获取指定热像仪的当前温度
        参数：
            flir_id: 热像仪的指定ID
        返回值：热像仪的当前温度值（double）
        """
        return self.safe_call(
            self.rpc_client.GetFlirCurrentTempValue,
            flir_id
        )

    def open_temperature_box(self, temperature_value: float, timeout: float = 0, wait_time: int = 0):
        """
        打开温箱，并设置目标温度
        参数：
            temperature_value: 要设置的恒温箱温度值
            timeout: 等待达到指定温度的超时时间，默认为0（立即返回）
            wait_time: 达到指定温度后等待的时间，单位为毫秒，默认为0（立即返回）
        返回值：True（成功）或 False（失败）
        """
        return self.safe_call(
            self.rpc_client.OpenTemperatureBox,
            temperature_value, timeout, wait_time
        )

    def close_temperature_box(self):
        """
        关闭温箱
        返回值：True（成功）或 False（失败）
        """
        return self.safe_call(
            self.rpc_client.CloseTemperatureBox
        )

    def get_current_temperature(self):
        """
        查询当前环境温度
        返回值：当前环境温度（double）
        """
        return self.safe_call(
            self.rpc_client.GetCurrentTemperature
        )

    def open_fan(self, group_id: int):
        """
        打开指定风扇组
        参数：
            group_id: 风扇组ID（1-4）
        返回值：True（成功）或 False（失败）
        """
        return self.safe_call(
            self.rpc_client.OpenFan,
            group_id
        )

    def open_fan_with_wind(self, group_id: int, wind: int):
        """
        打开指定风扇组并设置风力
        参数：
            group_id: 风扇组ID（1-4）
            wind: 风力（0-99）
        返回值：True（成功）或 False（失败）
        """
        return self.safe_call(
            self.rpc_client.OpenFanForWind,
            group_id, wind
        )

    def close_fan(self, group_id: int):
        """
        关闭指定风扇组
        参数：
            group_id: 风扇组ID（1-4）
        返回值：True（成功）或 False（失败）
        """
        return self.safe_call(
            self.rpc_client.CloseFan,
            group_id
        )

    def open_air_conditioner(self):
        """
        打开空调
        返回值：True（成功）或 False（失败）
        """
        return self.safe_call(
            self.rpc_client.OpenAir_Conditioner
        )

    def close_air_conditioner(self):
        """
        关闭空调
        返回值：True（成功）或 False（失败）
        """
        return self.safe_call(
            self.rpc_client.CloseAir_Conditioner
        )

    def change_power_status(self, channel_no: int, on_off_status: int):
        """
        控制程控电源指定通道的电源通断
        参数：
            channel_no: 通道号（从1开始）
            on_off_status: 开关状态（0：关，1：开）
        返回值：无
        """
        return self.safe_call(
            self.rpc_client.ChangePowerStatu,
            channel_no, on_off_status
        )

    def usb_charge_control(self, channel_no: int, control_type: str):
        """
        USB切换控制
        参数：
            channel_no: 通道号（从1开始）
            control_type: 控制类型（如“快充”、“浮地”、“接地”、“OTG”、“接通USB”、“断开USB”）
        返回值：无
        """
        return self.safe_call(
            self.rpc_client.USBChargeControl,
            channel_no, control_type
        )

    def open_usb(self, device_no: int, model: str) -> bool:
        """
        切换USB模式

        :param device_no: int 工位编号
        :param model: str USB模式
        :return: bool 操作结果
        """
        return self.safe_call(
            self.rpc_client.OpenUSB,
            device_no, model
        )

    def close_usb(self, device_no: int) -> bool:
        """
        断开USB连接

        :param device_no: int 工位编号
        :return: bool 操作结果
        """
        return self.safe_call(
            self.rpc_client.CloseUSB,
            device_no
        )

    def check_temperature(self, temperature_value: float, condition: str) -> bool:
        """
        检查温度是否符合给定条件

        :param temperature_value: float 参照温度
        :param condition: str 条件（GreatThan、Equal、LessThan）
        :return: bool 判断结果
        """
        return self.safe_call(
            self.rpc_client.IFTemperature,
            temperature_value,
            condition
        )


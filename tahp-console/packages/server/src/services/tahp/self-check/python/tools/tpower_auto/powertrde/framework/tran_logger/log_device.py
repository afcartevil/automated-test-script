import os
import socket
import subprocess
import time
from typing import Optional, Union, Callable, List

import mss
import mss.tools

from powertrde.env import ADB_EXE
from powertrde.framework.lazy_device_id import LazyDeviceID, SerialProvider, CachedSerialProvider
from powertrde.utils.trde import adb


class LogDevice:
    """
    设备基类，所有设备都应继承该类。
    - 设备 ID (`lazy_device_id`) 采用 `LazyDeviceID`，支持 **延迟计算** 或 **直接赋值**。
    - `device_id` 属性确保始终返回字符串。
    """

    def __init__(self, device_id: Union[
        None, str, SerialProvider, CachedSerialProvider, Callable[[], str], Callable[[], SerialProvider], Callable[
            [], CachedSerialProvider]] = None, device_name: str = "", lazy_device_id_call_factory_every_time=False):
        """
        :param device_id: 设备 ID，可以是字符串 (立即赋值) 或 工厂函数 (延迟计算)
        :param device_name: 设备名称
        """
        self.lazy_device_id: LazyDeviceID = LazyDeviceID(device_id, call_factory_every_time=lazy_device_id_call_factory_every_time)  # 使用 LazyDeviceID 进行管理
        self._device_name: str = device_name

    @property
    def device_id(self) -> str:
        """
        获取设备 ID，始终返回字符串。
        """
        return str(self.lazy_device_id)

    @property
    def device_name(self) -> str:
        """
        获取设备名称。
        """
        return self._device_name

    def screenshot(self) -> bytes:
        """
        截取设备屏幕，返回图像二进制数据。
        注意：这里为占位实现，根据实际设备类型做修改。
        """
        raise NotImplementedError("请在子类中实现截屏逻辑")

    # def save_screenshot(self, save_dir: str = ".", file_name_suffix: str = '', **kwargs) -> str:
    #     """
    #     截屏并保存到文件中，文件名格式：
    #     - 普通截图: "{设备名称}_{timestamp}.png"
    #     - 异常截图: "{设备名称}_exception_{timestamp}.png"
    #     """
    #     image_data = self.screenshot()
    #     if not os.path.exists(save_dir):
    #         os.makedirs(save_dir, exist_ok=True)
    #
    #     timestamp = time.strftime("%Y%m%d_%H%M%S")
    #     file_name_suffix_linker = ('_' + file_name_suffix) if file_name_suffix and self.device_name else ''
    #     file_suffix = f"{self.device_name}{file_name_suffix_linker}"
    #     file_suffix_linker = ('_' + file_suffix) if file_suffix else ''
    #     base_filename_without_ext = f"{timestamp}{file_suffix_linker}"
    #     base_filename = f"{base_filename_without_ext}.png"
    #     file_path = os.path.join(save_dir, base_filename)
    #
    #     # 避免重名，添加递增编号
    #     counter = 1
    #     while os.path.exists(file_path):
    #         base_filename = f"{base_filename_without_ext}_{counter}.png"
    #         file_path = os.path.join(save_dir, base_filename)
    #         counter += 1
    #
    #     with open(file_path, "wb") as f:
    #         f.write(image_data)
    #     return file_path

    def save_screenshot(self, save_dir: str = ".", file_name_suffix: str = '', **kwargs) -> str:
        """
        截屏并保存到文件中（保存为 JPEG 格式以减小体积），文件名格式：
        - 普通截图: "{设备名称}_{timestamp}.jpg"
        - 异常截图: "{设备名称}_exception_{timestamp}.jpg"
        可通过 kwargs 传入 pillow 的 JPEG 参数，例如 quality=75。
        """
        # 1. 先获取 PNG 二进制数据
        png_data = self.screenshot()
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)

        # 2. 构造文件名（.jpg 后缀）
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        file_name_suffix_linker = ('_' + file_name_suffix) if file_name_suffix and self.device_name else ''
        file_suffix = f"{self.device_name}{file_name_suffix_linker}"
        file_suffix_linker = ('_' + file_suffix) if file_suffix else ''
        base_filename_without_ext = f"{timestamp}{file_suffix_linker}"
        base_filename = f"{base_filename_without_ext}.jpg"
        file_path = os.path.join(save_dir, base_filename)

        # 3. 避免重名，添加递增编号
        counter = 1
        while os.path.exists(file_path):
            base_filename = f"{base_filename_without_ext}_{counter}.jpg"
            file_path = os.path.join(save_dir, base_filename)
            counter += 1

        # 4. 把 PNG 数据加载为 PIL Image，再保存为 JPEG
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(png_data))
        # 默认用 quality=75，如果调用时传了其他参数就覆盖
        jpeg_kwargs = {"format": "JPEG", "quality": 75}
        jpeg_kwargs.update(kwargs)
        img = img.convert("RGB")  # 确保图像模式正确
        img.save(file_path, **jpeg_kwargs)

        return file_path

    def capture_exception_status(self, save_dir: str = ".") -> str:
        """
        在发生异常时调用，截取当前状态的屏幕并保存到文件中，
        返回保存的文件路径，可用于日志记录时辅助判断当前状态。
        """
        # 这里可以添加其他捕获信息的逻辑，比如设备日志等
        return self.save_screenshot(save_dir=save_dir, file_name_suffix='error', error_shot=True)


# 本机设备（适配 Windows 和 Linux）实现示例，使用 mss 进行截屏
class LocalLogDevice(LogDevice):
    def __init__(self, device_id: Union[
        None, str, SerialProvider, CachedSerialProvider, Callable[[], str], Callable[[], SerialProvider], Callable[
            [], CachedSerialProvider]] = None, device_name: str = "", lazy_device_id_call_factory_every_time=True):
        # 当 device_id 为空时，自动获取本机计算机名作为 device_id
        if not device_id:
            device_id = socket.gethostname()
        super().__init__(device_id, device_name, lazy_device_id_call_factory_every_time)

    def screenshot(self) -> bytes:
        """
        使用 mss 库进行截屏，支持 Windows、Linux 以及 macOS。
        需要提前安装 mss: pip install mss
        """
        try:
            with mss.mss() as sct:
                # 选择第一个显示器
                monitor = sct.monitors[0]
                img = sct.grab(monitor)
                # 转换为 PNG 格式的字节数据
                png_bytes = mss.tools.to_png(img.rgb, img.size)
                return png_bytes
        except Exception as e:
            raise RuntimeError(f"本机截屏失败: {e}")


# adb设备实现示例
class AdbLogDevice(LogDevice):
    def __init__(self, device_id: Union[
        None, str, SerialProvider, CachedSerialProvider, Callable[[], str], Callable[[], SerialProvider], Callable[
            [], CachedSerialProvider]] = None, device_name: str = "", lazy_device_id_call_factory_every_time=False):
        # 当 device_id 为空时，从 adb devices 中自动获取第一个设备的 id
        if not device_id:
            try:
                result = subprocess.check_output([ADB_EXE, "devices"], universal_newlines=True)
                devices = []
                for line in result.splitlines():
                    if "\tdevice" in line:
                        dev_id = line.split()[0]
                        devices.append(dev_id)
                if not devices:
                    raise RuntimeError("没有可用的 adb 设备")
                device_id = devices[0]
            except Exception as e:
                raise RuntimeError(f"获取 adb 设备失败: {e}")
        super().__init__(device_id, device_name, lazy_device_id_call_factory_every_time)
        self.ensure_unlock_screen_shot = True

    def _dump_uix(self, base_filepath_without_ext: str) -> Optional[str]:
        """
        使用 uiautomator2.dump_hierarchy 将当前 UI 层级写到同目录同名的 .uix 文件中。
        返回最终生成的 .uix 完整路径。
        """
        # 构造 .uix 文件名：比如 base = "/path/20250603_123456_device"
        # 最终 uix_path = "/path/20250603_123456_device.uix"
        uix_path = None
        try:
            if self.device_id and adb.is_adb_connected(self.device_id):
                try:
                    if self.serial_provider:
                        dump_hierarchy_method = getattr(self.serial_provider, 'dump_hierarchy', None)
                        if dump_hierarchy_method is None:
                            return uix_path
                        uix_path = f"{base_filepath_without_ext}.uix"
                        xml_str = dump_hierarchy_method()
                        with open(uix_path, "w", encoding="utf-8") as f:
                            f.write(xml_str)
                except Exception as e:
                    print(f'[WARNING] Dump uix failed! Details: {e}')
        except Exception:
            pass
        return uix_path

    @property
    def serial_provider(self):
        return self.lazy_device_id.serial_provider

    def screenshot(self) -> bytes:
        """
        使用 adb 的 exec-out 命令直接输出截图数据，
        避免在设备上写入临时文件，提升截图效率。
        """
        try:
            image_data = subprocess.check_output(
                [ADB_EXE, "-s", self.device_id, "exec-out", "screencap", "-p"]
            )
            return image_data
        except Exception as e:
            raise RuntimeError(f"adb 截屏失败: {e}")

    def save_screenshot(self, save_dir: str = ".", file_name_suffix: str = "", **kwargs) -> str:
        """
        调用父类 save_screenshot 先保存 PNG，再根据需要生成同名的 .uix。
        :param save_dir: 保存目录
        :param file_name_suffix: 传给父类，决定文件名里的后缀
        :param kwargs: 传入魔法key值dump_uix: 是否同时 dump UI 层级，生成同名 .uix 文件
        :return: PNG 文件的完整路径
        """
        # 1) 直接调用父类方法，生成并保存 PNG，得到路径
        png_path = super().save_screenshot(save_dir=save_dir, file_name_suffix=file_name_suffix)

        # 尝试错误猎手
        if kwargs.get('error_shot'):
            # 2) 派生出 .uix 的完整路径：把 ".../xxx.png" 换成 ".../xxx.uix"
            base, _ = os.path.splitext(png_path)
            self._dump_uix(base)

        return png_path


class MultiLogDevice(LogDevice):
    def __init__(self, main_device: LogDevice, devices: List[LogDevice] = None,
                 device_id: Union[
                     None, str, SerialProvider, CachedSerialProvider, Callable[[], str], Callable[[], SerialProvider],
                     Callable[[], CachedSerialProvider]] = None, device_name: str = '', lazy_device_id_call_factory_every_time=False):
        """
        MultiDeviceManager 负责管理多个 LogDevice，并允许动态切换
        """
        super().__init__(device_id, device_name, lazy_device_id_call_factory_every_time)
        if not isinstance(main_device, LogDevice):
            raise ValueError("主设备必须是 LogDevice 的实例")

        self.devices = {main_device.device_name: main_device}
        self.main_device = main_device
        self._selected_device = main_device  # 默认选中主设备

        # 注册传入的子设备列表（如果提供）
        if devices:
            for device in devices:
                self.register_device(device)

    @property
    def selected_device_name(self) -> str:
        return self._selected_device.device_name

    @selected_device_name.setter
    def selected_device_name(self, device_name: str):
        if device_name in self.devices:
            self._selected_device = self.devices[device_name]
        else:
            raise ValueError(f"设备 {device_name} 不存在")

    @property
    def selected_device(self):
        return self._selected_device

    def register_device(self, device: LogDevice):
        """注册新设备"""
        self.devices[device.device_name] = device

    def has_device(self, device_name: str):
        return device_name in self.devices

    def reset_to_main_device(self):
        """快速切回主设备"""
        self._selected_device = self.main_device

    def save_screenshot(self, save_dir: str = ".", file_name_suffix: str = '', **kwargs) -> str:
        return self._selected_device.save_screenshot(save_dir, file_name_suffix, **kwargs)

    def screenshot(self) -> bytes:
        """使用当前选定的设备进行截图"""
        return self._selected_device.screenshot()

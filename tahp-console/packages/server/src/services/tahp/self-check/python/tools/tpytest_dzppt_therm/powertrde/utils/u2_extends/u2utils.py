import hashlib
import os.path
import time
from typing import Union, Tuple, List, Protocol, Optional, Callable, runtime_checkable, Any

import uiautomator2
from PIL.Image import Resampling

from powertrde import env
from powertrde.env import UIA2_TEST_JAR_PATH, ADB_EXE
from powertrde.framework.interfaces.i_has_device_id import IHasDeviceID, IHasCopilotDeviceID, IHasObserveDeviceID
from powertrde.framework.lazy_device_id import LazyDeviceID
from powertrde.utils.trde import adb
from powertrde.utils import misc_utils


@runtime_checkable
class U2XPathSelectorProtocol(Protocol):
    def child(self, _xpath: str):
        ...

    def fallback(self, func: Optional[Callable[..., bool]] = None, *args, **kwargs):
        ...

    def get(self, timeout=None) -> Any:
        ...


@runtime_checkable
class U2ObjectProtocol(Protocol):
    def click_gone(self, maxretry=10, interval=1.0):
        ...

    def center(self, offset=(0.5, 0.5)) -> Tuple[float, float]:
        ...

    def must_wait(self, exists=True, timeout=None):
        ...

    def bounds(self) -> Tuple[int, int, int, int]:
        ...


@runtime_checkable
class U2XMLElementProtocol(Protocol):
    def get_xpath(self, strip_index: bool = False):
        ...

    def center(self):
        ...

    def offset(self, px: float = 0.0, py: float = 0.0) -> Tuple[int, int]:
        ...


@runtime_checkable
class U2DeviceProtocol(Protocol):
    def window_size(self):
        ...

    def click(self, x: Union[float, int], y: Union[float, int]):
        ...

    def keyevent(self, v):
        ...


class IHasU2D(IHasDeviceID):
    def __init__(self):
        super().__init__()
        self._u2d: Union[None, uiautomator2.Device, U2DeviceProtocol] = None

    def set_device_id(self, value: Union[str, LazyDeviceID, None]):
        super().set_device_id(value)
        self._u2d = None

    def get_u2d(self):
        if self._u2d is None:
            self._u2d = connect_u2_device(self.device_id)
        return self._u2d

    @property
    def u2d(self):
        return self.get_u2d()


class IHasCopilotU2D(IHasCopilotDeviceID):
    def __init__(self):
        super().__init__()
        self._c_u2d: Union[None, uiautomator2.Device, U2DeviceProtocol] = None

    def set_c_device_id(self, value: Union[str, LazyDeviceID, None]):
        super().set_c_device_id(value)
        self._c_u2d = None

    def get_c_u2d(self):
        if self._c_u2d is None:
            self._c_u2d = connect_u2_device(self.c_device_id)
        return self._c_u2d

    @property
    def c_u2d(self):
        return self.get_c_u2d()


class IHasObserveU2D(IHasObserveDeviceID):
    def __init__(self):
        super().__init__()
        self._o_u2d: Union[None, uiautomator2.Device, U2DeviceProtocol] = None

    def set_o_device_id(self, value: Union[str, LazyDeviceID, None]):
        super().set_o_device_id(value)
        self._o_u2d = None

    def get_o_u2d(self):
        if self._o_u2d is None:
            self._o_u2d = connect_u2_device(self.o_device_id)
        return self._o_u2d

    @property
    def o_u2d(self):
        return self.get_o_u2d()


def connect_u2_device(device_id: str) -> Union[uiautomator2.Device, U2DeviceProtocol]:
    if not device_id:
        raise Exception(f"connect_u2_device parameter device_id:'{device_id}' is None.")
    if misc_utils.is_run_in_exe():
        need_install = False
        if os.path.exists(env.UIA2_BODY_APK_PATH):
            need_install = True
            app_version = None
            try:
                app_version = adb.get_installed_package_version(device_id, env.UIA2_BODY_APP_PACKAGE_NAME)
            except:
                pass
            if app_version:
                apk_version = misc_utils.get_apk_file_version(env.UIA2_BODY_APK_PATH)
                if apk_version == app_version:
                    need_install = False
        if need_install:
            adb.uninstall_apk(device_id, env.UIA2_BODY_APP_PACKAGE_NAME)
            adb.uninstall_apk(device_id, env.UIA2_TEST_APP_PACKAGE_NAME)
            adb.install_apk(device_id, env.UIA2_BODY_APK_PATH)
            time.sleep(0.5)

        _setup_jar(device_id)
        # 猴子补丁，防止原生setup jar被调用
        uiautomator2.Device._setup_jar = lambda self: print("call dummy uiautomator2.Device._setup_jar")

    return uiautomator2.connect(device_id)


def _setup_jar(device_id):
    jar_path = UIA2_TEST_JAR_PATH
    if not os.path.exists(jar_path):
        return
    target_path = "/data/local/tmp/u2.jar"
    if not check_device_file_hash(device_id, jar_path, target_path):
        adb.push_file(device_id, jar_path, target_path)


def check_device_file_hash(device_id, local_file: Union[str, os.PathLike], remote_file: str) -> bool:
    """ check if remote file hash is correct """
    md5 = hashlib.md5()
    with open(local_file, "rb") as f:
        md5.update(f.read())
    local_md5 = md5.hexdigest()
    r = misc_utils.run_command_get_text_output([ADB_EXE, '-s', device_id, 'shell', 'toybox', 'md5sum', remote_file],
                                               include_error_output=True)
    return r and local_md5 in r


def uninstall_u2(device_id: str):
    adb.uninstall_apk(device_id, env.UIA2_BODY_APP_PACKAGE_NAME)
    adb.uninstall_apk(device_id, env.UIA2_TEST_APP_PACKAGE_NAME)


def get_display_size(u2d: Union[uiautomator2.Device, U2DeviceProtocol]):
    return u2d.info["displayWidth"], u2d.info["displayHeight"]


def input_text(u2d, text: str):
    u2d.shell(f'input text "{text}"')


def is_u2_element_not_found_exception(exception: Exception):
    _n = exception.__class__.__name__
    return _n == 'UiObjectNotFoundError' or _n == 'XPathElementNotFoundError'


def press_enter(u2d: Union[uiautomator2.Device, U2DeviceProtocol]):
    """
    安全使用U2D打字，发送回车符
    """
    u2d.press('enter')


def click_offset(
        u2o: Union[U2ObjectProtocol, U2XPathSelectorProtocol, U2XMLElementProtocol],
        offset: Tuple[float, float]):
    if isinstance(u2o, U2XPathSelectorProtocol):
        final_u2o = u2o.get(timeout=-1.0)
        x, y = final_u2o.offset(offset[0], offset[1])
        final_u2o._parent._d.click(x, y)
    elif isinstance(u2o, U2XMLElementProtocol):
        final_u2o = u2o
        x, y = final_u2o.offset(offset[0], offset[1])
        final_u2o._parent._d.click(x, y)
    elif isinstance(u2o, U2ObjectProtocol):
        final_u2o = u2o
        x, y = final_u2o.center(offset)
        final_u2o.session.click(x, y)
    else:
        if u2o is None:
            raise ValueError(f'The u2o arg must not be None.')
        else:
            raise ValueError(f'Error arg type {u2o.__class__}, u2 object not support this type.')


def _wait_and_click(u2d: Union[uiautomator2.Device, U2DeviceProtocol],
                    u2o: Union[
                        U2ObjectProtocol, U2XPathSelectorProtocol, U2XMLElementProtocol, str],
                    pre_wait: float = 0.0, timeout: float = 5.0, post_wait: float = 0.5, no_raise: bool = False,
                    perform_click: bool = False, wait_after_click: float = 0.0, offset=(0.5, 0.5),
                    on_element_found=None) -> Union[
    U2ObjectProtocol, U2XMLElementProtocol, None]:
    """
    等待指定的UI对象加载，并根据需要执行点击操作。

    :param u2d: uiautomator2.Device实例，表示连接的Android设备。
    :param u2o: 目标UI对象，可以是UiObject、XPathSelector、XMLElement或字符串类型的XPath。
    :param pre_wait: 在查找UI对象之前等待的时间（秒），默认为0.0。
    :param timeout: 查找UI对象的超时时间（秒），默认为5.0。
    :param post_wait: 在找到UI对象后等待的时间（秒），默认为0.5。
    :param no_raise: 如果为True，在找不到UI对象时不抛出异常，默认为False。
    :param perform_click: 如果为True，找到UI对象后执行点击操作，默认为False。
    :param wait_after_click: 如果大于0且perform_click为True，则在点击之后执行等待相应时间（秒）。
    :param offset: 点击的相对位置（中心就是0.5, 0.5）。
    :return: 找到的UI对象（UiObject或XMLElement），如果未找到则返回None（仅在no_raise为True时）。

    :raises ValueError: 如果u2o参数类型不受支持或为None。
    :raises XPathElementNotFoundError: 如果u2o为XPath类型且未找到对象，且no_raise为False。
    :raises UiObjectNotFoundError: 如果u2o为UiObject类型且未找到对象，且no_raise为False。
    """
    if pre_wait > 0:
        time.sleep(pre_wait)

    try:
        if isinstance(u2o, U2XPathSelectorProtocol):
            final_u2o = u2o.get(timeout=timeout)
            if post_wait > 0:
                time.sleep(post_wait)
                final_u2o = u2o.get(timeout=-1.0)
            if on_element_found:
                on_element_found(final_u2o)
            if perform_click:
                click_offset(final_u2o, offset)
        elif isinstance(u2o, U2XMLElementProtocol):
            final_u2o = u2o
            if post_wait > 0:
                time.sleep(post_wait)
            if on_element_found:
                on_element_found(final_u2o)
            if perform_click:
                click_offset(final_u2o, offset)
        elif isinstance(u2o, str):
            tmp_u2o = u2d.xpath(u2o)
            final_u2o = tmp_u2o.get(timeout=timeout)
            if post_wait > 0:
                time.sleep(post_wait)
                final_u2o = tmp_u2o.get(timeout=-1.0)
            if on_element_found:
                on_element_found(final_u2o)
            if perform_click:
                click_offset(final_u2o, offset)
        elif isinstance(u2o, U2ObjectProtocol):
            final_u2o = u2o
            final_u2o.must_wait(timeout=timeout)
            if post_wait > 0:
                time.sleep(post_wait)
            if on_element_found:
                on_element_found(final_u2o)
            if perform_click:
                click_offset(final_u2o, offset)
        else:
            if u2o is None:
                raise ValueError(f'The u2o arg must not be None.')
            else:
                raise ValueError(f'Error arg type {u2o.__class__}, u2 object not support this type.')

        if perform_click and wait_after_click > 0.0:
            time.sleep(wait_after_click)
    except Exception as e:
        if is_u2_element_not_found_exception(e):
            if not no_raise:
                raise
            return None
        raise
    return final_u2o


def wait_ui_obj(u2d: Union[uiautomator2.Device, U2DeviceProtocol],
                u2o: Union[U2ObjectProtocol, U2XPathSelectorProtocol, U2XMLElementProtocol, str],
                pre_wait: float = 0.0, timeout: float = 5.0, post_wait: float = 0.5,
                raise_on_not_exist: bool = False) -> Union[U2ObjectProtocol, U2XMLElementProtocol, None]:
    """
    等待指定的UI对象加载，但不执行点击操作。

    :param u2d: uiautomator2.Device实例，表示连接的Android设备。
    :param u2o: 目标UI对象，可以是UiObject、XPathSelector、XMLElement或字符串类型的XPath。
    :param pre_wait: 在查找UI对象之前等待的时间（秒），默认为0.0。
    :param timeout: 查找UI对象的超时时间（秒），默认为5.0。
    :param post_wait: 在找到UI对象后等待的时间（秒），默认为0.5。
    :param raise_on_not_exist: 如果为True，未找到UI对象时抛出异常，默认为False。
    :return: 找到的UI对象（UiObject或XMLElement），如果未找到则返回None（仅在raise_on_not_exist为False时）。
    """
    return _wait_and_click(u2d, u2o, pre_wait, timeout, post_wait, not raise_on_not_exist, False)


def click_wait(u2d: Union[uiautomator2.Device, U2DeviceProtocol],
               u2o: Union[U2ObjectProtocol, U2XPathSelectorProtocol, U2XMLElementProtocol, str],
               pre_wait: float = 0.0, timeout: float = 5.0, post_wait: float = 0.5, no_raise: bool = False,
               wait_after_click: float = 0.0, offset=(0.5, 0.5)) -> Union[
    U2ObjectProtocol, U2XMLElementProtocol, None]:
    """
    等待指定的UI对象加载，并执行点击操作。

    :param u2d: uiautomator2.Device实例，表示连接的Android设备。
    :param u2o: 目标UI对象，可以是UiObject、XPathSelector、XMLElement或字符串类型的XPath。
    :param pre_wait: 在查找UI对象之前等待的时间（秒），默认为0.0。
    :param timeout: 查找UI对象的超时时间（秒），默认为5.0。
    :param post_wait: 在找到UI对象后等待的时间（秒），默认为0.5。
    :param no_raise: 如果为True，在找不到UI对象时不抛出异常，默认为False。
    :param wait_after_click: 如果大于0且perform_click为True，则在点击之后执行等待相应时间（秒）。
    :param offset: 点击的相对位置（中心就是0.5, 0.5）。
    :return: 找到的UI对象（UiObject或XMLElement），如果未找到则返回None（仅在no_raise为True时）。
    """
    return _wait_and_click(u2d, u2o, pre_wait, timeout, post_wait, no_raise, True, wait_after_click, offset)


def input_ui(u2d, char):
    coord_map = {
        'a': (0.113, 0.798), 'b': (0.6, 0.86), 'c': (0.4, 0.86), 'd': (0.3, 0.797), 'e': (0.258, 0.73),
        'f': (0.4, 0.796), 'g': (0.5, 0.80), 'h': (0.608, 0.796), 'i': (0.743, 0.732), 'j': (0.694, 0.80),
        'k': (0.79, 0.797), 'l': (0.889, 0.796), 'm': (0.793, 0.863), 'n': (0.694, 0.863), 'o': (0.843, 0.732),
        'p': (0.934, 0.734), 'q': (0.063, 0.734), 'r': (0.36, 0.734), 's': (0.208, 0.798), 't': (0.45, 0.734),
        'u': (0.644, 0.734), 'v': (0.499, 0.86), 'w': (0.159, 0.732), 'x': (0.305, 0.863), 'y': (0.549, 0.732),
        'z': (0.208, 0.863)
    }

    number_map = {
        '1': 'q', '2': 'w', '3': 'e', '4': 'r', '5': 't', '6': 'y', '7': 'u', '8': 'i', '9': 'o', '0': 'p'
    }

    if char in number_map:
        char = number_map[char]
    elif char.isalpha():
        char = char.lower()

    # 检查字符是否在映射中
    if char in coord_map:
        x, y = coord_map[char]
        u2d.click(x, y)
    else:
        print(f"Character '{char}' not found in coordinate map")


def scroll_find_by_xpath(u2d: Union[uiautomator2.Device, U2DeviceProtocol], xpath, max_swipes=10, direction="up"):
    """
    通过滚动查找元素
    :param u2d: uiautomator2 device
    :param xpath: 要查找的元素的XPath
    :param max_swipes: 最大滚动次数
    :param direction: 滚动方向（"up" 或 "down"）
    :return: 找到的元素对象或None
    """
    phone_width, phone_height = get_display_size(u2d)
    element = u2d.xpath(xpath)
    swipes = 0

    while not element.exists and swipes < max_swipes:
        if direction == "up":
            u2d.swipe_ext("up", 0.7)
        elif direction == "down":
            u2d.swipe_ext("down", 0.7)
        else:
            raise ValueError("Invalid direction: must be 'up' or 'down'")
        time.sleep(1.5)
        swipes += 1

    # 如果找到元素，检查其位置
    if element.exists:
        bounds = element.get().info.get('bounds', {})
        if bounds:
            screen_height = u2d.window_size()[1]
            if bounds['bottom'] < screen_height:  # 元素完全可见
                return element
            else:
                # 元素被遮挡，继续上滑
                u2d.swipe(phone_width * 0.5, phone_height * 0.6, phone_width * 0.5, phone_height * 0.5)
                element = u2d.xpath(xpath)

    return element if element.exists else None


def scroll_to_upper_middle(u2d: Union[uiautomator2.Device, U2DeviceProtocol], xpath, target_position=0.5):
    """
    (改成)
    滚动查找页面的评论按钮，并将按钮定位到屏幕,上下分成4份的第*份区域。（也就是保证在中上部分，下部分空出来，留给机械手识别，尤其是用在Facebook点击评论，查看第一帧反应的，第一针变化在屏幕最下面，只能把下面空出来，留给摄像头识别）

    :param u2d: uiautomator2设备对象
    :param xpath: 评论按钮的resource-id
    :param target_position: 目标位置的屏幕比例，默认是屏幕的25%（第二份区域）
    :return: True表示成功找到并定位评论按钮，False表示未找到
    """
    try:
        # 获取屏幕的高度和宽度
        screen_width, screen_height = u2d.window_size()

        # 滚动查找评论按钮
        for i in range(20):
            comment_button = u2d.xpath(xpath)

            if comment_button.exists:
                # 获取评论按钮的bounds
                # bounds = comment_button.bounds

                left, top, right, bottom = comment_button.bounds
                # 计算按钮当前的中心点位置
                button_center_x = (left + right) / 2
                button_center_y = (top + bottom) / 2

                # 目标位置的Y坐标
                target_y = int(screen_height * target_position)

                if abs(button_center_y - target_y) > 10:  # 如果按钮不在目标位置
                    offset_y = target_y - button_center_y
                    u2d.swipe(button_center_x, button_center_y, button_center_x, button_center_y + offset_y)
                    # print(f"已将评论按钮移动到目标位置：屏幕Y={target_y}")

                return True

            # 如果未找到，继续滚动
            # print("未找到评论按钮，继续滚动...")
            u2d.swipe(screen_width / 2, screen_height * 3 / 4, screen_width / 2, screen_height / 4)
        return False

    except Exception as e:
        # print(f"发生错误：{e}")
        return False


def scroll_to_lower_middle(u2d: Union[uiautomator2.Device, U2DeviceProtocol], xpath, target_position=0.70):
    """
    (使用场景较少，滑动评论，让评论在屏幕底部的3/4 到 4/4的位置，始终向上滑动，没有向下滑动的操作)

    :param u2d: uiautomator2设备对象
    :param xpath: 评论按钮的resource-id
    :param target_position: 目标位置的屏幕比例，默认是屏幕的25%（第二份区域）
    :return: True表示成功找到并定位评论按钮，False表示未找到
    """
    try:
        # 获取屏幕的高度和宽度
        screen_width, screen_height = u2d.window_size()

        # 滚动查找评论按钮
        for i in range(20):
            comment_button = u2d.xpath(xpath)

            if comment_button.exists:
                # 获取评论按钮的bounds
                # bounds = comment_button.bounds

                left, top, right, bottom = comment_button.bounds
                # 计算按钮当前的中心点位置
                button_center_x = (left + right) / 2
                button_center_y = (top + bottom) / 2

                # 目标位置的Y坐标
                target_y = int(screen_height * target_position)

                if button_center_y < target_y:  # 如果按钮不在目标位置
                    continue

                return True

            # 如果未找到，继续滚动
            # print("未找到评论按钮，继续滚动...")
            u2d.swipe(screen_width / 2, screen_height * 3 / 4, screen_width / 2, screen_height / 4)
        return False

    except Exception as e:
        # print(f"发生错误：{e}")
        return False


def record_pic_u2o(u2d: Union[uiautomator2.Device, U2DeviceProtocol], pic_save_path: str, u2o: Union[
    U2ObjectProtocol, U2XPathSelectorProtocol, U2XMLElementProtocol],
                   pos_offset=(0.0, 0.0), size_offset=(0.0, 0.0),
                   ):
    """
    记录控件图片以备后续图像识别使用。
    :param u2d: 设备对象
    :param pic_save_path: 保存文件名
    :param u2o: 控件对象，可以是UiObject、XPathSelector或XMLElement
    :param pos_offset: 控件位置的偏移量（x, y）
    :param size_offset: 控件大小的偏移量（width, height）
    """

    # 初始化边界变量
    left, top, right, bottom = 0, 0, 0, 0

    if isinstance(u2o, U2ObjectProtocol):
        left, top, right, bottom = u2o.bounds()
    elif isinstance(u2o, U2XPathSelectorProtocol):
        left, top, right, bottom = u2o.get().bounds
    elif isinstance(u2o, U2XMLElementProtocol):
        left, top, right, bottom = u2o.bounds
    elif isinstance(u2o, str):
        left, top, right, bottom = u2d.xpath(u2o).get().bounds
    else:
        raise ValueError(f'Not support u2o arg for value {u2o}')

    # 获取屏幕截图
    screenshot = u2d.screenshot()

    # 获取截图的尺寸
    orig_width, orig_height = screenshot.size

    # 计算缩放比例
    if orig_width < orig_height:
        scale = 720 / orig_width
        new_width = 720
        new_height = int(orig_height * scale)
    else:
        scale = 720 / orig_height
        new_height = 720
        new_width = int(orig_width * scale)

    # 调整截图尺寸
    resized_screenshot = screenshot.resize((new_width, new_height), Resampling.LANCZOS)

    # 根据缩放比例调整控件的边界
    left = int(left * scale)
    top = int(top * scale)
    right = int(right * scale)
    bottom = int(bottom * scale)

    # 计算位置和大小的偏移
    width = right - left
    height = bottom - top
    left += int(width * pos_offset[0])
    top += int(height * pos_offset[1])
    right = left + int(width * (1 + size_offset[0]))
    bottom = top + int(height * (1 + size_offset[1]))

    # 截取控件所在区域
    control_image = resized_screenshot.crop((left, top, right, bottom))

    # 如果是横屏，则进行翻转
    orientation = u2d.orientation
    if orientation == 'left':
        control_image = control_image.rotate(270, expand=True)
    elif orientation == 'right':
        control_image = control_image.rotate(90, expand=True)
    control_image.save(pic_save_path)


def xpath_within_region(
        d: Union[uiautomator2.Device, U2DeviceProtocol],
        xpath: str,
        region: Tuple[float, float, float, float]
) -> List[U2XMLElementProtocol]:
    """
    根据给定的 XPath 和相对屏幕区域，返回所有中心点位于该区域内的元素列表。

    Args:
        d: 已连接的 uiautomator2 设备实例。
        xpath: 要查找的 XPath 表达式。
        region: 目标区域，归一化坐标 (x1, y1, x2, y2)，数值范围 [0,1]。
                表示屏幕宽高的比例，如 (0.1, 0.2, 0.8, 0.6)。

    Returns:
        所有符合条件的 UiObject 列表，若无则返回空列表。

    Raises:
        ValueError: 如果 region 参数不合法。
    """
    # 校验 region
    if not (0 <= region[0] < region[2] <= 1 and 0 <= region[1] < region[3] <= 1):
        raise ValueError(f"Invalid region: {region}. Must satisfy 0<=x1<x2<=1 and 0<=y1<y2<=1.")

    # 获取屏幕尺寸
    width, height = d.window_size()
    # 计算绝对坐标边界
    x1 = region[0] * width
    y1 = region[1] * height
    x2 = region[2] * width
    y2 = region[3] * height

    # 查找所有匹配的元素
    elements = d.xpath(xpath).all()
    matched = []
    for elem in elements:
        # 获取元素 bounds: {'left':..., 'top':..., 'right':..., 'bottom':...}
        bounds = elem.info.get('bounds')
        if not bounds:
            continue
        left, top = bounds['left'], bounds['top']
        right, bottom = bounds['right'], bounds['bottom']
        # 计算中心坐标
        cx = (left + right) / 2
        cy = (top + bottom) / 2
        # 判断中心是否在指定区域内
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            matched.append(elem)

    return matched

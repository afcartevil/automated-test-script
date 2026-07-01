import ctypes
import os
import subprocess
import time

import win32con
from typing import List, Optional, Callable

import win32process

import win32gui
import commctrl
import psutil

from powertrde.framework.defines import IHasTextMatchMode, TextMatchMode, check_text_match
from powertrde.framework.logs_protocol import logs_p

__ctype_text_buffer = ctypes.create_unicode_buffer(255)
__wmi_service = None


class RepeatSleepCheckOption:
    __default_value = None

    @staticmethod
    def default_value():
        if RepeatSleepCheckOption.__default_value is None:
            RepeatSleepCheckOption.__default_value = RepeatSleepCheckOption()
        return RepeatSleepCheckOption.__default_value

    def __init__(self, first_delay_ms: int = 0, interval_ms: int = 0, check_count: int = 1):
        self.first_delay_ms = first_delay_ms
        self.interval_ms = interval_ms
        self.check_count = check_count


def repeat_sleep_check(option: RepeatSleepCheckOption, predicate: Callable[[], bool]):
    if option is None:
        option = RepeatSleepCheckOption.default_value()
    if option.check_count <= 0:
        return False
    if option.first_delay_ms > 0:
        time.sleep(option.first_delay_ms / 1000)
    for _ in range(option.check_count):
        if predicate():
            return True
        elif option.interval_ms > 0:
            time.sleep(option.interval_ms / 1000)
    return False


class SearchOption(RepeatSleepCheckOption, IHasTextMatchMode):
    __default_value = None
    __repeat_wait_retry = None
    __repeat_wait_retry_start_with = None
    __big_repeat_wait_retry_start_with = None

    @staticmethod
    def default_value():
        if SearchOption.__default_value is None:
            SearchOption.__default_value = SearchOption()
        return SearchOption.__default_value

    @staticmethod
    def repeat_wait_retry():
        if SearchOption.__repeat_wait_retry is None:
            SearchOption.__repeat_wait_retry = SearchOption(first_delay_ms=300, interval_ms=300, check_count=10)
        return SearchOption.__repeat_wait_retry

    @staticmethod
    def repeat_wait_retry_start_with():
        if SearchOption.__repeat_wait_retry_start_with is None:
            SearchOption.__repeat_wait_retry_start_with = SearchOption(text_match_mode=TextMatchMode.START_WITH,
                                                                       first_delay_ms=300, interval_ms=300,
                                                                       check_count=10)
        return SearchOption.__repeat_wait_retry_start_with

    @staticmethod
    def big_repeat_wait_retry_start_with():
        if SearchOption.__big_repeat_wait_retry_start_with is None:
            SearchOption.__big_repeat_wait_retry_start_with = SearchOption(text_match_mode=TextMatchMode.START_WITH,
                                                                           first_delay_ms=500, interval_ms=300,
                                                                           check_count=20)
        return SearchOption.__big_repeat_wait_retry_start_with

    def __init__(self, text_match_mode: TextMatchMode = TextMatchMode.FULL,
                 first_delay_ms: int = 0, interval_ms: int = 0, check_count: int = 1):
        super().__init__(first_delay_ms, interval_ms, check_count)
        self.__text_match_mode = text_match_mode

    @property
    def text_match_mode(self) -> TextMatchMode:
        return self.__text_match_mode


class WindowNode:
    def __init__(self, handle):
        self.handle = handle
        self._cached_children: Optional[List['WindowNode']] = None

    @property
    def title(self) -> str:
        return win32gui.GetWindowText(self.handle)

    @property
    def class_name(self) -> str:
        return win32gui.GetClassName(self.handle)

    @property
    def is_valid(self) -> bool:
        return win32gui.IsWindow(self.handle)

    @property
    def children(self) -> List['WindowNode']:
        if self._cached_children is None:
            self._cached_children = []

            def callback(hwnd, _):
                self._cached_children.append(WindowNode(hwnd))

            win32gui.EnumChildWindows(self.handle, callback, None)
        return self._cached_children

    def __iter__(self):
        return self.Iterator(self)

    class Iterator:
        def __init__(self, root: 'WindowNode'):
            self._root = root
            self.current = 0
            self.end = len(root.children)

        def __iter__(self):
            return self

        def __next__(self):
            if self.current < self.end:
                current = self._root.children[self.current]
                self.current += 1
                return current
            else:
                raise StopIteration


def find_window_by_content_text(content_text: str, class_name: str = None,
                                text_match_mode: TextMatchMode = TextMatchMode.FULL,
                                require_window_visible: bool = True):
    handle = None

    def callback(hwnd, _):
        if class_name is None or win32gui.GetClassName(hwnd) == class_name:
            if ((not require_window_visible or win32gui.IsWindowVisible(hwnd))
                    and check_text_match(get_control_text(hwnd), content_text, text_match_mode)):
                nonlocal handle
                handle = hwnd

    win32gui.EnumWindows(callback, None)
    return handle


def find_window_handle(title: str, class_name: str = None, title_match_mode: TextMatchMode = TextMatchMode.FULL,
                       require_window_visible: bool = True):
    """
    查找窗口句柄通过窗口标题和窗口的类名。
    如果窗口类名为None，则仅通过窗口标题查找。

    :param require_window_visible: 是否要求窗口必须可见
    :param title_match_mode: 窗口标题匹配模式
    :param title: 窗口标题
    :param class_name: 窗口类名 (可选)
    :return: 窗口句柄或None
    """
    handle = None

    def callback(hwnd, _):
        if class_name is None or win32gui.GetClassName(hwnd) == class_name:
            if ((not require_window_visible or win32gui.IsWindowVisible(hwnd))
                    and check_text_match(win32gui.GetWindowText(hwnd), title, title_match_mode)):
                nonlocal handle
                handle = hwnd

    win32gui.EnumWindows(callback, None)
    return handle


def _exists_windows(titles: List[str], class_name: str = None, title_match_mode: TextMatchMode = TextMatchMode.FULL,
                    require_window_visible: bool = True) -> bool:
    handle = None

    def callback(hwnd, _):
        if class_name is None or win32gui.GetClassName(hwnd) == class_name:
            if not require_window_visible or win32gui.IsWindowVisible(hwnd):
                for title in titles:
                    if check_text_match(win32gui.GetWindowText(hwnd), title, title_match_mode):
                        nonlocal handle
                        handle = hwnd
                        break

    win32gui.EnumWindows(callback, None)
    return handle is not None


def find_child_window(parent_handle, title: str, title_match_mode: TextMatchMode = TextMatchMode.FULL,
                      require_window_visible: bool = True):
    handle = None

    def callback(hwnd, _):
        if (check_text_match(win32gui.GetWindowText(hwnd), title, title_match_mode) and
                (not require_window_visible or win32gui.IsWindowVisible(hwnd))):
            nonlocal handle
            handle = hwnd

    win32gui.EnumChildWindows(parent_handle, callback, None)
    return handle


def find_child_window_by_class(parent_handle, class_name: str, class_match_mode: TextMatchMode = TextMatchMode.FULL,
                               require_window_visible: bool = False):
    handle = None

    def callback(hwnd, _):
        if (check_text_match(win32gui.GetClassName(hwnd), class_name, class_match_mode) and
                (not require_window_visible or win32gui.IsWindowVisible(hwnd))):
            nonlocal handle
            handle = hwnd

    win32gui.EnumChildWindows(parent_handle, callback, None)
    return handle


def find_child_windows(parent_handle, title: str, title_match_mode: TextMatchMode = TextMatchMode.FULL,
                       require_window_visible: bool = True) -> list:
    handle = []

    def callback(hwnd, _):
        if (check_text_match(win32gui.GetWindowText(hwnd), title, title_match_mode) and
                (not require_window_visible or win32gui.IsWindowVisible(hwnd))):
            handle.append(hwnd)

    win32gui.EnumChildWindows(parent_handle, callback, None)
    return handle


def get_control_handle(window_handle, control_id):
    """
    通过控件ID获取控件的句柄。

    :param window_handle: 窗口的句柄
    :param control_id: 控件的ID
    :return: 控件的句柄或None
    """
    control_handle = win32gui.GetDlgItem(window_handle, control_id)
    if control_handle == 0:
        return None
    else:
        return control_handle


def click_button(button_handle, blocked_operation: bool = False):
    """
    使用 SendMessage或PostMessage 发送消息给指定按钮句柄，模拟点击按钮

    :param button_handle: 按钮句柄
    :param blocked_operation: 是否阻塞运行（某些点击事件会阻塞运行结果）
    """
    if blocked_operation:
        win32gui.SendMessage(button_handle, win32con.BM_CLICK, 0, 0)
    else:
        win32gui.PostMessage(button_handle, win32con.BM_CLICK, 0, 0)


def activate_window(window_handle, use_topmost_mode: bool = True, power_mode: bool = False):
    """
    激活指定窗口，使其成为前台窗口并获得焦点
    参数:
    :param use_topmost_mode: 是否使用置顶模式激活窗口（置为 True 可避免控制台程序导致窗口无法激活）
    :param window_handle: 窗口句柄
    :param power_mode: 是否使用强力模式，强力模式会先恢复窗口的状态（比如最小化的窗口会让它恢复原状）
    """
    if power_mode:
        # 先显示窗口（如果窗口最小化需要还原）
        show_window(window_handle)
        restore_window(window_handle)
        time.sleep(0.1)  # 稍作延时，确保窗口显示

    if use_topmost_mode:
        # 将窗口置顶后取消置顶，这样可以变相激活窗口（避免控制台程序导致窗口无法激活）
        set_window_topmost(window_handle, True)
        set_window_topmost(window_handle, False)
    else:
        # 将窗口置于前台（这个函数容易在已激活的控制台程序中失效）
        win32gui.SetForegroundWindow(window_handle)


def hide_window(window_handle):
    """
    隐藏窗口
    :param window_handle: 窗口句柄
    """
    win32gui.ShowWindow(window_handle, win32con.SW_HIDE)


def show_window(window_handle):
    """
    显示隐藏的窗口
    :param window_handle: 窗口句柄
    """
    win32gui.ShowWindow(window_handle, win32con.SW_SHOW)


def minimize_window(window_handle):
    """
    最小化窗口
    :param window_handle: 窗口句柄
    """
    win32gui.ShowWindow(window_handle, win32con.SW_MINIMIZE)


def maximize_window(window_handle):
    """
    最小化窗口
    :param window_handle: 窗口句柄
    """
    win32gui.ShowWindow(window_handle, win32con.SW_MAXIMIZE)


def restore_window(window_handle):
    """
    还原最小化或最大化后的窗口
    :param window_handle: 窗口句柄
    """
    win32gui.ShowWindow(window_handle, win32con.SW_RESTORE)


def search_window(window_title: str, window_class_name: str = None, search_option: SearchOption = None
                  , stop_on_not_found: bool = False, require_visible: bool = True):
    """
    搜索窗口句柄
    :param window_title: 需要搜索的窗口标题
    :param window_class_name: 需要搜索的窗口类名
    :param search_option: 搜索选项，可以指定如何搜寻窗口标题（起始、包含、完全匹配），默认为完全匹配；也可以指定延迟多久、间隔多久、搜索多少次
    :param stop_on_not_found: 当未找到时是否立即停止搜索并返回None
    :param require_visible: 是否要求窗口可见
    :return: 窗口句柄
    """
    handle = None
    if search_option is None:
        search_option = SearchOption.default_value()

    def search_func() -> bool:
        nonlocal handle
        handle = find_window_handle(window_title, window_class_name, search_option.text_match_mode, require_visible)
        need_break = handle is not None
        return need_break if not stop_on_not_found else not need_break

    repeat_sleep_check(search_option, search_func)
    return handle


def exists_windows(window_titles: List[str], window_class_name: str = None, search_option: SearchOption = None):
    if search_option is None:
        search_option = SearchOption.default_value()
    exists = False

    def search_func() -> bool:
        nonlocal exists
        exists = _exists_windows(window_titles, window_class_name, search_option.text_match_mode)
        return exists

    repeat_sleep_check(search_option, search_func)
    return exists


def is_handle_valid(handle):
    """
    判断窗口/控件句柄是否有效
    :param handle: 窗口/控件句柄
    """
    return win32gui.IsWindow(handle)


def set_control_text(edit_handle, text):
    """
    给指定的 Edit 控件发送消息设置文本

    :param edit_handle: Edit 控件的句柄
    :param text: 要设置的文本内容
    """
    # 发送 WM_SETTEXT 消息来设置文本
    win32gui.SendMessage(edit_handle, win32con.WM_SETTEXT, 0, text)


def run_file(file_path: str, detach_run: bool, *args) -> bool:
    """
    运行一个指定路径的文件，可以是相对路径或绝对路径，并可传递参数

    :param detach_run: 是否以独立进程运行
    :param file_path: 文件的路径，支持相对路径和绝对路径
    :param args: 可选的参数，将传递给可执行文件

    :returns 文件是否运行成功
    """
    # 将相对路径转换为绝对路径
    abs_path = os.path.abspath(file_path)

    # 检查文件是否存在
    if not os.path.exists(abs_path):
        logs_p().log_error(f"The file {abs_path} does not exist.")
        return False

    # 使用 subprocess 运行文件
    try:
        # 运行文件
        if detach_run:
            # 构建命令
            # command = [f"cmd /c start /min /b /i {abs_path} " + " ".join(args) + " & exit"]
            command = [abs_path] + list(args)
            subprocess.Popen(command, shell=True, stdin=None, stdout=None, stderr=None, close_fds=True,
                             creationflags=subprocess.DETACHED_PROCESS, start_new_session=True)
        else:
            # 构建命令
            command = [abs_path] + list(args)
            completed_process = subprocess.run(command, check=True)
            # print(f"Process exited with code {completed_process.returncode}")
    except subprocess.CalledProcessError as e:
        logs_p().log_error(f"An error occurred while running the file: {e}")
        return False
    return True


def close_window(window_handle):
    """
    关闭指定句柄的窗口

    参数:
    :param window_handle: 窗口句柄
    """
    # 发送 WM_CLOSE 消息
    win32gui.PostMessage(window_handle, win32con.WM_CLOSE, 0, 0)


def is_control_disabled(control_handle) -> bool:
    """
    检查一个控件是否为禁用状态

    :param control_handle: 控件句柄
    """
    # 获取控件的样式
    style = win32gui.GetWindowLong(control_handle, win32con.GWL_STYLE)
    # 检查样式中是否包含 WS_DISABLED 标志
    return (style & win32con.WS_DISABLED) == win32con.WS_DISABLED


def is_checkbox_checked(checkbox_handle):
    """
    检查一个复选框是否被选中
    :param checkbox_handle: 复选框句柄
    :return: 复选框是否被选中
    """
    # 获取控件的样式
    style = win32gui.SendMessage(checkbox_handle, win32con.BM_GETCHECK, 0, 0)
    return style == win32con.BST_CHECKED


def get_process_id_from_window_handle(window_handle):
    """
    根据窗口句柄获取其所属进程的ID。

    :param window_handle: 窗口的句柄。
    :return: 该窗口所属进程的ID。
    """
    _, process_id = win32process.GetWindowThreadProcessId(window_handle)
    return process_id


def find_process_by_name(process_name, full_match=True) -> int:
    try:
        if full_match:
            pid_bytes = subprocess.check_output(f'tasklist /FO CSV | findstr /i /c:"\\"{process_name}\\""',
                                                shell=True)
        else:
            pid_bytes = subprocess.check_output(f'tasklist /FO CSV | find /i "{process_name}"', shell=True)
        pid = int(pid_bytes.decode(encoding="ansi").split(",")[1].replace("\"", ""))
    except:
        return 0
    return pid


def set_window_topmost(window_handle, set_topmost: bool = True):
    """
    将窗口置顶。
    :param set_topmost: 是否置顶。
    :param window_handle: 窗口句柄。
    """
    if set_topmost:
        win32gui.SetWindowPos(window_handle, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
    else:
        win32gui.SetWindowPos(window_handle, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)


def kill_process_by_name(process_name, full_match=True) -> int:
    pid = find_process_by_name(process_name, full_match)
    if pid != 0:
        os.system(f"taskkill /F /PID {pid} >nul 2>nul")
    return pid


def kill_all_process_by_name(process_name):
    os.system(f"taskkill /F /IM {process_name} >nul 2>nul")


def kill_process_by_pid(pid):
    if pid != 0:
        os.system(f"taskkill /F /PID {pid} >nul 2>nul")


def get_window_text(window_handle) -> Optional[str]:
    """
    获取窗口的文本。
    :return: 窗口的文本。
    """
    try:
        text = win32gui.GetWindowText(window_handle)
        return text
    except:
        pass
    return ""


def get_control_text(static_control_id) -> Optional[str]:
    """
    获取控件的文本
    :param static_control_id: 控件的句柄
    :return: 控件的文本
    """
    try:
        # 获取控件的文本
        text_length = win32gui.SendMessage(static_control_id, win32con.WM_GETTEXTLENGTH, 0, 0)
        buffer = ctypes.create_unicode_buffer(text_length + 1)
        win32gui.SendMessage(static_control_id, win32con.WM_GETTEXT, text_length + 1, buffer)
        return buffer.value
    except:
        pass
    return ""


def get_combobox_items(combobox_handle) -> List[str]:
    """
    获取ComboBox中所有选项的文本。

    :param combobox_handle: ComboBox控件的窗口句柄。
    :return: 包含ComboBox中所有选项文本的列表。
    """
    # 获取ComboBox中的项目数量
    count = win32gui.SendMessage(combobox_handle, win32con.CB_GETCOUNT, 0, 0)

    items = []
    for i in range(count):
        # 获取每个项目的文本长度
        length = win32gui.SendMessage(combobox_handle, win32con.CB_GETLBTEXTLEN, i, 0)
        # 根据长度分配缓冲区并获取文本
        if length > 0:
            win32gui.SendMessage(combobox_handle, win32con.CB_GETLBTEXT, i, __ctype_text_buffer)
            items.append(__ctype_text_buffer.value)
        elif length == 0:
            items.append("")
    return items


def get_combobox_item_text(combobox_handle, index) -> Optional[str]:
    """
    获取ComboBox中指定索引的选项的文本。
    :param combobox_handle: ComboBox控件的窗口句柄。
    :param index: 选项的索引。
    :return: 选项的文本。
    """
    length = win32gui.SendMessage(combobox_handle, win32con.CB_GETLBTEXTLEN, index, 0)
    if length > 0:
        win32gui.SendMessage(combobox_handle, win32con.CB_GETLBTEXT, index, __ctype_text_buffer)
        return __ctype_text_buffer.value
    elif length == 0:
        return ""
    return None


def get_combobox_selected_item_index(combobox_handle) -> int:
    """
    获取ComboBox当前选中项的索引和文本。

    :param combobox_handle: ComboBox控件的窗口句柄。
    :return: 选中项的索引（从0开始）。
    """
    # 获取当前选中项的索引
    selected_index = win32gui.SendMessage(combobox_handle, win32con.CB_GETCURSEL, 0, 0)
    return selected_index


def select_combobox_item(combobox_handle, index):
    """
    根据索引选择ComboBox中的一个选项。

    :param combobox_handle: ComboBox控件的窗口句柄。
    :param index: 要选择的选项的索引，从0开始。
    """
    # 发送CB_SETCURSEL消息来选择指定索引的项
    win32gui.SendMessage(combobox_handle, win32con.CB_SETCURSEL, index, 0)


def get_executable_path_by_pid(pid: int) -> str:
    """
    根据进程ID获取进程的可执行文件路径。
    :param pid: 进程ID。
    :return: 进程的可执行文件路径。
    """
    # path_bytes = subprocess.check_output(
    #     f"powershell -Command \"$process=Get-WmiObject Win32_Process -Filter 'ProcessID={pid}';" +
    #     "Write-Host $process.ExecutablePath\"",
    #     shell=True)
    # path = path_bytes.decode(encoding="utf-8")
    # return path
    try:
        # 创建一个Process对象
        process = psutil.Process(pid)

        # 获取进程的执行文件路径
        executable_path = process.exe()

        return executable_path
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
        # 如果进程不存在、权限不足或进程是僵尸进程，处理异常
        return f"无法获取进程ID为{pid}的执行文件路径: {e}"


def set_console_title(title):
    """
    设置控制台窗口的标题。
    :param title: 要设置的标题。
    """
    ctypes.windll.kernel32.SetConsoleTitleW(title)


def get_listview_item_count(hwnd):
    return win32gui.SendMessage(hwnd, commctrl.LVM_GETITEMCOUNT, 0, 0)


def get_system_dpi():
    # 获取系统DPI缩放因子
    hdc = ctypes.windll.user32.GetDC(0)
    dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # 88是LOGPIXELSX
    dpi_y = ctypes.windll.gdi32.GetDeviceCaps(hdc, 90)  # 90是LOGPIXELSY
    ctypes.windll.user32.ReleaseDC(0, hdc)
    return dpi_x / 96, dpi_y / 96  # 96是默认DPI


def adjust_for_dpi(x, y):
    # 调整坐标以考虑DPI缩放
    dpi_x, dpi_y = get_system_dpi()
    return int(x * dpi_x), int(y * dpi_y)


def show_warning_message(title, message):
    # 消息框类型：MB_OK | MB_ICONWARNING
    MB_OK = 0x0
    MB_ICONWARNING = 0x30

    # 调用Windows API的MessageBox函数
    ctypes.windll.user32.MessageBoxW(None, message, title, MB_OK | MB_ICONWARNING)

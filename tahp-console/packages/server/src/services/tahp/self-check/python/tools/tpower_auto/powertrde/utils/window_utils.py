import glob
import os
import tkinter as tk

from tkinter import messagebox, ttk
from typing import Optional, Dict, Any


class UnclosableWindow:
    def __init__(self, title, message, topmost=True):
        """
        初始化不可关闭的窗口。

        :param title: 窗口标题
        :param message: 窗口内容
        """
        self.title = title
        self.message = message
        self.topmost = topmost
        self.root = None

    def __enter__(self):
        """上下文管理器进入方法，创建并显示窗口。"""
        self.root = tk.Tk()
        self.root.title(self.title)

        if self.topmost:
            # 设置窗口始终保持在最前端
            self.root.wm_attributes("-topmost", True)

        # 禁用关闭按钮
        self.root.protocol("WM_DELETE_WINDOW", self.disable_event)

        # 创建标签显示消息
        label = tk.Label(self.root, text=self.message)
        label.pack(padx=20, pady=20)

        # 使窗口在屏幕中央显示
        self.root.eval('tk::PlaceWindow . center')

        # 更新窗口以显示
        self.root.update()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """上下文管理器退出方法，关闭窗口。"""
        self.close()

    def disable_event(self):
        """禁用关闭事件。"""
        pass

    def close(self):
        """关闭窗口。"""
        if self.root:
            self.root.destroy()


def show_yes_no_message_box(title, message, yes_callback, no_callback, topmost=True):
    """
    显示一个消息框，并在用户选择后调用相应的回调函数。

    :param title: 消息框标题
    :param message: 消息框内容
    :param yes_callback: 用户点击“是”按钮时调用的回调函数
    :param no_callback: 用户点击“否”按钮时调用的回调函数
    :param topmost: 窗口保持在最前端
    """
    # 创建一个新的Tk实例
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    if topmost:
        # 设置窗口始终保持在最前端
        root.wm_attributes("-topmost", True)

    # 弹出消息框，包含“是”和“否”按钮
    result = messagebox.askyesno(title, message)

    # 销毁主窗口
    root.destroy()

    # 根据用户选择调用相应的回调函数
    if result:
        if yes_callback:
            yes_callback()
    else:
        if no_callback:
            no_callback()


def show_warning_box(title, message, topmost=True):
    """
    显示一个警告消息框。

    :param title: 消息框标题
    :param message: 消息框内容
    :param topmost: 窗口保持在最前端
    """
    # 创建一个新的Tk实例
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    if topmost:
        # 设置窗口始终保持在最前端
        root.wm_attributes("-topmost", True)

    # 弹出警告消息框
    messagebox.showwarning(title, message)

    # 销毁主窗口
    root.destroy()


def show_message_box(title, message, topmost=True):
    """
    显示一个普通消息框。

    :param title: 消息框标题
    :param message: 消息框内容
    :param topmost: 窗口保持在最前端
    """
    # 创建一个新的Tk实例
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口

    if topmost:
        # 设置窗口始终保持在最前端
        root.wm_attributes("-topmost", True)

    # 弹出警告消息框
    messagebox.showinfo(title, message)

    # 销毁主窗口
    root.destroy()


def choose_file_dialog(
        folder: str,
        pattern: str,
        title: str,
        message: str,
        show_close: bool = True
) -> Optional[str]:
    """
    在一个 Tkinter 弹窗中，列出 folder 下符合 pattern 的所有文件，
    让用户从下拉框中选择一个，或关闭对话框。

    :param folder: 要搜索的目录路径
    :param pattern: 文件名筛选表达式，如 "*.json"
    :param title: 窗口标题
    :param message: 下拉框上方的提示文本
    :param show_close: 是否显示“关闭”按钮；若 False，仅有“确认”按钮
    :return:
        - 选中文件的完整路径（str）
        - 若无文件，用户点击“确认”返回 ""（空串）
        - 用户点击“关闭”或窗口右上角关闭，返回 None
    """
    # 构建文件列表和映射
    search = os.path.join(folder, pattern)
    full_paths = glob.glob(search)
    # 只取文件（排除目录），并按名称排序
    full_paths = [p for p in full_paths if os.path.isfile(p)]
    full_paths.sort()
    basenames = [os.path.basename(p) for p in full_paths]

    # 结果变量，外部通过闭包读取
    result: Dict[str, Any] = {'value': None}

    # 创建隐藏的主窗口
    root = tk.Tk()
    root.withdraw()
    # 创建对话框
    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.resizable(False, False)

    # 关闭按钮行为（等同点击“关闭”）
    def on_close():
        result['value'] = None
        dlg.destroy()

    dlg.protocol("WM_DELETE_WINDOW", on_close)

    # 提示 Label
    lbl = tk.Label(dlg, text=message, anchor='w', justify='left', wraplength=400)
    lbl.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky='we')

    # 下拉 Combobox
    cmb = ttk.Combobox(dlg, values=basenames, state="readonly")
    cmb.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky='we')
    # 如果有文件，默认选中第一项
    if basenames:
        cmb.current(0)

    # 确认按钮行为
    def on_confirm():
        if not basenames:
            # 无文件，返回空串
            result['value'] = ""
        else:
            sel = cmb.get()
            # sel 一定在 basenames 里
            full = full_paths[basenames.index(sel)]
            result['value'] = full
        dlg.destroy()

    btn_ok = tk.Button(dlg, text="确认", width=10, command=on_confirm)
    btn_ok.grid(row=2, column=0, padx=(10, 5), pady=10)

    # 可选关闭按钮
    if show_close:
        btn_close = tk.Button(dlg, text="关闭", width=10, command=on_close)
        btn_close.grid(row=2, column=1, padx=(5, 10), pady=10)
    else:
        # 如果不显示关闭按钮，占满两列，使布局平衡
        btn_ok.grid_configure(columnspan=2)

    # 让对话框居中
    dlg.update_idletasks()
    w = dlg.winfo_width()
    h = dlg.winfo_height()
    ws = dlg.winfo_screenwidth()
    hs = dlg.winfo_screenheight()
    x = (ws // 2) - (w // 2)
    y = (hs // 2) - (h // 2)
    dlg.geometry(f"{w}x{h}+{x}+{y}")

    # 模态：阻塞直到窗口销毁
    dlg.transient(root)
    dlg.grab_set()
    root.wait_window(dlg)
    root.destroy()

    return result['value']

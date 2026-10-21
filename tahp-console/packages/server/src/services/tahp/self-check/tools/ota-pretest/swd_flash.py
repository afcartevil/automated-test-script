# -*- coding: utf-8 -*-
"""
SWD_Development_Center 刷机工具自动化脚本
=====================================================
流程(与人工操作一致):
  0. 旧版本工具启动后若弹"版本升级提示"窗口, 自动点"否"跳过(不升级)
  1. 启动工具 -> "账号登录"界面, 从 swd_flash_config.ini 读取账号/密码填充, 点"确认"登录
  2. 点"设置" -> "加载" -> 选择传入的固件路径(flash.xml), 弹窗点"OK"
  3. 设置界面"下载方式"选择"固件升级"; "下载选项"中仅勾选 "下载后自动开机" 和 "退出开始状态", 其余不勾
  4. 点"确认" -> "Load Files Setting"界面点 "Select All"
  5. adb 检查手机: getprop ro.product.name 与固件版本匹配, 不匹配报错"无可用设备"
  6. 点"启动"(开始/停止按钮), 确认启动后下发 "adb reboot -p" 关机进入刷机
  7. 等待刷机完成, 检测 Pass/Fail, 出错则提示"刷机报错"

用法:
  python swd_flash.py <flash.xml路径>                 # 完整流程
  python swd_flash.py <flash.xml路径> --prepare-only  # 只做到第5步(不启动刷机)
  python swd_flash.py --status                        # 查询状态
  python swd_flash.py --stop                          # 停止刷机等待状态
  可选: --adb <adb.exe路径>  --flash-timeout <秒>  --config <ini路径>

说明:
  - 脚本自动请求管理员权限(目标工具是管理员进程)
  - 全程日志: 本目录 swd_flash_log.txt
  - 账号配置: 本目录 swd_flash_config.ini
  - 目录结构: 脚本与 Softwaredownload_* 工具目录分离部署; 工具目录在
    swd_flash_config.ini 的 [TOOL] Dir 中配置(缺省用内置默认路径),
    启动时校验路径有效性, 无效则报"烧录工具路径异常"并退出

控件依据(实测dump):
  登录框"账号登录": 工号Edit=1041 密码Edit=1039 确认=1170
  主窗口: 开始/停止=1019 设置=1020 帮助=1021 SW版本=1056 总数=1041 失败数=1042
          通过率=1043 端口列表=1007
  设置框"设置": 路径Edit=1025 加载=1026 确认=1027 取消=1028
    下载方式(单选): 格式化下载（清除NV）=1063 固件升级=1064 仅格式化=1065 保留用户数据=1066
    下载选项: 下载后自动开机=1067 Flash校验功能=1068 检查软件版本号=1069
              本地版本校验=1070 退出开始状态=1079 下载进入QMMI模式=1081
  "Load Files Setting": Select All=1084 OK=1109 Cancel=2
"""
import argparse
import configparser
import ctypes
import os
import shutil
import subprocess
import sys
import time
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "swd_flash_log.txt")
CONFIG_FILE = os.path.join(BASE_DIR, "swd_flash_config.ini")

TOOL_EXE_NAME = "SWD_Development_Center.exe"
# 配置文件未指定工具目录时的默认路径
DEFAULT_TOOL_DIR = r"D:\rd_tool\swd\Softwaredownload_V9.2026.09.01_for_Development_Center"

MAIN_TITLE_RE = r"DevelopmentDownload.*"
MAIN_TITLE_RE2 = r"^SoftwareDownload$"
LOGIN_TITLE_RE = r"^(账号登录|登录|Login)$"
SETTINGS_TITLE_RE = r"^(设置|Settings)$"
LFS_TITLE = "Load Files Setting"

# 主窗口控件
BTN_START_STOP = 1019
BTN_SETTINGS = 1020
BTN_HELP = 1021
STATIC_SW = 1056
EDIT_TOTAL = 1041
EDIT_FAIL = 1042
EDIT_PASSRATE = 1043
LIST_PORTS = 1007

# 登录框控件
LOGIN_EDIT_USER = 1041
LOGIN_EDIT_PWD = 1039
LOGIN_BTN_OK = 1170

# 设置框控件
EDIT_FW_PATH = 1025
BTN_LOAD = 1026
BTN_OK = 1027
# 下载方式单选。第一列是一组: 1063 格式化下载（清除NV）/ 1064 固件升级 / 1065 仅格式化 / 1066 保留用户数据
DL_MODE_FIRMWARE_UPGRADE = 1064
DL_MODE_RADIOS = (
    (1063, "格式化下载（清除NV）"),
    (1064, "固件升级"),
    (1065, "仅格式化"),
    (1066, "保留用户数据"),
    (1072, "内存测试"),
    (1113, "分区回读"),
    (1098, "分区写入"),
    (1111, "仅读熔丝信息"),
    (1165, "ETT BIN Download"),
    (1114, "仅写熔丝操作"),
    (1115, "读取SocID"),
    (1117, "高通设置参数模式"),
)

# 下载选项勾选框: 目标状态 True=勾选
DL_OPTIONS = {
    1067: True,   # 下载后自动开机
    1068: False,  # Flash校验功能
    1069: False,  # 检查软件版本号
    1070: False,  # 本地版本校验
    1079: True,   # 退出开始状态
    1081: False,  # 下载进入QMMI模式
}

# Load Files Setting 控件
LFS_SELECT_ALL = 1084

_log_fh = None
# 已知不需要当弹窗处理的窗口句柄(避免对繁忙窗口发消息导致阻塞)
_excluded_handles = set()


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    try:
        print(line)
    except Exception:
        pass
    global _log_fh
    if _log_fh is None:
        _log_fh = open(LOG_FILE, "a", encoding="utf-8")
    _log_fh.write(line + "\n")
    _log_fh.flush()


def ensure_admin(argv):
    if ctypes.windll.shell32.IsUserAnAdmin():
        return
    log("当前非管理员权限,请求 UAC 提权重启...")
    args = " ".join('"%s"' % a for a in argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
    sys.exit(0)


def find_pid():
    import psutil
    for p in psutil.process_iter(["pid", "name"]):
        if p.info["name"] and "SWD_Development_Center" in p.info["name"]:
            return p.info["pid"]
    return None


# 启动时从配置文件解析出的烧录工具目录(见 main())
_CFG_TOOL_DIR = None


def load_tool_dir(cfg_path):
    """从配置文件读取烧录工具目录([TOOL] Dir); 未配置时返回内置默认路径。"""
    cp = configparser.ConfigParser()
    if os.path.exists(cfg_path):
        cp.read(cfg_path, encoding="utf-8-sig")  # 兼容带BOM的ini(记事本保存)
    d = cp.get("TOOL", "Dir", fallback="").strip().strip('"').strip()
    return d if d else DEFAULT_TOOL_DIR


def is_valid_tool_dir(d):
    """工具目录有效: 目录存在且包含 SWD_Development_Center.exe。"""
    return bool(d) and os.path.isdir(d) and \
        os.path.exists(os.path.join(d, TOOL_EXE_NAME))


def resolve_tool_dir():
    """工具运行中则从进程反推目录(保证Logs定位准确);
    未运行时退化为配置文件指定的工具目录。"""
    import psutil
    pid = find_pid()
    if pid:
        try:
            exe = psutil.Process(pid).exe()
            if exe:
                return os.path.dirname(exe)
        except Exception:
            pass
    return _CFG_TOOL_DIR or DEFAULT_TOOL_DIR


def tool_exe_path():
    return os.path.join(resolve_tool_dir(), TOOL_EXE_NAME)


def connect_tool(launch_timeout=120):
    from pywinauto import Application
    pid = find_pid()
    if pid is None:
        exe = tool_exe_path()
        if not os.path.exists(exe):
            raise RuntimeError(
                "烧录工具路径异常: %s (请检查配置文件 [TOOL] Dir)" % exe)
        log("启动刷机工具: %s" % exe)
        subprocess.Popen([exe], cwd=os.path.dirname(exe))
        t0 = time.time()
        while time.time() - t0 < launch_timeout:
            pid = find_pid()
            if pid:
                try:
                    app = Application(backend="win32").connect(process=pid)
                    dismiss_upgrade_prompt(app)  # 旧版本启动即弹升级提示,点"否"
                    if find_main(app, timeout=1) is not None or \
                            find_login(app, timeout=1) is not None:
                        log("工具已启动, pid=%s" % pid)
                        return app
                except Exception:
                    pass
            time.sleep(2)
        raise RuntimeError("等待工具界面超时")
    return Application(backend="win32").connect(process=pid)


def find_main(app, timeout=0):
    """优先 DevelopmentDownload(登录后), 其次 SoftwareDownload(登录前)。
    必须限定class_name='#32770', 否则会误匹配tooltips_class32气泡。"""
    try:
        w = app.window(title_re=MAIN_TITLE_RE, class_name="#32770")
        if w.exists(timeout=timeout):
            return w
    except Exception:
        pass
    try:
        w = app.window(title_re=MAIN_TITLE_RE2, class_name="#32770")
        if w.exists(timeout=timeout):
            return w
    except Exception:
        pass
    return None


def find_login(app, timeout=0):
    try:
        w = app.window(title_re=LOGIN_TITLE_RE, class_name="#32770")
        if w.exists(timeout=timeout):
            return w
    except Exception:
        pass
    return None


def main_wnd(app):
    w = find_main(app, timeout=5)
    if w is None:
        raise RuntimeError("找不到主窗口")
    return w


def btn_enabled(app, cid):
    try:
        return bool(main_wnd(app).child_window(control_id=cid).is_enabled())
    except Exception:
        return None


def is_started(app):
    """开始状态: 设置按钮被禁用。"""
    return btn_enabled(app, BTN_SETTINGS) is False


def read_text(app, cid):
    try:
        return main_wnd(app).child_window(control_id=cid).window_text()
    except Exception:
        return None


def read_int(app, cid):
    t = read_text(app, cid)
    try:
        return int(str(t).strip())
    except Exception:
        return None


def list_dialogs(app):
    """列出 #32770 对话框(跳过已排除句柄, 避免对繁忙窗口发消息阻塞)。"""
    res = []
    for w in app.windows():
        try:
            h = w.handle
            if h in _excluded_handles:
                continue
            if w.class_name() == "#32770":
                res.append((h, w.window_text()))
        except Exception:
            pass
    return res


def dump_dialog(app, handle, tag):
    try:
        spec = app.window(handle=handle)
        lines = []

        def walk(ctrl, depth):
            try:
                cls = ctrl.class_name()
            except Exception:
                cls = "?"
            try:
                txt = ctrl.window_text()
            except Exception:
                txt = ""
            try:
                cid = ctrl.control_id()
            except Exception:
                cid = None
            try:
                en = ctrl.is_enabled()
            except Exception:
                en = None
            lines.append("%s[%s] %r id=%s en=%s" % ("  " * depth, cls, txt, cid, en))
            try:
                kids = ctrl.children()
            except Exception:
                kids = []
            for k in kids:
                walk(k, depth + 1)

        walk(spec.wrapper_object(), 0)
        fn = LOG_FILE.replace(".txt", "_%s.txt" % tag)
        with open(fn, "w", encoding="utf-8") as f:
            # 大对话框(现代文件对话框约600行)截断会丢掉文件名框/按钮区域, 放宽上限
            f.write("\n".join(lines[:2000]))
        log("弹窗控件树已保存: %s (%d行)" % (fn, len(lines)))
    except Exception as e:
        log("dump弹窗失败: %s" % e)


def click_popup_button(app, handle, labels=None):
    """遍历弹窗按钮,匹配规范化后的文本(去空格/大小写/&助记符)后点击。"""
    if labels is None:
        labels = ("确定", "OK", "确认", "是(&Y)", "是(Y)", "Yes", "&OK", "打开(&O)", "打开(O)")

    def norm(s):
        return (s or "").replace("&", "").strip().lower()

    targets = {norm(x) for x in labels}
    try:
        spec = app.window(handle=handle)
        for c in spec.wrapper_object().descendants():
            try:
                if c.class_name() != "Button":
                    continue
                txt = c.window_text()
                if norm(txt) in targets and c.is_enabled():
                    # 点击后按钮随弹窗销毁, 先取文本再点, 否则吞掉成功日志
                    c.click()
                    return txt
            except Exception:
                continue
    except Exception:
        pass
    return None


# 版本升级提示(旧版本工具启动时弹出): 一律点"否"跳过, 不升级
UPGRADE_BTN_LABELS = ("否(&N)", "否(N)", "否", "&No", "No")


def is_upgrade_prompt(title):
    """标题含"升级"的提示窗(版本升级提示)。"""
    t = (title or "").lower()
    return ("升级" in t) or ("upgrade" in t) or ("update" in t)


def handle_popups(app, known, tag="popup", auto_ok=False):
    """检测 known 之外的新弹窗; 返回[(h,title)]。auto_ok时尝试点确定类按钮。
    版本升级提示除外: 自动点"否"跳过升级(绝不点"是")。"""
    new = []
    try:
        now = list_dialogs(app)
    except Exception:
        return new
    for h, t in now:
        if (h, t) in known:
            continue
        if "DevelopmentDownload" in (t or "") or t == "SoftwareDownload":
            continue
        new.append((h, t))
        log("检测到弹窗: %r" % t)
        dump_dialog(app, h, tag)
        if auto_ok:
            if is_upgrade_prompt(t):
                b = click_popup_button(app, h, labels=UPGRADE_BTN_LABELS)
                if b:
                    log("版本升级提示,已点击'%s'(不升级)" % b)
                else:
                    log("警告: 版本升级提示未找到'否'按钮,保留弹窗等待人工处理")
                continue
            b = click_popup_button(app, h)
            if b:
                log("已点击弹窗按钮: %s" % b)
    return new


def dismiss_upgrade_prompt(app, rounds=3, interval=1.0):
    """主动扫描"版本升级提示"窗口并点"否"跳过(工具启动后调用)。
    返回是否处理过该弹窗。"""
    handled = False
    for _ in range(rounds):
        for h, t in list_dialogs(app):
            if not is_upgrade_prompt(t):
                continue
            log("检测到版本升级提示窗口: %r, 点击'否'跳过升级" % t)
            dump_dialog(app, h, "upgrade_popup")
            b = click_popup_button(app, h, labels=UPGRADE_BTN_LABELS)
            if b:
                log("已点击升级提示按钮: %s(不升级)" % b)
                handled = True
                break
            log("警告: 版本升级提示未找到'否'按钮")
        if handled:
            break
        time.sleep(interval)
    return handled


# ---------------- 步骤1: 登录 ----------------
def load_account(cfg_path):
    cp = configparser.ConfigParser()
    if not os.path.exists(cfg_path):
        raise RuntimeError("缺少账号配置文件: %s" % cfg_path)
    cp.read(cfg_path, encoding="utf-8-sig")  # 兼容带BOM的ini(记事本保存)
    user = cp.get("ACCOUNT", "User", fallback="").strip()
    pwd = cp.get("ACCOUNT", "Password", fallback="")
    if not user or not pwd:
        raise RuntimeError("配置文件 %s 中 User/Password 为空" % cfg_path)
    return user, pwd


def login_if_needed(app, cfg_path, timeout=90):
    # 等登录框或主窗口出现
    t0 = time.time()
    login = None
    while time.time() - t0 < timeout:
        login = find_login(app, timeout=0.5)
        if login is not None:
            break
        m = find_main(app, timeout=0.5)
        if m is not None:
            try:
                if m.is_enabled() and "DevelopmentDownload" in (m.window_text() or ""):
                    log("已是登录状态,跳过登录")
                    return
            except Exception:
                pass
        time.sleep(1)
    if login is None:
        log("未发现登录框,按已登录处理")
        return

    user, pwd = load_account(cfg_path)
    log("登录框已出现,填充账号 %s ..." % user)
    login.child_window(control_id=LOGIN_EDIT_USER).set_edit_text(user)
    time.sleep(0.3)
    login.child_window(control_id=LOGIN_EDIT_PWD).set_edit_text(pwd)
    time.sleep(0.3)
    known = list_dialogs(app)
    login.child_window(control_id=LOGIN_BTN_OK).click()
    log("已点击登录确认,等待登录结果(最长%ds)..." % timeout)

    t0 = time.time()
    while time.time() - t0 < timeout:
        if find_login(app, timeout=0.3) is None:
            # 登录框已关闭 -> 成功?
            m = find_main(app, timeout=2)
            if m is not None:
                log("登录成功,主窗口: %r" % (m.window_text() or ""))
                return
        popups = handle_popups(app, known, tag="login_popup", auto_ok=True)
        if popups:
            raise RuntimeError("登录失败,出现提示弹窗: %s (请检查账号密码)" %
                               [t for _, t in popups])
        time.sleep(2)
    raise RuntimeError("登录超时(登录框未关闭)")


# ---------------- 步骤2/3/4: 设置固件 ----------------
BM_CLICK = 0x00F5
WM_COMMAND = 0x0111


def press_button(ctrl):
    """PostMessage BM_CLICK。"""
    ctrl.post_message(BM_CLICK, 0, 0)


def notify_button_clicked(ctrl):
    """向父窗口 PostMessage BN_CLICKED。原因同 press_button。"""
    ctrl.parent().post_message(WM_COMMAND, ctrl.control_id(), ctrl.handle)


def find_settings_dialog(app):
    """已打开的设置框直接用句柄接管。title_re 的 exists() 会卡在繁忙窗口上。"""
    for handle, title in list_dialogs(app):
        if (title or "").strip() in ("设置", "Settings"):
            return app.window(handle=handle)
    return None


def wait_settings_dialog(app, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        dlg = find_settings_dialog(app)
        if dlg is not None:
            return dlg
        time.sleep(0.5)
    return None


def open_settings(app):
    dlg = find_settings_dialog(app)
    if dlg is not None:
        log("设置对话框已打开，继续后续操作")
        return dlg
    btn = main_wnd(app).child_window(control_id=BTN_SETTINGS).wrapper_object()
    log("点击设置按钮...")
    press_button(btn)
    dlg = wait_settings_dialog(app, 8)
    if dlg is None:
        log("设置按钮 BM_CLICK 未打开对话框，补发 BN_CLICKED")
        notify_button_clicked(btn)
        dlg = wait_settings_dialog(app, 12)
    if dlg is None:
        raise RuntimeError("设置对话框未出现")
    return dlg


def browse_and_load(app, dlg, fw_path, timeout=20):
    """点'加载'->文件对话框输入路径->打开->处理弹窗OK。"""
    known = list_dialogs(app)
    log("点击'加载'按钮...")
    press_button(dlg.child_window(control_id=BTN_LOAD).wrapper_object())
    # 等文件对话框
    fd = None
    t0 = time.time()
    while time.time() - t0 < timeout:
        for h, t in list_dialogs(app):
            if (h, t) not in known:
                fd = (h, t)
                break
        if fd:
            break
        time.sleep(0.5)
    if fd is None:
        raise RuntimeError("点击'加载'后未出现文件选择对话框")
    log("文件对话框已打开: %r, 输入固件路径..." % fd[1])
    fspec = app.window(handle=fd[0])
    _excluded_handles.add(fd[0])
    from pywinauto.keyboard import send_keys

    def _filename_edit_candidates():
        """候选文件名输入框(按可信度排序):
        1) 对话框直接子级 ComboBoxEx32 内的 Edit(现代对话框文件名框;
           地址栏/搜索框的 Edit 嵌套在导航容器内, 不是对话框直接子级)
        2) 对话框直接子级 Edit(老式对话框)
        3) 全部 Edit(兜底)"""
        tried = []

        def add(ctrls):
            for c in ctrls:
                try:
                    if any(c.handle == t.handle for t in tried):
                        continue
                except Exception:
                    pass
                tried.append(c)

        try:
            for c in fspec.wrapper_object().children():
                try:
                    if c.class_name() == "ComboBoxEx32":
                        add([e for e in c.descendants() if e.class_name() == "Edit"])
                except Exception:
                    continue
        except Exception:
            pass
        try:
            add([c for c in fspec.wrapper_object().children() if c.class_name() == "Edit"])
        except Exception:
            pass
        try:
            add([c for c in fspec.wrapper_object().descendants() if c.class_name() == "Edit"])
        except Exception:
            pass
        return tried

    ok = False
    for edit in _filename_edit_candidates():
        try:
            # 写入后读回校验, 防止路径落到搜索框等错误控件
            edit.set_edit_text(fw_path)
            if (edit.window_text() or "").strip().lower() == fw_path.strip().lower():
                ok = True
                break
        except Exception:
            continue
    if not ok:
        log("候选文件名框写入均失败,尝试键盘输入")
        try:
            fspec.set_focus()
            send_keys(fw_path, with_spaces=True)
            ok = True
        except Exception as e2:
            log("键盘输入也失败: %s" % e2)
    if not ok:
        dump_dialog(app, fd[0], "filedlg")
        raise RuntimeError("无法在文件对话框中输入路径")
    time.sleep(0.5)

    def settings_path_loaded():
        """结果校验: 设置框路径已写入目标固件。
        设置框可能被工具重建, 每次重新枚举而不是沿用旧句柄。"""
        try:
            settings = find_settings_dialog(app) or dlg
            cur = settings.child_window(control_id=EDIT_FW_PATH).window_text()
            return cur.strip().lower() == fw_path.strip().lower()
        except Exception:
            return False

    def file_dialog_alive():
        """句柄存在且窗口身份未被复用才算存活。
        Windows 会回收复用 HWND(实测被复用成设置框), 仅看 exists() 会误判;
        标题在对话框初始化期间可能为空且随导航变化, 不作为身份依据。"""
        try:
            if not fspec.exists(timeout=0.2):
                return False
        except Exception:
            return False
        try:
            # 设置框特有的固件路径Edit出现 => 句柄已被复用成设置框
            if fspec.child_window(control_id=EDIT_FW_PATH).exists(timeout=0.1):
                return False
        except Exception:
            pass
        return True

    # 关键: 文件名ComboBox下拉可能展开,第一次点"打开"仅导航到目录,
    # 需要循环点击直到对话框真正关闭(最多5次)。
    # 成功判据 = 对话框真正关闭; 工具会记住上次加载路径(陈旧匹配),
    # 绝不能仅凭设置框路径提前放行——对话框仍开着时必须点"打开"完成本次选择,
    # 否则工具内部未真正加载, 设置确认时会报"请选择升级文件夹"。
    for attempt in range(5):
        if not file_dialog_alive():
            break
        try:
            fspec.child_window(control_id=1).click()  # 打开(IDOK)
        except Exception:
            try:
                fspec.set_focus()
                send_keys("{ENTER}")
            except Exception:
                pass
        # 等对话框关闭(每次给3秒)
        t0 = time.time()
        while time.time() - t0 < 3:
            if not file_dialog_alive():
                break
            time.sleep(0.5)
        if not file_dialog_alive():
            break
        log("文件对话框未关闭,再次点击'打开'(第%d次)..." % (attempt + 2))
        time.sleep(0.5)
    _excluded_handles.discard(fd[0])
    if file_dialog_alive():
        dump_dialog(app, fd[0], "filedlg_stuck")
        raise RuntimeError("文件对话框多次确认后仍未关闭")
    log("文件对话框已关闭,固件选择完成")
    # 工具解析固件后才回写设置框路径, 宽限等待
    t0 = time.time()
    while time.time() - t0 < 5 and not settings_path_loaded():
        time.sleep(0.5)
    # 选择版本后若弹出提示框,直接点OK
    time.sleep(1)
    popups = handle_popups(app, known, tag="load_popup", auto_ok=True)
    for h, t in popups:
        log("加载后弹窗已处理: %r" % t)
    # 校验设置框路径(设置框可能被工具重建, 优先重新枚举)
    try:
        settings = find_settings_dialog(app) or dlg
        cur = settings.child_window(control_id=EDIT_FW_PATH).window_text()
        log("设置框当前路径: %r" % cur)
        if not cur.strip():
            raise RuntimeError("固件路径未写入设置框(加载失败)")
        if cur.strip().lower() != fw_path.strip().lower():
            log("警告: 设置框路径与传入不一致")
    except RuntimeError:
        raise
    except Exception as e:
        log("读取设置框路径失败: %s" % e)


def _download_mode_states(dlg):
    rows = []
    for cid, name in DL_MODE_RADIOS:
        radio = dlg.child_window(control_id=cid).wrapper_object()
        rows.append((cid, name, radio.get_check_state()))
    return rows


def _firmware_upgrade_selected(rows):
    selected = [name for _cid, name, state in rows if state == 1]
    return selected == ["固件升级"]


def _log_download_mode(prefix, rows):
    chosen = [name for _cid, name, state in rows if state == 1]
    log("  %s选中: %s" % (prefix, "、".join(chosen) or "无"))


def set_download_mode(dlg):
    """下载方式: 选择固件升级(1064)。"""
    log("配置'下载方式': 选择固件升级...")
    try:
        before = _download_mode_states(dlg)
        _log_download_mode("切换前", before)
        if _firmware_upgrade_selected(before):
            log("  固件升级已选中")
            return
        radio = dlg.child_window(control_id=DL_MODE_FIRMWARE_UPGRADE).wrapper_object()
        press_button(radio)
        time.sleep(0.4)
        after = _download_mode_states(dlg)
        _log_download_mode("消息点击后", after)
        if not _firmware_upgrade_selected(after):
            log("  BM_CLICK 未生效，补发 BN_CLICKED")
            notify_button_clicked(radio)
            time.sleep(0.4)
            after = _download_mode_states(dlg)
            _log_download_mode("补发后", after)
        if not _firmware_upgrade_selected(after):
            selected = [name for _cid, name, state in after if state == 1]
            raise RuntimeError("下载方式未能选中固件升级，当前选中: %s" % ("、".join(selected) or "无"))
    except RuntimeError:
        raise
    except Exception as e:
        log("  固件升级设置失败: %s" % e)
        raise RuntimeError("下载方式控件%d配置失败" % DL_MODE_FIRMWARE_UPGRADE)


def set_download_options(dlg):
    """下载选项: 仅勾选 下载后自动开机(1067) 与 退出开始状态(1079)。"""
    log("配置'下载选项'勾选状态...")
    for cid, want in DL_OPTIONS.items():
        try:
            cb = dlg.child_window(control_id=cid).wrapper_object()
            cur = cb.get_check_state()
            if cur != (1 if want else 0):
                if want:
                    cb.check()
                else:
                    cb.uncheck()
                time.sleep(0.2)
                cur2 = cb.get_check_state()
                log("  控件%d: %s -> %s" % (cid, cur, cur2))
            else:
                log("  控件%d: 已是目标状态(%s)" % (cid, cur))
        except Exception as e:
            log("  控件%d设置失败: %s" % (cid, e))
            raise RuntimeError("下载选项控件%d配置失败" % cid)


def confirm_settings(app, dlg, timeout=120):
    known = list_dialogs(app)
    log("点击设置'确认'...")
    press_button(dlg.child_window(control_id=BTN_OK).wrapper_object())
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if not dlg.exists(timeout=0.3):
                log("设置对话框已关闭")
                return known
        except Exception:
            return known
        handle_popups(app, known, tag="settings_popup", auto_ok=True)
        time.sleep(1)
    raise RuntimeError("设置确认后对话框未关闭(超时)")


def _lfs_select_all_spec(win):
    """分区框刚弹出或沿用上一轮窗口时，Select All 可能还没创建。"""
    try:
        spec = win.child_window(control_id=LFS_SELECT_ALL)
        if spec.exists(timeout=0.4):
            return spec
    except Exception:
        pass
    for title in ("Select All", "全选"):
        try:
            spec = win.child_window(title=title, class_name="Button")
            if spec.exists(timeout=0.2):
                return spec
        except Exception:
            pass
    return None


def lfs_select_all(app, timeout=90):
    """等'Load Files Setting'里的 Select All 出现再点击(之后不再触碰该框)。"""
    log("等待'Load Files Setting'分区选择框...")
    t0 = time.time()
    h = None
    spec = None
    announced = False
    while time.time() - t0 < timeout:
        for wh, wt in list_dialogs(app):
            if wt != LFS_TITLE:
                continue
            if not announced:
                log("分区框已出现，等待 Select All 按钮...")
                announced = True
            try:
                found = _lfs_select_all_spec(app.window(handle=wh))
            except Exception:
                found = None
            if found is not None:
                h = wh
                spec = found
                break
        if spec is not None:
            break
        time.sleep(1)
    if spec is None:
        for wh, wt in list_dialogs(app):
            if wt == LFS_TITLE:
                dump_dialog(app, wh, "lfs_no_select_all")
        raise RuntimeError("'Load Files Setting'里没有 Select All 按钮")
    log("点击 Select All ...")
    ctrl = spec.wrapper_object()
    visible = False
    try:
        visible = bool(ctrl.is_visible())
    except Exception:
        visible = False
    if visible:
        ctrl.click()
    else:
        # 分区列表还在创建时按钮已在控件树里，但尚未显示。.click() 会因此失败。
        log("Select All 尚未显示，改发点击消息")
        press_button(ctrl)
        try:
            notify_button_clicked(ctrl)
        except Exception as e:
            log("  Select All 点击消息未发出: %s" % e)
    log("已点击 Select All(按流程不点OK,保留该窗口)")
    _excluded_handles.add(h)  # 后续枚举对话框时跳过它, 防止其繁忙时阻塞
    time.sleep(2)


# ---------------- 步骤5: adb匹配 ----------------
def find_adb(adb_arg=None):
    cands = []
    if adb_arg:
        cands.append(adb_arg)
    w = shutil.which("adb")
    if w:
        cands.append(w)
    cands.append(r"C:\Program Files\ADB\adb.exe")
    for c in cands:
        if c and os.path.exists(c):
            return c
    raise RuntimeError("找不到adb.exe, 请用--adb指定")


def adb_devices(adb):
    r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=30)
    devs = []
    for line in (r.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 2 and parts[1] == "device":
            devs.append(parts[0])
    return devs


def adb_getprop(adb, serial, prop):
    r = subprocess.run([adb, "-s", serial, "shell", "getprop", prop],
                       capture_output=True, text=True, timeout=30)
    return (r.stdout or "").strip()


def project_code_from_path(fw_path):
    """从固件路径提取项目码。

    flash.xml: .../<版本目录>/download_agent/flash.xml，如 X6850。
    *_Android_scatter.txt 在包根目录时，版本目录就是文件所在目录。
    """
    if os.path.basename(fw_path).lower() == "flash.xml":
        ver_dir = os.path.basename(os.path.dirname(os.path.dirname(fw_path)))
    else:
        ver_dir = _package_dir_name(fw_path)
    return ver_dir.split("-")[0].strip(), ver_dir


def _package_dir_name(fw_path):
    """向上找到带版本号的包目录，跳过 download_agent 等中间目录。"""
    skip = {"download_agent", "open", "_downloads"}
    cur = os.path.dirname(os.path.abspath(fw_path))
    fallback = os.path.basename(cur)
    for _ in range(8):
        name = os.path.basename(cur)
        if name and name.lower() not in skip and "-" in name:
            return name
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return fallback


def adb_check_device(adb, fw_path, prefer_serial=None):
    code, ver_dir = project_code_from_path(fw_path)
    log("固件版本目录: %s, 项目码: %s" % (ver_dir, code))
    devs = adb_devices(adb)
    log("adb在线设备: %s" % (devs or "无"))
    if not devs:
        raise RuntimeError("无可用设备(adb未检测到在线手机)")
    matched = []
    for s in devs:
        try:
            pname = adb_getprop(adb, s, "ro.product.name")
        except Exception as e:
            log("设备%s读取getprop失败: %s" % (s, e))
            continue
        log("设备 %s ro.product.name = %s" % (s, pname))
        if pname and pname.upper().startswith(code.upper()):
            matched.append((s, pname))
    if not matched:
        raise RuntimeError("无可用设备(在线手机项目与固件版本%s不匹配)" % code)
    wanted = (prefer_serial or "").strip()
    if wanted:
        hit = [item for item in matched if item[0] == wanted]
        if not hit:
            online = wanted in devs
            raise RuntimeError(
                "指定设备 %s %s" % (
                    wanted,
                    "在线但项目与固件不匹配" if online else "不在 adb 在线列表",
                )
            )
        s, pname = hit[0]
        log("使用指定设备: %s (%s) 匹配项目 %s" % (s, pname, code))
        return s
    if len(matched) > 1:
        log("警告: 多台设备匹配, 使用第一台: %s" % matched[0][0])
    s, pname = matched[0]
    log("设备匹配成功: %s (%s) 匹配项目 %s" % (s, pname, code))
    return s


# ---------------- 步骤6: 启动并关机 ----------------
def start_tool(app, timeout=300):
    if is_started(app):
        log("工具已处于启动状态")
        return
    known = list_dialogs(app)
    log("点击'启动'按钮...")
    main_wnd(app).child_window(control_id=BTN_START_STOP).click()
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_started(app):
            log("刷机工具已确认启动(等待手机插入)")
            return
        handle_popups(app, known, tag="start_popup", auto_ok=True)
        time.sleep(2)
    raise RuntimeError("点击启动后,工具未进入启动状态(超时)")


def adb_reboot_poweroff(adb, serial):
    log("下发 adb reboot -p 关机命令到 %s ..." % serial)
    r = subprocess.run([adb, "-s", serial, "reboot", "-p"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        log("reboot命令返回码=%s, stderr=%s" % (r.returncode, (r.stderr or "").strip()))
    log("手机关机中, 刷机工具检测到手机后将自动开始刷机")


# ---------------- 步骤7: 等待刷机结果 ----------------
def read_port_rows(app):
    """读取端口列表各行文本; 失败返回[]。"""
    rows = []
    try:
        lv = main_wnd(app).child_window(control_id=LIST_PORTS).wrapper_object()
        ncol = 0
        try:
            ncol = lv.column_count()
        except Exception:
            pass
        for i in range(lv.item_count()):
            cells = []
            if ncol:
                for c in range(ncol):
                    try:
                        cells.append(lv.item(i, c).text() or "")
                    except Exception:
                        cells.append("")
            else:
                try:
                    cells.append(lv.item(i).text() or "")
                except Exception:
                    cells.append("")
            rows.append(cells)
    except Exception:
        pass
    return rows


def _today_log_dir():
    """工具当天日志目录(基于真实工具目录,每次调用实时解析,容忍目录后创建)。"""
    d = os.path.join(resolve_tool_dir(), "Logs", time.strftime("%Y%m%d"))
    return d if os.path.isdir(d) else None


def _list_thread_logs(logdir):
    """返回 {文件名: 完整路径} 的线程刷机日志(Index结尾__Pass/__Fail)。"""
    res = {}
    try:
        for fn in os.listdir(logdir):
            if fn.startswith("[--Index") and (fn.endswith("__Pass.log") or
                                              fn.endswith("__Fail.log")):
                res[fn] = os.path.join(logdir, fn)
    except Exception:
        pass
    return res


def _logdir_activity(logdir):
    """目录内最新文件修改时间(用于判断刷机是否仍有活动)。"""
    latest = 0.0
    try:
        for root, _, files in os.walk(logdir):
            for fn in files:
                try:
                    latest = max(latest, os.path.getmtime(os.path.join(root, fn)))
                except Exception:
                    pass
    except Exception:
        pass
    return latest


def _read_log_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _is_port_artifact(fail_log_path):
    """'Create COM File failed'类失败 = 端口切换残留的无效线程(手机随后在别的线程刷机)。"""
    content = _read_log_text(fail_log_path)
    if not content:
        return False
    return ("Create COM File failed" in content) or \
           ("Get UART 8210 pack data failed" in content and len(content) < 20000)


def _is_foreign_package_fail(fail_log_path):
    """SWD 启动后会扫所有下载口。另一台手机插着时，会用当前包去刷它并写下
    'not for this device'。这不是目标机的刷机结果。"""
    content = _read_log_text(fail_log_path)
    return "not for this device" in content or "Load-Package is not for this device" in content


def adb_online(adb, serial):
    try:
        return serial in adb_devices(adb)
    except Exception:
        return False


def wait_flash_result(app, base_total, base_fail, timeout=1800, poll=3,
                      adb=None, serial=None, base_logs=None):
    """等待刷机完成,三重完成信号(任一命中即返回):
      信号1(主): Logs目录新增 __Pass.log / __Fail.log 线程日志
      信号2: 计数器 - 总数增量 > 失败增量 判Pass; 失败增量>=总数增量且>0 判Fail
      信号3: adb设备先离线后重新上线(自动开机=刷成功的强信号,仅作Pass佐证)
    注意: 端口切换会产生无效Fail线程(Create COM File failed),不计入真实失败。
    另一台手机被扫到产生的 "not for this device" 也不计入目标机失败。
    """
    log("等待刷机完成(最长%ds)..." % timeout)
    known = list_dialogs(app)
    if base_logs is None:
        d = _today_log_dir()
        base_logs = _list_thread_logs(d) if d else {}
    foreign_fails = 0
    phone_offline_seen = False
    if adb and serial and not adb_online(adb, serial):
        phone_offline_seen = True  # 等待开始时手机已离线(关机快)
    t0 = time.time()
    last_log = 0
    last_adb_chk = 0
    artifact_time = None
    while time.time() - t0 < timeout:
        try:
            # ---- 弹窗检测 ----
            popups = handle_popups(app, known, tag="flash_popup", auto_ok=False)
            if popups:
                log("刷机报错: 出现弹窗 %s" % [t for _, t in popups])
                return False

            # ---- 信号1: 线程日志(目录可能尚未创建,每次实时解析) ----
            logdir = _today_log_dir()
            if logdir:
                for fn, path in _list_thread_logs(logdir).items():
                    if fn in base_logs:
                        continue
                    if fn.endswith("__Pass.log"):
                        log("刷机成功: 检测到Pass日志 %s" % fn)
                        return True
                    if _is_port_artifact(path):
                        log("忽略端口切换残留失败线程: %s" % fn)
                        base_logs[fn] = path
                        artifact_time = time.time()
                        continue
                    if _is_foreign_package_fail(path):
                        log("忽略其它设备的包不匹配失败(SWD 会扫到所有下载口): %s" % fn)
                        base_logs[fn] = path
                        foreign_fails += 1
                        continue
                    log("刷机报错: 检测到失败日志 %s" % fn)
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            log("失败日志尾部:\n%s" % f.read()[-1500:])
                    except Exception:
                        pass
                    return False
                if artifact_time and (time.time() - artifact_time > 120):
                    if time.time() - _logdir_activity(logdir) > 120:
                        log("刷机报错: 端口连接失败后120秒内无刷机活动")
                        return False

            # ---- 信号2: 计数器(独立于日志) ----
            total_now = read_int(app, EDIT_TOTAL)
            fail_now = read_int(app, EDIT_FAIL)
            if base_total is not None and total_now is not None:
                d_total = total_now - base_total
                d_fail = (fail_now - base_fail) if (base_fail is not None and
                                                    fail_now is not None) else 0
                # 其它手机的包不匹配会计入工具总数/失败数，不能当成目标机结果
                target_total = d_total - foreign_fails
                target_fail = d_fail - foreign_fails
                if target_fail < 0:
                    target_fail = 0
                if target_total > 0 and target_fail < target_total:
                    log("刷机成功(计数): 总数增量=%d 失败增量=%d 已忽略其它设备=%d" % (
                        d_total, d_fail, foreign_fails))
                    return True
                target_still_offline = bool(
                    serial and phone_offline_seen and adb and not adb_online(adb, serial)
                )
                if target_fail > 0 and target_fail >= max(target_total, 0) and not artifact_time and not target_still_offline:
                    # 没有端口残留的情况下,失败全部计入且无任何成功
                    if time.time() - t0 > 180:  # 给真实刷机线程留出启动时间
                        log("刷机报错(计数): 失败增量=%d,无成功记录" % target_fail)
                        return False

            # ---- 信号3: adb回在线(先离线后上线才算) ----
            if adb and serial and (time.time() - last_adb_chk > 10):
                last_adb_chk = time.time()
                if not phone_offline_seen:
                    if not adb_online(adb, serial):
                        phone_offline_seen = True
                        log("手机已离线(关机进入刷机)")
                else:
                    if adb_online(adb, serial):
                        log("刷机成功(adb): 手机已自动开机回在线(下载后自动开机仅成功时触发)")
                        return True
        except Exception as e:
            log("轮询异常(继续): %s" % e)

        if time.time() - last_log > 60:
            last_log = time.time()
            try:
                log("刷机中... 总数=%s 失败=%s 通过率=%s" % (
                    read_text(app, EDIT_TOTAL), read_text(app, EDIT_FAIL),
                    read_text(app, EDIT_PASSRATE)))
            except Exception:
                pass
        time.sleep(poll)
    log("刷机报错: 等待完成超时(%ds)" % timeout)
    return False


# ---------------- 辅助命令 ----------------
def ensure_idle(app, timeout=60):
    if not is_started(app):
        return True
    log("工具处于启动状态,点击停止...")
    main_wnd(app).child_window(control_id=BTN_START_STOP).click()
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not is_started(app):
            log("已停止")
            return True
        time.sleep(1)
    log("警告: 停止超时")
    return False


def wait_exit_started(app, timeout=120):
    """已勾选「退出开始状态」，刷完后工具自己退出，不要再点停止。"""
    if not is_started(app):
        log("工具已退出开始状态")
        return True
    log("等待工具自动退出开始状态...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not is_started(app):
            log("工具已退出开始状态")
            return True
        time.sleep(1)
    log("警告: 等待退出开始状态超时")
    return False


def show_status(app):
    log("=" * 50)
    log("SW版本 : %s" % read_text(app, STATIC_SW))
    log("状态   : %s" % ("已启动(等待/刷机中)" if is_started(app) else "空闲"))
    log("统计   : 总数=%s 失败数=%s 通过率=%s" % (
        read_text(app, EDIT_TOTAL), read_text(app, EDIT_FAIL),
        read_text(app, EDIT_PASSRATE)))
    log("按钮   : 启动/停止=%s 设置=%s 帮助=%s" % (
        btn_enabled(app, BTN_START_STOP), btn_enabled(app, BTN_SETTINGS),
        btn_enabled(app, BTN_HELP)))
    rows = read_port_rows(app)
    log("端口线程数: %d" % len(rows))
    for i, cells in enumerate(rows[:4]):
        log("  线程%d: %s" % (i, " | ".join(cells)))
    log("=" * 50)


def full_flow(app, fw_path, adb_path, prepare_only, flash_timeout, prefer_serial=None):
    # 前置: 若工具处于启动状态(连续刷机场景),先停止回到空闲
    ensure_idle(app)
    # 步骤2: 设置->加载->选择固件->弹窗OK
    dlg = open_settings(app)
    browse_and_load(app, dlg, fw_path)
    # 步骤3: 先勾选下载选项，再点击下载方式。放在最后，避免后续勾选消息打断刚点中的单选。
    set_download_options(dlg)
    set_download_mode(dlg)
    # 步骤4: 确认 -> Load Files Setting -> Select All
    confirm_settings(app, dlg)
    lfs_select_all(app)
    sw = read_text(app, STATIC_SW)
    log("当前SW版本显示: %r" % sw)
    # 步骤5: adb设备匹配
    serial = adb_check_device(adb_path, fw_path, prefer_serial)
    if prepare_only:
        log("--prepare-only: 已完成至步骤5,不启动刷机")
        return 0
    # 步骤6: 启动 + 关机(启动前快照日志/计数基线,防止漏检快速Pass)
    base_total = read_int(app, EDIT_TOTAL)
    base_fail = read_int(app, EDIT_FAIL)
    d = _today_log_dir()
    base_logs = _list_thread_logs(d) if d else {}
    start_tool(app)
    adb_reboot_poweroff(adb_path, serial)
    # 步骤7: 等待结果
    ok = wait_flash_result(app, base_total, base_fail, timeout=flash_timeout,
                           adb=adb_path, serial=serial, base_logs=base_logs)
    wait_exit_started(app)
    if ok:
        log("刷机完成: PASS")
        return 0
    log("刷机完成: FAIL(刷机报错)")
    return 1


def main():
    ap = argparse.ArgumentParser(description="SWD刷机工具自动化")
    ap.add_argument("firmware", nargs="?", help="固件 flash.xml 或 *_Android_scatter.txt 路径")
    ap.add_argument("--prepare-only", action="store_true",
                    help="只执行到步骤5(adb匹配),不启动刷机")
    ap.add_argument("--status", action="store_true", help="查询状态")
    ap.add_argument("--stop", action="store_true", help="停止启动状态")
    ap.add_argument("--adb", help="adb.exe路径")
    ap.add_argument("--config", default=CONFIG_FILE, help="账号配置ini路径")
    ap.add_argument("--flash-timeout", type=int, default=1800,
                    help="等待刷机完成秒数(默认1800)")
    ap.add_argument("--serial", help="指定 adb 序列号；多台同项目设备时只刷这一台")
    args = ap.parse_args()

    if not any([args.firmware, args.status, args.stop]):
        ap.print_help()
        sys.exit(2)

    argv = list(sys.argv)
    if args.firmware:
        abs_fw = os.path.abspath(args.firmware)
        argv = [abs_fw if a == args.firmware else a for a in argv]
        args.firmware = abs_fw
        if not os.path.exists(abs_fw):
            if ctypes.windll.shell32.IsUserAnAdmin():
                log("警告: 当前会话看不到该路径(可能为网络映射盘),仍将继续")
            else:
                print("错误: 固件路径不存在: %s" % abs_fw)
                sys.exit(2)

    # 启动前置校验: 烧录工具路径(配置文件 [TOOL] Dir, 缺省用默认路径)
    # 无效则提示"烧录工具路径异常"并退出, 有效才继续执行
    global _CFG_TOOL_DIR
    _CFG_TOOL_DIR = load_tool_dir(args.config)
    if not is_valid_tool_dir(_CFG_TOOL_DIR):
        log("烧录工具路径异常: %s" % _CFG_TOOL_DIR)
        log("请检查配置文件 %s 的 [TOOL] Dir (目录需存在且包含 %s)" %
            (args.config, TOOL_EXE_NAME))
        sys.exit(1)
    log("烧录工具路径: %s" % _CFG_TOOL_DIR)

    ensure_admin(argv)
    log("=" * 60)
    log("启动自动化: %s" % " ".join(sys.argv[1:]))

    try:
        app = connect_tool()
        # 旧版本工具启动时可能弹"版本升级提示", 点"否"跳过(不升级)
        dismiss_upgrade_prompt(app)
        # 主窗口句柄加入排除(不当弹窗处理)
        try:
            _excluded_handles.add(main_wnd(app).wrapper_object().handle)
        except Exception:
            pass

        if args.status:
            show_status(app)
            return
        if args.stop:
            ensure_idle(app)
            show_status(app)
            return

        # 步骤1: 登录
        login_if_needed(app, args.config)
        # 步骤2-7
        rc = full_flow(app, args.firmware, find_adb(args.adb),
                       args.prepare_only, args.flash_timeout, args.serial)
        show_status(app)
        sys.exit(rc)
    except SystemExit:
        raise
    except Exception as e:
        log("!!! 异常: %s" % e)
        log(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

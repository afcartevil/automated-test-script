#!/usr/bin/env python3
"""alarm 压测工具（休眠唤醒/重启/关机）启动与停止助手。

工具本体为 PyInstaller 成品包（start.exe + config.json，默认 D:\\rd_tool\\alarm_v2.1.029）：
- start: 合并写入 config.json 后启动压测，设备随后自治运行
- stop:  按设备 force-stop 相关包并杀掉 alarm.sh/aimonkey.sh/monkey 进程

设备定向（逆向 start.exe 实锤：其设备枚举 get_devices_list() 无任何过滤参数，会对
所有已连接设备启动；bind_devices.txt 属硬件继电器/串口集线器模块，与 start 流程无关）：
- 仅 1 台设备在线且为目标机 → 走 start.exe 原生流程（vendor 编排，行为不变）
- 多台设备在线 → 按 SN 直启：复刻 start.exe 逐设备流程（所有命令 -s SN /
  -device_id SN 定向，含两个安装器与 alarm.sh 模板替换），不触碰其它设备
  （安装器逆向实锤：install_apk 用 adb -s <device_id>，-device_id 即"只装此机"）

安装器坑（逆向 install_trde_apk 实锤）：其 APK 发现是 Path.cwd().glob('*.apk')，
必须以安装器自身目录为 cwd 运行，否则找不到 APK 而静默失败（退出码仍为 0，
输出尾部"完成安装手机 X, success/fail"才是真实结果）；故直启流程以安装器
自身目录为 cwd 并校验成功标记，装后再以 pm list 双保险校验。

启动判定：start.exe 路径＝退出码 0 且输出（GBK 双解码）含完成横幅；sleep 模式
额外在设备侧轮询确认 alarm.sh 已拉起并做稳定期复检（am instrument 瞬败会让
脚本数秒内退出，仅见进程不算启动成功，需进程存活且 alarm.log 无
INSTRUMENTATION_FAILED）。reboot/shutdown 模式设备随即断电/重启，无法事后
确认，仅以流程完成/横幅为准。
停止残留：周期性 RTC 唤醒闹钟存于硬件，force-stop 清不掉，睡眠周期中途停止后
数分钟内设备可能自行上电/重启一次，属工具固有行为。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ADB = "adb"
START_TIMEOUT_SEC = 240
INSTALLER_TIMEOUT_SEC = 120
# sleep 模式启动后设备侧确认窗口
SLEEP_CONFIRM_TIMEOUT_SEC = 20
SLEEP_CONFIRM_INTERVAL_SEC = 3
# 进程发现后的稳定期观察窗口（am instrument 瞬败会让 alarm.sh 数秒内退出）
SLEEP_STABILIZE_SEC = 10

FORCE_STOP_PACKAGES = [
    "com.trs.autotest.alarmtool",
    "com.mediatek.schpwronoff",
    "com.mediatek.schpwronoff.test",
    "com.android.commands.monkey.Monkey",
    "com.android.commands.monkey.transsion",
]
KILL_PROCESS_PATTERNS = ["alarm.sh", "alarmtool.sh", "aimonkey.sh", "monkey"]

# config.json 未暴露参数的工具默认值（与现网 config.json 保持一致）
MODE_DEFAULTS = {
    "sleep": {
        "exeMonkey": "0",
        "failStop": "-1",
        "monkeyBlackWhite": "black",
        "sheath": "0",
        "executeTMTS_Wakeup": 0,
        "monkeyType": "aimonkey",
    },
    "reboot": {"checkFileNum": "0"},
    "shutdown": {"checkFileNum": "0", "moreMode": "0"},
}


def run_cmd(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def online_devices() -> list[str]:
    result = run_cmd([ADB, "devices"])
    serials: list[str] = []
    for line in (result.stdout or "").splitlines()[1:]:
        line = line.strip()
        if line and line.endswith("\tdevice"):
            serials.append(line.split("\t", 1)[0])
    return serials


# start.exe 为 GBK 控制台输出的 PyInstaller 程序；按 utf-8 → gbk 双解码取可读版本
def decode_output(raw: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, AttributeError):
            continue
    return raw.decode("utf-8", errors="replace")


# 启动成功的正向标志（工具结束横幅，三模式通用；负向关键字不可用——
# usage 统计上传失败/wmic 缺失等非致命噪音会带 traceback 干扰判定）
START_SUCCESS_MARKS = ("所有设备启动完成了", "可以拔出usb", "不影响手机压测继续执行")


def confirm_sleep_running(serial: str) -> tuple[str | None, str | None]:
    """轮询确认 sleep 模式已在设备侧拉起 alarm.sh，并做稳定期复检。

    am instrument 瞬间失败（APK 缺失/签名不匹配）会让 alarm.sh 在数秒内跑完
    退出，仅看到进程并不能证明压测真正启动；故发现进程后额外观察
    SLEEP_STABILIZE_SEC 秒，要求进程仍存活且 alarm.log 无
    INSTRUMENTATION_FAILED。返回 (进程行, 失败原因)，成功时原因为 None。"""
    deadline = time.monotonic() + SLEEP_CONFIRM_TIMEOUT_SEC
    running_line = None
    while time.monotonic() < deadline:
        result = run_cmd(
            [ADB, "-s", serial, "shell", "ps -ef | grep alarm.sh | grep -v grep"],
            timeout=10,
        )
        out = (result.stdout or "").strip()
        if "alarm.sh" in out:
            running_line = out.splitlines()[0]
            break
        time.sleep(SLEEP_CONFIRM_INTERVAL_SEC)
    if running_line is None:
        return None, f"轮询 {SLEEP_CONFIRM_TIMEOUT_SEC}s 未见设备侧 alarm.sh 进程"
    # 稳定期复检：instrument 瞬败时脚本数秒内退出、alarm.log 留下失败痕迹
    time.sleep(SLEEP_STABILIZE_SEC)
    log_result = sh(
        serial,
        "grep INSTRUMENTATION_FAILED /data/local/tmp/alarm.log 2>/dev/null",
        timeout=10,
    )
    if "INSTRUMENTATION_FAILED" in (log_result.stdout or ""):
        return None, (
            "设备侧 am instrument 失败（INSTRUMENTATION_FAILED），压测未真正启动，"
            "请检查 APK 安装是否正常"
        )
    alive = sh(serial, "ps -ef | grep alarm.sh | grep -v grep", timeout=10)
    if "alarm.sh" not in (alive.stdout or ""):
        return None, "alarm.sh 启动后数秒内即退出（未进入稳定运行），压测未真正启动"
    return running_line, None


def adb_run(serial: str, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return run_cmd([ADB, "-s", serial, *args], timeout=timeout)


def sh(serial: str, cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return adb_run(serial, ["shell", cmd], timeout=timeout)


# alarm.sh 头部模板变量 → config 键（sleep 模式）
ALARM_SH_VAR_MAP = {
    "runtime": "loops",
    "mysleept": "sleepTimes",
    "exeMonkey": "exeMonkey",
    "failStop": "failStop",
    "monkeyBlackWhite": "monkeyBlackWhite",
    "executeTMTS_Wakeup": "executeTMTS_Wakeup",
    "sheath": "sheath",
    "monkeyType": "monkeyType",
}


def build_alarm_sh(script_path: Path, section: dict) -> tuple[bytes | None, str]:
    """按 config 值替换 resource/tmp/alarm.sh 头部变量（与 start.exe 行为一致：
    值替换保留注释）；任一变量缺失/模板不匹配即报错，绝不推送未替换的脚本。"""
    try:
        text = script_path.read_text(encoding="utf-8")
    except Exception as exc:
        return None, f"读取 alarm.sh 模板失败: {exc}"
    for var, key in ALARM_SH_VAR_MAP.items():
        if key not in section:
            return None, f"缺少 alarm.sh 参数: {key}"
        pattern = re.compile(rf"(?m)^({re.escape(var)}\s*=\s*)\S+")
        text, count = pattern.subn(lambda m: m.group(1) + str(section[key]), text, count=1)
        if count != 1:
            return None, f"alarm.sh 模板中未见变量 {var}=<值>"
    return text.encode("utf-8"), ""


def install_scripts_apk(serial: str, tool_dir: Path) -> None:
    """安装 tmts_scripts（辅助用例 APK；start.exe 失败时重试一次，未确认成功仅告警）。"""
    apk = tool_dir / "resource" / "tmts_scripts" / "scripts-debug.apk"
    if not apk.is_file():
        print(f"警告: 缺少 {apk}（辅助用例 APK，跳过）")
        return
    for attempt in (1, 2):
        result = adb_run(serial, ["install", "-r", "-g", "-t", str(apk)], timeout=120)
        combined = (result.stdout or "") + (result.stderr or "")
        if "success" in combined.lower():
            return
        print(f"警告: scripts-debug.apk 第 {attempt} 次安装未确认成功: {combined.strip()[:160]}")
    print("警告: scripts-debug.apk 安装未确认成功，继续执行")


def run_installer(serial: str, tool_dir: Path, installer: Path, extra_args: list[str]) -> int:
    """运行 vendor 安装器（自身带平台/签名变体自动选择，按 -device_id 定向）。

    cwd 必须设为安装器自身目录：其 APK 发现是 Path.cwd().glob('*.apk')（逆向
    install_trde_apk 实锤），在工具根目录运行会找不到 APK 而静默失败（退出码
    仍为 0）。同理退出码不可信，必须校验输出中的结果标记。"""
    try:
        result = subprocess.run(
            [str(installer), "-cmd_mode", "true", *extra_args, "-device_id", serial],
            cwd=str(installer.parent),
            capture_output=True,
            timeout=INSTALLER_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print(f"{installer.name} 执行超时（>{INSTALLER_TIMEOUT_SEC}s）", file=sys.stderr)
        return 6
    output = "\n".join(
        x
        for x in [decode_output(result.stdout or b"").strip(), decode_output(result.stderr or b"").strip()]
        if x
    )
    # 安装器"静默失败"：安装不成功退出码也是 0，必须见到成功标记
    success_line = next(
        (line for line in output.splitlines() if ", success" in line or "Finish install apk on phone" in line),
        "",
    )
    if not success_line:
        print(f"{installer.name} 安装未确认成功（未见成功标记）\n{output}", file=sys.stderr)
        return 7
    print(f"{installer.name} 成功: {success_line.strip()}")
    return 0


def direct_start(args: argparse.Namespace, tool_dir: Path, section: dict) -> int:
    """多设备场景：按 SN 直启（复刻 start.exe 逐设备流程，仅操作目标机）。

    步骤与 start.exe 实测日志逐条对应（2026-10-15 sleep / 2026-10-14 shutdown 运行日志）：
    预检 → 卸载旧包 → root/setenforce → 装包（scripts-debug + 两个安装器）→
    建目录 → 按模式执行（sleep: 模板替换+push alarm.sh+setsid；reboot/shutdown: 广播）。"""
    serial = args.serial
    installers = [
        (tool_dir / "resource" / "apk" / "install_alarm_tool_apk.exe", []),
        (tool_dir / "resource" / "apk" / "androidTest" / "install_alarm_tool_test_apk.exe", ["-save_none", "true"]),
    ]
    for installer, _ in installers:
        if not installer.is_file():
            print(f"未找到安装程序: {installer}", file=sys.stderr)
            return 2

    print(f"[定向启动] 目标设备 {serial}，复刻 start.exe 逐设备流程（不影响其它在线设备）")
    model = (sh(serial, "getprop ro.product.model").stdout or "").strip()
    print(f"设备型号: {model or '(未知)'}")

    # start.exe 预检与清理步骤（失败容忍，与 vendor 行为一致）
    adb_run(serial, ["uninstall", "com.mediatek.schpwronoff.test"], timeout=60)
    adb_run(serial, ["uninstall", "com.mediatek.schpwronoff"], timeout=60)
    build_type = (sh(serial, "getprop ro.build.type").stdout or "").strip()
    if build_type != "userdebug":
        print(f"警告: ro.build.type={build_type or '未知'}（非 userdebug，root 能力受限）")
    adb_run(serial, ["root"], timeout=30)
    time.sleep(2)
    sh(serial, "setenforce 0")
    soc = (sh(serial, "getprop ro.soc.manufacturer").stdout or "").strip().upper()
    if any(k in soc for k in ("QTI", "QCOM", "QUALCOMM")):
        for prop in (
            "mainlogcat", "systemlogcat", "eventslogcat",
            "radiologcat", "crashlogcat", "kernellogcat", "securitylogcat",
        ):
            sh(serial, f"setprop debug.logd.{prop} true")
    else:
        print(f"平台: {soc or '(未知)'}（MTK 分支，跳过 logd 开关）")

    install_scripts_apk(serial, tool_dir)
    for installer, extra_args in installers:
        code = run_installer(serial, tool_dir, installer, extra_args)
        if code != 0:
            return code
    # 安装后校验（安装器可能静默失败，双保险）
    pm_lines = (sh(serial, "pm list packages | grep schpwronoff").stdout or "").splitlines()
    installed = {line.strip() for line in pm_lines if line.strip().startswith("package:")}
    missing = [p for p in ("com.mediatek.schpwronoff", "com.mediatek.schpwronoff.test") if f"package:{p}" not in installed]
    if missing:
        print(f"安装后校验失败，目标机缺少: {', '.join(missing)}", file=sys.stderr)
        return 7
    print("包校验通过: com.mediatek.schpwronoff(.test) 均已安装")
    sh(serial, "mkdir /sdcard/Auto_1")
    sh(serial, "mkdir /sdcard/Auto")

    if args.mode == "sleep":
        return direct_sleep(serial, tool_dir, section)
    return direct_broadcast(serial, tool_dir, args.mode, section)


def direct_sleep(serial: str, tool_dir: Path, section: dict) -> int:
    """sleep 模式直启（与 start.exe sleep 分支逐条对应）。"""
    sh(serial, "settings put system screen_off_timeout 1999999999")
    sh(serial, "locksettings set-disabled true")
    report_line = (
        f"echo 睡眠唤醒开始启动looptime:{section['loops']}\t"
        f"failStop:{section['failStop']}\texeMonkey:{section['exeMonkey']} > /sdcard/Auto_1/testReport.txt"
    )
    sh(serial, report_line)
    # MTK 分支资源（aimonkey 全家桶，start.exe 对 MTK 设备必推）
    pushes = [
        (tool_dir / "resource" / "aimonkey" / "aimonkey.apk", "/data/local/tmp/monkey.apk"),
        (tool_dir / "resource" / "aimonkey" / "aim", "/data/local/tmp"),
        (tool_dir / "resource" / "tmp" / "monkey_rw_test_64bit", "/data/local/tmp/monkey_rw_test_64bit"),
        (tool_dir / "resource" / "tmp" / "monkey_video.3gpp", "/sdcard"),
        (tool_dir / "resource" / "blacklist.txt", "/data/local/tmp/blacklist.txt"),
        (tool_dir / "resource" / "blacklist.txt", "/sdcard/blacklist.txt"),
        (tool_dir / "resource" / "whitelist.txt", "/data/local/tmp/whitelist.txt"),
        (tool_dir / "resource" / "whitelist.txt", "/sdcard/whitelist.txt"),
        (tool_dir / "resource" / "shell" / "aimonkey.sh", "/sdcard/Auto"),
    ]
    for src, dst in pushes:
        if not src.is_file():
            print(f"缺少资源文件: {src}", file=sys.stderr)
            return 7
        result = adb_run(serial, ["push", str(src), dst], timeout=180)
        # adb 35 的 push 摘要可能走 stderr，两路合并判定
        combined = (result.stdout or "") + (result.stderr or "")
        if "pushed" not in combined:
            print(f"警告: push {src.name} 未确认成功: {(result.stdout or result.stderr or '').strip()[:160]}")
    sh(serial, "chmod 777 /data/local/tmp/aim")
    sh(serial, "chmod 777 /data/local/tmp/monkey.apk")

    content, error = build_alarm_sh(tool_dir / "resource" / "tmp" / "alarm.sh", section)
    if content is None:
        print(error, file=sys.stderr)
        return 7
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("wb", suffix=".sh", delete=False) as handle:
            handle.write(content)
            tmp = Path(handle.name)
        result = adb_run(serial, ["push", str(tmp), "/data/local/tmp/alarm.sh"], timeout=60)
        combined = (result.stdout or "") + (result.stderr or "")
        if "pushed" not in combined:
            print(f"push alarm.sh 失败: {combined.strip()}", file=sys.stderr)
            return 7
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)

    sh(serial, "setsid sh /data/local/tmp/alarm.sh </dev/null >/data/local/tmp/alarm.log 2>&1 &")
    sh(serial, "setprop debug.sysdump.enabled true")
    sh(serial, "getprop debug.sysdump.enabled")

    running, error = confirm_sleep_running(serial)
    if running is None:
        print(f"{error}（定向启动流程判定失败）", file=sys.stderr)
        return 9
    print(f"已确认设备侧稳定运行: {running}")
    return 0


def direct_broadcast(serial: str, tool_dir: Path, mode: str, section: dict) -> int:
    """reboot/shutdown 模式直启（与 start.exe 广播分支逐条对应，extras 取自 config 模式段）。"""
    sh(serial, "settings put system screen_off_timeout 1999999999")
    sh(serial, "locksettings set-disabled true")
    sh(serial, "input keyevent 82")
    sh(serial, "input keyevent 82")
    # MTK 侧抓取链路（设备无对应组件时失败容忍，与 vendor 行为一致）
    sh(serial, "am startservice -n com.reallytek.wg/.utils.LogControlService -e from adb -p com.reallytek.wg "
               "--ei magic 902 -e android 1 -e kernel 1 -e uboot 1 -e lastkmsg 1 -e thermal 1 -e bthci 1 -e apcap 1")
    sh(serial, "am broadcast -a com.debug.loggerui.ADB_CMD -e cmd_name start --ei cmd_target 1 "
               "--receiver-foreground --receiver-include-background")
    sh(serial, "mkdir /sdcard/Auto_1")
    sh(serial, "mkdir /sdcard/Auto")
    sh(serial, f"echo 开关机开始启动looptime:{section['loops']} > /sdcard/Documents/testReport.txt")
    for name in ("startLowPower.sh", "stopInstrument.sh", "startLkKernel.sh"):
        src = tool_dir / "resource" / "shell" / name
        if src.is_file():
            adb_run(serial, ["push", str(src), "/sdcard/Auto"], timeout=60)
        else:
            print(f"警告: 缺少 {src}，跳过")

    extras = ["--es", "mode", mode, "--ei", "loops", str(section["loops"])]
    if "poweronTime" in section:
        extras += ["--ei", "poweronTime", str(section["poweronTime"])]
    if "shutdownTime" in section:
        extras += ["--ei", "shutdownTime", str(section["shutdownTime"])]
    if "checkFileNum" in section:
        extras += ["--ei", "checkFileNum", str(section["checkFileNum"])]
    if "moreMode" in section:
        extras += ["--ei", "moreMode", str(section["moreMode"])]
    cmd = (
        "am broadcast -a transsion.alarmTool.ALARMEXE "
        "-n com.mediatek.schpwronoff/com.transsion.alarmtool.broadcast.AdbStartReceiver " + " ".join(extras)
    )
    result = sh(serial, cmd, timeout=60)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    print(f"已发送启动广播: {cmd}")
    print(f"广播返回: {output[:200] or '(空)'}")
    return 0


def write_config(tool_dir: Path, mode: str, params: dict) -> Path:
    """合并写 config.json：保留既有未知字段；三个模式段始终齐全（start.exe 会整体读取），
    未暴露参数保留既有值、缺省补工具默认值；仅当前模式覆盖 UI 暴露参数并切换 runType。"""
    config_path = tool_dir / "config.json"
    config: dict = {}
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            config = {}
    if not isinstance(config, dict):
        config = {}
    for m, defaults in MODE_DEFAULTS.items():
        existing = config.get(m)
        section = dict(defaults)
        if isinstance(existing, dict):
            section.update(existing)
        if m == mode:
            section.update(params)
        config[m] = section
    config["runType"] = mode
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return config_path


def cmd_start(args: argparse.Namespace) -> int:
    tool_dir = Path(args.tool_dir)
    start_exe = tool_dir / "start.exe"
    if not start_exe.is_file():
        print(f"未找到 alarm 启动程序: {start_exe}", file=sys.stderr)
        return 2

    devices = online_devices()
    if not devices:
        print("未检测到在线设备（adb devices 为空），请连接测试机", file=sys.stderr)
        return 3
    if args.serial not in devices:
        print(
            f"目标测试机 {args.serial} 不在线（当前在线: {', '.join(devices)}），请确认连接后重试",
            file=sys.stderr,
        )
        return 5

    params: dict = {}
    if args.loops is not None:
        params["loops"] = str(args.loops)
    if args.mode == "sleep" and args.sleep_times is not None:
        params["sleepTimes"] = str(args.sleep_times)
    if args.mode in ("reboot", "shutdown") and args.poweron_time is not None:
        params["poweronTime"] = str(args.poweron_time)
    if args.mode == "shutdown" and args.shutdown_time is not None:
        params["shutdownTime"] = str(args.shutdown_time)

    config_path = write_config(tool_dir, args.mode, params)
    print(f"已写入测试配置: {config_path} (runType={args.mode}, {params})")

    # 多设备在线：start.exe 的设备枚举无过滤参数（会对所有设备启动），改走按 SN
    # 定向的直启流程（复刻其逐设备步骤，仅操作目标机）；单设备保持 vendor 原生编排
    if len(devices) > 1:
        print(
            f"检测到 {len(devices)} 台在线设备（{', '.join(devices)}），"
            f"start.exe 会作用于全部设备；改用按序列号 {args.serial} 定向启动"
        )
        section = dict(MODE_DEFAULTS[args.mode])
        section.update(params)
        return direct_start(args, tool_dir, section)

    try:
        # 字节捕获 + 双解码：start.exe 控制台输出为 GBK，直接按 utf-8 解会乱码
        result = subprocess.run(
            [str(start_exe)],
            cwd=str(tool_dir),
            capture_output=True,
            timeout=START_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print(f"start.exe 执行超时（>{START_TIMEOUT_SEC}s）", file=sys.stderr)
        return 6

    output = "\n".join(
        x
        for x in [
            decode_output(result.stdout or b"").strip(),
            decode_output(result.stderr or b"").strip(),
        ]
        if x
    )
    if result.returncode != 0:
        print(f"start.exe 退出码 {result.returncode}\n{output}", file=sys.stderr)
        return 7
    # 正向判定：必须见到启动完成横幅，否则视为失败（输出中的 traceback 为
    # usage 统计上传失败等非致命噪音，不代表启动失败）
    if not any(mark in output for mark in START_SUCCESS_MARKS):
        print(
            f"start.exe 输出未见启动完成标志（{'/'.join(START_SUCCESS_MARKS)}），判定失败\n{output}",
            file=sys.stderr,
        )
        return 8
    # sleep 模式设备侧硬校验：start.exe 对掉线设备也会打完成横幅（后段命令
    # 全部失败照样"所有设备启动完成了"），必须确认 alarm.sh 真正拉起并进入
    # 稳定运行（instrument 瞬败会在数秒内退出）才算成功
    if args.mode == "sleep":
        running_line, error = confirm_sleep_running(args.serial)
        if running_line is None:
            print(
                f"start.exe 打印了完成横幅，但设备侧压测未真正启动：{error}"
                "（设备可能中途掉线、自行重启或 instrument 失败）\n" + output,
                file=sys.stderr,
            )
            return 9
        print(f"已确认设备侧稳定运行: {running_line}")
    print(output or "start.exe 执行完成")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    serial = args.serial
    run_cmd([ADB, "-s", serial, "root"], timeout=15)
    for pkg in FORCE_STOP_PACKAGES:
        run_cmd([ADB, "-s", serial, "shell", "am", "force-stop", pkg], timeout=15)
    ps = run_cmd([ADB, "-s", serial, "shell", "ps", "-ef"], timeout=15)
    lines = (ps.stdout or "").splitlines()
    for pattern in KILL_PROCESS_PATTERNS:
        for line in lines:
            if pattern not in line or "grep" in line:
                continue
            fields = line.split()
            if len(fields) < 2 or not fields[1].isdigit():
                continue
            run_cmd([ADB, "-s", serial, "shell", "kill", "-9", fields[1]], timeout=15)
            print(f"已结束进程 {pattern} PID={fields[1]}")
    print(f"alarm 停止命令已在 {serial} 上执行完成")
    print(
        "提示：周期性 RTC 唤醒闹钟存于硬件、force-stop 清不掉；若在睡眠周期中途"
        "停止，数分钟内设备可能自行上电/重启一次，属工具固有行为"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="alarm 压测工具启动/停止助手")
    parser.add_argument("-s", "--serial", required=True, help="目标设备序列号")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="写配置并启动压测")
    p_start.add_argument("--mode", required=True, choices=["sleep", "reboot", "shutdown"])
    p_start.add_argument("--tool-dir", required=True)
    p_start.add_argument("--loops", type=int, default=None)
    p_start.add_argument("--sleep-times", type=int, default=None)
    p_start.add_argument("--poweron-time", type=int, default=None)
    p_start.add_argument("--shutdown-time", type=int, default=None)

    sub.add_parser("stop", help="停止设备上的压测")

    args = parser.parse_args()
    if args.command == "start":
        return cmd_start(args)
    return cmd_stop(args)


if __name__ == "__main__":
    sys.exit(main())

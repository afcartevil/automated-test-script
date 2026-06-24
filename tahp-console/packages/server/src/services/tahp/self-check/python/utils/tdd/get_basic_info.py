import subprocess

PROJECT_NAME_PROPS = (
    "ro.product.name",
    "ro.build.product",
    "ro.product.model",
    "ro.product.device",
)

PLATFORM_PROPS = (
    "ro.board.platform",
    "ro.hardware",
    "ro.soc.manufacturer",
)

VENDOR_HW_DIR = "/vendor/bin/hw"
# 与 CMD「adb shell ls /vendor/bin/hw | findstr secure_element」预期一致（MTK）
EXPECTED_OMAPI_MTK_SERVICE = "android.hardware.secure_element@1.2-service-mediatek"
SECURE_ELEMENT_MARKER = "secure_element"


def _run_adb(args, timeout=10):
    result = subprocess.run(
        ["adb", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(stderr or "adb command failed")
    return result.stdout.strip()


def _list_connected_devices():
    output = _run_adb(["devices"])
    devices = []
    for line in output.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def _get_prop(device_id: str, prop: str) -> str:
    return _run_adb(["-s", device_id, "shell", "getprop", prop])


def _run_adb_shell(
    device_id: str,
    *shell_args: str,
    timeout: int = 15,
) -> tuple[int, str, str]:
    """执行 adb shell 子命令，返回 (returncode, stdout, stderr)。"""
    result = subprocess.run(
        ["adb", "-s", device_id, "shell", *shell_args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return (
        result.returncode,
        (result.stdout or "").strip(),
        (result.stderr or "").strip(),
    )


def check_omapi_enabled(device_id: str) -> tuple[bool, str]:
    """
    检查测试机是否已打开 OMAPI（secure_element HAL）接口。

    等价于在 PC 上执行::

        adb -s <device_id> shell ls /vendor/bin/hw | findstr secure_element

    若输出中包含 ``android.hardware.secure_element@1.2-service-mediatek``，
    表示该接口已打开。

    返回:
        (是否已打开, 说明信息)
    """
    if not (device_id or "").strip():
        return False, "device_id 为空"

    device_id = device_id.strip()
    try:
        code, stdout, stderr = _run_adb_shell(device_id, "ls", VENDOR_HW_DIR)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"adb 执行失败: {exc}"

    combined = "\n".join(part for part in (stdout, stderr) if part)
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    secure_lines = [line for line in lines if SECURE_ELEMENT_MARKER in line]

    if any(EXPECTED_OMAPI_MTK_SERVICE in line for line in lines):
        return True, f"已发现 {EXPECTED_OMAPI_MTK_SERVICE}，OMAPI 接口已打开"

    if secure_lines:
        joined = "；".join(secure_lines[:3])
        return (
            False,
            f"含 secure_element 服务但未匹配预期 MTK 服务：{joined}",
        )

    if code != 0:
        detail = stderr or stdout or f"ls {VENDOR_HW_DIR} 失败"
        return False, detail

    return False, "未发现 secure_element 相关 HAL 服务，OMAPI 接口未打开"


def _get_project_name(device_id):
    for prop in PROJECT_NAME_PROPS:
        value = _get_prop(device_id, prop)
        if value:
            return value
    return "Unknown"


def normalize_platform(board: str, hw: str, soc: str) -> str:
    """将 getprop 归一为 MTK / 展锐 / 高通 / unknown（与 scripts/init.py 一致）。"""
    blob = f"{board} {hw} {soc}".lower()
    if any(x in blob for x in ("mtk", "mediatek", "mt6")):
        return "MTK"
    if any(x in blob for x in ("unisoc", "sprd", "spreadtrum", "scooter", "ums")):
        return "展锐"
    if any(x in blob for x in ("qcom", "qualcomm", "msm", "sm8", "apq")):
        return "高通"
    return "unknown"


def _get_platform(device_id: str) -> str:
    board = _get_prop(device_id, PLATFORM_PROPS[0])
    hw = _get_prop(device_id, PLATFORM_PROPS[1])
    soc = _get_prop(device_id, PLATFORM_PROPS[2])
    return normalize_platform(board, hw, soc)


def format_project_display(phone: dict) -> str:
    """界面展示：项目名称后附带平台，如 X6886-OP (MTK)。"""
    name = (phone.get("project_name") or "").strip() or "未知项目"
    platform = (phone.get("platform") or "").strip()
    if platform and platform != "unknown":
        return f"{name} ({platform})"
    return name


def get_phone_project_names():
    devices = _list_connected_devices()
    if not devices:
        return []

    return [
        {
            "device_id": device_id,
            "project_name": _get_project_name(device_id),
            "platform": _get_platform(device_id),
        }
        for device_id in devices
    ]

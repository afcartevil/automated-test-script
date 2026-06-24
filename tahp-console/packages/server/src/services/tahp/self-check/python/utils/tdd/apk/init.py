import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

PACKAGE = "com.android.transsion.tdd.autotest"
MAIN_ACTIVITY = f"{PACKAGE}/.MainActivity"
DB_RELATIVE_PATH = "databases/tdd_autotest.db"
SIM_QUERY = (
    "SELECT slot_index,subscription_id,carrier_name,phone_number,display_name,country_iso "
    "FROM sim_info ORDER BY slot_index;"
)

_CAMERA_COUNT_PATTERN = re.compile(
    r"Number\s+of\s+camera\s+devices\s*:\s*(\d+)",
    re.IGNORECASE,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
APK_PATH = Path(__file__).resolve().parent / "app-debug.apk"
TEST_APP_MANIFEST = PROJECT_ROOT / "test_app" / "app" / "src" / "main" / "AndroidManifest.xml"

PERMISSIONS = [
    "android.permission.READ_PHONE_STATE",
    "android.permission.CALL_PHONE",
    "android.permission.READ_CALL_LOG",
    "android.permission.WRITE_CALL_LOG",
    "android.permission.ANSWER_PHONE_CALLS",
    "android.permission.MANAGE_OWN_CALLS",
    "android.permission.READ_PHONE_NUMBERS",
    "android.permission.RECORD_AUDIO",
    "android.permission.CAMERA",
    "android.permission.MODIFY_AUDIO_SETTINGS",
    "android.permission.BLUETOOTH_CONNECT",
    "android.permission.POST_NOTIFICATIONS",
    "android.permission.USE_FULL_SCREEN_INTENT",
    "android.permission.WAKE_LOCK",
    "android.permission.FOREGROUND_SERVICE",
    "android.permission.FOREGROUND_SERVICE_PHONE_CALL",
    "android.permission.CONTROL_INCALL_EXPERIENCE",
    "android.permission.READ_CONTACTS",
    "android.permission.WRITE_CONTACTS",
    "android.permission.SEND_SMS",
    "android.permission.RECEIVE_SMS",
    "android.permission.READ_SMS",
    "android.permission.WRITE_SMS",
    "android.permission.RECEIVE_MMS",
]

# pm grant 仅对危险/特殊权限有效；普通权限与合并生成的 signature 权限跳过
_SKIP_PM_GRANT_PERMISSIONS = frozenset(
    {
        "android.permission.INTERNET",
        "android.permission.ACCESS_NETWORK_STATE",
        "android.permission.WAKE_LOCK",
        "android.permission.FOREGROUND_SERVICE",
    }
)

ROLE_DIALER = "android.app.role.DIALER"
ROLE_SMS = "android.app.role.SMS"


def _run_adb(device_id, args, timeout=60, check=True, text=True):
    cmd = ["adb"]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=text,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        if text:
            stderr = (result.stderr or result.stdout or "").strip()
        else:
            stderr = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or "adb command failed")
    return result


def _install_apk(device_id):
    if not APK_PATH.is_file():
        raise FileNotFoundError(f"APK 不存在: {APK_PATH}")
    _run_adb(device_id, ["install", "-r", str(APK_PATH)], timeout=120)


def _should_grant_permission(permission: str) -> bool:
    if not permission.startswith("android.permission."):
        return False
    if permission in _SKIP_PM_GRANT_PERMISSIONS:
        return False
    if permission.endswith("DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"):
        return False
    return True


def _grant_permissions(device_id):
    for permission in _collect_required_permissions():
        if not _should_grant_permission(permission):
            continue
        _run_adb(
            device_id,
            ["shell", "pm", "grant", PACKAGE, permission],
            check=False,
        )


def _collect_required_permissions():
    permissions = list(PERMISSIONS)
    if TEST_APP_MANIFEST.is_file():
        try:
            root = ET.parse(TEST_APP_MANIFEST).getroot()
            android_ns = "{http://schemas.android.com/apk/res/android}"
            for item in root.findall("uses-permission"):
                name = (item.attrib.get(f"{android_ns}name") or "").strip()
                if name and name not in permissions:
                    permissions.append(name)
        except ET.ParseError:
            pass
    return permissions


def _is_device_locked(device_id):
    trust = _run_adb(device_id, ["shell", "dumpsys", "trust"], check=False)
    trust_text = f"{trust.stdout or ''}\n{trust.stderr or ''}".lower()
    if "devicelocked=true" in trust_text or "devicelocked=1" in trust_text:
        return True

    policy = _run_adb(device_id, ["shell", "dumpsys", "window", "policy"], check=False)
    text = f"{policy.stdout or ''}\n{policy.stderr or ''}".lower()
    lock_markers = (
        "isstatusbarkeyguard=true",
        "mshowinglockscreen=true",
        "keyguardshowing=true",
    )
    return any(marker in text for marker in lock_markers)


def _wake_unlock_and_keep_screen_on(device_id):
    _run_adb(device_id, ["shell", "input", "keyevent", "224"], check=False)  # WAKEUP
    time.sleep(0.3)

    # 多次尝试解锁：菜单键 + 上滑 + dismiss keyguard
    for _ in range(3):
        _run_adb(device_id, ["shell", "input", "keyevent", "82"], check=False)
        _run_adb(device_id, ["shell", "input", "swipe", "540", "1800", "540", "500", "250"], check=False)
        _run_adb(device_id, ["shell", "wm", "dismiss-keyguard"], check=False)
        time.sleep(0.5)
        if not _is_device_locked(device_id):
            break

    if _is_device_locked(device_id):
        raise RuntimeError("设备需要密码/图案解锁，请先手动解锁后再初始化")

    # 固定设置为 30 分钟
    _run_adb(device_id, ["shell", "settings", "put", "system", "screen_off_timeout", "1800000"], check=False)


def _add_role_holder(device_id, role: str) -> bool:
    result = _run_adb(
        device_id,
        ["shell", "cmd", "role", "add-role-holder", role, PACKAGE],
        check=False,
    )
    return result.returncode == 0


def _set_default_dialer(device_id):
    if _add_role_holder(device_id, ROLE_DIALER):
        return
    _run_adb(
        device_id,
        ["shell", "cmd", "telecom", "set-default-dialer", PACKAGE],
        check=False,
    )


def _set_default_sms_app(device_id):
    """接收 SMS_DELIVER / MMS 写库需要默认短信应用角色。"""
    _add_role_holder(device_id, ROLE_SMS)


def _start_main_activity(device_id):
    _run_adb(
        device_id,
        [
            "shell",
            "am",
            "start",
            "-n",
            MAIN_ACTIVITY,
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
        ],
    )


def _u2_verify_and_release(device_id: str) -> bool:
    device = None
    try:
        import uiautomator2 as u2
    except ImportError:
        return False
    try:
        device = u2.connect(device_id)
        device.info
        return True
    except Exception:
        return False
    finally:
        if device is not None:
            try:
                device.stop_uiautomator()
            except Exception:
                pass


def _init_uiautomator2(device_id):
    """安装/启动 uiautomator2 设备端代理，供 UI 自动化 set_text 等能力使用。"""
    try:
        import uiautomator2  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "缺少依赖 uiautomator2，请先在本机执行: pip install uiautomator2"
        ) from exc

    if _u2_verify_and_release(device_id):
        return

    result = subprocess.run(
        [sys.executable, "-m", "uiautomator2", "init", "--serial", device_id],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(detail or "uiautomator2 init 失败")

    if not _u2_verify_and_release(device_id):
        raise RuntimeError("uiautomator2 init 完成但无法连接设备")


def _query_sim_via_sqlite(device_id):
    result = _run_adb(
        device_id,
        [
            "shell",
            "run-as",
            PACKAGE,
            "sqlite3",
            DB_RELATIVE_PATH,
            SIM_QUERY,
        ],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return _parse_sim_output(result.stdout)
    return []


def _query_sim_via_pull(device_id):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        local_db = Path(tmp.name)
    try:
        pull_result = _run_adb(
            device_id,
            [
                "exec-out",
                "run-as",
                PACKAGE,
                "cat",
                DB_RELATIVE_PATH,
            ],
            check=False,
            text=False,
        )
        if pull_result.returncode != 0 or not pull_result.stdout:
            return []
        local_db.write_bytes(pull_result.stdout)
        conn = sqlite3.connect(local_db)
        try:
            cursor = conn.execute(SIM_QUERY)
            rows = cursor.fetchall()
        finally:
            conn.close()
        return [_row_to_record(row) for row in rows]
    finally:
        if local_db.exists():
            local_db.unlink(missing_ok=True)


def _row_to_record(row):
    return {
        "slot_index": int(row[0]),
        "subscription_id": int(row[1]),
        "carrier_name": row[2] or "",
        "phone_number": row[3] or "",
        "display_name": row[4] or "",
        "country_iso": row[5] or "",
    }


def _parse_sim_output(output):
    records = []
    for line in output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        records.append(_row_to_record(parts[:6]))
    return records


def _parse_camera_count_line(text: str) -> Optional[int]:
    match = _CAMERA_COUNT_PATTERN.search(text or "")
    if not match:
        return None
    return int(match.group(1))


def _fetch_camera_count(device_id) -> int:
    """dumpsys media.camera 仅取 Number of camera devices 一行。"""
    result = _run_adb(
        device_id,
        [
            "shell",
            "dumpsys media.camera | grep -m1 -i 'Number of camera devices'",
        ],
        check=False,
        timeout=60,
    )
    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    count = _parse_camera_count_line(combined)
    if count is not None:
        return count

    dump = _run_adb(
        device_id,
        ["shell", "dumpsys", "media.camera"],
        check=False,
        timeout=90,
    )
    for line in (dump.stdout or "").splitlines()[:300]:
        count = _parse_camera_count_line(line)
        if count is not None:
            return count
    return 0


def _fetch_sim_info(device_id, retries=10, interval=2):
    for _ in range(retries):
        records = _query_sim_via_sqlite(device_id)
        if records:
            return records
        records = _query_sim_via_pull(device_id)
        if records:
            return records
        time.sleep(interval)
    return []


def set_default_apps(device_id):
    """将 TDD 测试应用设为默认拨号与短信应用（通信模块用例执行前调用）。"""
    _set_default_dialer(device_id)
    _set_default_sms_app(device_id)


def _iter_test_device_ids(device_info):
    if not device_info:
        return
    for role in ("DUT", "Auxiliary"):
        for entry in device_info.get(role) or []:
            device_id = (entry.get("device_id") or "").strip()
            if device_id and device_id != "Error":
                yield device_id


def set_default_apps_for_test_devices(device_info):
    """为本轮测试涉及的全部设备设置默认拨号/短信应用。"""
    for device_id in _iter_test_device_ids(device_info):
        set_default_apps(device_id)


def init_device(device_id):
    _install_apk(device_id)
    _grant_permissions(device_id)
    _wake_unlock_and_keep_screen_on(device_id)
    _init_uiautomator2(device_id)
    _start_main_activity(device_id)
    time.sleep(3)
    return {
        "sim_cards": _fetch_sim_info(device_id),
        "camera_count": _fetch_camera_count(device_id),
    }


def init(devices):
    sim_info_by_device = {}
    for phone in devices:
        device_id = phone.get("device_id")
        if not device_id or device_id == "Error":
            continue
        sim_info_by_device[device_id] = init_device(device_id)
    return sim_info_by_device

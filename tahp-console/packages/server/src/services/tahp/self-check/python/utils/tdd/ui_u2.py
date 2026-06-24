"""uiautomator2 统一入口：连接池、释放、界面 dump。"""

import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from utils.tdd.ui_paths import device_ui_dir

U2_RELEASE_SETTLE_SECONDS = 0.15
REMOTE_ADB_UI_DUMP = "/sdcard/autotest_ui_dump.xml"

_pool: dict[str, Any] = {}
_pool_lock = threading.Lock()


def _latest_dump_path(device_id: str) -> Path:
    return device_ui_dir(device_id) / "_latest.xml"


def connect_u2(device_id: str) -> Optional[Any]:
    """新建 u2 连接（不写入连接池）。"""
    if not device_id:
        return None
    try:
        import uiautomator2 as u2
    except ImportError:
        return None
    try:
        return u2.connect(device_id)
    except Exception:
        return None


def acquire_u2(device_id: str) -> Optional[Any]:
    """获取设备 u2 连接（同 device_id 复用，避免反复 connect/stop）。"""
    if not device_id:
        return None
    with _pool_lock:
        cached = _pool.get(device_id)
        if cached is not None:
            return cached
    device = connect_u2(device_id)
    if device is None:
        return None
    with _pool_lock:
        _pool[device_id] = device
    return device


def release_uiautomator2(device_id: str, *, wait_ready: bool = False) -> None:
    """释放连接池中的 u2 会话。"""
    with _pool_lock:
        device = _pool.pop(device_id, None)
    if device is not None:
        try:
            device.stop_uiautomator()
        except Exception:
            pass
    if wait_ready and U2_RELEASE_SETTLE_SECONDS > 0:
        time.sleep(U2_RELEASE_SETTLE_SECONDS)


def _run_adb(device_id: str, *args: str, timeout: int = 30):
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def adb_dump_hierarchy_xml(device_id: str) -> Optional[str]:
    """u2 不可用时，通过 adb uiautomator dump 获取界面 XML。"""
    if not device_id:
        return None
    ret = _run_adb(
        device_id,
        "shell",
        "uiautomator",
        "dump",
        REMOTE_ADB_UI_DUMP,
        timeout=30,
    )
    output = f"{ret.stdout or ''}{ret.stderr or ''}"
    if ret.returncode != 0 and "dumped to" not in output.lower():
        return None
    cat = _run_adb(device_id, "shell", "cat", REMOTE_ADB_UI_DUMP, timeout=30)
    xml = (cat.stdout or "").strip()
    if not xml.startswith("<?xml") and "<hierarchy" not in xml:
        return None
    return xml


def dump_hierarchy_xml(
    device_id: str,
    *,
    compressed: bool = True,
    device: Optional[Any] = None,
) -> Optional[str]:
    """dump 当前界面 XML 字符串；u2 失败时回退 adb dump。"""
    own_acquire = device is None
    if own_acquire:
        device = acquire_u2(device_id)
    if device is not None:
        try:
            xml = device.dump_hierarchy(compressed=compressed)
            if xml:
                return xml
        except Exception:
            if own_acquire:
                release_uiautomator2(device_id)
    return adb_dump_hierarchy_xml(device_id)


def dump_current_ui(device_id: str) -> Optional[Path]:
    """dump 当前界面到 result_dir/ui/<device_id>/_latest.xml。"""
    if not device_id:
        return None
    xml = dump_hierarchy_xml(device_id)
    if not xml:
        return None
    try:
        path = _latest_dump_path(device_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(xml, encoding="utf-8")
        return path
    except OSError:
        return None


def click_dialog_positive(device: Any, *, settle_after: float = 0.5) -> bool:
    """在当前 u2 会话内点击弹框确定/保存按钮。"""
    confirm_texts = ("确定", "确认", "OK", "保存", "Save")
    for rid in (
        "com.android.server.telecom:id/btn_positive",
        "com.android.settings:id/btn_positive",
        "android:id/button1",
    ):
        selector = device(resourceId=rid)
        if selector.exists(timeout=0.8):
            selector.click()
            if settle_after > 0:
                time.sleep(settle_after)
            return True
    for kw in confirm_texts:
        selector = device(text=kw)
        if selector.exists(timeout=0.5):
            selector.click()
            if settle_after > 0:
                time.sleep(settle_after)
            return True
    selector = device(resourceIdMatches=".*btn_positive.*")
    if selector.exists(timeout=0.5):
        selector.click()
        if settle_after > 0:
            time.sleep(settle_after)
        return True
    return False

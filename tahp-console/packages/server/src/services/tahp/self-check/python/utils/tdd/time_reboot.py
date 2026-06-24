"""重开机系统时间检查：关自动对时 → 随机设时 → 校验 → 开自动对时 → 重启 → 校验与主机一致。"""

import random
import subprocess
import time
from datetime import datetime, timedelta

from utils.tdd.ui_automatic import _unlock_keyguard_after_wake

ADB_TIMEOUT_SEC = 45
ADB_PROBE_TIMEOUT_SEC = 15
POST_REBOOT_INIT_WAIT_SECONDS = 60.0
REBOOT_POLL_INTERVAL_SECONDS = 5.0
REBOOT_POLL_TIMEOUT_SECONDS = 600
SET_VERIFY_SLOP_SECONDS = 20
POST_SYNC_TOLERANCE_SECONDS = 180


def _run_adb(
    device_id: str,
    *args: str,
    timeout: int = ADB_TIMEOUT_SEC,
) -> tuple[int, str, str]:
    result = subprocess.run(
        ["adb", "-s", device_id, *args],
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


def _run_adb_ok(device_id: str, *args: str, timeout: int = ADB_TIMEOUT_SEC) -> str:
    code, out, err = _run_adb(device_id, *args, timeout=timeout)
    if code != 0:
        raise RuntimeError(err or out or "adb command failed")
    return out


def adb_root(device_id: str) -> None:
    code, out, err = _run_adb(device_id, "root", timeout=ADB_TIMEOUT_SEC)
    combined = f"{out}\n{err}".strip()
    low = combined.lower()
    if "cannot run as root" in low or "adbd cannot run as root" in low:
        raise RuntimeError(f"adb root 不可用: {combined}")
    if code != 0 and "restarting adbd as root" not in low:
        raise RuntimeError(f"adb root 失败 (exit {code}): {combined}")
    time.sleep(3)
    _run_adb(device_id, "wait-for-device", timeout=ADB_TIMEOUT_SEC)
    time.sleep(1)


def set_auto_time(device_id: str, enabled: bool) -> None:
    value = "1" if enabled else "0"
    _run_adb_ok(
        device_id,
        "shell",
        "settings",
        "put",
        "global",
        "auto_time",
        value,
    )


def random_datetime_2000_2025() -> datetime:
    start = datetime(2000, 1, 1, 0, 0, 0)
    end = datetime(2025, 12, 31, 23, 59, 59)
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=random.randint(0, span))


def format_toybox_date(dt: datetime) -> str:
    cc = dt.year // 100
    yy = dt.year % 100
    return f"{dt.month:02d}{dt.day:02d}{dt.hour:02d}{dt.minute:02d}{cc:02d}{yy:02d}.{dt.second:02d}"


def device_unix_ts(device_id: str) -> int:
    out = _run_adb_ok(device_id, "shell", "date", "+%s")
    return int(out.strip())


def device_date_human(device_id: str) -> str:
    return _run_adb_ok(device_id, "shell", "date")


def naive_local_epoch_seconds(dt: datetime) -> int:
    return int(time.mktime(dt.timetuple()))


def set_random_wall_time(
    device_id: str,
    *,
    set_verify_slop_seconds: int = SET_VERIFY_SLOP_SECONDS,
) -> tuple[datetime, int]:
    """随机设时并校验 epoch 偏差，返回 (目标时刻, drift 秒)。"""
    chosen = random_datetime_2000_2025()
    toy = format_toybox_date(chosen)
    _run_adb_ok(device_id, "shell", "date", toy)
    time.sleep(1)
    ts_dev = device_unix_ts(device_id)
    expected_ts = naive_local_epoch_seconds(chosen)
    drift = ts_dev - expected_ts
    if not (-5 <= drift <= set_verify_slop_seconds):
        raise RuntimeError(
            f"随机设时后设备时间与目标偏差 {drift}s"
            f"（允许 [-5, {set_verify_slop_seconds}]），"
            f"设备时间: {device_date_human(device_id)}"
        )
    return chosen, drift


def adb_reboot(device_id: str) -> None:
    code, out, err = _run_adb(device_id, "reboot", timeout=ADB_TIMEOUT_SEC)
    if code != 0:
        raise RuntimeError(err or out or "adb reboot failed")


def wait_for_adb_shell_after_reboot(
    device_id: str,
    *,
    poll_interval_seconds: float = REBOOT_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = REBOOT_POLL_TIMEOUT_SECONDS,
    post_reboot_init_wait_seconds: float = POST_REBOOT_INIT_WAIT_SECONDS,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.monotonic() < deadline:
        code, out, _ = _run_adb(
            device_id,
            "shell",
            "echo",
            "case12_ok",
            timeout=ADB_PROBE_TIMEOUT_SEC,
        )
        if code == 0 and "case12_ok" in out:
            if post_reboot_init_wait_seconds > 0:
                time.sleep(post_reboot_init_wait_seconds)
            if not _unlock_keyguard_after_wake(device_id):
                raise RuntimeError("重启后亮屏/解锁失败")
            return
        time.sleep(poll_interval_seconds)
    raise RuntimeError(
        f"重启后 {timeout_seconds}s 内 adb shell 仍不可用，请检查 USB 与授权"
    )


def verify_device_time_vs_host(
    device_id: str,
    *,
    post_sync_tolerance_seconds: int = POST_SYNC_TOLERANCE_SECONDS,
    post_reboot_ntp_wait_seconds: int = 0,
) -> tuple[int, str]:
    """校验设备时间与主机偏差，返回 (skew 秒, 设备 date 输出)。"""
    if post_reboot_ntp_wait_seconds > 0:
        time.sleep(post_reboot_ntp_wait_seconds)
    human = device_date_human(device_id)
    ts_after = device_unix_ts(device_id)
    host_now = int(time.time())
    skew = abs(ts_after - host_now)
    if skew > post_sync_tolerance_seconds:
        raise RuntimeError(
            f"重启后设备与主机时间偏差 {skew}s（允许 {post_sync_tolerance_seconds}s），"
            f"设备: {human}"
        )
    return skew, human

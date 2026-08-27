"""关闭 Wi‑Fi、打开移动数据后 ping 外网（供 pipeline_adapt/tdd 复用）。"""

from __future__ import annotations

import re
import subprocess
import time

from utils.tdd.carrier_service_dial import pick_preferred_sim
from utils.tdd.ui_automatic import set_mobile_data_enable, set_wifi_enable

DEFAULT_HOSTS = ("www.baidu.com", "www.qq.com")
_PING_RECV_RE = re.compile(r"(\d+)\s+packets?\s+transmitted.*?(\d+)\s+received", re.I | re.S)
_PING_RECV_ALT_RE = re.compile(r"(\d+)\s+received", re.I)


def _adb_shell(device_id: str, command: str, *, timeout: int = 60) -> tuple[int, str]:
    ret = subprocess.run(
        ["adb", "-s", device_id, "shell", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    out = f"{(ret.stdout or '').strip()}\n{(ret.stderr or '').strip()}".strip()
    return ret.returncode, out


def _fallback_set_wifi(device_id: str, enabled: bool) -> bool:
    state = "enabled" if enabled else "disabled"
    code, out = _adb_shell(device_id, f"cmd wifi set-wifi-enabled {state}", timeout=20)
    return code == 0 and "Error" not in out and "Exception" not in out


def _fallback_set_data(device_id: str, enabled: bool) -> bool:
    state = "enable" if enabled else "disable"
    code, out = _adb_shell(device_id, f"cmd phone data {state}", timeout=20)
    return code == 0 and "Error" not in out and "Exception" not in out


def ensure_wifi_off(device_id: str) -> bool:
    if set_wifi_enable(device_id, False, sleep_after=1.0):
        return True
    return _fallback_set_wifi(device_id, False)


def ensure_mobile_data_on(device_id: str) -> bool:
    if set_mobile_data_enable(device_id, True, sleep_after=1.0):
        return True
    return _fallback_set_data(device_id, True)


def ping_host(
    device_id: str,
    host: str,
    *,
    count: int = 4,
    deadline_s: int = 8,
) -> tuple[bool, str]:
    """
    adb shell ping 指定主机。
    成功：至少收到 1 个回复包。
    """
    host = (host or "").strip()
    if not host:
        return False, "主机名为空"
    # -c 发包数；-W 单次超时（秒，部分机型单位为秒）
    cmd = f"ping -c {int(count)} -W {int(deadline_s)} {host}"
    code, out = _adb_shell(device_id, cmd, timeout=max(30, count * deadline_s + 10))
    received = 0
    m = _PING_RECV_RE.search(out or "")
    if m:
        received = int(m.group(2))
    else:
        m2 = _PING_RECV_ALT_RE.search(out or "")
        if m2:
            received = int(m2.group(1))
    ok = received > 0
    summary = f"{host}: received={received}, exit={code}"
    if not ok and out:
        # 截断过长输出
        tail = out.replace("\n", " ")
        if len(tail) > 160:
            tail = tail[:160] + "…"
        summary = f"{summary}; {tail}"
    return ok, summary


def check_mobile_internet(
    device_id: str,
    *,
    hosts: tuple[str, ...] = DEFAULT_HOSTS,
    settle_after_data_s: float = 3.0,
) -> dict:
    """
    关 Wi‑Fi → 开数据 → ping 指定主机。

    返回 status: pass | fail | skip
    """
    choice, detail = pick_preferred_sim(device_id)
    if choice is None and "无法映射" not in detail:
        # 无 SIM 时移动数据通常不可用
        return {
            "status": "skip",
            "message": f"未插入SIM卡，跳过移动数据上网检查（{detail}）",
        }

    if not ensure_wifi_off(device_id):
        return {"status": "fail", "message": "关闭Wi‑Fi失败"}

    if not ensure_mobile_data_on(device_id):
        return {"status": "fail", "message": "打开移动数据失败"}

    if settle_after_data_s > 0:
        time.sleep(settle_after_data_s)

    results: list[str] = []
    failed: list[str] = []
    for host in hosts:
        ok, summary = ping_host(device_id, host)
        results.append(summary)
        if not ok:
            failed.append(host)

    sim_hint = ""
    if choice is not None:
        sim_hint = f"{choice.slot_label} {choice.carrier}; "
    if failed:
        return {
            "status": "fail",
            "message": f"{sim_hint}ping失败: {', '.join(failed)}; " + " | ".join(results),
        }
    return {
        "status": "pass",
        "message": f"{sim_hint}" + " | ".join(results),
    }

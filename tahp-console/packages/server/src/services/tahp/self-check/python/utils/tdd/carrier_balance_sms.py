"""向运营商服务号发短信并等待回复，用于验证短信收发能力。

供 pipeline_adapt/tdd「检查收发短信」用例复用。指令选用各运营商常用查询短码
（如 CXYE/101）作为可稳定触发回复的探针，用例目标是收发能力而非查话费结果。
走系统短信应用 SENDTO + 点击发送，通过 content://sms 确认已发送且收到回复。
"""

from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from utils.tdd.carrier_service_dial import (
    SimCarrierChoice,
    _force_dismiss_lockscreen,
    pick_preferred_sim,
)
from utils.tdd.ui_automatic import dump_current_ui, ensure_screen_on_and_unlocked
from utils.tdd.ui_xml import parse_bounds_center

# 可稳定触发运营商回复的短信探针：运营商 → (发送号码, 指令)
_BALANCE_SMS: dict[str, tuple[str, str]] = {
    "中国移动": ("10086", "CXYE"),
    "中国联通": ("10010", "CXYE"),
    "中国电信": ("10001", "101"),
}

_MSG_PKG = "com.transsion.smartmessage"
_RID_COMPOSE = f"{_MSG_PKG}:id/compose_message_text"
_RID_SEND = f"{_MSG_PKG}:id/send_message_ibtn"
_RID_TITLE = f"{_MSG_PKG}:id/conversation_title"
_RID_SIM_ICON = f"{_MSG_PKG}:id/sim_icon"


@dataclass(frozen=True)
class BalanceSmsPlan:
    choice: SimCarrierChoice
    to_number: str
    body: str

    @property
    def detail(self) -> str:
        c = self.choice
        return (
            f"{c.slot_label} {c.carrier}({c.numeric or c.alpha}) "
            f"短信 {self.to_number}「{self.body}」"
        )


def _adb_shell(device_id: str, command: str, *, timeout: int = 30) -> str:
    ret = subprocess.run(
        ["adb", "-s", device_id, "shell", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    out = (ret.stdout or "").strip()
    return out or (ret.stderr or "").strip()


def _adb_run(device_id: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def resolve_balance_sms(carrier: str) -> Optional[tuple[str, str]]:
    return _BALANCE_SMS.get((carrier or "").strip())


def plan_balance_sms(device_id: str) -> tuple[Optional[BalanceSmsPlan], str]:
    choice, detail = pick_preferred_sim(device_id)
    if choice is None:
        return None, detail
    mapped = resolve_balance_sms(choice.carrier)
    if not mapped:
        return None, f"{choice.slot_label} {choice.carrier} 无短信收发探针映射"
    to_number, body = mapped
    plan = BalanceSmsPlan(choice=choice, to_number=to_number, body=body)
    return plan, plan.detail


def _tap_bounds(device_id: str, bounds: str) -> bool:
    if not bounds:
        return False
    try:
        cx, cy = parse_bounds_center(bounds)
    except ValueError:
        return False
    ret = _adb_run(device_id, "shell", "input", "tap", str(cx), str(cy), timeout=8)
    return ret.returncode == 0


def _find_node(
    root: ET.Element,
    *,
    resource_id: str = "",
    desc_equals: tuple[str, ...] = (),
    text_equals: tuple[str, ...] = (),
) -> Optional[ET.Element]:
    for el in root.iter("node"):
        rid = el.attrib.get("resource-id") or ""
        text = (el.attrib.get("text") or "").strip()
        desc = (el.attrib.get("content-desc") or "").strip()
        if resource_id and rid == resource_id:
            return el
        if desc_equals and desc in desc_equals:
            return el
        if text_equals and text in text_equals:
            return el
    return None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_sms_rows(raw: str) -> list[dict]:
    """解析 content query 输出为 [{id,address,date,type,body}, ...]。"""
    rows: list[dict] = []
    for block in re.split(r"\n(?=Row:\s*\d+)", raw or ""):
        block = block.strip()
        if not block.startswith("Row:"):
            continue
        m = re.search(
            r"_id=(\d+)\s*,\s*address=([^,]*),\s*date=(\d+)\s*,\s*type=(\d+)\s*,\s*body=(.*)$",
            block,
            re.S,
        )
        if not m:
            # inbox-only projection without type
            m2 = re.search(
                r"_id=(\d+)\s*,\s*address=([^,]*),\s*date=(\d+)\s*,\s*body=(.*)$",
                block,
                re.S,
            )
            if not m2:
                continue
            rows.append(
                {
                    "id": int(m2.group(1)),
                    "address": (m2.group(2) or "").strip(),
                    "date": int(m2.group(3)),
                    "type": 1,
                    "body": (m2.group(4) or "").strip(),
                }
            )
            continue
        rows.append(
            {
                "id": int(m.group(1)),
                "address": (m.group(2) or "").strip(),
                "date": int(m.group(3)),
                "type": int(m.group(4)),
                "body": (m.group(5) or "").strip(),
            }
        )
    return rows


def query_sms(device_id: str) -> list[dict]:
    raw = _adb_shell(
        device_id,
        "content query --uri content://sms "
        "--projection _id:address:date:type:body "
        "--sort 'date DESC'",
        timeout=20,
    )
    return _parse_sms_rows(raw)


def _addr_matches_service(address: str, service_number: str) -> bool:
    addr = re.sub(r"\D", "", address or "")
    svc = re.sub(r"\D", "", service_number or "")
    if not addr or not svc:
        return False
    return addr == svc or addr.startswith(svc) or svc.startswith(addr)


def _best_effort_set_sms_slot(device_id: str, slot: int) -> None:
    sub_id = slot + 1
    _adb_shell(device_id, f"settings put global multi_sim_sms {sub_id}")
    time.sleep(0.3)


def _open_compose(device_id: str, to_number: str, body: str) -> bool:
    _force_dismiss_lockscreen(device_id)
    _adb_run(device_id, "shell", "input", "keyevent", "KEYCODE_HOME", timeout=8)
    time.sleep(0.3)
    _adb_run(device_id, "shell", "am", "force-stop", _MSG_PKG, timeout=10)
    time.sleep(0.4)
    # 用 am start 传 sms_body；正文尽量短，避免 shell 转义问题
    ret = _adb_run(
        device_id,
        "shell",
        "am",
        "start",
        "-a",
        "android.intent.action.SENDTO",
        "-d",
        f"sms:{to_number}",
        "--es",
        "sms_body",
        body,
        timeout=20,
    )
    out = f"{ret.stdout or ''}{ret.stderr or ''}"
    if ret.returncode != 0 or "Error" in out or "Exception" in out:
        return False
    time.sleep(2.0)

    deadline = time.time() + 12.0
    while time.time() < deadline:
        xml = dump_current_ui(device_id)
        if not xml:
            time.sleep(0.4)
            continue
        root = ET.parse(xml).getroot()
        title = _find_node(root, resource_id=_RID_TITLE)
        compose = _find_node(root, resource_id=_RID_COMPOSE)
        send_btn = _find_node(root, resource_id=_RID_SEND) or _find_node(
            root, desc_equals=("发送", "Send")
        )
        title_ok = True
        if title is not None:
            shown = re.sub(r"\D", "", title.attrib.get("text") or "")
            title_ok = to_number in shown or shown.endswith(to_number)
        body_ok = False
        if compose is not None:
            body_ok = body in ((compose.attrib.get("text") or "").strip())
        if send_btn is not None and title_ok and (body_ok or compose is not None):
            # 正文偶发未预填时补输
            if compose is not None and not body_ok:
                _tap_bounds(device_id, compose.attrib.get("bounds") or "")
                time.sleep(0.2)
                _adb_run(device_id, "shell", "input", "text", body, timeout=10)
                time.sleep(0.4)
            return True
        time.sleep(0.4)
    return False


def _tap_send(device_id: str) -> bool:
    xml = dump_current_ui(device_id)
    if not xml:
        return False
    root = ET.parse(xml).getroot()
    send_btn = _find_node(root, resource_id=_RID_SEND) or _find_node(
        root, desc_equals=("发送", "Send")
    )
    if send_btn is None:
        return False
    return _tap_bounds(device_id, send_btn.attrib.get("bounds") or "")


def _maybe_pick_sim(device_id: str, choice: SimCarrierChoice) -> None:
    """若弹出选卡，尽量点目标卡/运营商。"""
    time.sleep(0.6)
    xml = dump_current_ui(device_id)
    if not xml:
        return
    root = ET.parse(xml).getroot()
    # 已回到会话且发送按钮旁无选卡对话框时跳过
    labels = (
        choice.slot_label,
        f"SIM{choice.slot + 1}",
        choice.carrier,
        choice.alpha,
    )
    for label in labels:
        if not label:
            continue
        for el in root.iter("node"):
            text = (el.attrib.get("text") or "").strip()
            desc = (el.attrib.get("content-desc") or "").strip()
            if label in text or label in desc:
                if _tap_bounds(device_id, el.attrib.get("bounds") or ""):
                    time.sleep(0.5)
                    return


def find_sent_after(
    messages: list[dict],
    *,
    to_number: str,
    body: str,
    since_ms: int,
) -> Optional[dict]:
    body_norm = (body or "").strip().upper()
    candidates: list[dict] = []
    for msg in messages:
        if msg.get("type") != 2:  # Telephony.Sms.MESSAGE_TYPE_SENT
            continue
        if int(msg.get("date") or 0) < since_ms - 2000:
            continue
        if not _addr_matches_service(str(msg.get("address") or ""), to_number):
            continue
        candidates.append(msg)

    for msg in candidates:
        msg_body = (msg.get("body") or "").strip().upper()
        if not body_norm or body_norm in msg_body or msg_body == body_norm:
            return msg
    return candidates[0] if candidates else None


def find_reply_after(
    messages: list[dict],
    *,
    service_number: str,
    since_ms: int,
) -> Optional[dict]:
    for msg in messages:
        if msg.get("type") != 1:  # inbox
            continue
        if int(msg.get("date") or 0) < since_ms - 1000:
            continue
        if not _addr_matches_service(str(msg.get("address") or ""), service_number):
            continue
        if (msg.get("body") or "").strip():
            return msg
    return None


def query_balance_via_sms(
    device_id: str,
    *,
    result_dir=None,
    reply_timeout_s: float = 90.0,
) -> dict:
    """
    发送探针短信并等待运营商回复，用于验证短信收发。

    返回 dict: status(pass|fail|skip), message
    """
    if result_dir:
        from utils.tdd.ui_paths import set_ui_result_dir

        set_ui_result_dir(result_dir)

    plan, detail = plan_balance_sms(device_id)
    if plan is None:
        if "无法映射" in detail or "无短信收发" in detail:
            return {"status": "fail", "message": detail}
        return {
            "status": "skip",
            "message": f"未插入SIM卡，跳过短信收发检查（{detail}）",
        }

    ensure_screen_on_and_unlocked(device_id)
    _force_dismiss_lockscreen(device_id)
    _best_effort_set_sms_slot(device_id, plan.choice.slot)

    since_ms = _now_ms()
    if not _open_compose(device_id, plan.to_number, plan.body):
        return {
            "status": "fail",
            "message": f"打开短信编辑页失败: {detail}",
        }

    if not _tap_send(device_id):
        return {
            "status": "fail",
            "message": f"点击发送失败: {detail}",
        }
    _maybe_pick_sim(device_id, plan.choice)
    # 选卡后可能还要再点一次发送
    time.sleep(0.8)
    xml = dump_current_ui(device_id)
    if xml:
        root = ET.parse(xml).getroot()
        compose = _find_node(root, resource_id=_RID_COMPOSE)
        if compose is not None and plan.body in ((compose.attrib.get("text") or "")):
            _tap_send(device_id)

    sent = None
    reply = None
    deadline = time.time() + reply_timeout_s
    while time.time() < deadline:
        messages = query_sms(device_id)
        if sent is None:
            sent = find_sent_after(
                messages,
                to_number=plan.to_number,
                body=plan.body,
                since_ms=since_ms,
            )
        if sent is not None:
            reply = find_reply_after(
                messages,
                service_number=plan.to_number,
                since_ms=since_ms,
            )
            if reply is not None:
                preview = (reply.get("body") or "").replace("\n", " ")
                if len(preview) > 80:
                    preview = preview[:80] + "…"
                return {
                    "status": "pass",
                    "message": (
                        f"已发送并收到回复: {detail}; "
                        f"回复号码={reply.get('address')}; {preview}"
                    ),
                }
        time.sleep(2.0)

    if sent is None:
        return {
            "status": "fail",
            "message": f"短信发送未确认成功: {detail}",
        }
    return {
        "status": "fail",
        "message": f"短信已发送但未收到运营商回复({int(reply_timeout_s)}s): {detail}",
    }

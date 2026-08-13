"""解析功耗/续航 JIRA 描述中的 Precondition / Test Result 等结构化区块。"""
from __future__ import annotations

import re
from typing import Any

# 区块标题（中英文混排，忽略大小写与冒号后空格）
_SECTION_HEADERS = (
    ("precondition", r"Precondition"),
    ("environment", r"Environment"),
    ("operation_steps", r"Operation\s*Steps?"),
    ("expect_result", r"Expect\s*Result"),
    ("test_result", r"Test\s*Result"),
    ("ref_phone_results", r"Ref\s*Phone\s*Results?(?:\s*If\s*Needed)?"),
    ("risk", r"Risk"),
    ("log_address", r"Log\s*And\s*Screenshot\s*Address"),
    ("recovery_technique", r"Recovery\s*Technique"),
    ("problem_time", r"Problem\s*Time"),
    ("creator", r"Creator"),
    ("others", r"Others"),
)

_HEADER_RE = re.compile(
    r"(?im)^\s*(?:"
    + "|".join(f"(?P<{name}>{pat})" for name, pat in _SECTION_HEADERS)
    + r")\s*:\s*(?P<_inline>.*)$"
)

_MA_RE = re.compile(
    r"(?P<label>[^\d\n]{0,24}?)(?P<val>\d+(?:\.\d+)?)\s*mA",
    re.IGNORECASE,
)
_DELTA_RE = re.compile(
    r"(?:超出|偏高|差|差值|delta)\s*(?P<val>\d+(?:\.\d+)?)\s*mA",
    re.IGNORECASE,
)
_COMPARE_RE = re.compile(
    r"(?:对比|对照|竞品|对比机|内部竞品)\s*(?P<model>[A-Za-z][A-Za-z0-9\-]*)"
    r"[^\d]{0,24}?(?:功耗)?\s*(?P<val>\d+(?:\.\d+)?)\s*mA",
    re.IGNORECASE,
)
_DUT_POWER_RE = re.compile(
    r"(?:功耗|电流|平均电流)\s*(?P<val>\d+(?:\.\d+)?)\s*mA"
    r"|(?P<val2>\d+(?:\.\d+)?)\s*mA.*?对比",
    re.IGNORECASE,
)
_MODEL_TOKEN_RE = re.compile(r"\b([A-Z]{1,3}\d{3,5}[A-Z0-9]*)\b")
_EXPECT_MARGIN_RE = re.compile(
    r"[+＋]\s*(?P<val>\d+(?:\.\d+)?)\s*mA",
    re.IGNORECASE,
)
_UNC_RE = re.compile(r"\\\\[^\s\\]+(?:\\[^\s\\]+)+")
_LIST_ITEM_RE = re.compile(r"(?m)^\s*(?:\d+[\.\)、]|[-*•])\s*(.+?)\s*$")


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # 全角冒号
    t = t.replace("：", ":")
    return t


def _split_sections(description: str) -> dict[str, str]:
    text = _normalize_text(description)
    if not text.strip():
        return {}
    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        return {"raw": text.strip()}

    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = next(k for k, v in m.groupdict().items() if v and k != "_inline")
        start = m.end()
        inline = (m.group("_inline") or "").strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if inline:
            body = f"{inline}\n{body}".strip() if body else inline
        sections[name] = body
    return sections


def _parse_list_items(block: str) -> list[str]:
    if not block or block.strip() in {"/", "-", "无", "N/A", "n/a"}:
        return []
    items = [m.group(1).strip() for m in _LIST_ITEM_RE.finditer(block)]
    if items:
        # 备注行（非编号）附到末尾
        rem = _LIST_ITEM_RE.sub("", block).strip()
        for line in rem.split("\n"):
            line = line.strip()
            if line.startswith("备注") or line.startswith("Remark"):
                items.append(line)
        return items
    # 无编号：按行切
    lines = [ln.strip() for ln in block.split("\n") if ln.strip() and ln.strip() != "/"]
    return lines


def _first_ma_after(keywords: tuple[str, ...], text: str) -> float | None:
    low = text.lower()
    for kw in keywords:
        idx = low.find(kw.lower())
        if idx < 0:
            continue
        m = re.search(r"(\d+(?:\.\d+)?)\s*mA", text[idx : idx + 80], re.I)
        if m:
            return float(m.group(1))
    return None


def _extract_power_numbers(blob: str) -> dict[str, float | None]:
    test_ma = _first_ma_after(("功耗", "玩游戏", "测试机", "本机"), blob)
    competitor_ma: float | None = None
    delta_ma: float | None = None

    m_cmp = _COMPARE_RE.search(blob)
    if m_cmp:
        competitor_ma = float(m_cmp.group("val"))
        before = blob[: m_cmp.start()]
        all_before = list(re.finditer(r"(\d+(?:\.\d+)?)\s*mA", before, re.I))
        if all_before:
            test_ma = float(all_before[-1].group(1))

    m_delta = _DELTA_RE.search(blob)
    if m_delta:
        delta_ma = float(m_delta.group("val"))

    if test_ma is None:
        # 摘要常见：...功耗770.49mA，对比...
        m = re.search(
            r"功耗\s*(\d+(?:\.\d+)?)\s*mA",
            blob,
            re.I,
        )
        if m:
            test_ma = float(m.group(1))

    if test_ma is not None and competitor_ma is not None and delta_ma is None:
        delta_ma = round(test_ma - competitor_ma, 2)

    return {
        "test_power_ma": test_ma,
        "competitor_power_ma": competitor_ma,
        "delta_power_ma": delta_ma,
    }


def _extract_models(
    summary: str,
    description: str,
    affect_project: str | None,
    others: str,
    test_result: str,
) -> dict[str, str | None]:
    blob = "\n".join([summary or "", description or "", others or "", test_result or ""])
    dut = (affect_project or "").strip() or None
    competitor: str | None = None

    m = re.search(
        r"(?:对比|对照|竞品|内部竞品)\s*([A-Za-z][A-Za-z0-9\-]*)",
        blob,
        re.I,
    )
    if m:
        competitor = m.group(1).strip()

    # Others: "CN6 8+256 X6887 8+256"
    models = _MODEL_TOKEN_RE.findall(others or "")
    if models:
        if not dut:
            dut = models[0]
        if not competitor and len(models) >= 2:
            competitor = models[1]

    # summary tags 【CN6】
    if not dut:
        m2 = re.search(r"【\s*([A-Z0-9]{3,})\s*】", summary or "")
        if m2:
            dut = m2.group(1)

    return {"dut_model": dut, "competitor_model": competitor}


def _detect_test_case(summary: str, description: str) -> str:
    blob = f"{summary}\n{description}"
    if re.search(r"NPS|最大亮度|最大音量|差评模型", blob, re.I):
        return "nps"
    if re.search(r"基础场景|350\s*nit|72\s*dB", blob, re.I):
        return "basic"
    return "unknown"


def _detect_game(blob: str) -> dict[str, str | None]:
    title = None
    for name, pat in (
        ("PUBG", r"PUBG|和平精英|绝地求生"),
        ("MLBB", r"MLBB|Mobile\s*Legends|莫比"),
        ("Genshin", r"原神|Genshin"),
        ("HonorOfKings", r"王者荣耀|HoK|Honor\s*of\s*Kings"),
    ):
        if re.search(pat, blob, re.I):
            title = name
            break
    speaker = None
    if re.search(r"外放|扬声器|speaker", blob, re.I):
        speaker = "外放"
    elif re.search(r"耳机|headset", blob, re.I):
        speaker = "耳机"
    return {"game_title": title, "speaker_mode": speaker}


def _bool_from_text(blob: str, patterns: tuple[str, ...]) -> bool | None:
    if any(re.search(p, blob, re.I) for p in patterns):
        return True
    return None


def _derive_from_preconditions(items: list[str], steps: list[str]) -> dict[str, Any]:
    pre = "\n".join(items)
    step = "\n".join(steps)
    blob = pre + "\n" + step

    brightness = "max" if re.search(r"亮度.*最大|最大亮度", blob) else None
    volume = "max" if re.search(r"音量.*最大|最大音量", blob) else None
    refresh = "max" if re.search(r"刷新率.*最高|最高档", blob) else None

    network: dict[str, Any] = {}
    if re.search(r"WIFI\s*强|Wi-?Fi\s*强|强网|强信号", blob, re.I):
        network["wifi"] = "strong"
    elif re.search(r"WIFI|Wi-?Fi", blob, re.I):
        network["wifi"] = "on"
    if re.search(r"关闭数据流量|关闭流量|关掉数据|数据流量\s*关闭", blob):
        network["mobile_data"] = False
    elif re.search(r"开启数据流量|打开数据流量|开启流量|数据流量", blob):
        network["mobile_data"] = True
    m_car = re.search(r"(联通|移动|电信)", blob)
    if m_car:
        network["carrier"] = m_car.group(1)
    m_slot = re.search(r"卡槽\s*([12])|卡\s*([12])\s*(?:插入|放|装)", blob)
    if m_slot:
        network["sim_slot"] = int(m_slot.group(1) or m_slot.group(2))
    elif re.search(r"插入.*(?:联通|移动|电信|数据卡)|(?:联通|移动|电信|数据卡).*插入", blob):
        network["sim_slot"] = 1

    switches = {
        "usb_debug": _bool_from_text(blob, (r"usb\s*debug|USB\s*调试",)),
        "gps": _bool_from_text(blob, (r"GPS|定位",)),
        "nfc": _bool_from_text(blob, (r"NFC",)),
        "bluetooth": _bool_from_text(blob, (r"蓝牙|Bluetooth|BT\b",)),
    }
    switches = {k: v for k, v in switches.items() if v is not None}

    logs_required: list[str] = []
    if re.search(r"mobile\s*log", blob, re.I):
        logs_required.append("mobile_log")
    if re.search(r"net\s*log|network\s*log", blob, re.I):
        logs_required.append("net_log")

    game_play: dict[str, Any] = {}
    m_mode = re.search(r"经典模式|排位|匹配|娱乐模式", step)
    if m_mode:
        game_play["mode"] = m_mode.group(0)
    m_map = re.search(r"绝地海岛|海岛|地图[：:]\s*([^\s,，]+)", step)
    if m_map:
        game_play["map"] = m_map.group(0) if "绝地" in m_map.group(0) or "海岛" in m_map.group(0) else m_map.group(1)
    if re.search(r"组队", step):
        game_play["team"] = True
    if re.search(r"帧率最高|画质最高|最高配置", blob):
        game_play["graphics"] = "max_fps_quality"

    return {
        "brightness": brightness,
        "volume": volume,
        "refresh_rate": refresh,
        "network": network or None,
        "switches": switches or None,
        "logs_required": logs_required or None,
        "game_play": game_play or None,
        "clear_background": bool(re.search(r"清理所有后台|清后台", blob)),
    }


def parse_jira_testcase(
    *,
    description: str,
    summary: str = "",
    affect_project: str | None = None,
    jira_key: str | None = None,
) -> dict[str, Any]:
    """主入口：返回 sections + derived。"""
    sections_raw = _split_sections(description or "")
    precondition = _parse_list_items(sections_raw.get("precondition", ""))
    operation_steps = _parse_list_items(sections_raw.get("operation_steps", ""))

    sections: dict[str, Any] = {
        "precondition": precondition,
        "environment": (sections_raw.get("environment") or "").strip() or None,
        "operation_steps": operation_steps,
        "expect_result": (sections_raw.get("expect_result") or "").strip() or None,
        "test_result": (sections_raw.get("test_result") or "").strip() or None,
        "ref_phone_results": (sections_raw.get("ref_phone_results") or "").strip() or None,
        "risk": (sections_raw.get("risk") or "").strip() or None,
        "log_address": (sections_raw.get("log_address") or "").strip() or None,
        "recovery_technique": (sections_raw.get("recovery_technique") or "").strip() or None,
        "problem_time": (sections_raw.get("problem_time") or "").strip() or None,
        "creator": (sections_raw.get("creator") or "").strip() or None,
        "others": (sections_raw.get("others") or "").strip() or None,
    }

    power_blob = "\n".join(
        [
            summary or "",
            sections.get("test_result") or "",
            description or "",
        ]
    )
    powers = _extract_power_numbers(power_blob)
    models = _extract_models(
        summary,
        description or "",
        affect_project,
        sections.get("others") or "",
        sections.get("test_result") or "",
    )
    game = _detect_game(power_blob)
    pre_derived = _derive_from_preconditions(precondition, operation_steps)

    expect = sections.get("expect_result") or ""
    expect_margin = None
    m_exp = _EXPECT_MARGIN_RE.search(expect)
    if m_exp:
        expect_margin = float(m_exp.group("val"))

    smb = None
    log_addr = sections.get("log_address") or ""
    m_unc = _UNC_RE.search(log_addr.replace("/", "\\"))
    if m_unc:
        smb = m_unc.group(0)
    elif log_addr.strip() and log_addr.strip() != "/":
        smb = log_addr.strip()

    # 版本：Others 中 X6887版本：...
    competitor_version = None
    others = sections.get("others") or ""
    m_ver = re.search(
        r"(?:X\d+|竞品|对比机)?\s*版本\s*[：:]\s*([^\n]+)",
        others,
        re.I,
    )
    if m_ver:
        competitor_version = m_ver.group(1).strip()

    derived: dict[str, Any] = {
        **powers,
        **models,
        **game,
        "test_case": _detect_test_case(summary, description or ""),
        "expect_margin_ma": expect_margin,
        "smb_log_path": smb,
        "competitor_version": competitor_version,
        **{k: v for k, v in pre_derived.items() if v is not None},
    }

    return {
        "skill": "base_jira_testcase_parse",
        "status": "ok" if (precondition or sections.get("test_result") or powers.get("test_power_ma")) else "empty",
        "jira_key": jira_key,
        "summary": summary or None,
        "affect_project": affect_project,
        "sections": sections,
        "derived": derived,
    }


# CN6OS16-2121 样例（自检）
SAMPLE_CN6OS16_2121_DESCRIPTION = (
    "Precondition: \n"
    " 1.更新所有google商店应用\n"
    " 2.卡槽1插入1张联通数据卡，开启数据流量\n"
    " 3.手机开启usb debug，打开GPS/NFC/蓝牙开关\n"
    " 4.测试过程需要打开并记录mobile log和Net log\n"
    " 5.屏幕亮度调至最大，音量等级调至最大，屏幕刷新率调整到项目支持的最高档位、"
    "WIFI强信号（游戏使用强网测试）、游戏最高配置（优先帧率最高 + 画质最高）\n"
    " 6.测试前清理所有后台应用\n"
    " 备注：涉及到外发/大版本升级需要先刷基础版本，导入安装测试资源，OTA升级到目标版本后开展测试\n"
    " Environment: /\n"
    " Operation Steps:\n"
    " 1.打开WIFI链接外网，配置设置完成后重启进入游戏，选择经典模式--绝地海岛地图-组队"
    "(测试机和辅助机走相同路线)，进入后，跳伞落地后，使用整机及kite工具测试开始获取并记录一局游戏平均电流。 \n"
    " Expect Result: \n"
    " ≤产品定义的质量标杆机+20mA\n"
    " Test Result: \n"
    " PUBG外放玩游戏功耗770.49mA，对比内部竞品X6887功耗715.6mA，超出54.89mA，请分析\n"
    " Ref Phone Results If Needed: /\n"
    " Risk: 5/5\n"
    " Log And Screenshot Address: \\\\10.207.190.10\\sw_log\\快温省\\性能功耗\\wangchao\\CN6\\差评模型PUBG\n"
    " Recovery Technique: /\n"
    " Problem Time: 2026/6/26\n"
    " Creator: chao.wang13\n"
    " Others: CN6 8+256 X6887 8+256\n"
    " X6887版本：X6887-16.2.0.145SP07(OP004PF001AZ)"
)

SAMPLE_CN6OS16_2121_SUMMARY = (
    "【交付二部】【续航温升】【功耗】【CN6】【STR4A】【PR2-3】【用户场景模型】【NPS差评模型】"
    "PUBG外放玩游戏功耗770.49mA，对比内部竞品X6887功耗715.6mA，超出54.89mA，请分析"
)


def self_check() -> None:
    result = parse_jira_testcase(
        description=SAMPLE_CN6OS16_2121_DESCRIPTION,
        summary=SAMPLE_CN6OS16_2121_SUMMARY,
        affect_project="CN6",
        jira_key="CN6OS16-2121",
    )
    d = result["derived"]
    assert len(result["sections"]["precondition"]) >= 6, result["sections"]["precondition"]
    assert d["test_power_ma"] == 770.49, d
    assert d["competitor_power_ma"] == 715.6, d
    assert d["delta_power_ma"] == 54.89, d
    assert d["competitor_model"] == "X6887", d
    assert d["dut_model"] == "CN6", d
    assert d["game_title"] == "PUBG", d
    assert d["test_case"] == "nps", d
    assert d["brightness"] == "max", d
    assert d["expect_margin_ma"] == 20.0, d
    assert d.get("smb_log_path") and "10.207.190.10" in d["smb_log_path"], d
    assert "mobile_log" in (d.get("logs_required") or []), d

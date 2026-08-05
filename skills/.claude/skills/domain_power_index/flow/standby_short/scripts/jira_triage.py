"""flow_power_standby_short 专用：从 JIRA 文本推断 standby_type 与功耗阈值。

短待机 flow 仅使用 ``standby_type``；电流等级由 §1 ``Stdby_Curr``（60/70 mA）判定，
勿将输出的 ``threshold_ma``（25/30，与长待机 batteryinfo 对齐）用于短待机等级。
"""
from __future__ import annotations

import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_LIB = os.path.abspath(
    os.path.join(_SCRIPT_DIR, "..", "..", "..", "..", "..", "base", "lib")
)
if _BASE_LIB not in sys.path:
    sys.path.insert(0, _BASE_LIB)


def _setup_utf8_stdio() -> None:
    """统一脚本标准输入输出编码为 UTF-8，减少 Windows 终端乱码。"""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def infer_standby_type(summary: str = "", description: str = "") -> str:
    """从 JIRA summary/description 推断 WIFI 或 DATA 待机类型。

    优先级（由高到低）：
    1. summary 中的显式标记（SIM complex / wifi standby）
    2. description 中「Operate Steps / Precondition」段落（操作步骤优先于测试结果）
    3. description 全文中的开关状态（可能被测试结果段的笔误误导）
    4. 默认 DATA
    """
    summary_lower = (summary or "").lower()
    desc_lower = (description or "").lower()

    # 优先级 1：summary 中的显式标记
    if re.search(r"sim complex|sim standby|sim card complex", summary_lower, re.I):
        return "DATA"
    if re.search(r"wifi standby|wi-fi standby|wifi complex", summary_lower, re.I):
        return "WIFI"

    # 优先级 2：提取 Operate Steps / Precondition 段落（不含 Test result）
    # 测试人员常在 Test result 段写反开关状态，应以操作步骤为准
    operate_text = _extract_operate_section(description)
    if operate_text:
        op_lower = operate_text.lower()
        if re.search(
            r"mobile data on.{0,40}wifi off|wifi off.{0,40}mobile data on|"
            r"turn on mobile data|turn off wifi|"
            r"移动数据.{0,8}开.{0,20}wifi.{0,8}关|数据开.{0,20}wifi关",
            op_lower, re.I | re.S,
        ):
            return "DATA"
        if re.search(
            r"wifi on.{0,40}mobile data off|mobile data off.{0,40}wifi on|"
            r"turn on wifi|turn off mobile data|"
            r"wifi.{0,8}开.{0,20}移动数据.{0,8}关|wifi开.{0,20}数据关",
            op_lower, re.I | re.S,
        ):
            return "WIFI"

    # 优先级 3：全文匹配（可能被测试结果段误导，但仍作为回退）
    full_text = f"{summary_lower}\n{desc_lower}"
    if re.search(
        r"mobile data on.{0,40}wifi off|wifi off.{0,40}mobile data on|"
        r"turn on mobile data|turn off wifi|"
        r"移动数据.{0,8}开.{0,20}wifi.{0,8}关|数据开.{0,20}wifi关",
        full_text, re.I | re.S,
    ):
        return "DATA"
    if re.search(
        r"wifi on.{0,40}mobile data off|mobile data off.{0,40}wifi on|"
        r"turn on wifi|turn off mobile data|"
        r"wifi.{0,8}开.{0,20}移动数据.{0,8}关|wifi开.{0,20}数据关",
        full_text, re.I | re.S,
    ):
        return "WIFI"

    # 优先级 4：SIM / 运营商 / 蜂窝关键词
    if re.search(r"蜂窝|mobile data|data on|smartfren|safaricom|indosat|airtel|jio|vodafone", full_text, re.I):
        return "DATA"

    return "DATA"


def _extract_operate_section(description: str) -> str:
    """提取 description 中的操作步骤段落（Operate Steps / Preconditions），排除 Test result。

    测试人员在 Test result 段常写反开关状态，操作步骤才是实际测试设置。
    """
    if not description:
        return ""
    parts: list[str] = []
    in_operate = False
    for line in description.splitlines():
        lower = line.strip().lower()
        # 开始标记
        if re.search(r"(operate steps|precondition|前置条件|操作步骤|测试步骤)", lower):
            in_operate = True
            parts.append(line)
            continue
        # 结束标记：Test result / Expected result / Note 等
        if in_operate and re.search(
            r"(test result|测试结果|expected result|预期结果|note|备注|submitter|概率)",
            lower,
        ):
            break
        if in_operate:
            parts.append(line)
    return "\n".join(parts)


def flow_threshold_ma(standby_type: str = "DATA") -> float:
    """待机电流标准：WIFI 25 mA，DATA 30 mA（与长待机 batteryinfo 对齐；短待机 flow 勿用）。"""
    return 25.0 if standby_type.upper() == "WIFI" else 30.0


def parse_standby_threshold_ma(
    summary: str = "",
    description: str = "",
    *,
    standby_type: str = "DATA",
) -> float:
    """返回 flow 标准阈值（25/30）；不从 JIRA 解析项目自定义标准。"""
    _ = summary, description  # 保留签名兼容旧调用
    return flow_threshold_ma(standby_type)


def triage_from_text(
    summary: str = "",
    description: str = "",
    *,
    jira_key: str = "",
) -> dict[str, object]:
    standby_type = infer_standby_type(summary, description)
    out: dict[str, object] = {
        "standby_type": standby_type,
        "threshold_ma": flow_threshold_ma(standby_type),
    }
    if jira_key:
        out["key"] = jira_key
    return out


def triage_from_workspace(workspace: str) -> dict[str, object]:
    from repo_paths import load_jira_info  # noqa: WPS433

    info = load_jira_info(workspace)
    if not info:
        raise SystemExit(
            f"未找到有效 jira_info.json（workspace={workspace}）；"
            "请先运行 base_jirainfo 写入工作区。"
        )
    summary = str(info.get("summary") or "")
    description = str(info.get("description") or "")
    if not summary and not description:
        raise SystemExit("jira_info.json 中 summary/description 均为空")
    key = str(info.get("key") or "").strip()
    return triage_from_text(summary, description, jira_key=key)


def main() -> int:
    import argparse
    import json

    _setup_utf8_stdio()
    p = argparse.ArgumentParser(description="从 JIRA 文本推断 standby_type 与功耗阈值")
    p.add_argument(
        "-w",
        "--workspace",
        default="",
        help="工作区根目录 temp/<DATE>/<KEY>，从 jira_info.json 读取字段（推荐）",
    )
    p.add_argument("--summary", default="")
    p.add_argument("--description", default="")
    args = p.parse_args()

    if args.workspace:
        payload = triage_from_workspace(args.workspace)
    elif args.summary or args.description:
        payload = triage_from_text(args.summary, args.description)
    else:
        p.error("须指定 --workspace 或 --summary/--description")

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""L2 ModemEE 分析脚本

执行 ModemEE 域的深度分析，包括：
1. 从日志中提取 ModemEE 相关证据
2. 查询飞书多维表格判断是否已知异常
3. 若不存在则写入飞书表格记录

飞书多维表格链接: https://transsioner.feishu.cn/base/JzmgbczwraPHQ1s2Fz9cmHh7nov?table=tblANV8zkvN8llAf&view=vewLvx6K3h

Exit codes:
0 -> 分析成功
1 -> 分析失败
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "_shared"))
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

from modem_analysis_runtime import (
    analyze_domain,
    apply_l2_result,
    configure_stdio,
    load_manifest,
    save_manifest,
    setup_skill_logger,
    EE_ANALYSIS_PATTERNS,
)
from feishu_bitable_client import (
    FeishuBitableClient,
    build_modemee_record,
    generate_ee_hash,
    query_modemee_from_feishu,
    write_modemee_to_feishu,
)


EE_CODE_RE = re.compile(r"(?i)err_code\s*[:=]\s*(?P<code>0x[0-9a-fA-F]+|\d+)")
EE_SOURCE_RE = re.compile(r"(?i)exception\s*source\s*[:=]\s*(?P<source>[A-Za-z0-9_\-]+)")
EE_FILE_LINE_RE = re.compile(r"(?i)file\s*[:=]\s*(?P<file>[A-Za-z0-9_\-/\\\.]+)\s+line\s*[:=]\s*(?P<line>\d+)")
EE_TYPE_RE = re.compile(r"(?i)(?:modem\s*ee|modem\s*exception|phonecrash|subsystem\s*reset|watchdog|assert|fatal\s*error)")
PLATFORM_RE = re.compile(r"(?i)(CN\d+|GEN\d+|T\d+|OS\d+)")
VERSION_RE = re.compile(r"(?i)(\d+\.\d+\.\d+\.\d+|\d+-\d+\.\d+\.\d+)")

DEFAULT_FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
DEFAULT_FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")


def extract_ee_details(evidence: List[Dict[str, Any]], issue_text: str = "") -> Dict[str, Any]:
    """从证据和 Jira 文本中提取 EE 详细信息"""
    details = {
        "ee_type": "",
        "err_code": "",
        "exception_source": "",
        "exception_file": "",
        "exception_line": "",
        "first_occurrence": "",
    }
    
    all_texts = [issue_text or ""]
    for item in evidence:
        all_texts.append(item.get("text", ""))
    combined_text = "\n".join(all_texts)
    
    ee_match = EE_TYPE_RE.search(combined_text)
    if ee_match:
        details["ee_type"] = ee_match.group(0).lower().replace(" ", "_")
    
    code_match = EE_CODE_RE.search(combined_text)
    if code_match:
        details["err_code"] = code_match.group("code")
    
    source_match = EE_SOURCE_RE.search(combined_text)
    if source_match:
        details["exception_source"] = source_match.group("source")
    
    file_line_match = EE_FILE_LINE_RE.search(combined_text)
    if file_line_match:
        details["exception_file"] = file_line_match.group("file")
        details["exception_line"] = file_line_match.group("line")
        if not details["exception_source"]:
            details["exception_source"] = f"{file_line_match.group('file')}:{file_line_match.group('line')}"
    
    for item in evidence:
        timestamp = item.get("timestamp", "")
        if timestamp and not details["first_occurrence"]:
            details["first_occurrence"] = timestamp
            break
    
    return details


def extract_platform_info(manifest: Dict[str, Any]) -> Dict[str, str]:
    """从 manifest 中提取平台信息"""
    jira = manifest.get("jira", {})
    summary = jira.get("summary", "")
    description = jira.get("description", "")
    affected_versions = jira.get("affected_versions", [])
    
    combined_text = f"{summary}\n{description}"
    
    platform = ""
    platform_match = PLATFORM_RE.search(combined_text)
    if platform_match:
        platform = platform_match.group(1).upper()
    
    chip_vendor = ""
    if "mtk" in combined_text.lower() or "alps" in combined_text.lower():
        chip_vendor = "MTK"
    elif "展锐" in combined_text or "unisoc" in combined_text.lower() or "sprd" in combined_text.lower():
        chip_vendor = "展锐"
    elif "高通" in combined_text or "qualcomm" in combined_text.lower() or "qcom" in combined_text.lower():
        chip_vendor = "高通"
    
    chip_model = ""
    if "alps-mp-b0.mp1" in combined_text.lower():
        chip_model = "MT6833/MT6853"
    
    sw_version = ""
    if affected_versions:
        sw_version = affected_versions[0]
    if not sw_version:
        version_match = VERSION_RE.search(combined_text)
        if version_match:
            sw_version = version_match.group(1)
    
    return {
        "platform": platform,
        "chip_vendor": chip_vendor,
        "chip_model": chip_model,
        "sw_version": sw_version,
    }


def analyze_ee_domain(
    manifest: Dict[str, Any],
    log_root: Optional[str] = None,
    feishu_app_id: str = "",
    feishu_app_secret: str = "",
) -> Dict[str, Any]:
    """执行 EE 域分析"""
    base_result = analyze_domain(manifest, "ee", log_root=log_root)
    
    if base_result.get("status") == "skipped_invalid":
        return base_result
    
    jira_key = manifest.get("issue_key", "")
    jira = manifest.get("jira", {})
    issue_text = f"{jira.get('summary', '')}\n{jira.get('description', '')}\n{jira.get('comments_text', '')}"
    
    evidence = base_result.get("evidence", [])
    ee_details = extract_ee_details(evidence, issue_text)
    platform_info = extract_platform_info(manifest)
    
    ee_hash = generate_ee_hash(
        ee_details.get("ee_type", ""),
        ee_details.get("err_code", ""),
        ee_details.get("exception_source", ""),
    )
    
    client = FeishuBitableClient(
        app_id=feishu_app_id or DEFAULT_FEISHU_APP_ID,
        app_secret=feishu_app_secret or DEFAULT_FEISHU_APP_SECRET,
    )
    
    query_result = query_modemee_from_feishu(ee_hash, client)
    
    feishu_result = {
        "success": query_result.get("success", False),
        "exists": query_result.get("exists", False),
        "record": query_result.get("record"),
    }
    
    if query_result.get("success") and not query_result.get("exists"):
        occurrence_count = len(manifest.get("jira", {}).get("box_urls", []))
        if occurrence_count == 0:
            occurrence_count = 1
        
        record_data = build_modemee_record(
            jira_key=jira_key,
            ee_type=ee_details.get("ee_type", ""),
            err_code=ee_details.get("err_code", ""),
            exception_source=ee_details.get("exception_source", ""),
            platform=platform_info.get("platform", ""),
            chip_vendor=platform_info.get("chip_vendor", ""),
            chip_model=platform_info.get("chip_model", ""),
            sw_version=platform_info.get("sw_version", ""),
            title=jira.get("summary", ""),
            description=jira.get("description", ""),
            call_stack=ee_details.get("exception_file", ""),
            status="待分析",
            first_occurrence=ee_details.get("first_occurrence", ""),
            occurrence_count=occurrence_count,
        )
        
        write_result = write_modemee_to_feishu(record_data, client)
        feishu_result["write_result"] = write_result
        feishu_result["action"] = write_result.get("action", "")
    
    enhanced_result = {
        **base_result,
        "ee_details": ee_details,
        "platform_info": platform_info,
        "ee_hash": ee_hash,
        "feishu_query": feishu_result,
    }
    
    if query_result.get("success") and query_result.get("exists"):
        record = query_result.get("record", {})
        if record.get("root_cause"):
            enhanced_result["candidate_causes"].append(f"飞书表格已知根因: {record.get('root_cause')}")
        if record.get("solution"):
            enhanced_result["candidate_causes"].append(f"飞书表格已知解决方案: {record.get('solution')}")
    
    return enhanced_result


def parse_args():
    parser = argparse.ArgumentParser(description="执行 L2 ModemEE 域分析。")
    parser.add_argument("--manifest", required=True, help="manifest 文件路径")
    parser.add_argument("--log-root", help="覆盖 manifest.final_log_root")
    parser.add_argument("--output", help="结果 JSON 输出路径")
    parser.add_argument("--feishu-app-id", default=DEFAULT_FEISHU_APP_ID, help="飞书应用 ID")
    parser.add_argument("--feishu-app-secret", default=DEFAULT_FEISHU_APP_SECRET, help="飞书应用密钥")
    return parser.parse_args()


def main():
    configure_stdio()
    args = parse_args()

    try:
        manifest = load_manifest(args.manifest)
    except Exception as exc:
        print(f"SKILL_FAILED: L2-EE 无法加载 manifest ({args.manifest}): {exc}")
        sys.exit(1)

    issue_key = manifest.get("issue_key", "") or "unknown"
    logger = setup_skill_logger(args.manifest, issue_key)
    logger.info("=== L2 EE analysis 开始 ===")

    result = analyze_ee_domain(
        manifest,
        log_root=args.log_root,
        feishu_app_id=args.feishu_app_id,
        feishu_app_secret=args.feishu_app_secret,
    )
    logger.info(f"L2-EE 完成: status={result.get('status')}, "
                f"feishu_exists={result.get('feishu_query', {}).get('exists')}")

    apply_l2_result(manifest, "ee", result)
    save_manifest(args.manifest, manifest)
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

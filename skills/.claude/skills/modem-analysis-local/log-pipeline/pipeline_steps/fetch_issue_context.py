import argparse
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

try:
    from jira_dashboard_helpers import (
        normalize_jira_status_en,
        primary_log_path_from_urls_by_type,
    )
except ImportError:
    normalize_jira_status_en = None  # type: ignore
    primary_log_path_from_urls_by_type = None  # type: ignore

# Phase1 发布后 Jira 评论标记；含此标记的行不参与日志路径/URL 抽取（避免与工单原 log 路径重复）
PIPELINE_EXPORT_FLAG = "ModemLogPipelineExportFlag"
_PIPELINE_EXPORT_FLAGS = (
    PIPELINE_EXPORT_FLAG,
    "QcomModemLogPipelineExportFlag",
    "SprdModemLogPipelineExportFlag",
)


def text_without_export_flag_lines(text: str) -> str:
    """去掉含 export-flag 的行（通常为 pipeline 自动评论，内含 smb zip 等非下载路径）。"""
    if not text:
        return ""
    kept = [
        line
        for line in text.splitlines()
        if not any(flag in line for flag in _PIPELINE_EXPORT_FLAGS)
    ]
    return "\n".join(kept)


# 看板 / 下游可选字段（写入 manifest.jira，不破坏 Phase2 契约必填项）
_JIRA_DASHBOARD_DEFAULTS = {
    "issue_status_en": "",
    "log_path": "",
}

DEFAULT_MANIFEST = {
    "issue_key": "",
    "jira": {
        "summary": "",
        "description": "",
        "comments_text": "",
        "url_roles": {},
        "affected_versions": [],
        "urls_by_type": {
            "box": [],
            "feishu_file": [],
            "network_share": [],
            "http_direct": [],
        },
        "time_points": [],
        "test_steps": "",
        "expected_result": "",
        "actual_result": "",
        "time_window": {"start": None, "end": None},
        "platform": "",
        "chip_vendor": "",
        "chip_model": "",
        "sw_version": "",
        **_JIRA_DASHBOARD_DEFAULTS,
    },
}


def configure_stdio():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def merge_defaults(target, defaults):
    for key, value in defaults.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_defaults(target[key], value)
    return target


def load_manifest(path):
    if not path or not os.path.exists(path):
        return deepcopy(DEFAULT_MANIFEST)
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"manifest 格式错误: {path}")
    return merge_defaults(data, deepcopy(DEFAULT_MANIFEST))


def save_manifest(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = merge_defaults(data, deepcopy(DEFAULT_MANIFEST))
    data["_meta"] = {"updated_at": datetime.now().isoformat(timespec="seconds")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_and_classify_urls(text):
    """提取并分类所有日志链接"""
    if not text:
        return {
            "box": [],
            "feishu_file": [],
            "network_share": [],
            "http_direct": [],
        }
    
    classified = {
        "box": [],
        "feishu_file": [],
        "network_share": [],
        "http_direct": [],
    }
    seen = set()
    
    # 1. 提取 FRBOX/SGBOX 链接（box）
    box_pattern = r"https?://(?:frbox|sgbox)\.transsion\.com[^\s'\"<>]+"
    box_urls = [url.rstrip("].,);") for url in re.findall(box_pattern, text)]
    for url in box_urls:
        if url not in seen:
            seen.add(url)
            classified["box"].append(url)
    
    # 2. 提取飞书文件链接
    feishu_pattern = r"https?://[^\s'\"<>]*feishu\.cn/file/[^\s'\"<>]+"
    feishu_urls = [url.rstrip("].,);") for url in re.findall(feishu_pattern, text)]
    for url in feishu_urls:
        if url not in seen:
            seen.add(url)
            classified["feishu_file"].append(url)
    
    # 3. 提取网络共享路径（UNC 路径）
    path_patterns = [
        r'Path\s*:\s*([^\n\r]+)',
        r'\*Path\s*:\*\s*([^\n\r]+)',
        r'path\s*:\s*([^\n\r]+)',
        r'\\\\[\d\.]+\\[^\s\n\r]+',  # 直接的 UNC 路径
    ]
    for pattern in path_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            path = match.strip().strip('*').strip()
            # 确保是 UNC 路径格式
            if path and len(path) > 5 and path.startswith('\\\\') and path not in seen:
                seen.add(path)
                classified["network_share"].append(path)
    
    # 4. 提取其他 HTTP 直链（可直接下载的链接）
    http_pattern = r"https?://[^\s'\"<>\[\]]+"
    all_http_urls = [url.rstrip("].,);") for url in re.findall(http_pattern, text)]
    for url in all_http_urls:
        if url in seen:
            continue
        
        url_lower = url.lower()
        
        # 排除非日志链接
        exclude_domains = [
            'jira.transsion.com',
            'gerrit.transsion.com',
            'bug-sentry.transsion-os.com',
            'jenkins-tools.transsion.com',
        ]
        if any(domain in url_lower for domain in exclude_domains):
            continue
        
        # 排除图片链接（检查路径中是否包含图片扩展名）
        if any(ext in url_lower for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg']):
            continue
        
        # 排除明显的图片目录
        if 'picture' in url_lower or 'image' in url_lower or 'img' in url_lower:
            continue
        
        # 判断是否为可直接下载的链接
        # 包含文件扩展名或 OSS 等关键字
        download_indicators = [
            '.zip', '.rar', '.tar', '.gz', '.7z',
            '.log', '.txt', '.bin', '.dat',
            'aliyuncs.com', 'oss-', 'obs-',
            '/download/', '/file/',
        ]
        
        if any(indicator in url_lower for indicator in download_indicators):
            seen.add(url)
            classified["http_direct"].append(url)
    
    return classified


def extract_time_points(text):
    """从文本中提取时间点信息"""
    if not text:
        return []
    
    time_points = []
    seen = set()
    
    # 时间模式列表
    patterns = [
        # ISO 格式: 2026-04-15 14:04:38
        (r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', 'datetime'),
        # 日期时间: 20260415_140438
        (r'\d{8}_\d{6}', 'datetime_compact'),
        # 标准日期: 2026-04-15, 2026/04/15
        (r'\d{4}[-/]\d{2}[-/]\d{2}', 'date'),
        # ExpTime 格式: Fri Jan  1 02:04:02 WAT 2010
        (r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\w+\s+\d{4}', 'exptime'),
        # 时间戳: 1274537466000034 (13-16位数字)
        (r'\b\d{13,16}\b', 'timestamp'),
    ]
    
    for pattern, time_type in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            match = match.strip()
            if match and match not in seen:
                seen.add(match)
                time_points.append({
                    "value": match,
                    "type": time_type
                })
    
    return time_points


# ===== Phase 2 契约要求的扩展字段（启发式抽取，缺失时回空字符串） =====

# 测试步骤 / 预期 / 实际结果常见模板标签
_SECTION_PATTERNS = {
    "test_steps": [
        r"(?:^|\n)\s*\*?\s*(?:测试步骤|复现步骤|操作步骤|步骤|Steps?\s+to\s+Reproduce|Test\s+Steps?|Reproduce\s+Steps?)\s*[:：]?\s*\*?\s*\n",
    ],
    "expected_result": [
        r"(?:^|\n)\s*\*?\s*(?:预期结果|期望结果|Expected\s+Result|Expected)\s*[:：]?\s*\*?\s*\n",
    ],
    "actual_result": [
        r"(?:^|\n)\s*\*?\s*(?:实际结果|实际现象|实际表现|Actual\s+Result|Actual)\s*[:：]?\s*\*?\s*\n",
    ],
}
_SECTION_END_RE = re.compile(
    r"(?:^|\n)\s*\*?\s*"
    r"(?:测试步骤|复现步骤|操作步骤|步骤|预期结果|期望结果|实际结果|实际现象|实际表现|"
    r"附件|日志|备注|环境|Reproduce|Steps?|Expected|Actual|Logs?|Attachments?|Environment|Notes?)"
    r"\s*[:：]?\s*\*?\s*\n",
    re.IGNORECASE,
)


def _extract_section(text, start_patterns):
    """从描述文本中按"标签：内容\n下一个标签"切片，提取节内容。"""
    if not text:
        return ""
    for pattern in start_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        start = match.end()
        # 在剩余文本中找下一个同级章节标签作为结束
        remainder = text[start:]
        end_match = _SECTION_END_RE.search(remainder)
        body = remainder[: end_match.start()] if end_match else remainder
        body = body.strip()
        if body:
            return body
    return ""


def extract_test_context(description_text):
    """从 Jira 描述中启发式抽取 测试步骤 / 预期结果 / 实际结果。"""
    description_text = description_text or ""
    return {
        "test_steps": _extract_section(description_text, _SECTION_PATTERNS["test_steps"]),
        "expected_result": _extract_section(description_text, _SECTION_PATTERNS["expected_result"]),
        "actual_result": _extract_section(description_text, _SECTION_PATTERNS["actual_result"]),
    }


_PLATFORM_RE = re.compile(
    r"(?im)(?:^|\b)(?:platform|平台|Platform\s*Code)\s*[:：]\s*([A-Za-z0-9_\-]+)"
)
_CHIP_VENDOR_RE = re.compile(
    r"(?im)(?:^|\b)(?:chip\s*vendor|芯片厂商|芯片商|Vendor)\s*[:：]\s*([A-Za-z0-9_\-]+)"
)
_CHIP_MODEL_RE = re.compile(
    r"(?im)(?:^|\b)(?:chip\s*model|芯片型号|chipset|SoC)\s*[:：]\s*([A-Za-z0-9_\-\.]+)"
)
_SW_VERSION_RE = re.compile(
    r"(?im)(?:^|\b)(?:sw\s*version|软件版本|Build\s*Version|Build\s*Number|fingerprint)\s*[:：]\s*([^\s\r\n]+)"
)


def extract_platform_info(text):
    """从 Jira 文本中启发式抽取 平台代号 / 芯片厂商 / 芯片型号 / 软件版本。

    任一字段缺失时返回空字符串，不抛错。"""
    text = text or ""
    platform = ""
    chip_vendor = ""
    chip_model = ""
    sw_version = ""

    if (m := _PLATFORM_RE.search(text)) is not None:
        platform = m.group(1).strip()
    if (m := _CHIP_VENDOR_RE.search(text)) is not None:
        chip_vendor = m.group(1).strip()
    if (m := _CHIP_MODEL_RE.search(text)) is not None:
        chip_model = m.group(1).strip()
    if (m := _SW_VERSION_RE.search(text)) is not None:
        sw_version = m.group(1).strip()

    # 兜底：从常见关键词推断 chip_vendor
    if not chip_vendor:
        text_low = text.lower()
        if "mediatek" in text_low or "mtk" in text_low:
            chip_vendor = "MTK"
        elif "qualcomm" in text_low or "qcom" in text_low or "高通" in text:
            chip_vendor = "QCOM"
        elif "unisoc" in text_low or "spreadtrum" in text_low or "展锐" in text or "紫光" in text:
            chip_vendor = "UNISOC"

    return {
        "platform": platform,
        "chip_vendor": chip_vendor,
        "chip_model": chip_model,
        "sw_version": sw_version,
    }


def derive_time_window(time_points):
    """从 time_points 列表派生 time_window。

    简单策略：取所有 datetime 类型条目的 min/max；若没有则返回 (None, None)。"""
    if not time_points:
        return {"start": None, "end": None}
    datetime_values = sorted(
        p.get("value") for p in time_points
        if isinstance(p, dict) and p.get("type") in ("datetime", "datetime_compact") and p.get("value")
    )
    if not datetime_values:
        return {"start": None, "end": None}
    return {"start": datetime_values[0], "end": datetime_values[-1]}


def infer_url_roles(description_text, urls):
    description_text = "" if description_text is None else str(description_text)
    urls = list(urls or [])
    if not description_text or len(urls) != 2:
        return {}
    pattern = (
        r"(?is)REF.{0,80}?("
        + r"https?://(?:frbox|sgbox)\.transsion\.com[^\s'\"<>]+"
        + r")"
    )
    match = re.search(pattern, description_text)
    if not match:
        return {}
    ref_url = match.group(1)
    if ref_url not in urls:
        return {}
    roles = {ref_url: "REF"}
    other = urls[0] if urls[1] == ref_url else urls[1]
    roles[other] = "DUT"
    return roles


def parse_args():
    parser = argparse.ArgumentParser(description="根据 Jira 单号提取 issue 文本和日志链接（FRBOX/SGBOX、OSS直链、网络共享路径）。")
    parser.add_argument("--issue-key", help="Jira 单号，例如 XXX-1234")
    parser.add_argument("--manifest", help="manifest 文件路径")
    parser.add_argument("--output", help="结果 JSON 输出路径；默认回写 manifest 或打印到 stdout")
    parser.add_argument("--jira-server", default=os.getenv("JIRA_SERVER", "http://jira.transsion.com"))
    parser.add_argument("--jira-username", default=os.getenv("JIRA_USERNAME"))
    parser.add_argument("--jira-password", default=os.getenv("JIRA_PASSWORD"))
    return parser.parse_args()


def _create_jira_client(jira_server: str, jira_username: str = "", jira_password: str = ""):
    """创建 Jira 客户端；提供账号密码时使用 basic_auth。"""
    from jira import JIRA

    server = (jira_server or "").strip()
    username = (jira_username or "").strip()
    password = jira_password or ""
    if username and password:
        return JIRA(server=server, basic_auth=(username, password))
    return JIRA(server=server)


def fetch_issue_context(issue_key):
    """
    获取 Jira issue 上下文信息（供 pipeline 调用）
    
    Args:
        issue_key: Jira 单号
    
    Returns:
        dict: Jira 信息
    """
    configure_stdio()
    
    jira_server = os.getenv("JIRA_SERVER", "http://jira.transsion.com")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_password = os.getenv("JIRA_PASSWORD")

    try:
        from jira import JIRA
    except ModuleNotFoundError as e:
        raise ImportError(f"缺少依赖，无法执行 Jira 提取脚本: {e}") from e

    client = _create_jira_client(jira_server, jira_username, jira_password)
    issue = client.issue(issue_key)
    fields = getattr(issue, "fields", None)
    summary = str(getattr(fields, "summary", "") or "")
    description = str(getattr(fields, "description", "") or "")
    
    texts = [summary, description]
    comments_texts = []
    try:
        comments = client.comments(issue)
        for comment in comments:
            body = getattr(comment, "body", None)
            if body:
                body = str(body)
                if PIPELINE_EXPORT_FLAG in body:
                    body = text_without_export_flag_lines(body)
                    if not body.strip():
                        continue
                comments_texts.append(body)
                texts.append(body)
    except Exception:
        pass

    raw_fields = getattr(issue, "raw", {}).get("fields", {})
    for value in raw_fields.values():
        if isinstance(value, str):
            if PIPELINE_EXPORT_FLAG in value:
                value = text_without_export_flag_lines(value)
                if not value.strip():
                    continue
            texts.append(value)

    comments_text = "\n".join(comments_texts)
    all_text = text_without_export_flag_lines("\n".join(t for t in texts if t))

    # 提取并分类 URL
    urls_by_type = extract_and_classify_urls(all_text)
    
    # 合并所有 URL 用于角色推断
    all_urls = []
    for url_list in urls_by_type.values():
        all_urls.extend(url_list)
    
    url_roles = infer_url_roles(description, all_urls)
    
    # 提取时间点
    time_points = extract_time_points(all_text)
    time_window = derive_time_window(time_points)
    
    # 获取影响版本
    affected_versions = []
    try:
        if hasattr(fields, 'versions') and fields.versions:
            for version in fields.versions:
                version_name = getattr(version, 'name', None)
                if version_name:
                    affected_versions.append(str(version_name))
    except Exception:
        pass
    
    # Phase 2 契约要求的扩展字段（启发式抽取）
    test_context = extract_test_context(description)
    platform_info = extract_platform_info(all_text)

    status_raw = raw_fields.get("status")
    if normalize_jira_status_en and primary_log_path_from_urls_by_type:
        issue_status_en = normalize_jira_status_en(status_raw)
        log_path = primary_log_path_from_urls_by_type(urls_by_type)
    else:
        issue_status_en = ""
        log_path = ""

    return {
        "summary": summary,
        "description": description,
        "comments_text": comments_text,
        "url_roles": url_roles,
        "affected_versions": affected_versions,
        "urls_by_type": urls_by_type,
        "time_points": time_points,
        "test_steps": test_context["test_steps"],
        "expected_result": test_context["expected_result"],
        "actual_result": test_context["actual_result"],
        "time_window": time_window,
        "platform": platform_info["platform"],
        "chip_vendor": platform_info["chip_vendor"],
        "chip_model": platform_info["chip_model"],
        "sw_version": platform_info["sw_version"],
        "issue_status_en": issue_status_en,
        "log_path": log_path,
    }


def main():
    configure_stdio()
    args = parse_args()
    manifest = load_manifest(args.manifest)

    issue_key = (args.issue_key or manifest.get("issue_key") or "").strip()
    if not issue_key:
        raise SystemExit("缺少 issue_key，请通过 --issue-key 或 manifest 提供。")

    try:
        from jira import JIRA
    except ModuleNotFoundError as e:
        raise SystemExit(f"缺少依赖，无法执行 Jira 提取脚本: {e}")

    client = _create_jira_client(args.jira_server, args.jira_username, args.jira_password)
    issue = client.issue(issue_key)
    fields = getattr(issue, "fields", None)
    summary = str(getattr(fields, "summary", "") or "")
    description = str(getattr(fields, "description", "") or "")

    texts = [summary, description]
    comments_texts = []
    try:
        comments = client.comments(issue)
        for comment in comments:
            body = getattr(comment, "body", None)
            if body:
                body = str(body)
                if PIPELINE_EXPORT_FLAG in body:
                    body = text_without_export_flag_lines(body)
                    if not body.strip():
                        continue
                comments_texts.append(body)
                texts.append(body)
    except Exception:
        pass

    raw_fields = getattr(issue, "raw", {}).get("fields", {})
    for value in raw_fields.values():
        if isinstance(value, str):
            if PIPELINE_EXPORT_FLAG in value:
                value = text_without_export_flag_lines(value)
                if not value.strip():
                    continue
            texts.append(value)

    comments_text = "\n".join(comments_texts)
    all_text = text_without_export_flag_lines("\n".join(t for t in texts if t))

    # 提取并分类 URL
    urls_by_type = extract_and_classify_urls(all_text)

    # 合并所有 URL 用于角色推断
    all_urls = []
    for url_list in urls_by_type.values():
        all_urls.extend(url_list)

    url_roles = infer_url_roles(description, all_urls)

    # 提取时间点
    time_points = extract_time_points(all_text)
    time_window = derive_time_window(time_points)

    # 获取影响版本
    affected_versions = []
    try:
        if hasattr(fields, 'versions') and fields.versions:
            for version in fields.versions:
                version_name = getattr(version, 'name', None)
                if version_name:
                    affected_versions.append(str(version_name))
    except Exception:
        pass

    # Phase 2 契约要求的扩展字段（启发式抽取）
    test_context = extract_test_context(description)
    platform_info = extract_platform_info(all_text)

    manifest["issue_key"] = issue_key
    manifest["jira"]["summary"] = summary
    manifest["jira"]["description"] = description
    manifest["jira"]["comments_text"] = comments_text
    manifest["jira"]["url_roles"] = url_roles
    manifest["jira"]["affected_versions"] = affected_versions
    manifest["jira"]["urls_by_type"] = urls_by_type
    manifest["jira"]["time_points"] = time_points
    manifest["jira"]["test_steps"] = test_context["test_steps"]
    manifest["jira"]["expected_result"] = test_context["expected_result"]
    manifest["jira"]["actual_result"] = test_context["actual_result"]
    manifest["jira"]["time_window"] = time_window
    manifest["jira"]["platform"] = platform_info["platform"]
    manifest["jira"]["chip_vendor"] = platform_info["chip_vendor"]
    manifest["jira"]["chip_model"] = platform_info["chip_model"]
    manifest["jira"]["sw_version"] = platform_info["sw_version"]

    # 如果没有指定 manifest 路径，默认保存到 {WORKSPACE_ROOT}/{issue_key}/job_manifest.json
    if not args.manifest:
        workspace_base = os.getenv("WORKSPACE_ROOT") or os.path.join(os.getcwd(), "data_store")
        issue_dir = os.path.abspath(os.path.join(workspace_base, issue_key))
        os.makedirs(issue_dir, exist_ok=True)
        args.manifest = os.path.join(issue_dir, "job_manifest.json")

    if args.manifest:
        save_manifest(args.manifest, manifest)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

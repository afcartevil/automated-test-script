"""Extract and classify log URLs/paths from Jira issue text."""

from __future__ import annotations

import re
from typing import Dict, List

URL_TYPES = ("box", "feishu_file", "network_share", "http_direct")


def empty_urls_by_type() -> Dict[str, List[str]]:
    return {k: [] for k in URL_TYPES}


def extract_and_classify_urls(text: str) -> Dict[str, List[str]]:
    """Classify log sources into box / feishu_file / network_share / http_direct."""
    if not text:
        return empty_urls_by_type()

    classified = empty_urls_by_type()
    seen: set[str] = set()

    box_pattern = r"https?://(?:frbox|sgbox)\.transsion\.com[^\s'\"<>]+"
    for url in (u.rstrip("].,);") for u in re.findall(box_pattern, text)):
        if url not in seen:
            seen.add(url)
            classified["box"].append(url)

    feishu_pattern = r"https?://[^\s'\"<>]*feishu\.cn/file/[^\s'\"<>]+"
    for url in (u.rstrip("].,);") for u in re.findall(feishu_pattern, text)):
        if url not in seen:
            seen.add(url)
            classified["feishu_file"].append(url)

    path_patterns = [
        r"Path\s*:\s*([^\n\r]+)",
        r"\*Path\s*:\*\s*([^\n\r]+)",
        r"path\s*:\s*([^\n\r]+)",
        r"\\\\[\d\.]+\\[^\s\n\r]+",
    ]
    for pattern in path_patterns:
        for match in re.findall(pattern, text, re.IGNORECASE):
            path = match.strip().strip("*").strip()
            if path and len(path) > 5 and path.startswith("\\\\") and path not in seen:
                seen.add(path)
                classified["network_share"].append(path)

    http_pattern = r"https?://[^\s'\"<>\[\]]+"
    exclude_domains = (
        "jira.transsion.com",
        "gerrit.transsion.com",
        "bug-sentry.transsion-os.com",
        "jenkins-tools.transsion.com",
    )
    download_indicators = (
        ".zip",
        ".rar",
        ".tar",
        ".gz",
        ".7z",
        ".log",
        ".txt",
        ".bin",
        ".dat",
        ".tne",
        "aliyuncs.com",
        "oss-",
        "obs-",
        "/download/",
        "/file/",
        "fanslog",
        "taglog",
        "bugreport",
    )
    for url in (u.rstrip("].,);") for u in re.findall(http_pattern, text)):
        if url in seen:
            continue
        url_lower = url.lower()
        if any(domain in url_lower for domain in exclude_domains):
            continue
        if any(ext in url_lower for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg")):
            continue
        if "picture" in url_lower or "image" in url_lower or "img" in url_lower:
            continue
        if any(indicator in url_lower for indicator in download_indicators):
            seen.add(url)
            classified["http_direct"].append(url)

    return classified

"""Orchestrate multi-channel Jira log downloads."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .channels import (
    download_box_urls,
    download_feishu_file,
    download_http_direct,
    download_network_share,
)
from .url_classifier import URL_TYPES, empty_urls_by_type

ALL_CHANNELS = set(URL_TYPES)


def download_classified_urls(
    urls_by_type: Dict[str, List[str]],
    download_dir: str,
    *,
    channels: Optional[Set[str]] = None,
    prefer_box_http: bool = True,
    box_headless: bool = True,
    box_max_retries: int = 3,
) -> Dict[str, Any]:
    """
    Download logs for each classified URL group.

    channels: subset of box|feishu_file|network_share|http_direct; None = all.
    """
    active = channels or ALL_CHANNELS
    unknown = active - ALL_CHANNELS
    if unknown:
        raise ValueError(f"未知 channel: {', '.join(sorted(unknown))}")

    root = Path(download_dir)
    root.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []

    if "box" in active:
        box_urls = list(urls_by_type.get("box") or [])
        if box_urls:
            for row in download_box_urls(
                box_urls,
                str(root),
                prefer_http=prefer_box_http,
                headless=box_headless,
                max_retries=box_max_retries,
            ):
                results.append(row)

    if "feishu_file" in active:
        for index, url in enumerate(urls_by_type.get("feishu_file") or [], start=1):
            out = download_feishu_file(url, str(root))
            results.append(
                {
                    "url": url,
                    "url_type": "feishu_file",
                    "index": index,
                    "success": out["success"],
                    "downloaded_files": out["downloaded_files"],
                    "error": out["error"],
                    "download_method": "feishu_api",
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
            )

    if "network_share" in active:
        for index, path in enumerate(urls_by_type.get("network_share") or [], start=1):
            out = download_network_share(path, str(root))
            results.append(
                {
                    "url": path,
                    "url_type": "network_share",
                    "index": index,
                    "success": out["success"],
                    "downloaded_files": out["downloaded_files"],
                    "error": out["error"],
                    "download_method": "network_copy",
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
            )

    if "http_direct" in active:
        for index, url in enumerate(urls_by_type.get("http_direct") or [], start=1):
            out = download_http_direct(url, str(root))
            results.append(
                {
                    "url": url,
                    "url_type": "http_direct",
                    "index": index,
                    "success": out["success"],
                    "downloaded_files": out["downloaded_files"],
                    "error": out["error"],
                    "download_method": "http_download",
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
            )

    downloaded_any = any(r.get("success") for r in results)
    return {
        "download_dir": str(root.resolve()),
        "results": results,
        "downloaded_any": downloaded_any,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def load_optional_env(skill_root: Path) -> None:
    """Load jira-ops/.env if python-dotenv is available."""
    env_path = skill_root / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:
        pass

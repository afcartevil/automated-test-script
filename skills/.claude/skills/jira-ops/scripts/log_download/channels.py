"""Per-channel log download implementations (modem log-pipeline port)."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from .aliyun_pds_downloader import AliyunPDSDownloader

logger = logging.getLogger("jira-ops.log_download")


def _result_item(
    url: str,
    url_type: str,
    *,
    success: bool,
    downloaded_files: Optional[List[str]] = None,
    error: Optional[str] = None,
    download_method: Optional[str] = None,
    index: int = 0,
) -> Dict[str, Any]:
    return {
        "url": url,
        "url_type": url_type,
        "index": index,
        "success": success,
        "downloaded_files": downloaded_files or [],
        "error": error,
        "download_method": download_method,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def try_http_pds_download(
    url: str,
    download_dir: str,
    *,
    num_threads: int = 8,
    chunk_size: int = 10 * 1024 * 1024,
) -> Dict[str, Any]:
    if AliyunPDSDownloader is None:
        return {"success": False, "error": "aliyun_pds_downloader unavailable", "downloaded_files": [], "skip_browser": False}
    try:
        downloader = AliyunPDSDownloader(
            share_url=url,
            download_dir=download_dir,
            num_threads=num_threads,
            chunk_size=chunk_size,
        )
        if not downloader.parse_share_url():
            return {"success": False, "error": "解析分享链接失败", "downloaded_files": [], "skip_browser": True}
        if not downloader.get_share_token():
            return {"success": False, "error": "获取分享令牌失败", "downloaded_files": [], "skip_browser": True}
        downloader.download_dir.mkdir(parents=True, exist_ok=True)
        items = downloader.list_files()
        if not items:
            return {"success": False, "error": "目录为空或获取文件列表失败", "downloaded_files": [], "skip_browser": False}
        downloaded_files: List[str] = []
        for item in items:
            item_name = item.get("name", "unknown")
            item_id = item.get("file_id")
            file_size = item.get("size", 0)
            file_path = downloader.download_dir / item_name
            if file_path.exists() and file_path.stat().st_size == file_size:
                downloaded_files.append(item_name)
                continue
            download_url = downloader.get_download_url(item_id, item_name)
            if not download_url:
                continue
            if downloader.download_file(download_url, file_path):
                downloaded_files.append(item_name)
        if downloaded_files:
            return {"success": True, "error": None, "downloaded_files": downloaded_files, "skip_browser": False}
        return {"success": False, "error": "没有成功下载任何文件", "downloaded_files": [], "skip_browser": False}
    except Exception as exc:
        return {"success": False, "error": str(exc), "downloaded_files": [], "skip_browser": False}


def download_feishu_file(url: str, download_dir: str) -> Dict[str, Any]:
    if requests is None:
        return {"success": False, "error": "requests 未安装", "downloaded_files": []}
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        return {"success": False, "error": "缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET", "downloaded_files": []}
    try:
        file_token = url.split("/")[-1].split("?")[0]
        token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        token_result = requests.post(token_url, json={"app_id": app_id, "app_secret": app_secret}, timeout=60).json()
        if token_result.get("code") != 0:
            return {"success": False, "error": f"获取飞书 token 失败: {token_result}", "downloaded_files": []}
        access_token = token_result.get("tenant_access_token")
        download_url = f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}/download"
        response = requests.get(download_url, headers={"Authorization": f"Bearer {access_token}"}, stream=True, timeout=300)
        if response.status_code != 200:
            return {"success": False, "error": f"飞书文件下载失败，状态码: {response.status_code}", "downloaded_files": []}
        os.makedirs(download_dir, exist_ok=True)
        temp_filepath = os.path.join(download_dir, f"temp_{file_token}")
        with open(temp_filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        def detect_ext(filepath: str) -> str:
            with open(filepath, "rb") as fh:
                header = fh.read(16)
            if header[:4] == b"\x50\x4B\x03\x04":
                return ".zip"
            if header[:4] == b"\x52\x61\x72\x21":
                return ".rar"
            if header[:6] == b"\x37\x7A\xBC\xAF\x27\x1C":
                return ".7z"
            if header[:2] == b"\x1F\x8B":
                return ".tar.gz"
            return ""

        detected_ext = detect_ext(temp_filepath)
        filename = f"feishu_file_{file_token}{detected_ext}"
        cd = response.headers.get("Content-Disposition", "")
        if cd:
            match = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';]+)', cd)
            if match:
                from urllib.parse import unquote

                filename = unquote(match.group(1))
                if detected_ext and not any(
                    filename.lower().endswith(ext) for ext in (".zip", ".rar", ".7z", ".tar.gz", ".tar", ".gz")
                ):
                    filename = filename + detected_ext
        final_filepath = os.path.join(download_dir, filename)
        if os.path.exists(final_filepath):
            os.remove(final_filepath)
        os.rename(temp_filepath, final_filepath)
        return {"success": True, "error": None, "downloaded_files": [filename]}
    except Exception as exc:
        return {"success": False, "error": f"飞书文件下载异常: {exc}", "downloaded_files": []}


def download_network_share(unc_path: str, download_dir: str) -> Dict[str, Any]:
    try:
        network_servers_json = os.environ.get("NETWORK_SERVERS", "[]")
        network_servers = json.loads(network_servers_json)
        if not unc_path.startswith("\\\\"):
            return {"success": False, "error": "不是有效的 UNC 路径", "downloaded_files": []}
        parts = unc_path[2:].split("\\", 2)
        if len(parts) < 2:
            return {"success": False, "error": "UNC 路径格式错误", "downloaded_files": []}
        server = parts[0]
        share = parts[1].split("\\")[0]
        credentials = next((s for s in network_servers if s.get("server") == server), None)
        if credentials and sys.platform == "win32":
            username = credentials.get("username")
            password = credentials.get("password")
            share_path = f"\\\\{server}\\{share}"
            os.system(f'net use "{share_path}" /user:{username} {password} >nul 2>&1')
        if not os.path.exists(unc_path):
            return {"success": False, "error": f"网络路径不存在或无法访问: {unc_path}", "downloaded_files": []}
        os.makedirs(download_dir, exist_ok=True)
        if os.path.isfile(unc_path):
            filename = os.path.basename(unc_path)
            if filename == "__exp_main.txt":
                parent_dir = os.path.dirname(unc_path)
                parent_name = os.path.basename(parent_dir)
                dest_parent = os.path.join(download_dir, parent_name)
                os.makedirs(dest_parent, exist_ok=True)
                copied: List[str] = []
                for item in os.listdir(parent_dir):
                    src_item = os.path.join(parent_dir, item)
                    dst_item = os.path.join(dest_parent, item)
                    if os.path.isfile(src_item):
                        shutil.copy2(src_item, dst_item)
                    elif os.path.isdir(src_item):
                        if os.path.exists(dst_item):
                            shutil.rmtree(dst_item)
                        shutil.copytree(src_item, dst_item)
                    copied.append(item)
                return {"success": True, "error": None, "downloaded_files": [parent_name]}
            dest_path = os.path.join(download_dir, filename)
            shutil.copy2(unc_path, dest_path)
            return {"success": True, "error": None, "downloaded_files": [filename]}
        if os.path.isdir(unc_path):
            dir_name = os.path.basename(unc_path.rstrip("\\"))
            dest_path = os.path.join(download_dir, dir_name)
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.copytree(unc_path, dest_path)
            return {"success": True, "error": None, "downloaded_files": [dir_name]}
        return {"success": False, "error": "路径既不是文件也不是目录", "downloaded_files": []}
    except Exception as exc:
        return {"success": False, "error": f"网络共享复制异常: {exc}", "downloaded_files": []}


def download_http_direct(url: str, download_dir: str) -> Dict[str, Any]:
    if requests is None:
        return {"success": False, "error": "requests 未安装", "downloaded_files": []}
    try:
        filename = url.split("/")[-1].split("?")[0] or "downloaded_file"
        os.makedirs(download_dir, exist_ok=True)
        filepath = os.path.join(download_dir, filename)
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return {"success": True, "error": None, "downloaded_files": [filename]}
    except Exception as exc:
        return {"success": False, "error": f"HTTP 下载异常: {exc}", "downloaded_files": []}


class BoxBrowserDownloader:
    """Playwright fallback for FRBOX/SGBOX when PDS HTTP API fails."""

    def __init__(self, download_dir: str, *, headless: bool = True, max_retries: int = 2):
        self.download_dir = os.path.abspath(download_dir)
        self.headless = headless
        self.max_retries = max_retries
        self.playwright = None
        self.browser = None
        self.headless_fallback_used = False
        self.log = logging.getLogger("jira-ops.box-browser")

    def _lazy_imports(self):
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"缺少 playwright，请 pip install playwright && python -m playwright install chromium: {exc}") from exc
        return {"sync_playwright": sync_playwright, "TimeoutError": PlaywrightTimeoutError}

    def _find_browser_executable(self) -> str:
        candidates = [
            os.environ.get("CHROME_BINARY"),
            shutil.which("chrome"),
            shutil.which("chrome.exe"),
            shutil.which("msedge"),
            shutil.which("msedge.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return os.path.abspath(candidate)
        raise RuntimeError("未找到 Chrome/Edge，请设置 CHROME_BINARY")

    def setup_browser(self):
        libs = self._lazy_imports()
        os.makedirs(self.download_dir, exist_ok=True)
        self.playwright = libs["sync_playwright"]().start()
        launch_kwargs: Dict[str, Any] = {
            "headless": self.headless,
            "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        }
        try:
            self.browser = self.playwright.chromium.launch(**launch_kwargs)
        except Exception:
            launch_kwargs["executable_path"] = self._find_browser_executable()
            self.browser = self.playwright.chromium.launch(**launch_kwargs)

    def close(self):
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = None
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None

    @staticmethod
    def extract_password_from_url(url: str) -> Optional[str]:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "pwd" in params and params["pwd"]:
            return params["pwd"][0]
        match = re.search(r"pwd=([^&]+)", url)
        return match.group(1) if match else None

    def _click_first_button(self, page, names: List[str]) -> bool:
        for name in names:
            for locator in (
                page.get_by_role("button", name=name),
                page.locator("button").filter(has_text=name),
            ):
                try:
                    if locator.count() > 0:
                        locator.first.click(force=True)
                        return True
                except Exception:
                    continue
        return False

    def _fill_password_if_needed(self, page, password: Optional[str]):
        if not password:
            return
        for locator in (page.locator("input"), page.locator("input[type='password']"), page.get_by_role("textbox")):
            try:
                if locator.count() > 0:
                    locator.first.fill(password)
                    break
            except Exception:
                continue
        self._click_first_button(page, ["确认", "提取"])
        page.wait_for_timeout(1500)

    def download_single_url(self, url: str) -> List[str]:
        libs = self._lazy_imports()
        timeout_error = libs["TimeoutError"]
        if not self.browser:
            self.setup_browser()
        context = self.browser.new_context(accept_downloads=True, locale="zh-CN")
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(2000)
            self._fill_password_if_needed(page, self.extract_password_from_url(url))
            try:
                page.get_by_role("button", name="下载全部").wait_for(state="visible", timeout=15000)
            except timeout_error:
                page.wait_for_timeout(2000)
            with page.expect_download(timeout=120000) as download_info:
                if not self._click_first_button(page, ["下载全部", "批量下载", "下载"]):
                    raise RuntimeError("未找到下载按钮")
            download = download_info.value
            target_path = os.path.join(self.download_dir, download.suggested_filename)
            download.save_as(target_path)
            return [os.path.basename(target_path)]
        except Exception as exc:
            if self.headless and not self.headless_fallback_used and "ERR_CONNECTION_CLOSED" in str(exc):
                self.headless_fallback_used = True
                context.close()
                self.close()
                self.headless = False
                return self.download_single_url(url)
            raise
        finally:
            try:
                context.close()
            except Exception:
                pass

    def download_multiple_urls(
        self,
        urls: List[str],
        *,
        prefer_http: bool = True,
        num_threads: int = 8,
        chunk_size: int = 10 * 1024 * 1024,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        browser_needed = False
        for index, url in enumerate(urls, start=1):
            item: Dict[str, Any] = {
                "url": url,
                "index": index,
                "success": False,
                "downloaded_files": [],
                "error": None,
                "download_method": None,
            }
            if prefer_http:
                http_result = try_http_pds_download(url, self.download_dir, num_threads=num_threads, chunk_size=chunk_size)
                if http_result.get("success"):
                    item.update(success=True, downloaded_files=http_result["downloaded_files"], download_method="pds_http", error=None)
                    results.append(item)
                    continue
                item["error"] = f"HTTP/PDS 失败: {http_result.get('error')}"
                if http_result.get("skip_browser"):
                    item["download_method"] = "pds_http"
                    results.append(item)
                    continue
            browser_needed = True
            for attempt in range(1, self.max_retries + 1):
                try:
                    if self.browser is None:
                        self.setup_browser()
                    item["downloaded_files"] = self.download_single_url(url)
                    item["success"] = True
                    item["download_method"] = "browser"
                    item["error"] = None
                    break
                except Exception as exc:
                    item["error"] = f"浏览器下载第 {attempt} 次失败: {exc}"
                    item["download_method"] = "browser"
                    time.sleep(2)
            results.append(item)
        if browser_needed:
            self.close()
        return results


def download_box_urls(
    urls: List[str],
    download_dir: str,
    *,
    prefer_http: bool = True,
    headless: bool = True,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    downloader = BoxBrowserDownloader(download_dir, headless=headless, max_retries=max_retries)
    raw = downloader.download_multiple_urls(urls, prefer_http=prefer_http)
    for row in raw:
        row["url_type"] = "box"
    return raw

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from aliyun_pds_downloader import AliyunPDSDownloader
except ImportError:
    AliyunPDSDownloader = None

try:
    import requests
except ImportError:
    requests = None

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


DEFAULT_MANIFEST = {
    "issue_key": "",
    "workspace_root": "",
    "jira": {
        "urls_by_type": {
            "box": [],
            "feishu_file": [],
            "network_share": [],
            "http_direct": [],
        },
    },
    "downloads": {
        "download_root": "",
        "download_dirs": [],
        "results": [],
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


def try_http_download(url, download_dir, num_threads=8, chunk_size=10*1024*1024, logger=None):
    if AliyunPDSDownloader is None:
        return {"success": False, "error": "aliyun_pds_downloader 模块未安装", "downloaded_files": [], "skip_browser": False}
    
    try:
        downloader = AliyunPDSDownloader(
            share_url=url,
            download_dir=download_dir,
            num_threads=num_threads,
            chunk_size=chunk_size
        )
        
        if not downloader.parse_share_url():
            return {"success": False, "error": "解析分享链接失败", "downloaded_files": [], "skip_browser": True}
        
        if not downloader.get_share_token():
            return {"success": False, "error": "获取分享令牌失败", "downloaded_files": [], "skip_browser": True}
        
        downloader.download_dir.mkdir(parents=True, exist_ok=True)
        
        items = downloader.list_files()
        if not items:
            return {"success": False, "error": "目录为空或获取文件列表失败", "downloaded_files": [], "skip_browser": False}
        
        downloaded_files = []
        for item in items:
            item_type = item.get("type", "file")
            item_name = item.get("name", "unknown")
            item_id = item.get("file_id")
            
            file_size = item.get("size", 0)
            if logger:
                logger.info(f"下载文件: {item_name} ({downloader._format_size(file_size)})")
            
            file_path = downloader.download_dir / item_name
            
            if file_path.exists():
                existing_size = file_path.stat().st_size
                if existing_size == file_size:
                    if logger:
                        logger.info(f"文件已存在且大小相同，跳过: {file_path}")
                    downloaded_files.append(item_name)
                    continue
            
            download_url = downloader.get_download_url(item_id, item_name)
            if not download_url:
                if logger:
                    logger.error(f"获取下载地址失败: {item_name}")
                continue
            
            success = downloader.download_file(download_url, file_path)
            if success:
                if logger:
                    logger.info(f"下载完成: {file_path}")
                downloaded_files.append(item_name)
            else:
                if logger:
                    logger.error(f"下载失败: {file_path}")
        
        if downloaded_files:
            return {"success": True, "error": None, "downloaded_files": downloaded_files, "skip_browser": False}
        else:
            return {"success": False, "error": "没有成功下载任何文件", "downloaded_files": [], "skip_browser": False}
            
    except Exception as e:
        return {"success": False, "error": str(e), "downloaded_files": [], "skip_browser": False}


def download_feishu_file(url, download_dir, logger=None):
    """下载飞书文件"""
    if requests is None:
        return {"success": False, "error": "requests 模块未安装", "downloaded_files": []}
    
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    
    if not app_id or not app_secret:
        return {"success": False, "error": "缺少飞书凭据 FEISHU_APP_ID 或 FEISHU_APP_SECRET", "downloaded_files": []}
    
    try:
        # 提取 file_token
        file_token = url.split("/")[-1].split("?")[0]
        
        if logger:
            logger.info(f"提取飞书文件 token: {file_token}")
        
        # 获取 tenant_access_token
        token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        token_payload = {"app_id": app_id, "app_secret": app_secret}
        token_response = requests.post(token_url, json=token_payload)
        token_result = token_response.json()
        
        if token_result.get("code") != 0:
            return {"success": False, "error": f"获取飞书 token 失败: {token_result}", "downloaded_files": []}
        
        access_token = token_result.get("tenant_access_token")
        
        # 尝试下载云盘文件
        download_url = f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}/download"
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(download_url, headers=headers, stream=True)
        
        if response.status_code == 200:
            os.makedirs(download_dir, exist_ok=True)
            
            # 先下载到临时文件
            temp_filepath = os.path.join(download_dir, f"temp_{file_token}")
            with open(temp_filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # 检测文件类型（通过文件头）
            def detect_file_type(filepath):
                with open(filepath, 'rb') as f:
                    header = f.read(16)
                
                # ZIP: 50 4B 03 04
                if header[:4] == b'\x50\x4B\x03\x04':
                    return '.zip'
                # RAR: 52 61 72 21
                elif header[:4] == b'\x52\x61\x72\x21':
                    return '.rar'
                # 7z: 37 7A BC AF 27 1C
                elif header[:6] == b'\x37\x7A\xBC\xAF\x27\x1C':
                    return '.7z'
                # tar.gz: 1F 8B
                elif header[:2] == b'\x1F\x8B':
                    return '.tar.gz'
                # PDF: 25 50 44 46
                elif header[:4] == b'\x25\x50\x44\x46':
                    return '.pdf'
                # PNG: 89 50 4E 47
                elif header[:4] == b'\x89\x50\x4E\x47':
                    return '.png'
                # JPEG: FF D8 FF
                elif header[:3] == b'\xFF\xD8\xFF':
                    return '.jpg'
                # MP4: starts with ftyp
                elif b'ftyp' in header[:12]:
                    return '.mp4'
                else:
                    return ''
            
            # 检测文件类型
            detected_ext = detect_file_type(temp_filepath)
            
            # 尝试从响应头获取文件名
            filename = None
            content_disposition = response.headers.get('Content-Disposition', '')
            if content_disposition:
                # 解析 Content-Disposition 头
                import re
                from urllib.parse import unquote
                match = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';]+)', content_disposition)
                if match:
                    filename = unquote(match.group(1))
                    # 检查文件名是否有扩展名，如果没有且检测到了扩展名，则添加
                    if filename and detected_ext:
                        name_lower = filename.lower()
                        # 检查是否已有常见压缩格式扩展名
                        has_ext = any(name_lower.endswith(ext) for ext in ['.zip', '.rar', '.7z', '.tar.gz', '.tar', '.gz'])
                        if not has_ext:
                            filename = filename + detected_ext
            
            # 如果没有从响应头获取到文件名，使用 token + 检测到的扩展名
            if not filename:
                filename = f"feishu_file_{file_token}{detected_ext}"
            
            # 重命名临时文件
            final_filepath = os.path.join(download_dir, filename)
            if os.path.exists(final_filepath):
                os.remove(final_filepath)
            os.rename(temp_filepath, final_filepath)
            
            if logger:
                logger.info(f"飞书文件下载成功: {final_filepath}")
            
            return {"success": True, "error": None, "downloaded_files": [filename]}
        else:
            return {"success": False, "error": f"飞书文件下载失败，状态码: {response.status_code}", "downloaded_files": []}
    
    except Exception as e:
        return {"success": False, "error": f"飞书文件下载异常: {str(e)}", "downloaded_files": []}


def download_network_share(unc_path, download_dir, logger=None):
    """从网络共享路径复制文件"""
    try:
        # 从环境变量读取网络共享凭据
        network_servers_json = os.environ.get("NETWORK_SERVERS", "[]")
        network_servers = json.loads(network_servers_json)
        
        # 解析 UNC 路径: \\server\share\path\file
        if not unc_path.startswith("\\\\"):
            return {"success": False, "error": "不是有效的 UNC 路径", "downloaded_files": []}
        
        parts = unc_path[2:].split("\\", 2)
        if len(parts) < 2:
            return {"success": False, "error": "UNC 路径格式错误", "downloaded_files": []}
        
        server = parts[0]
        share = parts[1].split("\\")[0]
        
        # 查找匹配的服务器凭据
        credentials = None
        for srv in network_servers:
            if srv.get("server") == server:
                credentials = srv
                break
        
        if not credentials:
            if logger:
                logger.warning(f"未找到服务器 {server} 的凭据，尝试直接访问")
        
        # Windows 下使用 net use 挂载（如果有凭据）
        if credentials and sys.platform == "win32":
            username = credentials.get("username")
            password = credentials.get("password")
            share_path = f"\\\\{server}\\{share}"
            
            # 尝试挂载网络驱动器
            mount_cmd = f'net use "{share_path}" /user:{username} {password}'
            try:
                os.system(mount_cmd + " >nul 2>&1")
            except Exception:
                pass
        
        # 检查源路径是否存在
        if not os.path.exists(unc_path):
            return {"success": False, "error": f"网络路径不存在或无法访问: {unc_path}", "downloaded_files": []}
        
        os.makedirs(download_dir, exist_ok=True)
        
        # 如果是文件，检查是否需要复制整个父目录
        if os.path.isfile(unc_path):
            filename = os.path.basename(unc_path)
            
            # 特殊处理：如果是 __exp_main.txt，复制整个父目录以保留完整日志上下文
            if filename == "__exp_main.txt":
                parent_dir = os.path.dirname(unc_path)
                parent_name = os.path.basename(parent_dir)
                dest_parent = os.path.join(download_dir, parent_name)
                
                try:
                    # 创建目标目录
                    os.makedirs(dest_parent, exist_ok=True)
                    
                    # 复制父目录中的所有文件
                    copied_files = []
                    for item in os.listdir(parent_dir):
                        src_item = os.path.join(parent_dir, item)
                        dst_item = os.path.join(dest_parent, item)
                        
                        if os.path.isfile(src_item):
                            shutil.copy2(src_item, dst_item)
                            copied_files.append(item)
                        elif os.path.isdir(src_item):
                            if os.path.exists(dst_item):
                                shutil.rmtree(dst_item)
                            shutil.copytree(src_item, dst_item)
                            copied_files.append(item)
                    
                    if logger:
                        logger.info(f"网络共享目录复制成功（包含 {len(copied_files)} 个项目）: {dest_parent}")
                    
                    return {"success": True, "error": None, "downloaded_files": [parent_name]}
                    
                except Exception as e:
                    if logger:
                        logger.warning(f"复制父目录失败，回退到只复制文件: {e}")
                    # 回退到只复制文件
                    dest_path = os.path.join(download_dir, filename)
                    shutil.copy2(unc_path, dest_path)
                    if logger:
                        logger.info(f"网络共享文件复制成功: {dest_path}")
                    return {"success": True, "error": None, "downloaded_files": [filename]}
            else:
                # 普通文件，直接复制
                dest_path = os.path.join(download_dir, filename)
                shutil.copy2(unc_path, dest_path)
                
                if logger:
                    logger.info(f"网络共享文件复制成功: {dest_path}")
                
                return {"success": True, "error": None, "downloaded_files": [filename]}
        
        # 如果是目录，递归复制
        elif os.path.isdir(unc_path):
            dir_name = os.path.basename(unc_path.rstrip("\\"))
            dest_path = os.path.join(download_dir, dir_name)
            
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.copytree(unc_path, dest_path)
            
            if logger:
                logger.info(f"网络共享目录复制成功: {dest_path}")
            
            return {"success": True, "error": None, "downloaded_files": [dir_name]}
        else:
            return {"success": False, "error": "路径既不是文件也不是目录", "downloaded_files": []}
    
    except Exception as e:
        return {"success": False, "error": f"网络共享复制异常: {str(e)}", "downloaded_files": []}


def download_http_direct(url, download_dir, logger=None):
    """直接下载 HTTP 链接"""
    if requests is None:
        return {"success": False, "error": "requests 模块未安装", "downloaded_files": []}
    
    try:
        # 从 URL 提取文件名
        filename = url.split("/")[-1].split("?")[0]
        if not filename:
            filename = "downloaded_file"
        
        os.makedirs(download_dir, exist_ok=True)
        filepath = os.path.join(download_dir, filename)
        
        if logger:
            logger.info(f"开始下载 HTTP 文件: {url}")
        
        # 流式下载
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(filepath, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if logger and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            if downloaded % (10 * 1024 * 1024) < 8192:  # 每 10MB 打印一次
                                logger.info(f"下载进度: {progress:.1f}%")
        
        if logger:
            logger.info(f"HTTP 文件下载成功: {filepath}")
        
        return {"success": True, "error": None, "downloaded_files": [filename]}
    
    except Exception as e:
        return {"success": False, "error": f"HTTP 下载异常: {str(e)}", "downloaded_files": []}


class BoxLogDownloader:
    def __init__(self, download_dir, headless=False, max_retries=2):
        self.download_dir = os.path.abspath(download_dir)
        self.headless = headless
        self.max_retries = max_retries
        self.playwright = None
        self.browser = None
        self.headless_fallback_used = False
        self.logger = logging.getLogger("box-log-download")

    def _lazy_imports(self):
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as e:
            raise SystemExit(f"缺少依赖，无法执行 box 下载脚本: {e}")
        return {
            "sync_playwright": sync_playwright,
            "TimeoutError": PlaywrightTimeoutError,
        }

    def _find_browser_executable(self):
        candidates = [
            os.environ.get("CHROME_BINARY"),
            shutil.which("chrome"),
            shutil.which("chrome.exe"),
            shutil.which("msedge"),
            shutil.which("msedge.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return os.path.abspath(candidate)
        raise RuntimeError("未找到可用的 Chrome/Edge 浏览器，请通过 CHROME_BINARY 指定。")

    def setup_browser(self):
        libs = self._lazy_imports()
        sync_playwright = libs["sync_playwright"]
        os.makedirs(self.download_dir, exist_ok=True)
        self.playwright = sync_playwright().start()
        launch_kwargs = {
            "headless": self.headless,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
        }
        try:
            self.browser = self.playwright.chromium.launch(**launch_kwargs)
        except Exception:
            executable_path = self._find_browser_executable()
            launch_kwargs["executable_path"] = executable_path
            self.browser = self.playwright.chromium.launch(**launch_kwargs)
        return self.browser

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

    def extract_password_from_url(self, url):
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "pwd" in params and params["pwd"]:
            return params["pwd"][0]
        match = re.search(r"pwd=([^&]+)", url)
        return match.group(1) if match else None

    def _new_page(self):
        if not self.browser:
            self.setup_browser()
        context = self.browser.new_context(
            accept_downloads=True,
            locale="zh-CN",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page.set_default_timeout(15000)
        return context, page

    def _click_first_button(self, page, names):
        for name in names:
            try:
                locator = page.get_by_role("button", name=name)
                if locator.count() > 0:
                    locator.first.click()
                    return True
            except Exception:
                continue
            try:
                locator = page.locator("button").filter(has_text=name)
                if locator.count() > 0:
                    locator.first.click(force=True)
                    return True
            except Exception:
                continue
            try:
                clicked = page.evaluate(
                    """(text) => {
                        const btn = Array.from(document.querySelectorAll('button'))
                          .find(el => (el.innerText || '').includes(text));
                        if (!btn) return false;
                        btn.click();
                        return true;
                    }""",
                    name,
                )
                if clicked:
                    return True
            except Exception:
                continue
        return False

    def _fill_password_if_needed(self, page, password):
        if not password:
            return
        filled = False
        textboxes = [
            page.locator("input"),
            page.locator("input[type='password']"),
            page.locator("input[placeholder*='密码']"),
            page.get_by_role("textbox"),
        ]
        for locator in textboxes:
            try:
                if locator.count() > 0:
                    locator.first.fill(password)
                    filled = True
                    break
            except Exception:
                continue
        if not filled:
            try:
                filled = page.evaluate(
                    """(pwd) => {
                        const input = document.querySelector('input');
                        if (!input) return false;
                        input.value = pwd;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }""",
                    password,
                )
            except Exception:
                filled = False
        if not filled:
            raise RuntimeError("未找到可填写的分享密码输入框")
        self._click_first_button(page, ["确认", "提取"])
        page.wait_for_timeout(1500)

    def _download_from_page(self, page):
        with page.expect_download(timeout=120000) as download_info:
            if not self._click_first_button(page, ["下载全部", "批量下载", "下载"]):
                raise RuntimeError("未找到可点击的下载按钮")
        download = download_info.value
        target_path = os.path.join(self.download_dir, download.suggested_filename)
        download.save_as(target_path)
        if not os.path.exists(target_path):
            raise RuntimeError("下载动作已触发，但文件没有落盘到下载目录")
        return [os.path.basename(target_path)]

    def _goto_with_retry(self, page, url, attempts=3):
        last_error = None
        for _ in range(attempts):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=120000)
                return
            except Exception as e:
                last_error = e
                page.wait_for_timeout(1500)
        raise last_error

    def download_single_url(self, url):
        libs = self._lazy_imports()
        timeout_error = libs["TimeoutError"]
        context, page = self._new_page()
        try:
            self._goto_with_retry(page, url, attempts=3)
            page.wait_for_timeout(2000)
            password = self.extract_password_from_url(url)
            self._fill_password_if_needed(page, password)
            try:
                page.get_by_role("button", name="下载全部").wait_for(state="visible", timeout=15000)
            except timeout_error:
                page.wait_for_timeout(2000)
            return self._download_from_page(page)
        except Exception as e:
            message = str(e)
            if self.headless and (not self.headless_fallback_used) and "ERR_CONNECTION_CLOSED" in message:
                self.logger.warning("Headless 模式访问 FRBOX 断连，自动降级为 headed 重试。")
                self.headless_fallback_used = True
                try:
                    context.close()
                except Exception:
                    pass
                self.close()
                self.headless = False
                return self.download_single_url(url)
            raise
        finally:
            try:
                context.close()
            except Exception:
                pass

    def download_multiple_urls(self, urls, prefer_http=True, num_threads=8, chunk_size=10*1024*1024):
        results = []
        browser_needed = False

        for index, url in enumerate(urls, start=1):
            item = {
                "url": url,
                "index": index,
                "success": False,
                "downloaded_files": [],
                "error": None,
                "download_method": None,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }

            if prefer_http:
                self.logger.info(f"[{index}/{len(urls)}] 尝试 HTTP 下载: {url}")
                http_result = try_http_download(
                    url=url,
                    download_dir=self.download_dir,
                    num_threads=num_threads,
                    chunk_size=chunk_size,
                    logger=self.logger
                )
                if http_result.get("success"):
                    item["downloaded_files"] = http_result["downloaded_files"]
                    item["success"] = True
                    item["download_method"] = "http"
                    item["error"] = None
                    results.append(item)
                    continue
                else:
                    item["error"] = f"HTTP 下载失败: {http_result.get('error')}"
                    if http_result.get("skip_browser"):
                        self.logger.warning(f"HTTP 下载失败（链接无效/过期），跳过浏览器下载: {http_result.get('error')}")
                        item["download_method"] = "http"
                        results.append(item)
                        continue
                    else:
                        self.logger.warning(f"HTTP 下载失败: {http_result.get('error')}，将尝试浏览器下载")

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
                except Exception as e:
                    item["error"] = f"浏览器下载第 {attempt} 次失败: {e}"
                    item["download_method"] = "browser"
                    time.sleep(2)

            results.append(item)

        if browser_needed:
            self.close()

        return results


def parse_args():
    parser = argparse.ArgumentParser(description="下载 FRBOX/SGBOX 日志到本地目录。")
    parser.add_argument("--issue-key", help="Jira 单号，用于构造下载目录")
    parser.add_argument("--manifest", help="manifest 文件路径")
    parser.add_argument("--download-root", help="下载根目录")
    parser.add_argument("--headless", action="store_true", help="启用无头浏览器模式")
    parser.add_argument("--max-retries", type=int, default=2, help="每个 URL 最大重试次数")
    parser.add_argument("--output", help="结果 JSON 输出路径；默认回写 manifest 或打印到 stdout")
    parser.add_argument("--no-http", action="store_true", help="禁用 HTTP 下载，强制使用浏览器下载")
    parser.add_argument("--threads", type=int, default=8, help="HTTP 下载线程数 (默认: 8)")
    parser.add_argument("--chunk-size", type=int, default=10, help="HTTP 下载分块大小 MB (默认: 10)")
    return parser.parse_args()


def download_box_logs(manifest_path):
    """
    下载 BOX 日志文件（供 pipeline 调用）
    
    Args:
        manifest_path: manifest 文件路径
    
    Returns:
        dict: 下载结果
    """
    configure_stdio()
    logger = logging.getLogger("box-log-download")
    manifest = load_manifest(manifest_path)
    
    issue_key = manifest.get("issue_key", "").strip()
    if not issue_key:
        raise ValueError("manifest 中缺少 issue_key")
    
    # 从新的 manifest 结构读取 URLs
    urls_by_type = manifest.get("jira", {}).get("urls_by_type", {})
    box_urls = list(urls_by_type.get("box", []))
    feishu_urls = list(urls_by_type.get("feishu_file", []))
    network_shares = list(urls_by_type.get("network_share", []))
    http_directs = list(urls_by_type.get("http_direct", []))
    
    all_urls_count = len(box_urls) + len(feishu_urls) + len(network_shares) + len(http_directs)
    
    if all_urls_count == 0:
        raise ValueError("manifest 中没有任何 URL，请先执行 jira-issue-fetch")
    
    # 从环境变量或 manifest 读取 workspace_root
    workspace_root = os.getenv("WORKSPACE_ROOT") or manifest.get("workspace_root") or os.path.join(os.getcwd(), "data_store")
    issue_workspace = os.path.join(workspace_root, issue_key)
    download_root = os.path.join(issue_workspace, "downloads")
    os.makedirs(download_root, exist_ok=True)
    
    raw_results = []
    
    # 下载 BOX 链接
    if box_urls:
        logger.info(f"开始下载 {len(box_urls)} 个 BOX 链接")
        downloader = BoxLogDownloader(
            download_dir=download_root,
            headless=True,
            max_retries=3,
        )
        box_results = downloader.download_multiple_urls(
            box_urls,
            prefer_http=True,
            num_threads=8,
            chunk_size=10 * 1024 * 1024
        )
        for result in box_results:
            result["url_type"] = "box"
        raw_results.extend(box_results)
    
    # 下载飞书文件
    if feishu_urls:
        logger.info(f"开始下载 {len(feishu_urls)} 个飞书文件")
        for index, url in enumerate(feishu_urls, start=1):
            logger.info(f"[{index}/{len(feishu_urls)}] 下载飞书文件: {url}")
            result = download_feishu_file(url, download_root, logger)
            raw_results.append({
                "url": url,
                "url_type": "feishu_file",
                "index": index,
                "success": result["success"],
                "downloaded_files": result["downloaded_files"],
                "error": result["error"],
                "download_method": "feishu_api",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            })
    
    # 复制网络共享文件
    if network_shares:
        logger.info(f"开始复制 {len(network_shares)} 个网络共享路径")
        for index, path in enumerate(network_shares, start=1):
            logger.info(f"[{index}/{len(network_shares)}] 复制网络共享: {path}")
            result = download_network_share(path, download_root, logger)
            raw_results.append({
                "url": path,
                "url_type": "network_share",
                "index": index,
                "success": result["success"],
                "downloaded_files": result["downloaded_files"],
                "error": result["error"],
                "download_method": "network_copy",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            })
    
    # 下载 HTTP 直链
    if http_directs:
        logger.info(f"开始下载 {len(http_directs)} 个 HTTP 直链")
        for index, url in enumerate(http_directs, start=1):
            logger.info(f"[{index}/{len(http_directs)}] 下载 HTTP 文件: {url}")
            result = download_http_direct(url, download_root, logger)
            raw_results.append({
                "url": url,
                "url_type": "http_direct",
                "index": index,
                "success": result["success"],
                "downloaded_files": result["downloaded_files"],
                "error": result["error"],
                "download_method": "http_download",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            })
    
    downloaded_any = any(item.get("success") for item in raw_results)
    download_dirs = [download_root] if downloaded_any else []
    
    return {
        "issue_key": issue_key,
        "download_root": download_root,
        "download_dirs": download_dirs,
        "results": raw_results,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    configure_stdio()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    manifest = load_manifest(args.manifest)

    issue_key = (args.issue_key or manifest.get("issue_key") or "").strip()
    if not issue_key:
        raise SystemExit("缺少 issue_key，请通过 --issue-key 或 manifest 提供。")

    # 从新的 manifest 结构读取 URLs
    urls_by_type = manifest.get("jira", {}).get("urls_by_type", {})
    box_urls = list(urls_by_type.get("box", []))
    feishu_urls = list(urls_by_type.get("feishu_file", []))
    network_shares = list(urls_by_type.get("network_share", []))
    http_directs = list(urls_by_type.get("http_direct", []))
    
    all_urls_count = len(box_urls) + len(feishu_urls) + len(network_shares) + len(http_directs)
    
    if all_urls_count == 0:
        raise SystemExit("manifest 中没有任何 URL，请先执行 jira-issue-fetch。")

    # 从环境变量或 manifest 读取 workspace_root，默认为当前目录下的 data_store
    workspace_root = os.getenv("WORKSPACE_ROOT") or manifest.get("workspace_root") or os.path.join(os.getcwd(), "data_store")
    issue_workspace = os.path.join(workspace_root, issue_key)
    download_root = args.download_root or os.path.join(issue_workspace, "downloads")
    os.makedirs(download_root, exist_ok=True)

    logger = logging.getLogger("box-log-download")
    raw_results = []
    
    # 下载 BOX 链接
    if box_urls:
        logger.info(f"开始下载 {len(box_urls)} 个 BOX 链接")
        downloader = BoxLogDownloader(
            download_dir=download_root,
            headless=args.headless,
            max_retries=args.max_retries,
        )
        box_results = downloader.download_multiple_urls(
            box_urls,
            prefer_http=not args.no_http,
            num_threads=args.threads,
            chunk_size=args.chunk_size * 1024 * 1024
        )
        for result in box_results:
            result["url_type"] = "box"
        raw_results.extend(box_results)
    
    # 下载飞书文件
    if feishu_urls:
        logger.info(f"开始下载 {len(feishu_urls)} 个飞书文件")
        for index, url in enumerate(feishu_urls, start=1):
            logger.info(f"[{index}/{len(feishu_urls)}] 下载飞书文件: {url}")
            result = download_feishu_file(url, download_root, logger)
            raw_results.append({
                "url": url,
                "url_type": "feishu_file",
                "index": index,
                "success": result["success"],
                "downloaded_files": result["downloaded_files"],
                "error": result["error"],
                "download_method": "feishu_api",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            })
    
    # 复制网络共享文件
    if network_shares:
        logger.info(f"开始复制 {len(network_shares)} 个网络共享路径")
        for index, path in enumerate(network_shares, start=1):
            logger.info(f"[{index}/{len(network_shares)}] 复制网络共享: {path}")
            result = download_network_share(path, download_root, logger)
            raw_results.append({
                "url": path,
                "url_type": "network_share",
                "index": index,
                "success": result["success"],
                "downloaded_files": result["downloaded_files"],
                "error": result["error"],
                "download_method": "network_copy",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            })
    
    # 下载 HTTP 直链
    if http_directs:
        logger.info(f"开始下载 {len(http_directs)} 个 HTTP 直链")
        for index, url in enumerate(http_directs, start=1):
            logger.info(f"[{index}/{len(http_directs)}] 下载 HTTP 文件: {url}")
            result = download_http_direct(url, download_root, logger)
            raw_results.append({
                "url": url,
                "url_type": "http_direct",
                "index": index,
                "success": result["success"],
                "downloaded_files": result["downloaded_files"],
                "error": result["error"],
                "download_method": "http_download",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            })

    downloaded_any = any(item.get("success") for item in raw_results)
    download_dirs = [download_root] if downloaded_any else []

    result = {
        "issue_key": issue_key,
        "download_root": download_root,
        "download_dirs": download_dirs,
        "results": raw_results,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

    manifest["issue_key"] = issue_key
    manifest["workspace_root"] = issue_workspace
    manifest["downloads"]["download_root"] = download_root
    manifest["downloads"]["download_dirs"] = download_dirs
    manifest["downloads"]["results"] = raw_results

    if args.manifest:
        save_manifest(args.manifest, manifest)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

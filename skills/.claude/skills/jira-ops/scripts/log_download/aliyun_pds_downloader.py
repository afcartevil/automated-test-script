#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云PDS网盘分享链接下载工具
支持从FRBOX/SGBOX等阿里云PDS网盘分享链接下载文件
支持多线程分块下载，提升下载速度
"""

import re
import os
import json
import time
import threading
import logging
import requests
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置日志
logger = logging.getLogger(__name__)


class MultiThreadDownloader:
    def __init__(self, num_threads: int = 8, chunk_size: int = 10 * 1024 * 1024):
        self.num_threads = num_threads
        self.chunk_size = chunk_size
        self.lock = threading.Lock()
        self.downloaded_bytes = 0
        self.start_time = 0
        self.total_size = 0
        self.status = "准备中"
        self._stop_progress = False
        
    def download_range(self, url: str, start: int, end: int, file_path: Path, 
                       temp_dir: Path, chunk_index: int, headers: dict) -> int:
        temp_file = temp_dir / f"chunk_{chunk_index}.tmp"
        
        if temp_file.exists():
            downloaded = temp_file.stat().st_size
            if downloaded >= (end - start + 1):
                with self.lock:
                    self.downloaded_bytes += downloaded
                return downloaded
            start = start + downloaded
        
        req_headers = headers.copy()
        req_headers["Range"] = f"bytes={start}-{end}"
        
        try:
            response = requests.get(url, headers=req_headers, stream=True, timeout=30)
            
            if response.status_code not in (200, 206):
                return 0
                
            mode = 'ab' if temp_file.exists() else 'wb'
            with open(temp_file, mode) as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        with self.lock:
                            self.downloaded_bytes += len(chunk)
                            
            return temp_file.stat().st_size
            
        except Exception as e:
            logger.error(f"分块 {chunk_index} 下载失败: {e}")
            return 0
    
    def merge_chunks(self, temp_dir: Path, output_path: Path, num_chunks: int):
        with open(output_path, 'wb') as outfile:
            for i in range(num_chunks):
                chunk_file = temp_dir / f"chunk_{i}.tmp"
                if chunk_file.exists():
                    with open(chunk_file, 'rb') as infile:
                        outfile.write(infile.read())
                    chunk_file.unlink()
    
    def download(self, url: str, file_path: Path, headers: dict = None) -> bool:
        if headers is None:
            headers = {}
            
        try:
            print(f"\r检测服务器能力...                    ", end="")
            response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
            
            total_size = int(response.headers.get('content-length', 0))
            accept_ranges = response.headers.get('accept-ranges', '').lower() == 'bytes'
            
            if total_size == 0 or not accept_ranges:
                return self._stream_download(url, file_path, headers)
            
            self.total_size = total_size
            self.downloaded_bytes = 0
            self.start_time = time.time()
            
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            if file_path.exists():
                existing_size = file_path.stat().st_size
                if existing_size == total_size:
                    print(f"\r文件已存在且完整，跳过下载                    ")
                    return True
            
            if total_size < self.chunk_size:
                return self._single_thread_download(url, file_path, headers)
            
            temp_dir = file_path.parent / f".{file_path.name}.chunks"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            num_chunks = (total_size + self.chunk_size - 1) // self.chunk_size
            chunks = []
            
            for i in range(num_chunks):
                start = i * self.chunk_size
                end = min(start + self.chunk_size - 1, total_size - 1)
                chunks.append((start, end, i))
            
            print(f"\r使用 {self.num_threads} 线程分块下载，共 {num_chunks} 个分块                    ")
            
            self._stop_progress = False
            progress_thread = threading.Thread(
                target=self._print_progress_loop, 
                daemon=True
            )
            progress_thread.start()
            
            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                futures = {
                    executor.submit(
                        self.download_range, url, start, end, file_path, temp_dir, idx, headers
                    ): idx for start, end, idx in chunks
                }
                
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"下载出错: {e}")
            
            self._stop_progress = True
            progress_thread.join(timeout=1)
            
            print(f"\r合并分块...                    ", end="")
            self.merge_chunks(temp_dir, file_path, num_chunks)
            
            try:
                temp_dir.rmdir()
            except:
                pass
            
            return True
            
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False
    
    def _stream_download(self, url: str, file_path: Path, headers: dict) -> bool:
        try:
            print(f"\r开始流式下载...                    ", end="")
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            self.total_size = total_size
            self.downloaded_bytes = 0
            self.start_time = time.time()
            
            self._stop_progress = False
            progress_thread = threading.Thread(
                target=self._print_progress_loop, 
                daemon=True
            )
            progress_thread.start()
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        with self.lock:
                            self.downloaded_bytes += len(chunk)
            
            self._stop_progress = True
            progress_thread.join(timeout=1)
            print()
            return True
            
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False
    
    def _single_thread_download(self, url: str, file_path: Path, headers: dict) -> bool:
        try:
            print(f"\r下载中...                    ", end="")
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            self.total_size = total_size
            self.downloaded_bytes = 0
            self.start_time = time.time()
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        self.downloaded_bytes += len(chunk)
                        self._print_progress_once()
            
            print()
            return True
            
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return False
    
    def _print_progress_loop(self):
        while not self._stop_progress:
            self._print_progress_once()
            time.sleep(0.3)
    
    def _print_progress_once(self):
        with self.lock:
            if self.total_size > 0:
                progress = (self.downloaded_bytes / self.total_size) * 100
                elapsed = time.time() - self.start_time
                if elapsed > 0 and self.downloaded_bytes > 0:
                    speed = self.downloaded_bytes / elapsed
                    speed_str = self._format_size(speed) + "/s"
                    
                    remaining_bytes = self.total_size - self.downloaded_bytes
                    if speed > 0:
                        eta_seconds = remaining_bytes / speed
                        eta_str = self._format_time(eta_seconds)
                    else:
                        eta_str = "计算中"
                else:
                    speed_str = "计算中..."
                    eta_str = "计算中"
                
                downloaded_str = self._format_size(self.downloaded_bytes)
                total_str = self._format_size(self.total_size)
                
                print(f"\r下载进度: {progress:.1f}% ({downloaded_str}/{total_str}) 速度: {speed_str} 剩余: {eta_str}    ", end="")
    
    def _format_time(self, seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes}分{secs}秒"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}时{minutes}分"
    
    def _format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"


class AliyunPDSDownloader:
    def __init__(self, share_url: str, download_dir: str = "./downloads", 
                 num_threads: int = 8, chunk_size: int = 10 * 1024 * 1024):
        self.share_url = share_url
        self.download_dir = Path(download_dir)
        self.share_id: Optional[str] = None
        self.share_pwd: Optional[str] = None
        self.domain_id: Optional[str] = None
        self.share_token: Optional[str] = None
        self.api_endpoint: Optional[str] = None
        self.num_threads = num_threads
        self.chunk_size = chunk_size
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        
    def parse_share_url(self) -> bool:
        url = urlparse(self.share_url)
        path_parts = url.path.split('/')
        
        for i, part in enumerate(path_parts):
            if part == 's' and i + 1 < len(path_parts):
                self.share_id = path_parts[i + 1]
                break
        
        query_params = parse_qs(url.query)
        self.share_pwd = query_params.get('pwd', [None])[0]
        self.domain_id = query_params.get('domainId', [None])[0]
        
        if not self.share_id:
            logger.error(f"无法从链接中提取share_id: {self.share_url}")
            return False
        
        # 如果没有 domainId，根据域名自动推断
        if not self.domain_id:
            hostname = url.hostname.lower() if url.hostname else ""
            if 'frbox' in hostname:
                self.domain_id = 'fra315'
                print(f"检测到 FRBOX 链接，使用默认 domainId: fra315")
            elif 'sgbox' in hostname:
                self.domain_id = 'sg776'
                print(f"检测到 SGBOX 链接，使用默认 domainId: sg776")
            else:
                logger.error(f"无法从链接中提取 domainId，且无法自动推断: {self.share_url}")
                logger.info("请在 URL 中添加 domainId 参数，例如: ?domainId=fra315")
                return False
            
        self.api_endpoint = f"https://{self.domain_id}.api.aliyunpds.com"
        print(f"解析分享链接成功:")
        print(f"  share_id: {self.share_id}")
        print(f"  share_pwd: {self.share_pwd or '(无提取码)'}")
        print(f"  domain_id: {self.domain_id}")
        print(f"  API地址: {self.api_endpoint}")
        return True
    
    def get_share_token(self) -> bool:
        if not self.share_id or not self.api_endpoint:
            logger.error("缺少必要参数: share_id 或 api_endpoint")
            return False
            
        url = f"{self.api_endpoint}/v2/share_link/get_share_token"
        payload = {
            "share_id": self.share_id
        }
        
        if self.share_pwd:
            payload["share_pwd"] = self.share_pwd
            
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            self.share_token = data.get("share_token")
            if not self.share_token:
                logger.error(f"获取share_token失败: {data}")
                return False
                
            print(f"获取share_token成功，有效期: {data.get('expires_in', 7200)}秒")
            self.session.headers["x-share-token"] = self.share_token
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"错误详情: {json.dumps(error_data, ensure_ascii=False, indent=2)}")
                except:
                    logger.error(f"响应内容: {e.response.text}")
            return False
    
    def list_files(self, parent_file_id: str = "root") -> List[Dict[str, Any]]:
        if not self.share_token:
            logger.error("缺少share_token，请先调用get_share_token()")
            return []
            
        url = f"{self.api_endpoint}/v2/file/list"
        payload = {
            "share_id": self.share_id,
            "parent_file_id": parent_file_id,
            "limit": 100
        }
        
        all_items = []
        
        try:
            while True:
                response = self.session.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                items = data.get("items", [])
                all_items.extend(items)
                
                marker = data.get("next_marker")
                if not marker:
                    break
                    
                payload["marker"] = marker
                
            return all_items
            
        except requests.exceptions.RequestException as e:
            logger.error(f"列举文件失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"错误详情: {json.dumps(error_data, ensure_ascii=False, indent=2)}")
                except:
                    logger.error(f"响应内容: {e.response.text}")
            return []
    
    def get_download_url(self, file_id: str, file_name: str = "") -> Optional[str]:
        url = f"{self.api_endpoint}/v2/file/get_download_url"
        payload = {
            "share_id": self.share_id,
            "file_id": file_id,
            "expire_sec": 3600
        }
        
        if file_name:
            payload["file_name"] = file_name
            
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            download_url = data.get("url")
            if not download_url:
                logger.error(f"获取下载地址失败: {data}")
                return None
                
            return download_url
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取下载地址失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"错误详情: {json.dumps(error_data, ensure_ascii=False, indent=2)}")
                except:
                    logger.error(f"响应内容: {e.response.text}")
            return None
    
    def download_file(self, download_url: str, file_path: Path) -> bool:
        downloader = MultiThreadDownloader(
            num_threads=self.num_threads,
            chunk_size=self.chunk_size
        )
        return downloader.download(download_url, file_path)
    
    def process_directory(self, parent_file_id: str = "root", current_path: Path = None):
        if current_path is None:
            current_path = self.download_dir
            
        print(f"\n正在扫描目录: {current_path}")
        items = self.list_files(parent_file_id)
        
        if not items:
            logger.warning("目录为空或获取失败")
            return
            
        for item in items:
            item_type = item.get("type", "file")
            item_name = item.get("name", "unknown")
            item_id = item.get("file_id")
            
            if item_type == "folder":
                print(f"\n[文件夹] {item_name}")
                folder_path = current_path / item_name
                folder_path.mkdir(parents=True, exist_ok=True)
                self.process_directory(item_id, folder_path)
            else:
                file_size = item.get("size", 0)
                size_str = self._format_size(file_size)
                print(f"\n[文件] {item_name} ({size_str})")
                
                file_path = current_path / item_name
                
                if file_path.exists():
                    existing_size = file_path.stat().st_size
                    if existing_size == file_size:
                        print(f"文件已存在且大小相同，跳过: {file_path}")
                        continue
                
                print(f"获取下载地址...", end="\r")
                download_url = self.get_download_url(item_id, item_name)
                
                if download_url:
                    success = self.download_file(download_url, file_path)
                    if success:
                        print(f"\n下载完成: {file_path}")
                    else:
                        print(f"\n下载失败: {file_path}")
                    
    def _format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"
    
    def run(self):
        print("=" * 60)
        print("阿里云PDS网盘分享链接下载工具 (多线程版)")
        print(f"线程数: {self.num_threads}, 分块大小: {self._format_size(self.chunk_size)}")
        print("=" * 60)
        
        print("\n[1/4] 解析分享链接...")
        if not self.parse_share_url():
            return False
            
        print("\n[2/4] 获取分享令牌...")
        if not self.get_share_token():
            return False
            
        print("\n[3/4] 扫描并下载文件...")
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.process_directory()
        
        print("\n[4/4] 下载完成!")
        print(f"文件保存目录: {self.download_dir.absolute()}")
        return True


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="阿里云PDS网盘分享链接下载工具 (支持多线程下载)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python aliyun_pds_downloader.py "https://frbox.transsion.com/disk/s/RhPHMzvzv8L?pwd=303023&domainId=fra315"
  python aliyun_pds_downloader.py "https://xxx.com/disk/s/xxxxx?pwd=xxx&domainId=xxx" -o ./my_downloads -t 16
  python aliyun_pds_downloader.py "分享链接" -t 8 -c 20  # 8线程，20MB分块

多线程下载说明:
  - 默认使用8线程下载，可通过 -t 参数调整
  - 默认分块大小为10MB，可通过 -c 参数调整（单位MB）
  - 服务器需支持 Range 请求才能启用多线程下载
        """
    )
    
    parser.add_argument("share_url", help="阿里云PDS网盘分享链接")
    parser.add_argument("-o", "--output", default="./downloads", help="下载目录 (默认: ./downloads)")
    parser.add_argument("-t", "--threads", type=int, default=8, help="下载线程数 (默认: 8)")
    parser.add_argument("-c", "--chunk", type=int, default=10, help="分块大小 MB (默认: 10)")
    
    args = parser.parse_args()
    
    downloader = AliyunPDSDownloader(
        share_url=args.share_url,
        download_dir=args.output,
        num_threads=args.threads,
        chunk_size=args.chunk * 1024 * 1024
    )
    downloader.run()


if __name__ == "__main__":
    main()

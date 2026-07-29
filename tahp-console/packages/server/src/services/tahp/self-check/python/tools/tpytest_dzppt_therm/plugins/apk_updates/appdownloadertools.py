import os
import random
import time
import requests
from threading import Thread
from tqdm import tqdm

class ApkDownloaderTools:
    def __init__(self) -> None:
        # 定义多个 User-Agent
        self.headers = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
                    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:142.0) Gecko/20100101 Firefox/142.0"
                   ]

    def get_random_headers(self):
        # 随机选择一个 User-Agent
        return {"User-Agent": random.choice(self.headers)}
        
    def download_w_progress_bar(self, url: str, file_name: str, total_size=None | int):
        print(f"#{file_name}")
        
        # 添加重试机制，最多重试100次，参考crawler.py的逻辑
        for attempt in range(100):
            try:
                # 随机选择一个请求头，防止反爬
                headers = self.get_random_headers()
                response = requests.get(url=url, stream=True, headers=headers, timeout=30)
                
                # 检查HTTP状态码
                if response.status_code != 200:
                    print(f"HTTP状态码错误: {response.status_code}，等待5分钟后重试...")
                    if attempt < 99:
                        time.sleep(300)  # 等待5分钟
                        continue
                    else:
                        print(f"❌ 下载失败: {file_name} (HTTP状态码: {response.status_code})")
                        # 删除可能创建的空文件
                        try:
                            if os.path.exists(file_name):
                                os.remove(file_name)
                        except:
                            pass
                        return False
                
                # 获取文件大小
                try:
                    total_size = int(response.headers.get("content-length"))
                except (ValueError, TypeError):
                    pass
                    
                if total_size is None or total_size == 0:
                    print(f"⚠️ 文件大小异常，可能是无效的下载链接: {url}")
                    # 删除可能创建的空文件
                    try:
                        if os.path.exists(file_name):
                            os.remove(file_name)
                    except:
                        pass
                    return False
                
                # 开始下载
                chunk_size = 1024
                progress_bar = tqdm(total=total_size, unit="B", unit_scale=True) if total_size > 0 else None
                
                with open(file_name, "wb") as f:
                    for data in response.iter_content(chunk_size=chunk_size):
                        if progress_bar:
                            progress_bar.update(len(data))
                        f.write(data)
                        
                if progress_bar:
                    progress_bar.close()
                if os.path.getsize(file_name) == 0:
                    print(f"❌ 下载的文件为空: {file_name}")
                    os.remove(file_name)
                    return False
                print(f"✅ 下载完成: {file_name}")
                return True  # 下载成功
                
            except requests.exceptions.Timeout:
                print(f"请求超时: {url}，等待5分钟后重试...")
                if attempt < 99:  # 不是最后一次尝试
                    time.sleep(300)  # 等待5分钟
                else:
                    print(f"❌ 下载失败: {file_name} (请求超时)")
                    return False
                    
            except requests.exceptions.RequestException as e:
                print(f"请求失败: {e}，等待5分钟后重试...")
                if attempt < 99:  # 不是最后一次尝试
                    time.sleep(300)  # 等待5分钟
                else:
                    print(f"❌ 下载失败: {file_name} (请求异常)")
                    return False
                    
            except Exception as e:
                print(f"下载过程中发生错误: {e}，等待5分钟后重试...")
                if attempt < 99:
                    time.sleep(300)
                else:
                    print(f"❌ 下载失败: {file_name} (未知错误)")
                    return False

    def download_in_t_background(self, url: str, file_name: str):
        """后台下载，也添加重试机制"""
        def download_with_retry():
            for attempt in range(100):
                try:
                    headers = self.get_random_headers()
                    response = requests.get(url=url, stream=True, headers=headers, timeout=30)
                    
                    if response.status_code != 200:
                        print(f"后台下载HTTP状态码错误: {response.status_code}，等待5分钟后重试...")
                        if attempt < 99:
                            time.sleep(300)
                            continue
                        else:
                            print(f"❌ 后台下载失败: {file_name}")
                            return
                    
                    chunk_size = 1024
                    with open(file_name, "wb") as f:
                        for data in response.iter_content(chunk_size=chunk_size):
                            f.write(data)
                    
                    print(f"✅ 后台下载完成: {file_name}")
                    return
                    
                except requests.exceptions.Timeout:
                    print(f"后台下载超时，等待5分钟后重试...")
                    if attempt < 99:
                        time.sleep(300)
                    else:
                        print(f"❌ 后台下载失败: {file_name}")
                        return
                        
                except Exception as e:
                    print(f"后台下载错误: {e}，等待5分钟后重试...")
                    if attempt < 99:
                        time.sleep(300)
                    else:
                        print(f"❌ 后台下载失败: {file_name}")
                        return
        
        Thread(target=download_with_retry).start()



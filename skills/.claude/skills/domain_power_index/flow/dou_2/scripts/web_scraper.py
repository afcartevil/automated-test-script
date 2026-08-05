#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网页内容抓取工具：上传bugreport压缩包到 http://localhost:9999/ 并提取 WiFi Traffic Per App 相关信息。
工作区根解析见 analysis/base/lib/repo_paths.py。
"""

import requests
from bs4 import BeautifulSoup
def _setup_utf8_stdio() -> None:
    import sys
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

import sys
import os
import json


def upload_bugreport(bugreport_path):
    """
    上传bugreport压缩包到Battery Historian
    """
    # 首先访问主页
    base_url = "http://localhost:9999"
    upload_url = f"{base_url}/upload"
    
    try:
        print(f"正在上传 bugreport: {bugreport_path}")
        print(f"文件大小: {os.path.getsize(bugreport_path)} 字节")
        
        # 检查文件是否存在
        if not os.path.exists(bugreport_path):
            print(f"文件不存在: {bugreport_path}")
            return None
        
        # 检查文件是否是有效的ZIP文件
        try:
            import zipfile
            with zipfile.ZipFile(bugreport_path, 'r') as zf:
                file_list = zf.namelist()
                print(f"ZIP文件包含 {len(file_list)} 个文件")
                
                # 检查是否包含bugreport相关文件
                bugreport_files = [f for f in file_list if 'bugreport' in f.lower() or 'dumpstate' in f.lower()]
                if bugreport_files:
                    print("找到bugreport相关文件:")
                    for f in bugreport_files[:5]:  # 只显示前5个文件
                        print(f"  - {f}")
                else:
                    print("未找到bugreport相关文件")
                    print("ZIP文件内容:")
                    for f in file_list[:10]:  # 只显示前10个文件
                        print(f"  - {f}")
        except zipfile.BadZipFile:
            print("文件不是有效的ZIP文件")
            return None
        
        # 创建会话以维护状态
        session = requests.Session()
        
        # 先访问主页
        print("正在访问Battery Historian主页...")
        home_response = session.get(base_url, timeout=10)
        home_response.raise_for_status()
        print("访问主页成功！")
        
        # 准备文件 - 尝试使用不同的字段名
        with open(bugreport_path, 'rb') as f:
            # 尝试使用bugreport字段，这是Battery Historian常用的字段名
            files = {'bugreport': (os.path.basename(bugreport_path), f, 'application/zip')}
            data = {'submit': 'Upload'}
            
            # 发送POST请求上传文件并点击submit
            print("正在上传文件并点击submit...")
            response = session.post(upload_url, files=files, data=data, timeout=120, allow_redirects=True)
            
            # 检查响应
            print(f"响应状态码: {response.status_code}")
            print(f"响应URL: {response.url}")
            
            # 检查响应内容
            if response.status_code == 200:
                if "not a valid zip file" in response.text:
                    print("错误: Battery Historian 认为文件不是有效的ZIP文件")
                    return None
                elif "failed to analyze file" in response.text:
                    print("错误: Battery Historian 分析文件失败")
                    print(f"响应内容: {response.text[:500]}...")
                    return None
                else:
                    print("上传成功！")
                    # 保存上传后的响应URL
                    session.upload_response_url = response.url
                    return session
            else:
                print(f"上传失败，状态码: {response.status_code}")
                print(f"响应内容: {response.text[:500]}...")
                return None
        
    except requests.RequestException as e:
        print(f"上传失败: {e}")
        return None
    except Exception as e:
        print(f"处理文件时出错: {e}")
        return None


def fetch_wifi_traffic_per_app(session=None, html_content=None):
    """
    抓取网页内容并提取 WiFi Traffic Per App 信息
    """
    # 尝试多个可能的结果页面路径
    possible_urls = [
        "http://localhost:9999/",
        "http://localhost:9999/historian",
        "http://localhost:9999/view",
        "http://localhost:9999/result",
        "http://localhost:9999/powerstats",
        "http://localhost:9999/power_statistics"
    ]
    
    try:
        if html_content:
            print("正在解析上传后的网页内容...")
            soup = BeautifulSoup(html_content, 'html.parser')
        else:
            # 尝试每个可能的URL
            soup = None
            for url in possible_urls:
                try:
                    print(f"正在请求网页: {url}")
                    if session:
                        response = session.get(url, timeout=10)
                    else:
                        response = requests.get(url, timeout=10)
                    response.raise_for_status()  # 检查请求是否成功
                    
                    print("请求成功，正在解析网页内容...")
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # 检查是否找到WiFi Traffic Per App
                    for element in soup.find_all('*'):
                        if 'WiFi Traffic Per App' in element.get_text():
                            print(f"在 {url} 找到 WiFi Traffic Per App 相关内容")
                            break
                    else:
                        # 未找到，继续尝试下一个URL
                        continue
                    break
                except Exception as e:
                    print(f"访问 {url} 失败: {e}")
                    continue
            
            if not soup:
                print("所有URL都访问失败，使用默认页面")
                if session:
                    response = session.get("http://localhost:9999/", timeout=10)
                else:
                    response = requests.get("http://localhost:9999/", timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
        
        # 查找包含 "WiFi Traffic Per App" 的部分
        wifi_traffic_section = None
        
        # 方法1：查找包含该文本的标签
        for element in soup.find_all(['h1', 'h2', 'h3', 'div', 'section']):
            if 'WiFi Traffic Per App' in element.get_text():
                wifi_traffic_section = element
                break
        
        # 方法2：如果方法1失败，搜索整个文档
        if not wifi_traffic_section:
            for element in soup.find_all('*'):
                if 'WiFi Traffic Per App' in element.get_text():
                    wifi_traffic_section = element
                    break
        
        if wifi_traffic_section:
            print("\n=== WiFi Traffic Per App ===")
            
            # 提取该部分的所有内容
            section_text = wifi_traffic_section.get_text(separator='\n', strip=True)
            out_path = os.path.join(os.getcwd(), "wifi_traffic_section.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(section_text)
            print(f"wrote {out_path}")
            
            # 尝试提取表格数据（如果存在）
            table = wifi_traffic_section.find('table')
            if table:
                print("\n=== 表格数据 ===")
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    print('\t'.join(cell_texts))
        else:
            print("未找到 'WiFi Traffic Per App' 相关内容")
            
            # 打印网页的主要内容，以便了解网页结构
            print("\n=== 网页主要内容 ===")
            print(soup.get_text(separator='\n', strip=True)[:2000] + "..." if len(soup.get_text()) > 2000 else soup.get_text())
            
    except requests.RequestException as e:
        print(f"网络请求失败: {e}")
        return False
    except Exception as e:
        print(f"处理网页内容时出错: {e}")
        return False
    
    return True


if __name__ == "__main__":
    _setup_utf8_stdio()
    if len(sys.argv) < 2:
        bugreport_path = os.environ.get("DOU_BUGREPORT_PATH", "").strip()
        if not bugreport_path:
            print("用法: python web_scraper.py <bugreport.zip>", file=sys.stderr)
            print("或设置环境变量 DOU_BUGREPORT_PATH", file=sys.stderr)
            raise SystemExit(2)
    else:
        bugreport_path = sys.argv[1]
    
    print("开始上传 bugreport 到 Battery Historian...")
    
    # 上传bugreport
    session = upload_bugreport(bugreport_path)
    
    if session:
        print("\n上传成功！等待分析完成...")
        # 等待一段时间让分析完成
        import time
        time.sleep(10)  # 等待10秒
        
        print("\n正在访问分析结果页面...")
        # 上传成功后，访问分析结果页面
        try:
            # 首先使用上传后的响应URL
            if hasattr(session, 'upload_response_url'):
                analysis_url = session.upload_response_url
                print(f"正在访问分析结果页面: {analysis_url}")
                response = session.get(analysis_url, timeout=10)
                response.raise_for_status()
            else:
                # 如果没有保存的URL，尝试访问Power Statistics页面
                power_stats_url = "http://localhost:9999/powerstats"
                print(f"正在访问Power Statistics页面: {power_stats_url}")
                response = session.get(power_stats_url, timeout=10)
                response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找包含 "WiFi Traffic Per App" 的部分
            print("正在查找 'WiFi Traffic Per App' 相关内容...")
            
            # 搜索所有包含 "WiFi Traffic Per App" 的元素
            wifi_traffic_elements = soup.find_all(string=lambda text: text and 'WiFi Traffic Per App' in text)
            
            if wifi_traffic_elements:
                print("找到 'WiFi Traffic Per App' 相关内容")
                
                # 找到包含这些元素的父容器
                for element in wifi_traffic_elements:
                    # 找到包含这个文本的父容器
                    container = element.find_parent()
                    
                    # 查找包含表格的父容器
                    while container:
                        if container.find('table'):
                            break
                        container = container.find_parent()
                    
                    if container:
                        print("\n=== WiFi Traffic Per App ===")
                        # 找到表格
                        table = container.find('table')
                        if table:
                            # 提取表头
                            headers = []
                            header_rows = table.find_all('thead')
                            if not header_rows:
                                # 如果没有thead，尝试从第一行获取表头
                                header_rows = [table.find('tr')]
                            
                            for header_row in header_rows:
                                if header_row:
                                    header_cells = header_row.find_all(['th', 'td'])
                                    for cell in header_cells:
                                        title = cell.get('title', cell.get_text(strip=True))
                                        headers.append(title)
                            
                            # 打印表头
                            if headers:
                                print('\t'.join(headers))
                            
                            # 提取表格数据
                            rows = table.find_all('tr')
                            for row in rows:
                                cells = row.find_all('td')
                                if cells:
                                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                                    # 移除HTML实体编码
                                    cell_texts = [text.replace('&#34;', '"') for text in cell_texts]
                                    print('\t'.join(cell_texts))
                            break
            else:
                print("未找到 'WiFi Traffic Per App' 相关内容")
                # 尝试访问Historian页面
                print("\n尝试访问Historian页面...")
                historian_url = "http://localhost:9999/historian"
                response = session.get(historian_url, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 查找包含 "WiFi Traffic Per App" 的部分
                print("正在查找 'WiFi Traffic Per App' 相关内容...")
                wifi_traffic_elements = soup.find_all(string=lambda text: text and 'WiFi Traffic Per App' in text)
                
                if wifi_traffic_elements:
                    print("找到 'WiFi Traffic Per App' 相关内容")
                    
                    # 找到包含这些元素的父容器
                    for element in wifi_traffic_elements:
                        # 找到包含这个文本的父容器
                        container = element.find_parent()
                        
                        # 查找包含表格的父容器
                        while container:
                            if container.find('table'):
                                break
                            container = container.find_parent()
                        
                        if container:
                            print("\n=== WiFi Traffic Per App ===")
                            # 找到表格
                            table = container.find('table')
                            if table:
                                # 提取表头
                                headers = []
                                header_rows = table.find_all('thead')
                                if not header_rows:
                                    # 如果没有thead，尝试从第一行获取表头
                                    header_rows = [table.find('tr')]
                                
                                for header_row in header_rows:
                                    if header_row:
                                        header_cells = header_row.find_all(['th', 'td'])
                                        for cell in header_cells:
                                            title = cell.get('title', cell.get_text(strip=True))
                                            headers.append(title)
                                
                                # 打印表头
                                if headers:
                                    print('\t'.join(headers))
                                
                                # 提取表格数据
                                rows = table.find_all('tr')
                                for row in rows:
                                    cells = row.find_all('td')
                                    if cells:
                                        cell_texts = [cell.get_text(strip=True) for cell in cells]
                                        # 移除HTML实体编码
                                        cell_texts = [text.replace('&#34;', '"') for text in cell_texts]
                                        print('\t'.join(cell_texts))
                                break
                else:
                    print("未找到 'WiFi Traffic Per App' 相关内容")
        except Exception as e:
            print(f"访问页面失败: {e}")
    else:
        print("上传失败，尝试直接从主页获取信息...")
        success = fetch_wifi_traffic_per_app()
    
    print("\n抓取完成！")

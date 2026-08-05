"""
CPU日志分析模块 - 修正版（一次性获取所有数据）
包含CPU分析相关的所有功能，供app.py调用
"""
import re
import os
import pandas as pd
import json
import time
import uuid
import threading
import traceback
from datetime import datetime
from collections import defaultdict
from flask import jsonify
from paths import CPU_CACHE_DIR
from utils import CacheManager


class CPUAnalyzerAPI:
    """CPU分析API类，封装所有CPU分析相关的功能"""
    
    def __init__(self, app_state):
        """初始化CPU分析器API
        
        Args:
            app_state: 应用状态对象
        """
        self.app_state = app_state
    
    def analyze_cpu(self, suffix):
        """分析CPU数据（一次性获取所有数据）"""
        if not self.app_state:
            return jsonify({'success': False, 'message': '应用未初始化'})
        
        self.app_state.current_suffix = suffix
        
        try:
            analyzer = CPULogAnalyzer(
                scene1_folder=self.app_state.scene1_folder,
                scene2_folder=self.app_state.scene2_folder,
                scene1_platform=self.app_state.scene1_platform,
                scene2_platform=self.app_state.scene2_platform,
                scene_excel_path=self.app_state.scene_excel_path
            )
            
            # 检查缓存
            cache_key = f"cpu_analysis_{suffix}"
            if cache_key in self.app_state.analysis_cache:
                result = self.app_state.analysis_cache[cache_key]
                result['from_cache'] = True
                return jsonify({
                    'success': True,
                    'from_cache': True,
                    'suffix': suffix,
                    'data': result
                })
            
            # 执行分析（一次性获取所有数据）
            result = analyzer.analyze(suffix)
            
            # 确保结果中包含平均值数据
            if result and 'averages' not in result:
                # 从原始数据中提取平均值
                if 'scene1' in result and 'averages' in result['scene1']:
                    result['averages'] = {
                        'scene1': result['scene1'].get('averages', []),
                        'scene2': result['scene2'].get('averages', []),
                        'diff': result.get('diff', [])
                    }
            
            self.app_state.analysis_cache[cache_key] = result
            
            return jsonify({
                'success': True,
                'from_cache': False,
                'suffix': suffix,
                'data': result
            })
            
        except Exception as e:
            return jsonify({'success': False, 'message': f'分析失败: {str(e)}'})
    
    def analyze_cpu_quick(self, suffix):
        """快速分析入口：优先返回内存/磁盘缓存，否则异步启动后台分析并返回 job_id"""
        if not self.app_state:
            return jsonify({'success': False, 'message': '应用未初始化'})

        self.app_state.current_suffix = suffix

        analyzer = CPULogAnalyzer(
            scene1_folder=self.app_state.scene1_folder,
            scene2_folder=self.app_state.scene2_folder,
            scene1_platform=self.app_state.scene1_platform,
            scene2_platform=self.app_state.scene2_platform,
            scene_excel_path=self.app_state.scene_excel_path
        )

        cache_key_data = {
            'suffix': suffix,
            'scene1_folder': self.app_state.scene1_folder,
            'scene2_folder': self.app_state.scene2_folder,
            'scene1_platform': self.app_state.scene1_platform,
            'scene2_platform': self.app_state.scene2_platform
        }
        md5_key = analyzer.cache_manager.get_cache_key(cache_key_data)
        mem_key = f"cpu_analysis_{suffix}"

        # 1) 内存缓存（兼容旧逻辑）
        if mem_key in self.app_state.analysis_cache:
            result = self.app_state.analysis_cache[mem_key]
            result['from_cache'] = True
            return jsonify({'success': True, 'from_cache': True, 'suffix': suffix, 'data': result})

        # 2) 磁盘缓存
        disk_result = analyzer.cache_manager.get(md5_key)
        if disk_result:
            # 验证磁盘缓存是否包含关键字段（cpu/process/averages）
            valid = False
            try:
                if isinstance(disk_result, dict):
                    if disk_result.get('averages_enhanced'):
                        valid = True
                    if disk_result.get('diff_data') and len(disk_result.get('diff_data', [])) > 0:
                        valid = True
                    if disk_result.get('cpu_usage') and len(disk_result.get('cpu_usage', [])) > 0:
                        valid = True
            except Exception:
                valid = False

            if valid:
                disk_result['from_cache'] = True
                # 同步写入内存缓存，便于前端快速访问
                self.app_state.analysis_cache[mem_key] = disk_result
                self.app_state.analysis_cache[md5_key] = disk_result
                return jsonify({'success': True, 'from_cache': True, 'suffix': suffix, 'data': disk_result})
            else:
                # 缓存不完整，忽略并启动后台分析
                print(f"磁盘缓存不完整或缺失关键数据，忽略缓存，后缀: {suffix}")

        # 3) 启动后台作业
        job_id = str(uuid.uuid4())
        with self.app_state.jobs_lock:
            self.app_state.jobs[job_id] = {
                'status': 'running',
                'suffix': suffix,
                'started_at': time.time(),
                'finished_at': None,
                'result': None,
                'progress': 0,
                'message': '作业已启动'
            }

        def run_analysis_job(jid, sfx, anl, key, memk):
            # 报告进度的回调函数，线程安全更新作业状态
            def report_progress(percent, msg=None):
                try:
                    with self.app_state.jobs_lock:
                        job = self.app_state.jobs.get(jid)
                        if job:
                            job['progress'] = max(0, min(100, int(percent)))
                            if msg is not None:
                                job['message'] = str(msg)
                except Exception:
                    pass

            try:
                report_progress(2, '开始检查缓存')
                res = anl.analyze(sfx, progress_callback=report_progress)
                res['from_cache'] = False

                report_progress(95, '保存缓存')
                anl.cache_manager.set(key, res)
                self.app_state.analysis_cache[memk] = res
                self.app_state.analysis_cache[key] = res

                with self.app_state.jobs_lock:
                    self.app_state.jobs[jid]['status'] = 'completed'
                    self.app_state.jobs[jid]['finished_at'] = time.time()
                    self.app_state.jobs[jid]['result'] = res
                    self.app_state.jobs[jid]['progress'] = 100
                    self.app_state.jobs[jid]['message'] = '完成'
            except Exception as e:
                tb = traceback.format_exc()
                # 保存详细的错误信息，便于调试
                try:
                    os.makedirs('./analysis_cache', exist_ok=True)
                    with open('./analysis_cache/job_errors.log', 'a', encoding='utf-8') as f:
                        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Job {jid} failed:\n")
                        f.write(tb + '\n')
                except Exception:
                    pass
                with self.app_state.jobs_lock:
                    self.app_state.jobs[jid]['status'] = 'failed'
                    self.app_state.jobs[jid]['finished_at'] = time.time()
                    self.app_state.jobs[jid]['error'] = tb
                    self.app_state.jobs[jid]['message'] = str(e)
                    self.app_state.jobs[jid]['progress'] = 0

        thread = threading.Thread(target=run_analysis_job, args=(job_id, suffix, analyzer, md5_key, mem_key), daemon=True)
        thread.start()

        return jsonify({'success': True, 'started': True, 'job_id': job_id, 'message': '分析已在后台启动'})
    
    def get_cpu_view_data(self, suffix, view_type='cpu'):
        """获取CPU视图数据（根据视图类型返回不同格式）"""
        if not self.app_state:
            return jsonify({'success': False, 'message': '应用未初始化'})
        
        if not suffix:
            return jsonify({'success': False, 'message': '请选择后缀'})
        
        # 获取缓存数据
        cache_key = f"cpu_analysis_{suffix}"
        if cache_key not in self.app_state.analysis_cache:
            return jsonify({'success': False, 'message': '请先执行CPU分析'})
        
        cpu_data = self.app_state.analysis_cache[cache_key]
        
        # 根据视图类型格式化数据
        if view_type == 'cpu':
            # CPU使用率视图数据
            result = {
                'view_type': 'cpu',
                'scene1': {
                    'cpu_usage': cpu_data.get('scene1', {}).get('cpu_usage_display', ''),
                    'time_range': cpu_data.get('time_ranges', {}).get('scene1', {})
                },
                'scene2': {
                    'cpu_usage': cpu_data.get('scene2', {}).get('cpu_usage_display', ''),
                    'time_range': cpu_data.get('time_ranges', {}).get('scene2', {})
                }
            }
        else:  # 'process'
            # 进程数据视图
            result = {
                'view_type': 'process',
                'scene1': {
                    'process_data': cpu_data.get('scene1', {}).get('process_data', []),
                    'time_range': cpu_data.get('time_ranges', {}).get('scene1', {})
                },
                'scene2': {
                    'process_data': cpu_data.get('scene2', {}).get('process_data', []),
                    'time_range': cpu_data.get('time_ranges', {}).get('scene2', {})
                }
            }
        
        return jsonify({
            'success': True,
            'data': result
        })
    
    def switch_cpu_view(self, view_type='cpu'):
        """切换CPU分析视图"""
        # 这里可以记录用户的视图偏好到session
        if self.app_state:
            self.app_state.current_view = view_type
        
        return jsonify({
            'success': True,
            'view_type': view_type,
            'message': f'已切换到{view_type}视图'
        })
    
    def clear_current_cache(self, suffix):
        """清除当前后缀的缓存"""
        if not self.app_state:
            return jsonify({'success': False, 'message': '应用未初始化'})
        
        if not suffix:
            return jsonify({'success': False, 'message': '请指定要清除的后缀'})
        
        cache_key = f"cpu_analysis_{suffix}"
        deleted = False
        
        # 1. 清除内存缓存
        if cache_key in self.app_state.analysis_cache:
            del self.app_state.analysis_cache[cache_key]
            deleted = True
        
        # 2. 清除文件缓存
        from utils import CacheManager
        cache_manager = CacheManager(str(CPU_CACHE_DIR))
        cache_manager.clear(cache_key)
        
        return jsonify({
            'success': True,
            'message': f'后缀_{suffix}的缓存已清除',
            'deleted': deleted
        })
    
    def analyze_cpu_quick(self, suffix):
        """快速分析入口：优先返回内存/磁盘缓存，否则异步启动后台分析并返回 job_id"""
        if not self.app_state:
            return jsonify({'success': False, 'message': '应用未初始化'})

        self.app_state.current_suffix = suffix

        analyzer = CPULogAnalyzer(
            scene1_folder=self.app_state.scene1_folder,
            scene2_folder=self.app_state.scene2_folder,
            scene1_platform=self.app_state.scene1_platform,
            scene2_platform=self.app_state.scene2_platform,
            scene_excel_path=self.app_state.scene_excel_path
        )

        cache_key_data = {
            'suffix': suffix,
            'scene1_folder': self.app_state.scene1_folder,
            'scene2_folder': self.app_state.scene2_folder,
            'scene1_platform': self.app_state.scene1_platform,
            'scene2_platform': self.app_state.scene2_platform
        }
        md5_key = analyzer.cache_manager.get_cache_key(cache_key_data)
        mem_key = f"cpu_analysis_{suffix}"

        # 1) 内存缓存（兼容旧逻辑）
        if mem_key in self.app_state.analysis_cache:
            result = self.app_state.analysis_cache[mem_key]
            result['from_cache'] = True
            return jsonify({'success': True, 'from_cache': True, 'suffix': suffix, 'data': result})

        # 2) 磁盘缓存
        disk_result = analyzer.cache_manager.get(md5_key)
        if disk_result:
            # 验证磁盘缓存是否包含关键字段（cpu/process/averages）
            valid = False
            try:
                if isinstance(disk_result, dict):
                    if disk_result.get('averages_enhanced'):
                        valid = True
                    if disk_result.get('diff_data') and len(disk_result.get('diff_data', [])) > 0:
                        valid = True
                    if disk_result.get('cpu_usage') and len(disk_result.get('cpu_usage', [])) > 0:
                        valid = True
            except Exception:
                valid = False

            if valid:
                disk_result['from_cache'] = True
                # 同步写入内存缓存，便于前端快速访问
                self.app_state.analysis_cache[mem_key] = disk_result
                self.app_state.analysis_cache[md5_key] = disk_result
                return jsonify({'success': True, 'from_cache': True, 'suffix': suffix, 'data': disk_result})
            else:
                # 缓存不完整，忽略并启动后台分析
                print(f"磁盘缓存不完整或缺失关键数据，忽略缓存，后缀: {suffix}")


        # 3) 启动后台作业
        import uuid
        import time
        import threading
        import traceback
        import os
        from datetime import datetime
        
        job_id = str(uuid.uuid4())
        with self.app_state.jobs_lock:
            self.app_state.jobs[job_id] = {
                'status': 'running',
                'suffix': suffix,
                'started_at': time.time(),
                'finished_at': None,
                'result': None,
                'progress': 0,
                'message': '作业已启动'
            }

        def run_analysis_job(jid, sfx, anl, key, memk):
            # 报告进度的回调函数，线程安全更新作业状态
            def report_progress(percent, msg=None):
                try:
                    with self.app_state.jobs_lock:
                        job = self.app_state.jobs.get(jid)
                        if job:
                            job['progress'] = max(0, min(100, int(percent)))
                            if msg is not None:
                                job['message'] = str(msg)
                except Exception:
                    pass

            try:
                report_progress(2, '开始检查缓存')
                res = anl.analyze(sfx, progress_callback=report_progress)
                res['from_cache'] = False

                report_progress(95, '保存缓存')
                anl.cache_manager.set(key, res)
                self.app_state.analysis_cache[memk] = res
                self.app_state.analysis_cache[key] = res

                with self.app_state.jobs_lock:
                    self.app_state.jobs[jid]['status'] = 'completed'
                    self.app_state.jobs[jid]['finished_at'] = time.time()
                    self.app_state.jobs[jid]['result'] = res
                    self.app_state.jobs[jid]['progress'] = 100
                    self.app_state.jobs[jid]['message'] = '完成'
            except Exception as e:
                tb = traceback.format_exc()
                # 保存详细的错误信息，便于调试
                try:
                    os.makedirs('./analysis_cache', exist_ok=True)
                    with open('./analysis_cache/job_errors.log', 'a', encoding='utf-8') as f:
                        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Job {jid} failed:\n")
                        f.write(tb + '\n')
                except Exception:
                    pass
                with self.app_state.jobs_lock:
                    self.app_state.jobs[jid]['status'] = 'failed'
                    self.app_state.jobs[jid]['finished_at'] = time.time()
                    self.app_state.jobs[jid]['error'] = tb
                    self.app_state.jobs[jid]['message'] = str(e)
                    self.app_state.jobs[jid]['progress'] = 0

        thread = threading.Thread(target=run_analysis_job, args=(job_id, suffix, analyzer, md5_key, mem_key), daemon=True)
        thread.start()

        return jsonify({'success': True, 'started': True, 'job_id': job_id, 'message': '分析已在后台启动'})
    
    def quick_check_cache(self, suffix):
        """快速检查缓存是否存在（1秒内返回）"""
        try:
            import time
            start_time = time.time()
            if not self.app_state:
                return jsonify({'success': False, 'exists': False, 'message': '应用未初始化'}), 400

            # 使用 CPULogAnalyzer 的 CacheManager 构造缓存键并检查磁盘缓存
            analyzer = CPULogAnalyzer(
                scene1_folder=self.app_state.scene1_folder,
                scene2_folder=self.app_state.scene2_folder,
                scene1_platform=self.app_state.scene1_platform,
                scene2_platform=self.app_state.scene2_platform,
                scene_excel_path=self.app_state.scene_excel_path
            )

            cache_key_data = {
                'suffix': suffix,
                'scene1_folder': self.app_state.scene1_folder,
                'scene2_folder': self.app_state.scene2_folder,
                'scene1_platform': self.app_state.scene1_platform,
                'scene2_platform': self.app_state.scene2_platform
            }

            cache_key = analyzer.cache_manager.get_cache_key(cache_key_data)
            exists = analyzer.cache_manager.get(cache_key) is not None

            elapsed = time.time() - start_time
            print(f"快速缓存检查耗时: {elapsed:.3f}秒, suffix={suffix}, exists={exists}")

            return jsonify({
                'success': True,
                'exists': bool(exists),
                'elapsed_ms': round(elapsed * 1000, 1)
            })

        except Exception as e:
            print(f"快速缓存检查错误: {str(e)}")
            return jsonify({
                'success': False,
                'exists': False,
                'message': str(e)
            }), 500
    
    def check_cache_status(self, suffixes):
        """检查多个后缀的缓存状态"""
        try:
            # 使用 CPULogAnalyzer 的 CacheManager 检查磁盘缓存是否存在
            analyzer = CPULogAnalyzer(
                scene1_folder=self.app_state.scene1_folder,
                scene2_folder=self.app_state.scene2_folder,
                scene1_platform=self.app_state.scene1_platform,
                scene2_platform=self.app_state.scene2_platform,
                scene_excel_path=self.app_state.scene_excel_path
            )

            cache_status = {}
            for suffix in suffixes:
                cache_key_data = {
                    'suffix': suffix,
                    'scene1_folder': self.app_state.scene1_folder,
                    'scene2_folder': self.app_state.scene2_folder,
                    'scene1_platform': self.app_state.scene1_platform,
                    'scene2_platform': self.app_state.scene2_platform
                }
                key = analyzer.cache_manager.get_cache_key(cache_key_data)
                cache_status[suffix] = analyzer.cache_manager.get(key) is not None

            return cache_status

        except Exception as e:
            print(f"检查缓存状态错误: {str(e)}")
            return {}


# 创建全局CPU分析器实例
cpu_analyzer_api = None

def init_cpu_analyzer(app_state):
    """初始化CPU分析器API
    
    Args:
        app_state: 应用状态对象
    """
    global cpu_analyzer_api
    cpu_analyzer_api = CPUAnalyzerAPI(app_state)
    return cpu_analyzer_api


def get_cpu_analyzer():
    """获取CPU分析器实例"""
    global cpu_analyzer_api
    return cpu_analyzer_api


class CPULogAnalyzer:
    """CPU日志分析器（一次性获取CPU和进程数据）"""
    
    def __init__(self, scene1_folder, scene2_folder, 
                 scene1_platform, scene2_platform, scene_excel_path):
        self.scene1_folder = scene1_folder
        self.scene2_folder = scene2_folder
        self.scene1_platform = scene1_platform
        self.scene2_platform = scene2_platform
        self.scene_excel_path = scene_excel_path
        self.cache_manager = CacheManager(str(CPU_CACHE_DIR))
    
    def extract_suffix(self, name):
        """从名称中提取数字后缀"""
        if not isinstance(name, str):
            name = str(name)
        
        name = name.strip()
        match = re.search(r"_(\d+)$", name)
        if match:
            return match.group(1)
        return None
    
    def find_test_report_in_folder(self, folder_path):
        """在文件夹中查找场景报告 xlsx（与 utils.find_test_report 一致，含回退）。"""
        from utils import find_test_report
        return find_test_report(folder_path)
    
    def parse_excel_time(self, excel_path, target_suffix):
        """解析Excel中的时间范围"""
        try:
            df = pd.read_excel(excel_path, sheet_name="report")
            
            if not all(col in df.columns for col in ["name", "starttime", "endtime"]):
                return None
            
            for _, row in df.iterrows():
                name = str(row["name"]).strip()
                name_suffix = self.extract_suffix(name)
                
                if name_suffix == target_suffix:
                    start_str = str(row["starttime"])
                    end_str = str(row["endtime"])
                    
                    try:
                        # 解析开始时间
                        if "." in start_str:
                            start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S.%f")
                        else:
                            start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                        
                        # 解析结束时间
                        if "." in end_str:
                            end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S.%f")
                        else:
                            end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                        
                        return {
                            "start": start,
                            "end": end,
                            "matched_name": name,
                            "base_year": start.year
                        }
                    except:
                        continue
            
            return None
            
        except Exception as e:
            print(f"解析Excel时间失败: {str(e)}")
            return None
    
    def load_log_content(self, log_info):
        """加载日志文件内容 - 优化版，支持大文件分块读取和 .gz 文件"""
        try:
            import gzip
            file_path = log_info.get("path")
            if not file_path or not os.path.exists(file_path):
                return []
            file_size = os.path.getsize(file_path)
            
            # 判断是否为 gz 文件
            is_gz = file_path.endswith(".gz")
            
            if file_size > 100 * 1024 * 1024:  # 100MB
                lines = []
                if is_gz:
                    with gzip.open(file_path, "rt", encoding="utf-8", errors="ignore") as f:
                        max_bytes = 1024 * 1024 * 1024  # 1GB
                        bytes_read = 0
                        for line in f:
                            lines.append(line)
                            bytes_read += len(line.encode('utf-8'))
                            if bytes_read > max_bytes:
                                break
                else:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        max_bytes = 1024 * 1024 * 1024  # 1GB
                        bytes_read = 0
                        for line in f:
                            lines.append(line)
                            bytes_read += len(line.encode('utf-8'))
                            if bytes_read > max_bytes:
                                break
                return lines
            else:
                if is_gz:
                    with gzip.open(file_path, "rt", encoding="utf-8", errors="ignore") as f:
                        return f.readlines()
                else:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        return f.readlines()
        except Exception as e:
            print(f"加载日志文件失败 {log_info.get('path')}: {e}")
            return []
    
    def analyze_quick_preview(self, suffix, progress_callback=None):
        """快速预览模式：只分析基本信息，不进行详细的数据处理"""

        def _report(pct, msg=None):
            if progress_callback:
                try:
                    progress_callback(pct, msg)
                except Exception:
                    pass

        _report(1, '生成缓存键')
        cache_key_data = {
            "suffix": suffix,
            "scene1_folder": self.scene1_folder,
            "scene2_folder": self.scene2_folder,
            "scene1_platform": self.scene1_platform,
            "scene2_platform": self.scene2_platform,
            "scene_excel_path": self.scene_excel_path
        }

        cache_key = self.cache_manager.get_cache_key(cache_key_data)

        # 检查缓存
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            cached_result["from_cache"] = True
            _report(100, '使用缓存')
            return cached_result

        _report(10, '查找 testReport.xlsx')
        scene1_excel = self.find_test_report_in_folder(self.scene1_folder)
        scene2_excel = self.find_test_report_in_folder(self.scene2_folder)

        if not scene1_excel or not scene2_excel:
            raise ValueError("未找到testReport.xlsx文件")

        _report(20, '解析时间范围')
        time_range1 = self.parse_excel_time(scene1_excel, suffix)
        time_range2 = self.parse_excel_time(scene2_excel, suffix)

        if not time_range1 or not time_range2:
            raise ValueError(f"未找到后缀 {suffix} 的时间范围")

        _report(30, '获取日志文件列表')
        from utils import get_platform_logs

        scene1_logs = get_platform_logs(self.scene1_folder, self.scene1_platform)
        scene2_logs = get_platform_logs(self.scene2_folder, self.scene2_platform)

        if not scene1_logs:
            raise ValueError("版本1没有找到相关日志文件")
        if not scene2_logs:
            raise ValueError("版本2没有找到相关日志文件")

        # 快速统计：只读取每个文件的开头部分
        _report(50, '快速统计日志文件')

        scene1_stats = self.get_log_file_stats(scene1_logs[:3])  # 只检查前3个文件
        scene2_stats = self.get_log_file_stats(scene2_logs[:3])

        _report(80, '获取场景描述')
        scene_desc = "无描述"
        try:
            merged_df = pd.read_excel(self.scene_excel_path, usecols=["name", "desc"])
            for name in merged_df["name"]:
                name_str = str(name).strip()
                name_suffix = self.extract_suffix(name_str)
                if name_suffix == suffix:
                    desc_row = merged_df[merged_df["name"] == name].iloc[0]
                    scene_desc = desc_row.get("desc", "无描述")
                    break
        except Exception:
            scene_desc = "无描述"

        # 返回快速预览结果
        result = {
            "success": True,
            "from_cache": False,
            "suffix": suffix,
            "scene_desc": scene_desc,
            "preview_mode": True,
            "scene1": {
                "log_files_count": len(scene1_logs),
                "estimated_lines": scene1_stats.get("total_lines", 0),
                "estimated_size_mb": scene1_stats.get("total_size_mb", 0),
                "time_range": f"{time_range1['start'].strftime('%m-%d %H:%M:%S')} 至 {time_range1['end'].strftime('%m-%d %H:%M:%S')}",
                "platform": self.scene1_platform,
                "excel_path": scene1_excel
            },
            "scene2": {
                "log_files_count": len(scene2_logs),
                "estimated_lines": scene2_stats.get("total_lines", 0),
                "estimated_size_mb": scene2_stats.get("total_size_mb", 0),
                "time_range": f"{time_range2['start'].strftime('%m-%d %H:%M:%S')} 至 {time_range2['end'].strftime('%m-%d %H:%M:%S')}",
                "platform": self.scene2_platform,
                "excel_path": scene2_excel
            },
            "estimated_analysis_time": self.estimate_analysis_time(scene1_stats, scene2_stats),
            "recommendations": self.get_performance_recommendations(scene1_stats, scene2_stats)
        }

        _report(100, '预览完成')
        return result

    def get_log_file_stats(self, log_files):
        """获取日志文件的快速统计信息"""
        total_lines = 0
        total_size = 0

        for log_info in log_files[:3]:  # 只检查前3个文件
            try:
                file_size = os.path.getsize(log_info["path"])
                total_size += file_size

                # 快速估算行数（读取文件开头部分）
                with open(log_info["path"], "r", encoding="utf-8", errors="ignore") as f:
                    sample_lines = []
                    for i, line in enumerate(f):
                        if i >= 100:  # 只读取前100行作为样本
                            break
                        sample_lines.append(len(line))

                    if sample_lines:
                        avg_line_length = sum(sample_lines) / len(sample_lines)
                        estimated_lines = int(file_size / avg_line_length)
                        total_lines += min(estimated_lines, 1000000)  # 限制最大估算行数
            except Exception:
                continue

        return {
            "total_lines": total_lines,
            "total_size_mb": total_size / (1024 * 1024),
            "file_count": len(log_files)
        }

    def estimate_analysis_time(self, stats1, stats2):
        """估算分析时间（分钟）"""
        total_lines = stats1.get("total_lines", 0) + stats2.get("total_lines", 0)
        total_size_mb = stats1.get("total_size_mb", 0) + stats2.get("total_size_mb", 0)

        # 基于经验估算：每100万行大约需要2-3分钟
        time_by_lines = (total_lines / 1000000) * 2.5

        # 基于文件大小估算：每100MB大约需要1分钟
        time_by_size = (total_size_mb / 100) * 1.0

        estimated_minutes = max(time_by_lines, time_by_size, 0.5)  # 最少0.5分钟

        return round(estimated_minutes, 1)

    def get_performance_recommendations(self, stats1, stats2):
        """获取性能优化建议"""
        recommendations = []

        total_size_mb = stats1.get("total_size_mb", 0) + stats2.get("total_size_mb", 0)
        total_lines = stats1.get("total_lines", 0) + stats2.get("total_lines", 0)

        if total_size_mb > 500:
            recommendations.append("日志文件较大，建议使用SSD存储以提高读取速度")

        if total_lines > 2000000:
            recommendations.append("日志行数较多，分析可能需要5分钟以上")

        if total_lines > 5000000:
            recommendations.append("日志行数非常多，建议缩小时间范围或使用更少的日志文件")

        if not recommendations:
            recommendations.append("日志文件大小适中，分析时间预计在2分钟以内")

        return recommendations
    
# 在你的 parse_cpu_log 方法中，需要更新正则表达式：
    def parse_cpu_log(self, merged_logs, time_range, platform="高通"):
        """解析CPU日志（同时获取CPU使用率和进程数据）- 优化版本"""
        start_time = time_range["start"]
        end_time = time_range["end"]
        base_year = time_range["base_year"]

        cpu_usage = []           # CPU使用率数据（对象格式）
        process_data = []        # 进程数据（按Perf块分组）
        perf_start_times = []    # Perf块开始时间

        current_time = None
        in_perf_block = False
        current_perf_processes = []
        block_start_time = None

        # 性能优化：预编译正则表达式
        time_pattern = re.compile(
            r"(\[?)(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+|\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)(\]?)"
        )

        perf_start_pattern = re.compile(r".*\[K\]\[Perf\]\s+TRAN Perf Statistic start\s+\(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\)")

        process_pattern = re.compile(r".*\[K\]\s+(\d+)%\s+(\d+)\s+(.*?)\s+(\d+)\(ns\)\s+(-?\d+)")

        cpu_usage_pattern = re.compile(r".*\[K\]\s*.*?Cpus Usage.*?")

        cpu_cores_pattern = re.compile(r".*\[K\]\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%")

        cpu_header_pattern = re.compile(r".*Usage.*PID.*Name.*Total.*Oom_Score_Adj", re.IGNORECASE)

        # 性能优化：限制处理的总行数，避免无限循环
        max_lines = min(len(merged_logs), 5000000)  # 最多处理500万行
        processed_lines = 0

        # ========== 日志解析主循环 ==========
        for line_num, line in enumerate(merged_logs[:max_lines], 1):
            processed_lines += 1

            # 性能优化：每处理10000行输出一次进度
            if processed_lines % 10000 == 0:
                print(f"已处理 {processed_lines}/{len(merged_logs)} 行日志")

            # 1. 提取时间戳
            time_match = time_pattern.search(line)
            if time_match:
                raw_time_str = time_match.group(2).strip()
                try:
                    if "-" in raw_time_str and raw_time_str.count("-") == 2:
                        # 带年份的格式：2024-01-30 10:27:08.818362
                        log_time = datetime.strptime(raw_time_str, "%Y-%m-%d %H:%M:%S.%f")
                        current_time = log_time.replace(year=base_year)
                    else:
                        # 不带年份的格式：01-30 10:27:08.818362
                        log_time = datetime.strptime(raw_time_str, "%m-%d %H:%M:%S.%f")
                        current_time = log_time.replace(year=base_year)

                    # 检查是否在时间范围内
                    if not (start_time <= current_time <= end_time):
                        current_time = None
                        in_perf_block = False
                        current_perf_processes = []
                        block_start_time = None
                        continue
                except Exception as e:
                    # 时间解析失败，重置状态
                    current_time = None
                    in_perf_block = False
                    current_perf_processes = []
                    block_start_time = None
                    continue

            if not current_time:
                # 无有效时间戳，跳过该行
                continue

            # 2. 检测Perf块开始
            if perf_start_pattern.search(line):
                in_perf_block = True
                current_perf_processes = []
                block_start_time = current_time
                continue

            # 3. 跳过CPU表头行
            if cpu_header_pattern.search(line):
                continue

            # 4. 在Perf块中解析进程数据
            if in_perf_block:
                process_match = process_pattern.search(line)
                if process_match:
                    usage = int(process_match.group(1))
                    pid = process_match.group(2)
                    name = process_match.group(3).strip()
                    total = process_match.group(4)
                    oom_score = process_match.group(5)

                    current_perf_processes.append({
                        "时间": current_time.strftime("%m-%d %H:%M:%S.%f")[:-2],
                        "使用率(%)": usage,
                        "PID": pid,
                        "进程名": name,
                        "总时间(ns)": total,
                        "OOM评分": oom_score,
                        "原始行号": line_num
                    })

            # 5. 检测CPU使用率行（同时结束当前Perf块）
            if cpu_usage_pattern.search(line):
                # 清理空白格（多个空格替换为单个空格）
                cleaned_line = re.sub(r'\s+', ' ', line.strip())

                # 尝试提取CPU核心使用率
                cpu_values = []
                cpu_match = cpu_cores_pattern.search(line)
                if cpu_match:
                    # 提取8个核心的使用率
                    cpu_values = [int(cpu_match.group(i)) for i in range(1, 9)]

                # 构建CPU数据对象
                cpu_data = {
                    "raw": cleaned_line,  # 清理后的原始行
                    "time": current_time.strftime("%m-%d %H:%M:%S.%f")[:-2],
                    "timestamp": current_time.timestamp(),
                    "usage": cpu_values,  # CPU核心使用率数组
                    "has_cores_data": bool(cpu_values),
                    "original_line": line.strip(),  # 原始未清理的行
                    "line_number": line_num
                }
                cpu_usage.append(cpu_data)

                # 保存当前Perf块的进程数据
                if current_perf_processes and block_start_time:
                    perf_start_times.append(block_start_time)
                    process_data.append(current_perf_processes)

                # 重置Perf块状态
                in_perf_block = False
                current_perf_processes = []
                block_start_time = None

        # 6. 处理最后一个Perf块（如果没有遇到CPU使用率行）
        if in_perf_block and current_perf_processes and block_start_time:
            perf_start_times.append(block_start_time)
            process_data.append(current_perf_processes)

        # 7. 统计信息
        total_cpu_lines = len(cpu_usage)
        total_process_blocks = len(process_data)
        total_processes = sum(len(block) for block in process_data)

        print(f"解析完成: {total_cpu_lines}条CPU记录, {total_process_blocks}个Perf块, {total_processes}个进程 (处理了{processed_lines}行日志)")

        return cpu_usage, process_data, perf_start_times
    
    
    def analyze(self, suffix, progress_callback=None):
        """分析指定后缀的数据（一次性获取所有数据）- 完整版本"""
        
        def _report(pct, msg=None):
            """报告进度"""
            if progress_callback:
                try:
                    progress_callback(pct, msg)
                except Exception:
                    pass
        
        # ========== 第1步：生成缓存键并检查缓存 ==========
        _report(1, '生成缓存键并检查缓存')
        cache_key_data = {
            "suffix": suffix,
            "scene1_folder": self.scene1_folder,
            "scene2_folder": self.scene2_folder,
            "scene1_platform": self.scene1_platform,
            "scene2_platform": self.scene2_platform,
            "scene_excel_path": self.scene_excel_path
        }
        
        cache_key = self.cache_manager.get_cache_key(cache_key_data)
        
        # 检查缓存
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            cached_result["from_cache"] = True
            _report(100, '使用缓存')
            return cached_result
        
        # ========== 第2步：查找testReport.xlsx文件 ==========
        _report(10, '查找 testReport.xlsx')
        scene1_excel = self.find_test_report_in_folder(self.scene1_folder)
        scene2_excel = self.find_test_report_in_folder(self.scene2_folder)
        
        if not scene1_excel or not scene2_excel:
            raise ValueError(f"未找到testReport.xlsx文件")
        
        # ========== 第3步：解析时间范围 ==========
        _report(20, '解析时间范围')
        time_range1 = self.parse_excel_time(scene1_excel, suffix)
        time_range2 = self.parse_excel_time(scene2_excel, suffix)
        
        if not time_range1 or not time_range2:
            raise ValueError(f"未找到后缀 {suffix} 的时间范围")
        
        # 获取时间范围字符串（用于显示）
        scene1_time_range_str = (
            f"{time_range1['start'].strftime('%m-%d %H:%M:%S')} 至 "
            f"{time_range1['end'].strftime('%m-%d %H:%M:%S')}"
        )
        
        scene2_time_range_str = (
            f"{time_range2['start'].strftime('%m-%d %H:%M:%S')} 至 "
            f"{time_range2['end'].strftime('%m-%d %H:%M:%S')}"
        )
        
        # ========== 第4步：获取日志文件列表 ==========
        _report(30, '获取日志列表')
        from utils import get_platform_logs
        
        scene1_logs = get_platform_logs(self.scene1_folder, self.scene1_platform)
        scene2_logs = get_platform_logs(self.scene2_folder, self.scene2_platform)
        
        if not scene1_logs:
            raise ValueError(f"版本1没有找到相关日志文件")
        if not scene2_logs:
            raise ValueError(f"版本2没有找到相关日志文件")
        
        # ========== 第5步：加载和合并日志内容 ==========
        merged_logs1 = []
        for i, log in enumerate(scene1_logs):
            merged_logs1.extend(self.load_log_content(log))
            if scene1_logs:
                progress = 30 + int(10 * (i+1) / max(1, len(scene1_logs)))
                _report(progress, f'版本1加载日志 {i+1}/{len(scene1_logs)}')
        
        merged_logs2 = []
        for i, log in enumerate(scene2_logs):
            merged_logs2.extend(self.load_log_content(log))
            if scene2_logs:
                progress = 40 + int(10 * (i+1) / max(1, len(scene2_logs)))
                _report(progress, f'版本2加载日志 {i+1}/{len(scene2_logs)}')
        
        # ========== 第6步：解析CPU日志 ==========
        _report(55, '解析版本1 CPU日志')
        cpu_usage1, process_data1, perf_times1 = self.parse_cpu_log(
            merged_logs1, time_range1, self.scene1_platform
        )
        
        _report(70, '解析版本2 CPU日志')
        cpu_usage2, process_data2, perf_times2 = self.parse_cpu_log(
            merged_logs2, time_range2, self.scene2_platform
        )
        
        # ========== 第7步：过滤CPU使用率数据 ==========
        # 类似Tkinter版本的过滤逻辑：只保留包含"Cpus Usage"的行
        filtered_cpu1 = []
        for cpu_item in cpu_usage1:
            raw_line = cpu_item.get("raw", "")
            if raw_line and "Cpus Usage" in raw_line:
                filtered_cpu1.append(cpu_item)
        
        filtered_cpu2 = []
        for cpu_item in cpu_usage2:
            raw_line = cpu_item.get("raw", "")
            if raw_line and "Cpus Usage" in raw_line:
                filtered_cpu2.append(cpu_item)
        
        # 获取CPU使用率的原始字符串表示
        cpu_raw_strings1 = [item.get("raw", "") for item in filtered_cpu1]
        cpu_raw_strings2 = [item.get("raw", "") for item in filtered_cpu2]
        
        # ========== 第8步：计算进程平均值和差异 ==========
        _report(80, '计算进程平均值')
        avg1 = self.calculate_process_averages(process_data1)
        avg2 = self.calculate_process_averages(process_data2)
        
        _report(85, '计算差异数据')
        diff_data = self.calculate_diff(avg1, avg2)
        
        # ========== 第9步：获取场景描述信息 ==========
        _report(90, '获取场景描述')
        scene_desc = "无描述"
        try:
            merged_df = pd.read_excel(self.scene_excel_path, usecols=["name", "desc"])
            for name in merged_df["name"]:
                name_str = str(name).strip()
                name_suffix = self.extract_suffix(name_str)
                if name_suffix == suffix:
                    desc_row = merged_df[merged_df["name"] == name].iloc[0]
                    scene_desc = desc_row.get("desc", "无描述")
                    break
        except Exception as e:
            print(f"获取场景描述失败: {str(e)}")
            scene_desc = "无描述"
        
        # ========== 第10步：格式化数据用于Web显示 ==========
        _report(92, '格式化数据用于显示')
        
        # 格式化CPU使用率数据
        formatted_cpu1 = self.format_cpu_data_for_web(filtered_cpu1, perf_times1, time_range1["start"])
        formatted_cpu2 = self.format_cpu_data_for_web(filtered_cpu2, perf_times2, time_range2["start"])
        
        # 格式化进程数据
        formatted_process1 = self.format_process_data_for_web(process_data1, perf_times1, time_range1["start"])
        formatted_process2 = self.format_process_data_for_web(process_data2, perf_times2, time_range2["start"])
        
        # 格式化Perf开始时间
        perf_times_str1 = [t.strftime("%m-%d %H:%M:%S.%f")[:-2] for t in perf_times1] if perf_times1 else []
        perf_times_str2 = [t.strftime("%m-%d %H:%M:%S.%f")[:-2] for t in perf_times2] if perf_times2 else []
        
        # ========== 第11步：构建完整结果 ==========
        _report(95, '构建结果')
        
        result = {
            "success": True,
            "from_cache": False,
            "suffix": suffix,
            "scene_desc": scene_desc,
            
            # 场景1数据
            "scene1": {
                "cpu_usage": formatted_cpu1,  # 格式化的CPU数据
                "cpu_raw": cpu_raw_strings1,  # 原始字符串格式
                "cpu_count": len(filtered_cpu1),
                "process_data": formatted_process1,  # 格式化的进程数据
                "process_blocks": len(process_data1),
                "total_processes": sum(len(block) for block in process_data1) if process_data1 else 0,
                "perf_start_times": perf_times_str1,
                "time_range": scene1_time_range_str,
                "base_year": time_range1.get("base_year"),
                "matched_name": time_range1.get("matched_name", ""),
                "excel_path": scene1_excel,
                "platform": self.scene1_platform
            },
            
            # 场景2数据
            "scene2": {
                "cpu_usage": formatted_cpu2,  # 格式化的CPU数据
                "cpu_raw": cpu_raw_strings2,  # 原始字符串格式
                "cpu_count": len(filtered_cpu2),
                "process_data": formatted_process2,  # 格式化的进程数据
                "process_blocks": len(process_data2),
                "total_processes": sum(len(block) for block in process_data2) if process_data2 else 0,
                "perf_start_times": perf_times_str2,
                "time_range": scene2_time_range_str,
                "base_year": time_range2.get("base_year"),
                "matched_name": time_range2.get("matched_name", ""),
                "excel_path": scene2_excel,
                "platform": self.scene2_platform
            },
            
            # 平均值和差异数据
            "averages_enhanced": {
                "scene1": {
                    "data": avg1,
                    "total_processes": len(avg1),
                    "avg_cpu_usage": sum(item["平均使用率(%)"] for item in avg1) / len(avg1) if avg1 else 0,
                    "high_usage_processes": [p for p in avg1 if p["平均使用率(%)"] > 20],
                    "frequent_processes": [p for p in avg1 if p["出现次数"] > 10],
                    "top_processes": avg1[:20] if len(avg1) > 20 else avg1
                },
                "scene2": {
                    "data": avg2,
                    "total_processes": len(avg2),
                    "avg_cpu_usage": sum(item["平均使用率(%)"] for item in avg2) / len(avg2) if avg2 else 0,
                    "high_usage_processes": [p for p in avg2 if p["平均使用率(%)"] > 20],
                    "frequent_processes": [p for p in avg2 if p["出现次数"] > 10],
                    "top_processes": avg2[:20] if len(avg2) > 20 else avg2
                },
                "diff": {
                    "data": diff_data,
                    "total_diffs": len(diff_data),
                    "max_diff": max(abs(item["差异值(%)"]) for item in diff_data) if diff_data else 0,
                    "processes_with_large_diff": [p for p in diff_data if abs(p["差异值(%)"]) > 5],
                    "new_processes_in_scene2": [p for p in diff_data if p["版本1平均值(%)"] == 0 and p["版本2平均值(%)"] > 0],
                    "disappeared_processes": [p for p in diff_data if p["版本2平均值(%)"] == 0 and p["版本1平均值(%)"] > 0],
                    "top_diffs": diff_data
                },
                "statistics": {
                    "total_unique_processes": len(set([p["进程名"] for p in avg1] + [p["进程名"] for p in avg2])),
                    "scene1_total_cpu": sum(p["平均使用率(%)"] for p in avg1),
                    "scene2_total_cpu": sum(p["平均使用率(%)"] for p in avg2),
                    "scene1_avg_cpu": sum(p["平均使用率(%)"] for p in avg1) / len(avg1) if avg1 else 0,
                    "scene2_avg_cpu": sum(p["平均使用率(%)"] for p in avg2) / len(avg2) if avg2 else 0,
                    "total_diff": sum(abs(p["差异值(%)"]) for p in diff_data),
                    "scene1_cpu_blocks": len(filtered_cpu1),
                    "scene2_cpu_blocks": len(filtered_cpu2),
                    "scene1_process_blocks": len(process_data1),
                    "scene2_process_blocks": len(process_data2)
                }
            },
            
            # 原始数据摘要
            "raw_data_summary": {
                "scene1_original_cpu_count": len(cpu_usage1),
                "scene2_original_cpu_count": len(cpu_usage2),
                "scene1_filtered_cpu_count": len(filtered_cpu1),
                "scene2_filtered_cpu_count": len(filtered_cpu2),
                "scene1_process_blocks": len(process_data1),
                "scene2_process_blocks": len(process_data2),
                "scene1_total_processes": sum(len(block) for block in process_data1),
                "scene2_total_processes": sum(len(block) for block in process_data2)
            },
            
            # 解析摘要信息（类似Tkinter的messagebox显示）
            "summary": {
                "message": (
                    f"版本1：{len(filtered_cpu1)}条CPU记录（已过滤），{len(process_data1)}个Perf块\n"
                    f"版本2：{len(filtered_cpu2)}条CPU记录（已过滤），{len(process_data2)}个Perf块"
                ),
                "scene1_details": {
                    "time_range": scene1_time_range_str,
                    "matched_name": time_range1.get("matched_name", ""),
                    "base_year": time_range1.get("base_year"),
                    "cpu_records": len(filtered_cpu1),
                    "perf_blocks": len(process_data1)
                },
                "scene2_details": {
                    "time_range": scene2_time_range_str,
                    "matched_name": time_range2.get("matched_name", ""),
                    "base_year": time_range2.get("base_year"),
                    "cpu_records": len(filtered_cpu2),
                    "perf_blocks": len(process_data2)
                }
            },
            
            # 缓存信息（先占位，避免在构建 result 时访问未定义的变量）
            "cache_info": {
                "cache_key": cache_key,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data_size_estimate": 0  # 构建完成后更新
            }
        }

        # 完成 result 构建后更新估算大小，避免在字面量内引用未定义的局部变量
        try:
            result['cache_info']['data_size_estimate'] = len(str(result))
        except Exception:
            result['cache_info']['data_size_estimate'] = 0
        
        # ========== 第12步：保存到缓存 ==========
        _report(98, '保存到缓存')
        self.cache_manager.set(cache_key, result)
        
        _report(100, '分析完成')
        
        return result
    def format_cpu_data_for_web(self, cpu_usage_data, perf_start_times, scene_start_time):
        """格式化CPU使用率数据用于Web显示"""
        if not cpu_usage_data:
            return []
        
        formatted_data = []
        
        for i, cpu_item in enumerate(cpu_usage_data):
            # 计算相对时间
            relative_time = ""
            if perf_start_times and i < len(perf_start_times):
                delta = perf_start_times[i] - scene_start_time
                total = int(delta.total_seconds())
                minutes = total // 60
                seconds = total % 60
                relative_time = f"{minutes:02d}:{seconds:02d}"
            
            # 构建格式化数据
            formatted_item = {
                "type": "cpu_block",
                "time": cpu_item.get("time", ""),
                "raw": cpu_item.get("raw", ""),
                "usage": cpu_item.get("usage", []),
                "relative_time": relative_time,
                "has_cores_data": cpu_item.get("has_cores_data", False),
                "block_index": i + 1,
                "timestamp": cpu_item.get("timestamp")
            }
            
            # 如果有CPU核心数据，添加摘要
            if cpu_item.get("usage"):
                usage_values = cpu_item["usage"]
                if usage_values:
                    formatted_item["max_usage"] = max(usage_values)
                    formatted_item["min_usage"] = min(usage_values)
                    formatted_item["avg_usage"] = sum(usage_values) / len(usage_values)
            
            formatted_data.append(formatted_item)
        
        return formatted_data
    
    def format_process_data_for_web(self, process_data, perf_start_times, scene_start_time):
        """格式化进程数据用于Web显示

        说明：有些日志情况下 perf_start_times 的数量可能与 process_data 的块数不一致，
        这里增加容错：当两者长度不匹配时仍尽量展示所有的进程块，并尝试从单个进程条目的时间或 perf_start_times 中获取时间信息。
        """
        if not process_data:
            return []
        
        formatted_data = []
        
        # perf_start_times 可能为空或与 process_data 长度不一致，我们按 block index 遍历 process_data
        for block_num, block in enumerate(process_data, 1):
            # 尝试获取对应的 perf_start_time
            perf_start_time = None
            if perf_start_times and len(perf_start_times) >= block_num:
                perf_start_time = perf_start_times[block_num - 1]

            # 若没有 perf_start_time，则尝试从该块第一个进程的时间字段解析
            relative_time = ''
            perf_start_time_str = ''
            perf_ts = None
            try:
                if perf_start_time:
                    delta = perf_start_time - scene_start_time
                    total = int(delta.total_seconds())
                    minutes = total // 60
                    seconds = total % 60
                    relative_time = f"{minutes:02d}:{seconds:02d}"
                    perf_start_time_str = perf_start_time.strftime("%m-%d %H:%M:%S.%f")[:-2]
                    perf_ts = perf_start_time.timestamp()
                else:
                    # 取块中第一个进程的时间（如果存在），格式示例："01-30 10:27:08.8183"
                    first_proc_time = None
                    if block and isinstance(block, list) and len(block) > 0:
                        first_proc_time = block[0].get('时间')
                    if first_proc_time:
                        perf_start_time_str = first_proc_time
                        # 无法准确计算相对时间（缺少年份/秒数解析），保留空的 relative_time
            except Exception:
                pass

            # 添加块分隔符
            formatted_data.append({
                "type": "separator",
                "content": f"========== Perf块 {block_num} {('[' + relative_time + ']') if relative_time else ''} ==========",
                "block_num": block_num,
                "relative_time": relative_time,
                "perf_start_time": perf_start_time_str,
                "timestamp": perf_ts,
                "is_separator": True
            })

            # 添加进程数据
            for proc in block:
                formatted_data.append({
                    "type": "process",
                    "时间": proc.get("时间", ""),
                    "使用率(%)": proc.get("使用率(%)", 0),
                    "PID": proc.get("PID", ""),
                    "进程名": proc.get("进程名", ""),
                    "总时间(ns)": proc.get("总时间(ns)", ""),
                    "OOM评分": proc.get("OOM评分", ""),
                    "block_num": block_num,
                    "relative_time": relative_time,
                    "is_separator": False
                })
        
        return formatted_data
    def calculate_process_averages(self, process_data):
        """计算进程平均值 - 返回全部数据"""
        process_stats = defaultdict(lambda: {"sum": 0, "count": 0, "pids": set()})
        
        for block in process_data:
            for proc in block:
                name = proc["进程名"]
                process_stats[name]["sum"] += proc["使用率(%)"]
                process_stats[name]["count"] += 1
                process_stats[name]["pids"].add(proc["PID"])
        
        result = [
            {
                "进程名": name,
                "平均使用率(%)": round(stats["sum"] / stats["count"], 2) if stats["count"] > 0 else 0,
                "PID列表": ", ".join(sorted(stats["pids"])) if stats["pids"] else "无",
                "数据条数": stats["count"],
                "出现次数": stats["count"],
                "CPU等级": self.classify_cpu_level(stats["sum"] / stats["count"] if stats["count"] > 0 else 0),
                "出现频率(%)": round(stats["count"] / len(process_data) * 100, 2) if process_data else 0
            }
            for name, stats in process_stats.items()
        ]
        
        # 按出现次数和平均使用率排序
        result.sort(key=lambda x: (-x["出现次数"], -x["平均使用率(%)"]))
        return result

    # def analyze_cpu_data(suffix, quick_mode=False, limit_processes=None, **kwargs):
    #     """
    #     分析CPU数据（支持快速模式）
        
    #     Args:
    #         suffix: 后缀名
    #         quick_mode: 快速模式（True时跳过耗时计算）
    #         limit_processes: 限制分析的进程数量
    #     """
        
    #     if quick_mode:
    #         print(f"快速模式分析后缀: {suffix}")
            
    #         # 快速模式的优化：
    #         # 1. 减少数据读取量
    #         # 2. 简化计算
    #         # 3. 跳过非关键步骤
            
    #         # 例如，只分析差异最大的前N个进程
    #         if limit_processes:
    #             kwargs['process_limit'] = limit_processes
            
    #         # 跳过耗时统计
    #         kwargs['skip_statistics'] = True
            
    #         # 使用简化的分析方法
    #         result = analyze_cpu_data_simple(suffix, **kwargs)
            
    #     else:
    #         # 完整分析模式
    #         result = analyze_cpu_data_full(suffix, **kwargs)
        
    #     return result
    # def analyze(self, suffix, progress_callback=None):
        """分析指定后缀的数据（一次性获取所有数据）。支持 progress_callback(percent, message) 回调。"""
        def _report(pct, msg=None):
            if progress_callback:
                try:
                    progress_callback(pct, msg)
                except Exception:
                    pass
    
        _report(1, '生成缓存键并检查缓存')
        # 生成缓存键
        cache_key_data = {
            "suffix": suffix,
            "scene1_folder": self.scene1_folder,
            "scene2_folder": self.scene2_folder,
            "scene1_platform": self.scene1_platform,
            "scene2_platform": self.scene2_platform
        }
    
        cache_key = self.cache_manager.get_cache_key(cache_key_data)
    
        # 检查缓存
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            cached_result["from_cache"] = True
            _report(100, '使用缓存')
            return cached_result
    
        _report(10, '查找 testReport.xlsx')
        # 查找两个文件夹中的testReport.xlsx文件
        scene1_excel = self.find_test_report_in_folder(self.scene1_folder)
        scene2_excel = self.find_test_report_in_folder(self.scene2_folder)
    
        if not scene1_excel or not scene2_excel:
            raise ValueError(f"未找到testReport.xlsx文件")
    
        _report(20, '解析时间范围')
        # 解析时间范围
        time_range1 = self.parse_excel_time(scene1_excel, suffix)
        time_range2 = self.parse_excel_time(scene2_excel, suffix)
    
        if not time_range1 or not time_range2:
            raise ValueError(f"未找到后缀 {suffix} 的时间范围")
    
        _report(30, '获取日志列表')
        # 获取日志文件
        from utils import get_platform_logs
    
        scene1_logs = get_platform_logs(self.scene1_folder, self.scene1_platform)
        scene2_logs = get_platform_logs(self.scene2_folder, self.scene2_platform)
    
        # 合并相关日志
        merged_logs1 = []
        for i, log in enumerate(scene1_logs):
            merged_logs1.extend(self.load_log_content(log))
            if scene1_logs:
                _report(30 + int(10 * (i+1) / max(1, len(scene1_logs))), f'版本1加载日志 {i+1}/{len(scene1_logs)}')
    
        merged_logs2 = []
        for i, log in enumerate(scene2_logs):
            merged_logs2.extend(self.load_log_content(log))
            if scene2_logs:
                _report(40 + int(10 * (i+1) / max(1, len(scene2_logs))), f'版本2加载日志 {i+1}/{len(scene2_logs)}')
    
        _report(55, '解析CPU日志')
        # 解析CPU数据（同时获取CPU使用率和进程数据）
        cpu_usage1, process_data1, perf_times1 = self.parse_cpu_log(
            merged_logs1, time_range1, self.scene1_platform)
        
        _report(70, '解析版本2 CPU日志')
        cpu_usage2, process_data2, perf_times2 = self.parse_cpu_log(
            merged_logs2, time_range2, self.scene2_platform)
    
        # 获取时间范围字符串
        scene1_time_range_str = f"{time_range1['start'].strftime('%m-%d %H:%M:%S')} 至 {time_range1['end'].strftime('%m-%d %H:%M:%S')}"
        scene2_time_range_str = f"{time_range2['start'].strftime('%m-%d %H:%M:%S')} 至 {time_range2['end'].strftime('%m-%d %H:%M:%S')}"
    
        _report(80, '格式化数据用于显示')
        # 格式化CPU使用率数据用于Web显示
        formatted_cpu1 = self.format_cpu_data_for_web(cpu_usage1, perf_times1, time_range1["start"])
        formatted_cpu2 = self.format_cpu_data_for_web(cpu_usage2, perf_times2, time_range2["start"])
    
        # 格式化进程数据用于Web显示
        formatted_process1 = self.format_process_data_for_web(process_data1, perf_times1, time_range1["start"])
        formatted_process2 = self.format_process_data_for_web(process_data2, perf_times2, time_range2["start"])
    
        _report(85, '计算平均值和差异')
        # 计算平均值
        avg1 = self.calculate_process_averages(process_data1)
        avg2 = self.calculate_process_averages(process_data2)
    
        # 计算差异
        diff_data = self.calculate_diff(avg1, avg2)
    
        # 获取场景描述信息
        try:
            merged_df = pd.read_excel(self.scene_excel_path, usecols=["name", "desc"])
            scene_desc = ""
            for name in merged_df["name"]:
                name_str = str(name).strip()
                name_suffix = self.extract_suffix(name_str)
                if name_suffix == suffix:
                    desc_row = merged_df[merged_df["name"] == name].iloc[0]
                    scene_desc = desc_row.get("desc", "无描述")
                    break
        except:
            scene_desc = "无描述"
    
        _report(90, '构建结果')
        # 构建完整的结果
        result = {
            "success": True,
            "from_cache": False,
            "suffix": suffix,
            "scene_desc": scene_desc,
            "scene1": {
                "cpu_usage": formatted_cpu1,
                "process_data": formatted_process1,
                "perf_start_times": [t.strftime("%m-%d %H:%M:%S.%f")[:-2] for t in perf_times1] if perf_times1 else [],
                "time_range": scene1_time_range_str,
                "cpu_count": len(formatted_cpu1),
                "process_block_count": len(formatted_process1),
                "total_processes": sum(len(block) for block in process_data1) if process_data1 else 0
            },
            "scene2": {
                "cpu_usage": formatted_cpu2,
                "process_data": formatted_process2,
                "perf_start_times": [t.strftime("%m-%d %H:%M:%S.%f")[:-2] for t in perf_times2] if perf_times2 else [],
                "time_range": scene2_time_range_str,
                "cpu_count": len(formatted_cpu2),
                "process_block_count": len(formatted_process2),
                "total_processes": sum(len(block) for block in process_data2) if process_data2 else 0
            },
            "averages_enhanced": {
                "scene1": {
                    "data": avg1,
                    "total_processes": len(avg1),
                    "avg_cpu_usage": sum(item["平均使用率(%)"] for item in avg1) / len(avg1) if avg1 else 0,
                    "high_usage_processes": [p for p in avg1 if p["平均使用率(%)"] > 20],
                    "frequent_processes": [p for p in avg1 if p["出现次数"] > 10]
                },
                "scene2": {
                    "data": avg2,
                    "total_processes": len(avg2),
                    "avg_cpu_usage": sum(item["平均使用率(%)"] for item in avg2) / len(avg2) if avg2 else 0,
                    "high_usage_processes": [p for p in avg2 if p["平均使用率(%)"] > 20],
                    "frequent_processes": [p for p in avg2 if p["出现次数"] > 10]
                },
                "diff": {
                    "data": diff_data,
                    "total_diffs": len(diff_data),
                    "max_diff": max(abs(item["差异值(%)"]) for item in diff_data) if diff_data else 0,
                    "processes_with_large_diff": [p for p in diff_data if abs(p["差异值(%)"]) > 5],
                    "new_processes_in_scene2": [p for p in diff_data if p["版本1平均值(%)"] == 0 and p["版本2平均值(%)"] > 0],
                    "disappeared_processes": [p for p in diff_data if p["版本2平均值(%)"] == 0 and p["版本1平均值(%)"] > 0]
                },
                "statistics": {
                    "total_unique_processes": len(set([p["进程名"] for p in avg1] + [p["进程名"] for p in avg2])),
                    "scene1_total_cpu": sum(p["平均使用率(%)"] for p in avg1),
                    "scene2_total_cpu": sum(p["平均使用率(%)"] for p in avg2),
                    "scene1_avg_cpu": sum(p["平均使用率(%)"] for p in avg1) / len(avg1) if avg1 else 0,
                    "scene2_avg_cpu": sum(p["平均使用率(%)"] for p in avg2) / len(avg2) if avg2 else 0,
                    "total_diff": sum(abs(p["差异值(%)"]) for p in diff_data)
                }
            },
            "raw_data_summary": {
                "scene1_original_cpu_count": len(cpu_usage1),
                "scene2_original_cpu_count": len(cpu_usage2),
                "scene1_process_blocks": len(process_data1),
                "scene2_process_blocks": len(process_data2)
            }
        }
    
        _report(95, '保存缓存')
        # 保存到缓存
        self.cache_manager.set(cache_key, result)
        _report(100, '完成')
    
        return result
    def classify_cpu_level(self, cpu_usage):
        """分类CPU使用率等级"""
        if cpu_usage > 50:
            return "高"
        elif cpu_usage > 20:
            return "中"
        elif cpu_usage > 5:
            return "低"
        else:
            return "很低"
    
    def calculate_diff(self, scene1_data, scene2_data):
        """计算差异数据 - 返回全部数据"""
        scene1_map = {item["进程名"]: item for item in scene1_data}
        scene2_map = {item["进程名"]: item for item in scene2_data}
        
        all_processes = set(scene1_map.keys()).union(set(scene2_map.keys()))
        
        diff_data = []
        for process in all_processes:
            s1 = scene1_map.get(process, {"平均使用率(%)": 0, "出现次数": 0})
            s2 = scene2_map.get(process, {"平均使用率(%)": 0, "出现次数": 0})
            
            diff = s2["平均使用率(%)"] - s1["平均使用率(%)"]
            
            # 判断变化趋势
            trend = "增加" if diff > 0 else "减少" if diff < 0 else "不变"
            
            diff_data.append({
                "进程名": process,
                "版本1平均值(%)": s1["平均使用率(%)"],
                "版本2平均值(%)": s2["平均使用率(%)"],
                "差异值(%)": round(diff, 2),
                "变化趋势": trend,
                "版本1出现次数": s1["出现次数"],
                "版本2出现次数": s2["出现次数"]
            })
        
        # 按差异绝对值排序
        diff_data.sort(key=lambda x: abs(x["差异值(%)"]), reverse=True)
        return diff_data
    # def analyze(self, suffix, progress_callback=None):
    #     """分析指定后缀的数据（一次性获取所有数据）。支持 progress_callback(percent, message) 回调。"""
    #     def _report(pct, msg=None):
    #         if progress_callback:
    #             try:
    #                 progress_callback(pct, msg)
    #             except Exception:
    #                 pass

    #     _report(1, '生成缓存键并检查缓存')
    #     # 生成缓存键
    #     cache_key_data = {
    #         "suffix": suffix,
    #         "scene1_folder": self.scene1_folder,
    #         "scene2_folder": self.scene2_folder,
    #         "scene1_platform": self.scene1_platform,
    #         "scene2_platform": self.scene2_platform
    #     }

    #     cache_key = self.cache_manager.get_cache_key(cache_key_data)

    #     # 检查缓存
    #     cached_result = self.cache_manager.get(cache_key)
    #     if cached_result:
    #         cached_result["from_cache"] = True
    #         _report(100, '使用缓存')
    #         return cached_result

    #     _report(10, '查找 testReport.xlsx')
    #     # 查找两个文件夹中的testReport.xlsx文件
    #     scene1_excel = self.find_test_report_in_folder(self.scene1_folder)
    #     scene2_excel = self.find_test_report_in_folder(self.scene2_folder)

    #     if not scene1_excel or not scene2_excel:
    #         raise ValueError(f"未找到testReport.xlsx文件")

    #     _report(20, '解析时间范围')
    #     # 解析时间范围
    #     time_range1 = self.parse_excel_time(scene1_excel, suffix)
    #     time_range2 = self.parse_excel_time(scene2_excel, suffix)

    #     if not time_range1 or not time_range2:
    #         raise ValueError(f"未找到后缀 {suffix} 的时间范围")

    #     _report(30, '获取日志列表')
    #     # 获取日志文件
    #     from utils import get_platform_logs

    #     scene1_logs = get_platform_logs(self.scene1_folder, self.scene1_platform)
    #     scene2_logs = get_platform_logs(self.scene2_folder, self.scene2_platform)

    #     # 合并相关日志
    #     merged_logs1 = []
    #     for i, log in enumerate(scene1_logs):
    #         merged_logs1.extend(self.load_log_content(log))
    #         if scene1_logs:
    #             _report(30 + int(10 * (i+1) / max(1, len(scene1_logs))), f'版本1加载日志 {i+1}/{len(scene1_logs)}')

    #     merged_logs2 = []
    #     for i, log in enumerate(scene2_logs):
    #         merged_logs2.extend(self.load_log_content(log))
    #         if scene2_logs:
    #             _report(40 + int(10 * (i+1) / max(1, len(scene2_logs))), f'版本2加载日志 {i+1}/{len(scene2_logs)}')

    #     _report(55, '解析CPU日志')
    #     # 解析CPU数据（同时获取CPU使用率和进程数据）
    #     cpu_usage1, process_data1, perf_times1 = self.parse_cpu_log(
    #         merged_logs1, time_range1, self.scene1_platform)
    #     _report(70, '解析版本2 CPU日志')
    #     cpu_usage2, process_data2, perf_times2 = self.parse_cpu_log(
    #         merged_logs2, time_range2, self.scene2_platform)

    #     _report(80, '计算平均值和差异')
    #     # 计算平均值
    #     avg1 = self.calculate_process_averages(process_data1)
    #     avg2 = self.calculate_process_averages(process_data2)

    #     # 计算差异
    #     diff_data = self.calculate_diff(avg1, avg2)

    #     _report(90, '格式化结果用于显示')
    #     # 获取场景描述信息
    #     try:
    #         merged_df = pd.read_excel(self.scene_excel_path, usecols=["name", "desc"])
    #         scene_desc = ""
    #         for name in merged_df["name"]:
    #             name_str = str(name).strip()
    #             name_suffix = self.extract_suffix(name_str)
    #             if name_suffix == suffix:
    #                 desc_row = merged_df[merged_df["name"] == name].iloc[0]
    #                 scene_desc = desc_row.get("desc", "无描述")
    #                 break
    #     except:
    #         scene_desc = "无描述"

    #     # 过滤CPU使用率数据（只包含Cpus Usage的行）
    #     filtered_cpu1 = [line for line in cpu_usage1 if "Cpus Usage" in line]
    #     filtered_cpu2 = [line for line in cpu_usage2 if "Cpus Usage" in line]

    #     # 格式化进程数据用于Web显示
    #     formatted_process1 = self.format_process_data_for_web(process_data1, perf_times1, time_range1["start"])
    #     formatted_process2 = self.format_process_data_for_web(process_data2, perf_times2, time_range2["start"])

    #     _report(95, '构建结果并保存缓存')
    #     # 构建结果（包含所有数据）
    #     result = {
    #             "success": True,
    #             "from_cache": False,
    #             "suffix": suffix,
    #             "scene_desc": scene_desc,
    #             "averages_enhanced": {
    #                 "scene1": {
    #                     "data": avg1,
    #                     "total_processes": len(avg1),
    #                     "avg_cpu_usage": sum(item["平均使用率(%)"] for item in avg1) / len(avg1) if avg1 else 0,
    #                     "high_usage_processes": [p for p in avg1 if p["平均使用率(%)"] > 20],
    #                     "frequent_processes": [p for p in avg1 if p["出现次数"] > 10]
    #                 },
    #                 "scene2": {
    #                     "data": avg2,
    #                     "total_processes": len(avg2),
    #                     "avg_cpu_usage": sum(item["平均使用率(%)"] for item in avg2) / len(avg2) if avg2 else 0,
    #                     "high_usage_processes": [p for p in avg2 if p["平均使用率(%)"] > 20],
    #                     "frequent_processes": [p for p in avg2 if p["出现次数"] > 10]
    #                 },
    #                 "diff": {
    #                     "data": diff_data,
    #                     "total_diffs": len(diff_data),
    #                     "max_diff": max(abs(item["差异值(%)"]) for item in diff_data) if diff_data else 0,
    #                     "processes_with_large_diff": [p for p in diff_data if abs(p["差异值(%)"]) > 5],
    #                     "new_processes_in_scene2": [p for p in diff_data if p["版本1平均值(%)"] == 0 and p["版本2平均值(%)"] > 0],
    #                     "disappeared_processes": [p for p in diff_data if p["版本2平均值(%)"] == 0 and p["版本1平均值(%)"] > 0]
    #                 },
    #                 "statistics": {
    #                     "total_unique_processes": len(set([p["进程名"] for p in avg1] + [p["进程名"] for p in avg2])),
    #                     "scene1_total_cpu": sum(p["平均使用率(%)"] for p in avg1),
    #                     "scene2_total_cpu": sum(p["平均使用率(%)"] for p in avg2),
    #                     "scene1_avg_cpu": sum(p["平均使用率(%)"] for p in avg1) / len(avg1) if avg1 else 0,
    #                     "scene2_avg_cpu": sum(p["平均使用率(%)"] for p in avg2) / len(avg2) if avg2 else 0,
    #                     "total_diff": sum(abs(p["差异值(%)"]) for p in diff_data)
    #                 }
    #             }
    #         }
        
    #     # 保存到缓存
    #     self.cache_manager.set(cache_key, result)
    #     _report(100, '完成')

    #     return result

    def calculate_enhanced_averages(self, process_data, scene_start_time=None):
        """计算增强版的进程平均值"""
        if not process_data:
            return []
        
        process_stats = defaultdict(lambda: {"sum": 0, "count": 0, "pids": set(), "times": []})
        
        # 收集所有数据
        for block_num, block in enumerate(process_data, 1):
            for proc in block:
                name = proc["进程名"]
                process_stats[name]["sum"] += proc["使用率(%)"]
                process_stats[name]["count"] += 1
                process_stats[name]["pids"].add(proc["PID"])
                process_stats[name]["times"].append(proc["时间"])
        
        # 计算增强的统计信息
        result = []
        for name, stats in process_stats.items():
            avg_usage = round(stats["sum"] / stats["count"], 2) if stats["count"] > 0 else 0
            
            # 计算标准差（波动情况）
            if len(stats["times"]) > 1:
                # 这里可以添加标准差计算
                variance = 0
            else:
                variance = 0
            
            result.append({
                "进程名": name,
                "平均使用率(%)": avg_usage,
                "最大使用率(%)": max([p["使用率(%)"] for block in process_data for p in block if p["进程名"] == name], default=avg_usage),
                "最小使用率(%)": min([p["使用率(%)"] for block in process_data for p in block if p["进程名"] == name], default=avg_usage),
                "PID列表": ", ".join(sorted(stats["pids"])),
                "出现次数": stats["count"],
                "数据条数": stats["count"],
                "使用率波动": variance,
                "CPU等级": self.classify_cpu_level(avg_usage),
                "出现频率(%)": round(stats["count"] / len(process_data) * 100, 2) if process_data else 0
            })
        
        # 按出现次数和平均使用率排序
        result.sort(key=lambda x: (-x["出现次数"], -x["平均使用率(%)"]))
        return result
    
    def classify_cpu_level(self, cpu_usage):
        """分类CPU使用率等级"""
        if cpu_usage > 50:
            return "高"
        elif cpu_usage > 20:
            return "中"
        elif cpu_usage > 5:
            return "低"
        else:
            return "很低"

    def format_process_data_for_web(self, process_data, perf_start_times, scene_start_time):
        """格式化进程数据用于Web显示"""
        if not process_data or not perf_start_times or len(process_data) != len(perf_start_times):
            return []
        
        formatted_data = []
        
        for block_num, (block, perf_start_time) in enumerate(zip(process_data, perf_start_times), 1):
            # 计算相对时间
            delta = perf_start_time - scene_start_time
            minutes = delta.seconds // 60
            seconds = delta.seconds % 60
            relative_time = f"{minutes:02d}:{seconds:02d}"
            
            # 添加分隔符行
            formatted_data.append({
                "type": "separator",
                "content": f"========== Perf块 {block_num} [距离开始时间过去{relative_time}] ==========",
                "block_num": block_num,
                "relative_time": relative_time
            })
            
            # 添加进程数据行
            for proc in block:
                formatted_data.append({
                    "type": "process",
                    "时间": proc["时间"],
                    "使用率(%)": proc["使用率(%)"],
                    "PID": proc["PID"],
                    "进程名": proc["进程名"],
                    "总时间(ns)": proc["总时间(ns)"],
                    "OOM评分": proc["OOM评分"],
                    "block_num": block_num
                })
        
        return formatted_data
    
    def calculate_diff(self, scene1_data, scene2_data):
        """计算差异数据"""
        scene1_map = {item["进程名"]: item for item in scene1_data}
        scene2_map = {item["进程名"]: item for item in scene2_data}
        
        all_processes = set(scene1_map.keys()).union(set(scene2_map.keys()))
        
        diff_data = []
        for process in all_processes:
            s1 = scene1_map.get(process, {"平均使用率(%)": 0, "出现次数": 0})
            s2 = scene2_map.get(process, {"平均使用率(%)": 0, "出现次数": 0})
            
            diff = s2["平均使用率(%)"] - s1["平均使用率(%)"]
            
            diff_data.append({
                "进程名": process,
                "版本1平均值(%)": s1["平均使用率(%)"],
                "版本2平均值(%)": s2["平均使用率(%)"],
                "差异值(%)": round(diff, 2),
                "版本1出现次数": s1["出现次数"],
                "版本2出现次数": s2["出现次数"]
            })
        
        diff_data.sort(key=lambda x: abs(x["差异值(%)"]), reverse=True)
        return diff_data
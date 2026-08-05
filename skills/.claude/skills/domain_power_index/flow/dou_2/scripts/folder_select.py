"""
文件夹选择模块 - 独立封装文件夹选择和管理相关功能
包含根文件夹设置、平台设置、场景对比、文件查找、统计、分组、缓存等功能
"""
import os
import json
import hashlib
import time
import shutil
from datetime import datetime
import pandas as pd
from paths import CPU_CACHE_DIR
from utils import (
    find_test_report,
    get_platform_logs,
    is_screen_off_scene,
    mah_to_screen_current_impact_ma,
)


def _format_scene_time_cell(value):
    """将 report 表中的 starttime/endtime 格式化为可读字符串。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    if not text or text.lower() in ("nan", "nat"):
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return text


def _format_scene_time_range(start, end):
    """合并起止时间为「开始 至 结束」。"""
    start_s = _format_scene_time_cell(start)
    end_s = _format_scene_time_cell(end)
    if start_s and end_s:
        return f"{start_s} 至 {end_s}"
    return start_s or end_s or ""


def _merged_scene_time(row, side: str) -> str:
    """从 merge 后行取指定版本（1=高/2=低）的场景时间。"""
    if side == "1":
        start = row.get("starttime_1", row.get("starttime"))
        end = row.get("endtime_1", row.get("endtime"))
    else:
        start = row.get("starttime_2")
        end = row.get("endtime_2")
    return _format_scene_time_range(start, end)


class FileManager:
    """文件管理器类 - 处理文件查找、统计、分组、缓存等功能"""
    
    def __init__(self, cache_dirs=None):
        """初始化文件管理器"""
        self.cache_dirs = cache_dirs or [str(CPU_CACHE_DIR), './analysis_cache']
        self.cache_stats = {}
    
    def find_log_files(self, folder_path):
        """在文件夹中查找日志文件
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            list: 找到的日志文件列表
        """
        log_extensions = ['.log', '.txt', '.csv']
        log_files = []
        
        try:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    if any(item.lower().endswith(ext) for ext in log_extensions):
                        log_files.append(item)
        except Exception:
            pass
            
        return log_files
    
    def find_files_by_extension_recursive(self, folder_path, extension):
        """递归查找指定扩展名的文件（包含所有子文件夹）
        
        Args:
            folder_path: 文件夹路径
            extension: 文件扩展名（如'.cap'）
            
        Returns:
            list: 找到的完整文件路径列表
        """
        files = []
        try:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    if item.lower().endswith(extension.lower()):
                        files.append(item_path)
                elif os.path.isdir(item_path):
                    # 递归搜索子文件夹
                    sub_files = self.find_files_by_extension_recursive(item_path, extension)
                    files.extend(sub_files)
        except Exception:
            pass
        return files
    
    def find_files_by_keywords_recursive(self, folder_path, keywords):
        """递归查找包含指定关键字的文件（包含所有子文件夹）
        
        Args:
            folder_path: 文件夹路径
            keywords: 关键字列表
            
        Returns:
            list: 找到的完整文件路径列表
        """
        files = []
        try:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    # 检查文件名是否包含所有关键字
                    item_lower = item.lower()
                    if all(keyword.lower() in item_lower for keyword in keywords):
                        files.append(item_path)
                elif os.path.isdir(item_path):
                    # 递归搜索子文件夹
                    sub_files = self.find_files_by_keywords_recursive(item_path, keywords)
                    files.extend(sub_files)
        except Exception:
            pass
        return files
    
    def group_files_by_folder(self, file_paths):
        """按文件夹对文件路径进行分组
        
        Args:
            file_paths: 文件路径列表
            
        Returns:
            dict: 按文件夹分组的文件字典
        """
        grouped_files = {}
        
        for file_path in file_paths:
            folder = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            
            if folder not in grouped_files:
                grouped_files[folder] = []
            
            grouped_files[folder].append({
                'name': filename,
                'path': file_path,
                'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
            })
        
        return grouped_files
    
    def find_files_by_extension(self, folder_path, extension):
        """查找指定扩展名的文件（不递归）
        
        Args:
            folder_path: 文件夹路径
            extension: 文件扩展名
            
        Returns:
            list: 找到的文件列表
        """
        files = []
        try:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path) and item.lower().endswith(extension.lower()):
                    files.append(item)
        except Exception:
            pass
        return files
    
    def find_files_by_keywords(self, folder_path, keywords):
        """查找包含指定关键字的文件（不递归）
        
        Args:
            folder_path: 文件夹路径
            keywords: 关键字列表
            
        Returns:
            list: 找到的文件列表
        """
        files = []
        try:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    item_lower = item.lower()
                    if all(keyword.lower() in item_lower for keyword in keywords):
                        files.append(item)
        except Exception:
            pass
        return files
    
    def get_file_statistics(self, folder_path):
        """获取文件夹的文件统计信息
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            dict: 文件统计信息
        """
        stats = {
            'total_files': 0,
            'total_size': 0,
            'file_types': {},
            'subfolders': 0
        }
        
        try:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                
                if os.path.isfile(item_path):
                    stats['total_files'] += 1
                    stats['total_size'] += os.path.getsize(item_path)
                    
                    # 统计文件类型
                    _, ext = os.path.splitext(item)
                    ext = ext.lower() if ext else '无扩展名'
                    if ext not in stats['file_types']:
                        stats['file_types'][ext] = 0
                    stats['file_types'][ext] += 1
                    
                elif os.path.isdir(item_path):
                    stats['subfolders'] += 1
                    
        except Exception:
            pass
            
        return stats
    
    def scan_folder_for_kernel_logs(self, folder_path):
        """扫描文件夹中的kernel日志文件
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            list: 找到的kernel日志文件信息
        """
        kernel_files = []
        
        try:
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    # 检查是否是kernel日志文件
                    if self.is_kernel_log_file(item):
                        file_info = {
                            'name': item,
                            'path': item_path,
                            'size': os.path.getsize(item_path),
                            'time_info': self.parse_time_from_filename(item)
                        }
                        kernel_files.append(file_info)
                        
        except Exception:
            pass
            
        return kernel_files
    
    def is_kernel_log_file(self, filename):
        """检查文件是否是kernel日志文件
        
        Args:
            filename: 文件名
            
        Returns:
            bool: 是否是kernel日志文件
        """
        # 支持：kernel_log_YYYY_MMDD_HHMMSS(.curf)、kernel_log_xxx_YYYY_MMDD_HHMMSS(.curf)
        import re
        if '_linli_666' in filename.lower():
            return False
        pattern = r'^kernel_log_(?:.+_)?(\d{4})_(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(\.curf)?$'
        return bool(re.match(pattern, filename, re.IGNORECASE))
    
    def parse_time_from_filename(self, filename):
        """从文件名解析时间信息
        
        Args:
            filename: 文件名
            
        Returns:
            dict: 时间信息或None
        """
        import re
        from datetime import datetime
        
        pattern = r'^kernel_log_(?:.+_)?(\d{4})_(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(\.curf)?$'
        match = re.match(pattern, filename, re.IGNORECASE)
        
        if not match:
            return None
        
        try:
            year = int(match[1])
            month = int(match[2])
            day = int(match[3])
            hour = int(match[4])
            minute = int(match[5])
            second = int(match[6])
            extension = match[7] or ''
            
            date = datetime(year, month, day, hour, minute, second)
            
            return {
                'year': year, 'month': month, 'day': day,
                'hour': hour, 'minute': minute, 'second': second,
                'extension': extension or '无后缀',
                'timestamp': date.timestamp(),
                'datetime': date.strftime('%Y-%m-%d %H:%M:%S'),
                'raw': match[0]
            }
        except Exception:
            return None
    
    def get_cache_statistics(self):
        """获取缓存统计信息
        
        Returns:
            dict: 缓存统计信息
        """
        cache_stats = {}
        
        for cache_dir in self.cache_dirs:
            if os.path.exists(cache_dir):
                cache_files = []
                total_size = 0
                
                for root, dirs, files in os.walk(cache_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        file_size = os.path.getsize(file_path)
                        cache_files.append({
                            'name': file,
                            'path': file_path,
                            'size': file_size,
                            'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
                        })
                        total_size += file_size
                
                cache_stats[cache_dir] = {
                    'file_count': len(cache_files),
                    'total_size': total_size,
                    'files': cache_files
                }
        
        return cache_stats
    
    def clear_cache(self, cache_dir=None):
        """清空缓存
        
        Args:
            cache_dir: 指定缓存目录，如果为None则清空所有缓存
            
        Returns:
            dict: 清空结果
        """
        cleared_dirs = []
        
        if cache_dir:
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
                cleared_dirs.append(cache_dir)
        else:
            for cache_dir in self.cache_dirs:
                if os.path.exists(cache_dir):
                    shutil.rmtree(cache_dir)
                    os.makedirs(cache_dir, exist_ok=True)
                    cleared_dirs.append(cache_dir)
        
        return {
            'success': True,
            'message': f'已清空 {len(cleared_dirs)} 个缓存目录',
            'cleared_dirs': cleared_dirs
        }
    
    def get_converted_files(self, upload_folder):
        """获取已转换的文件列表
        
        Args:
            upload_folder: 上传文件夹路径
            
        Returns:
            list: 已转换的文件列表
        """
        converted_files = []
        
        try:
            if os.path.exists(upload_folder):
                for item in os.listdir(upload_folder):
                    item_path = os.path.join(upload_folder, item)
                    if os.path.isfile(item_path):
                        # 检查是否是转换后的文件
                        if item.startswith('converted_') or item.endswith('_linli_666.txt'):
                            file_info = {
                                'name': item,
                                'path': item_path,
                                'size': os.path.getsize(item_path),
                                'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')
                            }
                            converted_files.append(file_info)
        except Exception:
            pass
            
        return converted_files
    
    def validate_test_files_structure(self, folder_path):
        """验证测试文件结构是否有效
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            dict: 验证结果
        """
        if not folder_path or not os.path.isdir(folder_path):
            return {'success': False, 'message': '无效的文件夹路径'}
        
        # 检查文件夹中是否有必要的文件
        required_extensions = ['.cap', '.log', '.txt', '.csv']
        found_files = []
        
        for ext in required_extensions:
            files = self.find_files_by_extension(folder_path, ext)
            if files:
                found_files.extend(files)
        
        if not found_files:
            return {
                'success': False,
                'message': f'文件夹中没有找到任何 {required_extensions} 格式的文件'
            }
        
        # 获取文件统计信息
        stats = self.get_file_statistics(folder_path)
        
        return {
            'success': True,
            'message': f'文件夹结构有效，找到 {len(found_files)} 个相关文件',
            'file_count': len(found_files),
            'stats': stats
        }


# 创建全局文件管理器实例
file_manager = FileManager()


class FolderSelector:
    """文件夹选择器类"""
    
    def __init__(self, app_state):
        """初始化文件夹选择器"""
        self.app_state = app_state
    
    def set_scene_folders(self, high_folder, low_folder):
        """直接设置高功耗场景文件夹与低功耗对比文件夹"""
        high_folder = (high_folder or '').strip()
        low_folder = (low_folder or '').strip()
        if not high_folder or not os.path.isdir(high_folder):
            return {'success': False, 'message': '高功耗场景文件夹无效或不存在'}
        if not low_folder or not os.path.isdir(low_folder):
            return {'success': False, 'message': '低功耗对比文件夹无效或不存在'}
        self.app_state.scene1_folder = os.path.abspath(high_folder)
        self.app_state.scene2_folder = os.path.abspath(low_folder)
        self.app_state.root_folder = self.app_state.scene1_folder
        return {'success': True, 'state': self.app_state.to_dict()}

    def set_root_folder(self, root_folder):
        """设置根文件夹（兼容：从根目录下自动取两个子文件夹作为场景1/2）"""
        if not root_folder or not os.path.isdir(root_folder):
            return {'success': False, 'message': '无效的文件夹路径'}
        
        self.app_state.root_folder = root_folder
        
        subfolders = [f.path for f in os.scandir(root_folder) if f.is_dir()]
        if len(subfolders) >= 2:
            subfolders.sort(key=lambda x: os.path.getmtime(x))
            self.app_state.scene1_folder = subfolders[0]
            self.app_state.scene2_folder = subfolders[1]
        
        return {'success': True, 'state': self.app_state.to_dict()}
    
    def set_platform(self, scene, platform):
        """设置平台类型"""
        if scene == 'scene1':
            self.app_state.scene1_platform = platform
        elif scene == 'scene2':
            self.app_state.scene2_platform = platform
        
        return {'success': True, 'state': self.app_state.to_dict()}
    
    def execute_scene_comparison(self):
        """执行场景对比"""
        try:
            scene1 = self.app_state.scene1_folder
            scene2 = self.app_state.scene2_folder
            if not scene1 or not os.path.isdir(scene1):
                return {'success': False, 'message': '请先设置高功耗场景文件夹'}
            if not scene2 or not os.path.isdir(scene2):
                return {'success': False, 'message': '请先设置低功耗对比文件夹'}
            
            # 查找Excel文件
            file_path_1 = find_test_report(self.app_state.scene1_folder)
            file_path_2 = find_test_report(self.app_state.scene2_folder)
            
            if not file_path_1 or not file_path_2:
                return {
                    'success': False,
                    'message': '未找到场景报告 Excel（优先 testReport.xlsx，或含 report 工作表的其它 xlsx）',
                }
            
            # 读取并对比数据（含两版场景起止时间）
            report1 = pd.read_excel(file_path_1, sheet_name="report")
            report2 = pd.read_excel(file_path_2, sheet_name="report")

            df1_cols = ["name", "desc", "duration", "avg_cur_4v"]
            df2_cols = ["name", "avg_cur_4v"]
            if "starttime" in report1.columns and "endtime" in report1.columns:
                df1_cols.extend(["starttime", "endtime"])
            if "starttime" in report2.columns and "endtime" in report2.columns:
                df2_cols.extend(["starttime", "endtime"])

            missing1 = [c for c in df1_cols if c not in report1.columns]
            missing2 = [c for c in df2_cols if c not in report2.columns]
            if missing1 or missing2:
                return {
                    "success": False,
                    "message": (
                        "report 表缺少必要列："
                        f"版本1 {missing1 or 'OK'}；版本2 {missing2 or 'OK'}"
                    ),
                }

            df1 = report1[df1_cols].copy()
            df2 = report2[df2_cols].copy()

            # 数据处理
            df1 = df1.drop_duplicates(subset=["name"], keep="first")
            df2 = df2.drop_duplicates(subset=["name"], keep="first")
            
            merged_df = pd.merge(
                df1, 
                df2, 
                on="name", 
                how="left", 
                suffixes=("_1", "_2")
            )

            merged_df["版本1场景时间"] = merged_df.apply(
                lambda row: _merged_scene_time(row, "1"),
                axis=1,
            )
            merged_df["版本2场景时间"] = merged_df.apply(
                lambda row: _merged_scene_time(row, "2"),
                axis=1,
            )
            drop_time_cols = [
                c
                for c in (
                    "starttime",
                    "endtime",
                    "starttime_1",
                    "endtime_1",
                    "starttime_2",
                    "endtime_2",
                )
                if c in merged_df.columns
            ]
            if drop_time_cols:
                merged_df = merged_df.drop(columns=drop_time_cols)
            
            merged_df["avg_cur_4v_diff"] = merged_df["avg_cur_4v_1"] - merged_df["avg_cur_4v_2"]
            merged_df["duration"] = pd.to_timedelta(merged_df["duration"], errors="coerce")
            merged_df["duration_sec"] = merged_df["duration"].dt.total_seconds().fillna(0)
            merged_df["功耗差异mAh"] = merged_df["duration_sec"] * merged_df["avg_cur_4v_diff"] / 3600
            merged_df["功耗差异mAh"] = merged_df["功耗差异mAh"].round(4)

            # 单场景对亮/灭屏电流影响：功耗差异mAh / 同类型场景总时长(h) -> mA
            is_off_list = [
                is_screen_off_scene(desc, name)
                for desc, name in zip(merged_df["desc"], merged_df["name"])
            ]
            merged_df["场景亮灭屏"] = [
                "灭屏" if off else "亮屏" for off in is_off_list
            ]
            off_mask = pd.Series(is_off_list, index=merged_df.index)
            total_on_sec = float(merged_df.loc[~off_mask, "duration_sec"].sum())
            total_off_sec = float(merged_df.loc[off_mask, "duration_sec"].sum())

            on_impacts = []
            off_impacts = []
            for is_off, mah in zip(is_off_list, merged_df["功耗差异mAh"]):
                if is_off:
                    on_impacts.append(None)
                    off_impacts.append(
                        mah_to_screen_current_impact_ma(mah, total_off_sec)
                    )
                else:
                    on_impacts.append(
                        mah_to_screen_current_impact_ma(mah, total_on_sec)
                    )
                    off_impacts.append(None)
            merged_df["对亮屏电流影响(mA)"] = on_impacts
            merged_df["对灭屏电流影响(mA)"] = off_impacts

            preferred_cols = [
                "name",
                "desc",
                "版本1场景时间",
                "版本2场景时间",
                "duration",
                "avg_cur_4v_1",
                "avg_cur_4v_2",
                "avg_cur_4v_diff",
                "duration_sec",
                "功耗差异mAh",
                "场景亮灭屏",
                "对亮屏电流影响(mA)",
                "对灭屏电流影响(mA)",
            ]
            ordered = [c for c in preferred_cols if c in merged_df.columns]
            extra = [c for c in merged_df.columns if c not in ordered]
            merged_df = merged_df[ordered + extra]
            
            # 保存对比文件（写入高功耗场景文件夹）
            output_file_name = "DOU3.0版本数据对比.xlsx"
            output_file_path = os.path.join(self.app_state.scene1_folder, output_file_name)
            merged_df.to_excel(output_file_path, index=False)
            self.app_state.scene_excel_path = output_file_path
            
            # 保存两个版本各自的Excel文件路径
            self.app_state.scene1_excel_path = file_path_1
            self.app_state.scene2_excel_path = file_path_2
            
            # 获取日志文件
            self.app_state.scene1_log_files = get_platform_logs(
                self.app_state.scene1_folder, self.app_state.scene1_platform)
            self.app_state.scene2_log_files = get_platform_logs(
                self.app_state.scene2_folder, self.app_state.scene2_platform)
            
            # 统计信息
            unmatched_names = merged_df[merged_df["avg_cur_4v_2"].isna()]["name"].tolist()
            
            result = {
                'success': True,
                'message': '场景对比完成',
                'result': {
                    'output_file': output_file_path,
                    'total_records': len(merged_df),
                    'unmatched_count': len(unmatched_names),
                    'total_scenes': len(merged_df),
                    'matched_scenes': len(merged_df) - len(unmatched_names),
                    'unmatched_scenes': len(unmatched_names),
                    'unmatched_names': unmatched_names[:10],
                    'scene1_log_count': len(self.app_state.scene1_log_files),
                    'scene2_log_count': len(self.app_state.scene2_log_files),
                }
            }
            
            return result
            
        except Exception as e:
            return {'success': False, 'message': f'执行失败: {str(e)}'}
    
    def get_folder_info(self):
        """获取文件夹信息"""
        if not self.app_state:
            return {'success': False, 'message': '应用未初始化'}
        
        return {'success': True, 'state': self.app_state.to_dict()}
    
    def clear_folders(self):
        """清空文件夹设置"""
        self.app_state.root_folder = ''
        self.app_state.scene1_folder = ''
        self.app_state.scene2_folder = ''
        self.app_state.scene_excel_path = ''
        self.app_state.scene1_log_files = []
        self.app_state.scene2_log_files = []
        
        return {'success': True, 'message': '文件夹设置已清空', 'state': self.app_state.to_dict()}


# 创建全局文件夹选择器实例
folder_selector = None

def init_folder_selector(app_state):
    """初始化文件夹选择器"""
    global folder_selector
    folder_selector = FolderSelector(app_state)
    return folder_selector
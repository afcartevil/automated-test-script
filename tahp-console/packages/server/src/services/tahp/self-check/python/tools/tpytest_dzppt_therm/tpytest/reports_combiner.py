import os.path
import os
import re
from pathlib import Path
import shutil
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Sequence, Union, Callable, Iterator, Tuple, Set

from powertrde.framework.tran_logger import t_log
from powertrde.utils import misc_utils, yaml_utils
from tpytest.test_reporter import TestReporter, CaseReporterUnit, CaseSummaryReporter

PathLike = Union[str, Path]


class ReportMergeMode(Enum):
    RelacePrevious = 0,
    PassRelace = 1,
    Append = 2


class ReportsCombiner:
    class OneTestUnits:
        def __init__(self):
            self.case_id_no_retry = ''
            self.parent_index = 0
            self.last_retry_unit: Optional[CaseReporterUnit] = None
            self.units: List[CaseReporterUnit] = []

        @property
        def is_pass(self):
            if not self.units:
                return False
            return (self.last_retry_unit or self.units[0]).result == 'pass'

    class ReportProcessor:
        def __init__(self, index: int, report_path: str, target_scheme: str, test_report_class: type):
            self.index = index
            self.test_reporter = test_report_class(report_path, target_scheme=target_scheme, try_overwrite_meta_report_dir_name='ori_meta_report')
            self.test_reporter.parse_reporter_units()
            for u in self.test_reporter.summary_reporter_units:
                u.source = str(index)

            self.test_units_dict: Dict[str, ReportsCombiner.OneTestUnits] = {}

            _source_units = self.test_reporter.case_meta_reporter_units

            for u in _source_units:
                _exist_sub = self.test_units_dict.get(u.case_id_no_retry)
                if _exist_sub is None:
                    _exist_sub = ReportsCombiner.OneTestUnits()
                    _exist_sub.parent_index = index
                    _exist_sub.case_id_no_retry = u.case_id_no_retry
                    self.test_units_dict[u.case_id_no_retry] = _exist_sub
                u.parent_index = index
                _exist_sub.units.append(u)
                if u.last_retry:
                    _exist_sub.last_retry_unit = u

    def __init__(self, target_scheme_name: str, to_merge_reports_paths: Union[List[str], str], merge_mode: ReportMergeMode, target_merged_report_dir_path: Optional[str] = None, search_retests: bool = False, test_reporter_class: Optional[type] = None):
        self.test_reporter_class = test_reporter_class or TestReporter
        self.target_scheme_name = target_scheme_name
        self.search_retests = search_retests

        if isinstance(to_merge_reports_paths, str):
            _ori_reports_paths = [to_merge_reports_paths]
        else:
            _ori_reports_paths = to_merge_reports_paths

        self.reports_paths = [_r for _r in _ori_reports_paths if TestReporter.is_report_dir_available(_r)]

        if not self.reports_paths:
            raise Exception('No valid report folder to be merged was found.\n找不到要合并的有效报告文件夹。')

        if not target_merged_report_dir_path:
            self.target_merged_report_dir_path = os.path.join(_ori_reports_paths[0], 'meta_report')
            self.backup_exists_target_path = os.path.join(_ori_reports_paths[0], 'ori_meta_report')
        else:
            self.target_merged_report_dir_path = target_merged_report_dir_path
            self.backup_exists_target_path = ''

        if self.search_retests:
            _ps = list(self.reports_paths)
            self.reports_paths.clear()
            for p in _ps:
                self.reports_paths.append(p)
                _r_p = os.path.join(p, 'retests')
                if os.path.exists(_r_p):
                    self.reports_paths.extend(self._iter_matching_folders(_r_p, lambda _path: TestReporter.is_report_dir_available(str(_path))))

        self.target_merged_report_dir_path_tmp = self.target_merged_report_dir_path + '.tmp'
        self.merge_mode = merge_mode
        self.report_processors: List[ReportsCombiner.ReportProcessor] = []
        self._merged_units: List[CaseReporterUnit] = []
        self._merged_total_report_dict = None
        self._merged_runtime_config_dict = None

    @staticmethod
    def _iter_matching_folders(
            root: PathLike,
            predicate: Callable[[Path], bool],
            *,
            follow_symlinks: bool = False,
    ) -> Iterator[str]:
        """
        生成器：按规则迭代返回满足 predicate 的子文件夹全路径（Path 对象）。

        算法（简要）:
          - 对传入 root 的表层子目录逐个检查 predicate(subdir)。
          - 若 predicate(subdir) 为 True: yield subdir；随后检查 subdir/'retests'：
              - 若存在且为目录，则将该 retests 子目录加入待处理栈（在该目录的表层继续同样的检查）。
          - 如此递归直到处理完所有进入的 retests 树。
        说明:
          - predicate 接受 Path（子文件夹路径）并返回 bool。
          - follow_symlinks 决定在判定目录存在和 os.stat 时是否跟随符号链接（默认为 False，防止环路）。
          - 为防止循环（例如符号链接或硬链接导致），使用 (st_dev, st_ino) 去重访问过的目录。
          - 如果 predicate 自身抛异常，则会忽略该子目录并继续（可根据需要修改为让异常外抛）。
        """
        root = Path(root)

        # 使用显式栈处理（避免深递归）
        stack = [root]

        # 记录已访问目录的 inode (st_dev, st_ino) 避免环路
        seen: Set[Tuple[int, int]] = set()

        while stack:
            current = stack.pop()
            # 获取 current 的 stat 以便检测环路 / 重复访问
            try:
                st = os.stat(current, follow_symlinks=follow_symlinks)
                key = (st.st_dev, st.st_ino)
            except Exception:
                # 无法 stat（可能权限或不存在），跳过
                continue
            if key in seen:
                continue
            seen.add(key)

            # 列出 current 的直接子目录（表层）
            try:
                # 使用 iterdir 遍历，过滤非目录项；尊重 follow_symlinks: 如果不跟随符号链接，排除 symlink
                children = []
                for p in current.iterdir():
                    try:
                        if not p.is_dir():
                            continue
                        if not follow_symlinks and p.is_symlink():
                            # 跳过符号链接（避免环路）；如果需要跟随，follow_symlinks=True
                            continue
                        children.append(p)
                    except Exception:
                        # 无法访问此条目（权限等），跳过它
                        continue
            except Exception:
                # 当前目录不可遍历（权限、IO 错误等），跳过
                continue

            # 遍历表层子目录，按发现顺序处理
            for subdir in children:
                try:
                    ok = predicate(subdir)
                except Exception:
                    # predicate 出错时跳过该子目录（你也可以选择 re-raise）
                    continue

                if ok:
                    # 符合条件 -> 返回该路径
                    yield str(subdir)

                    # 检查子目录下是否存在 "retests"（仅作为目录名匹配）
                    try:
                        retests = subdir / "retests"
                        if retests.exists() and retests.is_dir():
                            # 把 retests 加入栈以便后续对其表层进行同样查找
                            stack.append(retests)
                    except Exception:
                        # 若检查 retests 时出现 IO 错误，忽略并继续
                        continue
                # 若不满足 predicate，不进入它的 retests（即仅在满足 predicate 时才进入 retests）

    def parse_report_processors(self):
        self.report_processors.clear()
        for i, p in enumerate(self.reports_paths):
            rp = ReportsCombiner.ReportProcessor(i, p, target_scheme=self.target_scheme_name, test_report_class=self.test_reporter_class)
            self.report_processors.append(rp)

    def merge_reports(self):
        # TODO：应该有更多的模式，暂时仅实现了 ReplacePrevious 和 PassRelace 模式
        if self.merge_mode == ReportMergeMode.RelacePrevious or self.merge_mode == ReportMergeMode.PassRelace:
            self._merge_case_units_with_replace()
        else:
            raise NotImplementedError(f'暂未实现{self.merge_mode}合并模式')
        self._merge_runtime_config()
        self._merge_total_report()

    def _check_can_write_file_to_target(self):
        _target_check_file = os.path.join(self.target_merged_report_dir_path, 'session_process_report.yaml')
        _target_check_dict = yaml_utils.read_yaml(_target_check_file)
        if not isinstance(_target_check_dict, dict):
            return True
        _target_check_merged_from_list = _target_check_dict.get('merged_from')
        if not isinstance(_target_check_merged_from_list, list):
            return True
        _check_sum = ''
        for _d in _target_check_merged_from_list:
            _check_sum += _d.get('start_time', '')

        _check_sum_current = ''
        for _d in (rp.test_reporter.summary_report_dict for rp in self.report_processors):
            _check_sum_current += _d.get('start_time', '')

        return bool(_check_sum != _check_sum_current)

    def merge_write_files(self, force_rewrite=False):
        if not force_rewrite and not self._check_can_write_file_to_target():
            t_log.info(f'[{self.__class__.__name__}] Skipping merging report files as it was found that the source report to be merged has the same Check Sum value as the previously merged report.', ext_event=True)
            return

        self._files_merge_others()
        self._files_merge_case_units()
        self._files_merge_summary()

        if os.path.exists(self.target_merged_report_dir_path):
            if self.backup_exists_target_path and not os.path.exists(self.backup_exists_target_path):
                # 尝试备份已存在的target文件夹
                shutil.move(self.target_merged_report_dir_path, self.backup_exists_target_path)
            else:
                shutil.rmtree(self.target_merged_report_dir_path)
        shutil.move(self.target_merged_report_dir_path_tmp, self.target_merged_report_dir_path)

    def _merge_case_units_with_replace(self):
        self._merged_units.clear()

        assert self.report_processors, 'You must call parse_report_processors first!'

        merged_one_units = dict(self.report_processors[0].test_units_dict)

        if self.merge_mode == ReportMergeMode.RelacePrevious:
            for i in range(len(self.report_processors) - 1):
                rp = self.report_processors[i + 1]
                _next_merge_units = rp.test_units_dict
                merged_one_units.update(_next_merge_units)
        else:
            for i in range(len(self.report_processors) - 1):
                rp = self.report_processors[i + 1]
                _next_merge_units = rp.test_units_dict
                for v in _next_merge_units.values():
                    if v.is_pass:
                        merged_one_units.update(_next_merge_units)

        for v in merged_one_units.values():
            self._merged_units.extend(v.units)

        self._merged_units.sort(key=lambda it: it.start_time)

    def _merge_runtime_config(self):
        self._merged_runtime_config_dict = dict(self.report_processors[0].test_reporter.session_runtime_config_dict)
        merged_from = []
        last_task_id = ''
        for i in range(len(self.report_processors)):
            cur_reporter_dict = self.report_processors[i].test_reporter.session_runtime_config_dict
            task_id = cur_reporter_dict.get('task_id')
            if task_id:
                last_task_id = task_id
            merged_from.append(cur_reporter_dict)

        self._merged_runtime_config_dict.update({'task_id': last_task_id, 'merged_from': merged_from})


    def _merge_total_report(self):
        base_reporter_dict = self.report_processors[0].test_reporter.summary_report_dict
        merged_reporter_dict: dict = dict(base_reporter_dict)
        merged_from = []
        merged_reporter_dict['merged_from'] = merged_from

        all_time_points = []
        max_total_count = 0
        max_last_update_time = ''
        last_run_case_id = ''

        def _parse_start_end_time(_reporter: CaseSummaryReporter, _reporter_source_dict: dict):
            _s_t = _reporter_source_dict['start_time']
            _e_t = _reporter_source_dict.get('end_time')
            if not _e_t:
                _e_t = _reporter.end_time.replace(' ', 'T')
            return _s_t, _e_t

        for rp in self.report_processors:
            all_time_points.extend(_parse_start_end_time(rp.test_reporter.summary_reporter_unit, rp.test_reporter.summary_report_dict))
            if rp.test_reporter.summary_reporter_unit.total_count > max_total_count:
                max_total_count = rp.test_reporter.summary_reporter_unit.total_count
            _l_u_t = rp.test_reporter.summary_report_dict['last_update_time']
            if _l_u_t > max_last_update_time:
                max_last_update_time = _l_u_t
                last_run_case_id = rp.test_reporter.summary_report_dict.get('last_run_case_id', '')
            merged_from.append(rp.test_reporter.summary_report_dict)

        # 过滤掉空字符串、None 和仅包含空格的字符串
        all_time_points = [point for point in all_time_points if point and point.strip()]

        all_time_points.sort()
        merged_reporter_dict['start_time'] = all_time_points[0]
        merged_reporter_dict['end_time'] = all_time_points[-1]
        merged_reporter_dict['duration'] = (datetime.fromisoformat(all_time_points[-1]) - datetime.fromisoformat(
            all_time_points[0])).total_seconds()
        merged_reporter_dict['last_update_time'] = max_last_update_time

        total_count = 0
        pass_count = 0
        fail_count = 0

        for u in self._merged_units:
            if not u.last_retry:
                continue
            total_count += 1
            if u.result == 'pass':
                pass_count += 1
            else:
                fail_count += 1

        if total_count > max_total_count:
            max_total_count = total_count

        merged_reporter_dict['total_count'] = max_total_count
        merged_reporter_dict['finish_count'] = total_count
        merged_reporter_dict['finish_rate'] = total_count / max_total_count
        merged_reporter_dict['pass_count'] = pass_count
        merged_reporter_dict['fail_count'] = fail_count
        merged_reporter_dict['pass_rate'] = pass_count / total_count
        merged_reporter_dict['fail_rate'] = 1.0 - merged_reporter_dict['pass_rate']

        merged_reporter_dict['last_run_case_id'] = last_run_case_id
        merged_reporter_dict.pop('filepath', None)
        self._merged_total_report_dict = merged_reporter_dict

    def _files_merge_case_units(self):
        target_dir = self.target_merged_report_dir_path_tmp

        for u in self._merged_units:
            source_path = u.filepath
            bn = os.path.basename(source_path)

            _p_inx = getattr(u, 'parent_index', None)
            if _p_inx:
                target_path = os.path.join(target_dir, bn[:-5] + f'[{_p_inx}].yaml')
                _t = misc_utils.read_all_text(source_path)
                _t = f'source: {_p_inx}\n{_t}'
                misc_utils.write_all_text(target_path, _t)
            else:
                target_path = os.path.join(target_dir, bn)
                shutil.copy(source_path, target_path)

    def _files_merge_summary(self):
        write_total_reports_files = ['session_process_report.yaml']
        if self._merged_total_report_dict['total_count'] <= self._merged_total_report_dict['finish_count']:
            write_total_reports_files.append('session_total_report.yaml')

        for _rf in write_total_reports_files:
            _p = os.path.join(self.target_merged_report_dir_path_tmp, _rf)
            yaml_utils.write_yaml(self._merged_total_report_dict, _p, ignore_yaml_error=False, no_alias=True)

        _merged_runtime_config_file = os.path.join(self.target_merged_report_dir_path_tmp, 'session_runtime_config.yaml')
        yaml_utils.write_yaml(self._merged_runtime_config_dict, _merged_runtime_config_file, ignore_yaml_error=False, no_alias=True)

    def _files_merge_others(self):
        meta_report_paths = [rp.test_reporter.meta_report_dir for rp in self.report_processors]
        self.merge_folders_to_new(meta_report_paths, self.target_merged_report_dir_path_tmp, overwrite_dst=True)

    def get_all_pass_fail_case_ids(self):
        """
        获取测试ID集，返回 all, pass, fail 集
        """
        _all_ids = set()
        _pass_ids = set()
        _fail_ids = set()
        for u in self._merged_units:
            if u.last_retry and u.result != 'pass':
                _fail_ids.add(u.case_id_no_retry)
            else:
                _pass_ids.add(u.case_id_no_retry)
            _all_ids.add(u.case_id_no_retry)
        return _all_ids, _pass_ids, _fail_ids

    @staticmethod
    def merge_folders_to_new(
            src_folders: Sequence[PathLike],
            dst_folder: PathLike,
            *,
            overwrite_dst: bool = False,
            text_merge_exts: Sequence[str] = (".txt", ".log"),
            text_merge_encoding: Optional[str] = None,
            # 当文件位于源文件夹根目录时，若文件名匹配下列任一 pattern 则忽略（不复制）
            root_exclude_regex: str = r"^\d{17}_",  # 17位数字 + 下划线 开头
            root_exclude_names: Sequence[str] = ("session_process_report.yaml",
                                                 "session_runtime_config.yaml",
                                                 "session_total_report.yaml",
                                                 "testReport.xlsx"),
            follow_symlinks: bool = True,
            buffer_size: int = 64 * 1024,
            verbose: bool = False,
    ) -> None:
        """
        将多个文件夹合并为一个新的目标文件夹（另存为新文件夹），按 src_folders 顺序合并。

        参数说明:
          src_folders: 源文件夹路径的可迭代对象，按此顺序合并。
          dst_folder: 目标新文件夹路径（会创建）。如果已存在且 overwrite_dst=False 会抛出 FileExistsError。
          overwrite_dst: 如果 True 且目标已存在，会清空目标（谨慎）。
          text_merge_exts: 视为文本追加合并的扩展名（不区分大小写）。
          text_merge_encoding: 若为 None（默认），对 .txt/.log 使用二进制追加（更保守）。若指定编码（如 "utf-8"），则以文本模式读取/写入（errors='replace'）。
          root_exclude_regex: 在源根目录（仅根）排除的正则（匹配文件名）。
          root_exclude_names: 在源根目录（仅根）精确匹配的文件名列表（忽略大小写按需要调整）。
          follow_symlinks: 是否跟随符号链接（传给 shutil.copy2）。
          buffer_size: 二进制拷贝或追加时的缓冲区大小（字节）。
          verbose: True 则打印过程要点。

        规则实现细节见函数文档（参见题主要求）。
        """
        dst = Path(dst_folder)
        src_paths = [Path(p) for p in src_folders]

        # 目标存在处理
        if dst.exists():
            if not overwrite_dst:
                raise FileExistsError(f"目标文件夹已存在：{dst}（如需覆盖请设置 overwrite_dst=True）")
            # 清空目标
            if verbose:
                print(f"[merge] 清空已存在目标：{dst}")
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)

        # 编译 root 排除正则（用于匹配文件名）
        root_re = re.compile(root_exclude_regex)

        # 规范化 text extset 小写
        text_ext_set = {ext.lower() for ext in text_merge_exts}

        # 依次处理每个源文件夹
        for src_idx, src in enumerate(src_paths):
            if verbose:
                print(f"[merge] 处理源({src_idx})：{src}")
            if not src.exists() or not src.is_dir():
                raise FileNotFoundError(f"源文件夹不存在或不是目录：{src}")

            # walk 源目录，递归复制文件
            # 我们使用 os.walk 以便在 root 级别过滤文件名（只针对 root）
            for root, dirs, files in os.walk(src):
                root_path = Path(root)
                # 判断当前 root 是否为源目录的根（即直接子文件属于根）
                is_root_level = (root_path == src)

                # 在根层过滤要忽略的文件（非递归）
                iter_files = list(files)
                if is_root_level:
                    filtered = []
                    for fname in iter_files:
                        # 精确名匹配或者正则匹配则跳过
                        if fname in root_exclude_names or root_re.match(fname):
                            if verbose:
                                print(f"[merge] 忽略根目录文件（按规则）：{src}/{fname}")
                            continue
                        filtered.append(fname)
                    iter_files = filtered

                for fname in iter_files:
                    src_file = root_path / fname
                    # 目标相对路径基于源根
                    rel = src_file.relative_to(src)
                    dst_file = dst / rel

                    # 确保目标父目录存在
                    dst_file.parent.mkdir(parents=True, exist_ok=True)

                    if not dst_file.exists():
                        # 目标不存在 -> 直接复制（保留元数据）
                        shutil.copy2(src_file, dst_file, follow_symlinks=follow_symlinks)
                        if verbose:
                            print(f"[copy] {src_file} -> {dst_file}")
                        continue

                    # 目标已存在 -> 冲突处理
                    ext = src_file.suffix.lower()
                    if ext in text_ext_set:
                        # 文本合并（追加）
                        if text_merge_encoding is None:
                            # 二进制追加：先写一个换行，再追加源文件 bytes（stream）
                            with open(dst_file, "ab") as dst_f, open(src_file, "rb") as src_f:
                                dst_f.write(b"\n")
                                # 分块写入，避免一次性读入太大文件
                                while True:
                                    chunk = src_f.read(buffer_size)
                                    if not chunk:
                                        break
                                    dst_f.write(chunk)
                            if verbose:
                                print(f"[append-binary] {src_file} -> append to {dst_file}")
                        else:
                            # 文本追加（使用给定编码，errors='replace'）
                            with open(dst_file, "a", encoding=text_merge_encoding, errors="replace",
                                      newline="") as dst_f, \
                                    open(src_file, "r", encoding=text_merge_encoding, errors="replace",
                                         newline="") as src_f:
                                dst_f.write("\n")
                                # 按行追加以避免一次性读大文件
                                for line in src_f:
                                    dst_f.write(line)
                            if verbose:
                                print(
                                    f"[append-text] {src_file} -> append to {dst_file} (encoding={text_merge_encoding})")
                    else:
                        # 非文本扩展名：重命名后复制，命名方式在扩展名前插入 [src_idx]
                        # 目标文件名例如 a.tar.gz 只会把最后一个 suffix 视为扩展名（Path.suffix）。
                        base = dst_file.stem  # 文件名（不含最后的 suffix）
                        suffix = dst_file.suffix  # 包含点，如 ".bin" 或 "" 若无
                        new_name = f"{base}[{src_idx}]{suffix}"
                        new_dst = dst_file.with_name(new_name)
                        counter = 0
                        # 若仍然存在，尝试加计数保持唯一
                        while new_dst.exists():
                            counter += 1
                            new_name = f"{base}[{src_idx}]-{counter}{suffix}"
                            new_dst = dst_file.with_name(new_name)
                        shutil.copy2(src_file, new_dst, follow_symlinks=follow_symlinks)
                        if verbose:
                            print(f"[rename-copy] {src_file} -> {new_dst} (original {dst_file} preserved)")

        if verbose:
            print(f"[merge] 完成，目标文件夹：{dst}")


if __name__ == '__main__':
    rc = ReportsCombiner('fsc',
                         r'D:\Projects\dz_auto_env\.retest\20250908_161004_fsc_X6855_BCL8000000000311',
                         merge_mode=ReportMergeMode.PassRelace,
                         search_retests=True)
    rc.parse_report_processors()
    rc.merge_reports()
    rc.merge_write_files()

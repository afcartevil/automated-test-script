import ast
import os.path
import sys
import textwrap
from functools import cached_property
from io import StringIO
import re
from pathlib import Path
from typing import List, Optional, Tuple, Union, Generator




def iter_test_dirs(root_dir: str) -> Generator[str, None, None]:
    """
    递归遍历指定文件夹，若文件夹中存在任意以 'test_' 开头且以 '.py' 结尾的文件，
    则 yield 该文件夹的绝对路径。
    即使该文件夹满足条件，也会继续递归其子目录。

    :param root_dir: 起始根目录路径
    :return: 生成器，逐个返回匹配文件夹的绝对路径
    """
    for current_dir, dirnames, files in os.walk(root_dir):
        # 判断当前文件夹下是否存在符合条件的测试文件
        if any(f.startswith("test_") and f.endswith(".py") for f in files):
            yield os.path.abspath(current_dir)

def _regex_fallback_extract_docstring(source: str, func_name: str) -> Optional[str]:
    """
    回退方案（文本搜索）：
    - 在 def func_name(...) 的位置处向下查找第一个字符串字面量（优先 triple-quoted）
    - 提取其文本内容（不含引号），对内部做 dedent 后返回
    注意：这是 best-effort 回退，不如 ast 精确，但能在源文件有轻微语法问题时仍取到 docstring。
    """
    # 找到函数定义位置（最先匹配）
    def_re = re.compile(r'^\s*def\s+' + re.escape(func_name) + r'\s*\(', re.MULTILINE)
    m = def_re.search(source)
    if not m:
        return None
    # 从 def 行结束处开始扫描后续文本
    start_pos = m.start()
    # slice from the end of the def line to EOF
    # we want the text after the line containing the def (to skip function signature lines)
    # find the end of the def line (first newline after match start)
    nl = source.find('\n', m.start())
    scan_pos = nl + 1 if nl >= 0 else m.end()

    tail = source[scan_pos:]

    # Try triple-quoted string first ("""...""" or '''...''')
    triple_re = re.compile(r'^[ \t]*([ruRf]?)(?P<quote>"""|\'\'\')(?P<body>.*?)(?P=quote)', re.DOTALL | re.MULTILINE)
    m2 = triple_re.search(tail)
    if m2:
        body = m2.group('body')
        # dedent and strip leading/trailing line breaks similar to inspect.cleandoc behavior
        ded = textwrap.dedent(body)
        # remove a single leading/trailing newline if present (mimic common docstring style trimming)
        if ded.startswith('\n'):
            ded = ded[1:]
        if ded.endswith('\n'):
            ded = ded[:-1]
        return ded

    # If no triple-quoted found, try single-line quoted docstring (e.g. "short" or 'short')
    single_re = re.compile(r'^[ \t]*([ruRf]?)(?P<quote>"|\')(?P<body>.*?)(?P=quote)', re.DOTALL | re.MULTILINE)
    m3 = single_re.search(tail)
    if m3:
        body = m3.group('body')
        # single-line: just return stripped body
        return body

    return None


def find_test_py_files(
        root: Union[str, Path],
        *,
        follow_symlinks: bool = True,
        max_depth: Optional[int] = None
) -> List[str]:
    """
    在 root 目录下递归查找以 "test_" 开头且以 ".py" 结尾的 Python 文件，返回绝对路径列表（字符串）。

    参数:
      root: 要搜索的根目录路径（str 或 Path）。
      follow_symlinks: 是否跟随目录符号链接（默认 True）。
      max_depth: 可选最大递归深度（相对于 root）。
                 - None 表示无限制。
                 - 0 表示只在 root 的表层查找。
                 - 1 表示查找 root 及其直接子目录，依此类推。

    返回:
      List[str]：匹配到的文件绝对路径，按字符串排序。
    """
    root_path = Path(root)
    if not root_path.exists():
        return []

    # Normalize root for relative-depth calculations
    root_path = root_path.resolve(strict=False)

    results: List[str] = []
    # Use os.walk to control followlinks and allow pruning directories by depth
    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=follow_symlinks):
        # compute depth relative to root_path
        try:
            rel = Path(dirpath).relative_to(root_path)
            depth = len(rel.parts)  # root -> depth 0; child -> 1; ...
        except Exception:
            # if relative_to fails for some reason, conservatively set depth large
            depth = 0

        # prune when beyond max_depth
        if (max_depth is not None) and (depth > max_depth):
            # don't descend further from this directory
            dirnames[:] = []
            continue

        for name in filenames:
            # filename must start with 'test_' and end with '.py' (case-insensitive suffix)
            if name.startswith("test_") and name.lower().endswith(".py"):
                p = Path(dirpath) / name
                # produce an absolute/resolved path; use strict=False to avoid exceptions on broken symlinks
                try:
                    abs_p = p.resolve(strict=False)
                except Exception:
                    abs_p = p.absolute()
                results.append(str(abs_p))

    results.sort()
    return results


def extract_function_docstring(source: str, func_name: str) -> Optional[str]:
    """
    从 Python 源码字符串 source 中提取函数 func_name 下方的 docstring 内容（若存在）。
    返回:
      - str: docstring 的文本内容（不含首尾引号，去掉统一缩进，保留内部换行）
      - None: 未找到该函数或该函数没有 docstring

    说明:
      - 优先使用 ast.get_docstring(..., clean=True)（可靠且去除公共缩进）
      - 在 ast 解析失败时使用文本正则进行回退提取（best-effort）
    """
    # First try with ast for robustness
    try:
        module = ast.parse(source)
    except Exception:
        # parsing failed: fallback
        return _regex_fallback_extract_docstring(source, func_name)

    # Walk the AST to find a FunctionDef or AsyncFunctionDef with the given name.
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            # ast.get_docstring with clean=True removes common indentation (inspect.cleandoc)
            ds = ast.get_docstring(node, clean=True)
            return ds  # may be None if no docstring
    # If not found, fallback to regex method
    return _regex_fallback_extract_docstring(source, func_name)


def _normalize_decorator_lines(lines: List[str]) -> str:
    """
    将一个装饰器的多行文本归一化为单行：
      - 去掉每行前后的空白
      - 如果行以反斜线结尾，去掉反斜线并在合并处插入空格
      - 合并多行，最后把连续空白压缩为单个空格
    返回单行字符串（以 '@' 开头）。
    """
    parts: List[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.endswith("\\"):
            s = s[:-1].rstrip()
            parts.append(s)
            # We'll ensure a separating space when joining
            parts.append(" ")
        else:
            parts.append(s)
            parts.append(" ")
    joined = "".join(parts).strip()
    # collapse multiple whitespace into single space, but keep meaningful spacing inside strings/parentheses.
    # This is a pragmatic approach: collapse sequences of whitespace characters into a single space.
    normalized = re.sub(r'\s+', ' ', joined)
    return normalized


def collect_pytest_marks(source: str, func_name: str) -> List[str]:
    """
    从 source（完整 .py 文件内容）中，找到函数 func_name 的定义，并收集该函数上方
    属于该函数的所有以 '@pytest.mark.' 开头的装饰器（支持多行装饰器）。
    返回按源码自上而下顺序的 list[str]，每个元素为归一化后的单行装饰器文本。

    参数:
      source: Python 文件内容（字符串）
      func_name: 要查找的函数名（例如 "test_foo"）

    返回:
      list of normalized decorator strings. 如果函数未找到或没有匹配装饰器，返回空列表。
    """
    lines = source.splitlines()
    n = len(lines)

    # 1) 找到函数定义行（第一个匹配的 def func_name(...)）
    func_def_idx: Optional[int] = None
    func_def_re = re.compile(r'^\s*def\s+' + re.escape(func_name) + r'\s*\(')
    for i, ln in enumerate(lines):
        if func_def_re.match(ln):
            func_def_idx = i
            break
    if func_def_idx is None:
        # 未找到函数定义
        return []

    # 2) 逐行扫描源码以识别所有装饰器块（start_idx, end_idx, lines_list）
    decorator_blocks = []  # list of tuples (start, end, lines)
    i = 0
    while i < n:
        ln = lines[i]
        # A decorator begins with a line whose non-space prefix starts with '@'
        if ln.lstrip().startswith('@'):
            start = i
            # We need to find the end line of this decorator expression.
            # Strategy: scan forward, track parentheses depth and backslash continuations.
            paren_depth = 0
            ended = False
            j = i
            while j < n:
                cur = lines[j]
                # Count parentheses but ignore those inside simple string literals is hard.
                # We use a heuristic: count '(' and ')' naively.
                # This will cover the vast majority of pytest.mark(...) multi-line cases.
                for ch in cur:
                    if ch == '(':
                        paren_depth += 1
                    elif ch == ')':
                        if paren_depth > 0:
                            paren_depth -= 1
                # If current line ends with a backslash (line continuation), keep going.
                if cur.rstrip().endswith('\\'):
                    j += 1
                    continue
                # If we have no open parentheses and the current line doesn't end with a backslash,
                # then the decorator expression is complete at this line.
                if paren_depth == 0:
                    ended = True
                    j += 1
                    break
                else:
                    j += 1
                    continue
            if not ended:
                # Reached EOF w/o closing parentheses; treat until last line as decorator
                end = n - 1
            else:
                end = j - 1
            block_lines = lines[start:end + 1]
            decorator_blocks.append((start, end, block_lines))
            i = end + 1
            continue
        else:
            i += 1

    # 3) 从 func_def_idx 向上收集属于该函数的装饰器块
    results: List[str] = []
    cur_idx = func_def_idx - 1
    # We'll allow contiguous decorator blocks that directly attach to the function:
    # that means each block must occupy lines that are immediately above the next one (no intervening non-decorator lines),
    # and the top-most decorator's start must be the first non-empty non-comment line when scanning upward until a break.
    # Implementation: while cur_idx >= 0 and the line at cur_idx is inside any decorator block, collect that block.
    # After collecting a block, set cur_idx to block.start - 1 and continue.
    # Stop when cur_idx points to a line not belonging to any decorator block (this handles multiple stacked decorators).
    decorator_map = {}  # map any line index -> block index
    for bi, (s, e, blines) in enumerate(decorator_blocks):
        for idx in range(s, e + 1):
            decorator_map[idx] = bi

    collected_blocks = []
    while cur_idx >= 0:
        if cur_idx in decorator_map:
            bi = decorator_map[cur_idx]
            s, e, blines = decorator_blocks[bi]
            # Add this block (but ensure we don't add duplicates if we encounter same block twice)
            if bi not in collected_blocks:
                collected_blocks.append(bi)
            # move pointer to the line above this block
            cur_idx = s - 1
            # Also skip over any blank/comment lines between decorators?
            # Python requires decorators to be contiguous; but be conservative and skip comment lines
            # However if an intervening non-empty non-comment line exists, we'll break next loop iteration.
            while cur_idx >= 0 and lines[cur_idx].strip().startswith('#'):
                cur_idx -= 1
            continue
        else:
            break

    # collected_blocks is list of block indices in bottom-to-top order (because we scanned upward).
    # Convert to top-to-bottom order:
    collected_blocks.reverse()

    # 4) Filter those starting with '@pytest.mark.' and normalize them
    for bi in collected_blocks:
        s, e, blines = decorator_blocks[bi]
        # Determine the first non-space content of the first line
        first_line_stripped = blines[0].lstrip()
        if first_line_stripped.startswith('@pytest.mark.'):
            normalized = _normalize_decorator_lines(blines)
            results.append(normalized)

    return results


class TaepTestClassConverter:
    def __init__(self, source_test_class_filepath: str, sub_module_path: str):
        self.source_test_class_filepath = source_test_class_filepath
        self.sub_module_path = sub_module_path.replace('\\', '/').rstrip('/')
        self.relative_source_test_class_filepath = os.path.normpath(source_test_class_filepath).replace(
            os.path.normpath(PROJ_DIR), '').lstrip('/\\')
        s_flag = '\\'
        if self.relative_source_test_class_filepath.find('/') >= 0:
            s_flag = '/'
        _relative_source_test_class_filepath_splits = self.relative_source_test_class_filepath.split(s_flag, maxsplit=4)
        self.team_name = _relative_source_test_class_filepath_splits[1]
        self.scheme_name = _relative_source_test_class_filepath_splits[2]

        if self.sub_module_path:
            _sub_module_ext = '_' + self.sub_module_path.replace('/', '_')
        else:
            _sub_module_ext = ''

        self.target_test_class_filepath = os.path.join(os.path.dirname(source_test_class_filepath),
                                                       f'{os.path.basename(source_test_class_filepath)[:-3]}{_sub_module_ext}_taep.py')

        _r = os.path.dirname(self.relative_source_test_class_filepath)[5:].replace('\\', '/')

        if self.sub_module_path:
            _r = _r + '/' + self.sub_module_path

        _rs = _r.split('/')
        self.source_taep_cases_repo_dir = str(os.path.join(PROJ_DIR, 'taep', 'TestCase', *_rs))

    @cached_property
    def source_test_class_name(self):
        _text = misc_utils.read_all_text(self.source_test_class_filepath)
        _a = _text.index('class ')
        _b = _text.index('(', _a)
        return _text[_a + 6:_b]

    @cached_property
    def target_test_class_name(self):
        if self.sub_module_path:
            _ss = [_s.capitalize() for _s in self.sub_module_path.split('/')]
            return self.source_test_class_name + ''.join(_ss) + 'Taep'
        else:
            return self.source_test_class_name + 'Taep'

    @cached_property
    def _text_target_import_header(self):
        _m = self.relative_source_test_class_filepath.replace('/', '.').replace('\\', '.')[:-3]
        return f'import pytest\n\nfrom {_m} import {self.source_test_class_name}\n'

    @cached_property
    def source_taep_package_name(self):
        _o = 'testcase' + self.relative_source_test_class_filepath[5:-len(os.path.basename(self.relative_source_test_class_filepath))].replace('\\', '.').replace('/', '.').rstrip('.')
        if self.sub_module_path:
            _o += '.' + self.sub_module_path.replace('/', '.')
        return _o

    def _collect_taep_cases_decorators_docs(self) -> List[Tuple[str, Optional[List[str]], Optional[str]]]:
        _files = find_test_py_files(self.source_taep_cases_repo_dir, max_depth=0)
        ret = []
        for _f in _files:
            _f_text = misc_utils.read_all_text(_f)
            _func_name = os.path.basename(_f)[:-3]
            ret.append((_func_name, collect_pytest_marks(_f_text, _func_name), extract_function_docstring(_f_text, _func_name)))
        return ret

    def _build_one_case_text(self, text_builder: StringIO, case_name: str, case_decorators: Optional[List[str]], case_docs: Optional[str]):
        if case_decorators:
            for _d in case_decorators:
                text_builder.write(f'    {_d}\n')
        text_builder.write(f'    def {case_name}(self):\n')
        if case_docs:
            text_builder.write('        """\n')
            for _l in case_docs.splitlines():
                text_builder.write('        ')
                text_builder.write(_l)
                text_builder.write('\n')
            text_builder.write('        """\n')
        text_builder.write(f'        from {self.source_taep_package_name} import {case_name}\n')
        text_builder.write(f'        {case_name}.{case_name}()\n')

    def build(self):
        with StringIO() as _target_text_builder:
            _target_text_builder.write(self._text_target_import_header)
            _target_text_builder.write('\n\n')
            _target_text_builder.write(f'class {self.target_test_class_name}({self.source_test_class_name}):\n')
            _build_any = False
            for _case_name, _case_decorators, _case_docs in self._collect_taep_cases_decorators_docs():
                _case_decorators.insert(0, f"@pytest.mark.taep_case('{self.source_taep_package_name}.{_case_name}')")
                _target_text_builder.write('\n')
                self._build_one_case_text(_target_text_builder, _case_name, _case_decorators, _case_docs)
                _build_any = True
            if not _build_any:
                _target_text_builder.write('    ...\n')
            misc_utils.write_all_text(self.target_test_class_filepath, _target_text_builder.getvalue())


class TaepTestClassConverterRecursively:
    def __init__(self, root_source_test_class_filepath: str):
        super().__init__()
        self.root_source_test_class_filepath = root_source_test_class_filepath
        self.relative_source_test_class_filepath = os.path.normpath(root_source_test_class_filepath).replace(os.path.normpath(PROJ_DIR), '').lstrip('/\\')
        _r = os.path.dirname(self.relative_source_test_class_filepath)[5:].replace('\\', '/')
        _rs = _r.split('/')
        self.root_source_taep_cases_repo_dir = str(os.path.join(PROJ_DIR, 'taep', 'TestCase', *_rs))

    def build(self):
        for _i in self.iter_test_dirs_relative(self.root_source_taep_cases_repo_dir):
            _ttcc = TaepTestClassConverter(self.root_source_test_class_filepath, _i).build()

    @staticmethod
    def iter_test_dirs_relative(root_dir: str) -> Generator[str, None, None]:
        root_dir = os.path.normpath(os.path.abspath(root_dir))
        root_dir_len = len(str(root_dir)) + 1
        for _p in iter_test_dirs(root_dir):
            _pp = os.path.normpath(_p)[root_dir_len:].replace('\\', '/')
            yield _pp

def add_path_to_python_env():
    root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    print(root_path)
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    plugins_path = os.path.join(root_path, 'plugins')
    if os.path.exists(plugins_path):
        sys.path.insert(0, plugins_path)

if __name__ == '__main__':
    if len(sys.argv) == 1:
        from powertrde.env import PROJ_DIR
        from powertrde.utils import misc_utils
        # 相当于python taep_case_converter.py，不传参，使用默认方法，手动
        TaepTestClassConverterRecursively(r'D:\RUN\ppt\taep\tests\dzppt\fsc\mock\test_fsc_mock.py').build()
    else:
        # 当前使用传参方式，方便于右键插件执行
        add_path_to_python_env()
        from powertrde.env import PROJ_DIR
        from powertrde.utils import misc_utils
        if len(sys.argv) < 2:
            print("用法: python teep_case_converter.py <case的test父类文件> <子目录>")
            print(r"示例: python teep_case_converter.py "
                  r"D:\RUN\ppt\taep\tests\dzppt\fsc\mock\test_fsc_mock.py phone/mymock")
            sys.exit(1)
        converter_py = sys.argv[0]  # ......\taep_case_converter.py
        case_py = sys.argv[1]  # D:\RUN\ppt\taep\tests\dzppt\fsc\mock\test_fsc_mock.py
        if len(sys.argv) < 3 or sys.argv[2] == '.':  # 如果有子目录参数，并且不为.
            TaepTestClassConverterRecursively(f'{case_py}').build()
        else:
            TaepTestClassConverter(f'{case_py}', sys.argv[2]).build()

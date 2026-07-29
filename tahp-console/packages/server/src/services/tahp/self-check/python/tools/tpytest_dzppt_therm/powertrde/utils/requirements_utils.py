from __future__ import annotations

import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import importlib.util
from typing import Iterable, Tuple, List, Dict, Optional, Set, Union, Mapping, Any
import os
import re

from powertrde.framework.tran_logger import t_log
from powertrde.utils.lazy_shared_pool import LazySharedPool

# --- 强烈建议在环境中安装 packaging ----
try:
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version, InvalidVersion

    # packaging 用于更准确解析 requirement 行（不是必须）
    from packaging.requirements import Requirement as _PackReq  # type: ignore
    from packaging.utils import canonicalize_name as _canonicalize

    _HAS_PACKAGING = True

except Exception as _e:
    _PackReq = None  # type: ignore


    def _canonicalize(n: str) -> str:
        """简单 canonicalize：lower and replace '_' -> '-' (compatible with packaging.utils)"""
        return n.lower().replace('_', '-')


    _HAS_PACKAGING = False

# 用于检测 requirements 文件名（你可以调整前缀/后缀）
DEFAULT_PREFIX = "requirements"
DEFAULT_SUFFIX = ".txt"

RequirementSource = Union[str, Path, Iterable[str]]

# -r / --requirement 包含文件的解析正则
_INCL_RE = re.compile(r'^(?:-r|--requirement)[=\s]+(.+)$', flags=re.IGNORECASE)


def _find_requirement_files(roots: Iterable[Union[str, Path]], pattern_prefix: str = DEFAULT_PREFIX,
                            pattern_suffix: str = DEFAULT_SUFFIX) -> List[Path]:
    """
    递归在 roots 中查找文件名以 pattern_prefix 开头并以 pattern_suffix 结尾的文件（去重）。
    roots 可以包含文件或目录（如果传入单个 requirements.txt 文件路径也支持）。
    """
    roots = [Path(r) for r in roots]
    files: List[Path] = []
    for r in roots:
        if r.exists() and r.is_file():
            files.append(r.resolve())
        elif r.exists() and r.is_dir():
            for dirpath, _dirnames, filenames in os.walk(r):
                for fn in filenames:
                    ln = fn.lower()
                    if ln.startswith(pattern_prefix) and ln.endswith(pattern_suffix):
                        files.append(Path(dirpath) / fn)
    # 保持顺序去重
    seen: Set[Path] = set()
    uniq: List[Path] = []
    for f in files:
        try:
            fr = f.resolve()
        except Exception:
            fr = f
        if fr not in seen:
            seen.add(fr)
            uniq.append(fr)
    return uniq


def _parse_requirements_file(path: Path, out: List[Tuple[str, Path]], visited: Set[Path],
                             follow_includes: bool = True) -> None:
    """
    读取文件，将非注释行加入 out，同时如果遇到 -r/--requirement 则递归解析（如果 follow_includes=True）。
    使用 utf-8 首选，失败回退 latin-1，最终读取失败则跳过。
    """
    try:
        p = path.resolve()
    except Exception:
        p = path
    if p in visited:
        return
    visited.add(p)
    text = None
    for enc in ("utf-8", "latin-1"):
        try:
            text = p.read_text(encoding=enc)
            break
        except Exception:
            text = None
    if text is None:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        m = _INCL_RE.match(line)
        if m and follow_includes:
            inc = m.group(1).strip().strip('"').strip("'")
            inc_path = (p.parent / inc)
            if inc_path.exists():
                _parse_requirements_file(inc_path, out, visited, follow_includes)
                continue
        out.append((line, p))


def smart_merge_requirements(
        roots: Iterable[Union[str, Path]],
        *,
        output_file: Optional[Union[str, Path]] = None,
        follow_includes: bool = True,
        pattern_prefix: str = DEFAULT_PREFIX,
        pattern_suffix: str = DEFAULT_SUFFIX,
        verbose: bool = False
) -> Dict[str, object]:
    """
    从一个或多个根目录中自动收集 requirements 文件并智能合并依赖。

    返回字典:
      {
        'merged': List[str],    # 合并后的 requirements 行（已去重，按包名排序）
        'warnings': List[str],  # 合并过程中的警告信息
        'sources': List[str],   # 扫描到的 requirements 文件路径
      }

    参数说明:
      - roots: 可迭代路径列表（字符串或 Path），可以是文件或目录。
      - output_file: 若不为 None 或空，则把合并结果写到此路径（可为 None）。
      - follow_includes: 是否跟随 -r/--requirement 引用的文件（递归）。
      - pattern_prefix / pattern_suffix: 用于匹配 requirements 文件名（默认匹配 requirements*.txt）。
      - verbose: 输出额外信息。
    """
    if not _HAS_PACKAGING:
        raise RuntimeError("需要安装 'packaging' 库：pip install packaging")

    roots = list(roots)
    req_files = _find_requirement_files(roots, pattern_prefix, pattern_suffix)
    if verbose:
        print("[smart-merge] found requirement files:", req_files)

    collected: List[Tuple[str, Path]] = []
    visited: Set[Path] = set()
    for f in req_files:
        _parse_requirements_file(Path(f), collected, visited, follow_includes)

    if verbose:
        print("[smart-merge] collected lines:", len(collected))

    # 分组数据结构
    grouped = {}  # key = (canonical_name, extras_tuple) -> list of entries { 'req': Requirement, 'raw': str, 'src': Path, 'editable': bool }
    url_group = {}  # key = (canonical_name, extras) -> list of raw URL/VCS lines (无法用数字版本比较)
    options: List[Tuple[str, Path]] = []  # 以 '-' 开头的非 -e 行（index、flags等）
    unparsed: List[Tuple[str, Path]] = []  # 无法解析的行

    for line, src in collected:
        # 以 - 开头且不是 -e 的，归入 options（如 -i, --extra-index-url）
        if line.startswith('-') and not line.lower().startswith('-e '):
            options.append((line, src))
            continue

        # 尝试用 packaging.Requirement 解析
        try:
            req = _PackReq(line)
        except Exception:
            # 识别 '#egg=name' 的 URL（常见在 VCS/直接 URL）
            m = re.search(r'#egg=([^&]+)', line)
            if m:
                name = m.group(1)
                key = (_canonicalize(name), tuple())
                url_group.setdefault(key, []).append({'raw': line, 'src': src})
                continue
            # 未知行/无法解析 -> 记录到 unparsed（保留原行）
            unparsed.append((line, src))
            continue

        # 如果解析成功但没有 name（罕见），放 unparsed
        if not req.name:
            unparsed.append((line, src))
            continue

        # 制作分组 key：包名 canonical + extras tuple（sorted）
        name_key = _canonicalize(req.name)
        extras_t = tuple(sorted(req.extras)) if req.extras else tuple()
        key = (name_key, extras_t)
        entry = {'req': req, 'raw': line, 'src': src, 'editable': line.lower().startswith('-e ')}
        grouped.setdefault(key, []).append(entry)

    # 对每个包进行合并决策
    merged_items: List[Tuple[Optional[str], str, Set[str]]] = []  # (name_or_none, line_to_emit, source_set)
    warnings: List[str] = []

    for key, items in grouped.items():
        name, extras = key
        extras_str = f"[{','.join(extras)}]" if extras else ""
        sources = set(str(it['src']) for it in items)

        # collect pinned explicit versions (== / ===), and collect spec strings for intersection
        pinned_versions: Set[Version] = set()
        spec_parts: List[str] = []
        has_specifier = False

        for it in items:
            req = it['req']
            spec_str = str(req.specifier) if req.specifier else ''
            if spec_str:
                has_specifier = True
                spec_parts.append(spec_str)
            # 从各个 Specifier 中搜集精确 pinned(== 或 ===) 版本
            if req.specifier:
                for sp in req.specifier:
                    if sp.operator in ('==', '==='):
                        try:
                            v = Version(sp.version)
                            pinned_versions.add(v)
                        except InvalidVersion:
                            # 如果非法版本字符串忽略
                            continue

        # 形成合并结果（优先级：explicit == 最大 > 合并后的区间 > 无版本）
        chosen_line = None
        if pinned_versions:
            chosen = max(pinned_versions)
            chosen_line = f"{name}{extras_str}=={chosen}"
            if len(pinned_versions) > 1:
                warnings.append(
                    f"{name}: found multiple pinned versions {sorted(str(v) for v in pinned_versions)} in {sources}; chose highest {chosen}")
            # 若同时存在区间约束，检查 chosen 是否满足区间
            if spec_parts:
                combined_spec = SpecifierSet(','.join(spec_parts))
                if not (chosen in combined_spec):
                    warnings.append(
                        f"{name}: chosen pinned version {chosen} does NOT satisfy other constraints {combined_spec}; sources: {sources}")
        elif has_specifier:
            combined_spec = SpecifierSet(','.join(spec_parts))
            # 如果 combined_spec 为真，则输出类似 "name>=1.0,<2.0"
            chosen_line = f"{name}{extras_str}{combined_spec}"
        else:
            # 没有任何版本约束 -> 产出无版本的行（但如果同包被别处指定版本，则该无版本会被覆盖，因为 grouped 只包含同名项）
            chosen_line = f"{name}{extras_str}"

        merged_items.append((name, chosen_line, sources))

    # 把 URL / VCS / editable 等条目单独加入（这些行无法通过数字版本比较）
    for key, vals in url_group.items():
        name, extras = key
        for v in vals:
            merged_items.append((name, v['raw'], {str(v['src'])}))
            warnings.append(f"{name}: included direct URL/VCS entry from {v['src']}; kept as-is")

    # 把 options / unparsed 放到末尾（原样追加）
    for line, src in options + unparsed:
        merged_items.append((None, line, {str(src)}))

    # 排序：按包名（字母序）排列，options（name None）放在末尾
    named = sorted([t for t in merged_items if t[0]], key=lambda x: x[0].lower())
    tail = [t for t in merged_items if not t[0]]
    final_list = [t[1] for t in (named + tail)]

    # 去重（保留首次出现）
    seen: Set[str] = set()
    deduped: List[str] = []
    for ln in final_list:
        if ln in seen:
            continue
        seen.add(ln)
        deduped.append(ln)

    # 写文件（可选）
    if output_file:
        outp = Path(output_file)
        header = ["# merged requirements", f"# source files: {', '.join(str(x) for x in req_files)}"]
        if warnings:
            header.append("# warnings:")
            for w in warnings:
                header.append(f"#   {w}")
        outp.write_text("\n".join(header + [""] + deduped), encoding="utf-8")

    return {'merged': deduped, 'warnings': warnings, 'sources': [str(p) for p in req_files]}


# Python 3.8+ 有 importlib.metadata；对旧版本做兼容导入
try:
    import importlib.metadata as _imd
except Exception:
    try:
        import importlib_metadata as _imd  # type: ignore
    except Exception:
        _imd = None  # type: ignore

# -------- helpers: 解析 requirements 行（尽量快速） --------
_INCL_RE = re.compile(r'^\s*(?:-r|--requirement)\s+(.+)', re.IGNORECASE)
_EGG_RE = re.compile(r'#egg=([^&\s]+)')
_COMMENT_RE = re.compile(r'(^|\s)#')  # 找到注释开始


# 用于从一行中提取“包名”（不含 extras, 不含版本）
def _extract_name_from_line(line: str) -> Optional[str]:
    """
    从 requirement 文件的一行中提取包名（如果能提取）。
    支持这些情形:
      - pkg==1.2.3  -> pkg
      - pkg[extra]>=1.0 -> pkg
      - pkg @ git+...#egg=name -> 尝试取 egg 或左侧 name
      - -e git+...#egg=name -> egg
      - url...#egg=name -> egg
      - git+ssh://... -> None 如果没有 egg
      - -i/--index-url 或以 '-' 开头的控制行 -> None
    """
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    # options like -i, --extra-index-url, --find-links 等 -> ignore
    if line.startswith('-') and not line.lower().startswith('-e '):
        return None

    # 包含 #egg= 的 URL 或 -e 可通过 egg 提取名字
    m = _EGG_RE.search(line)
    if m:
        return m.group(1)

    # 如果使用 packaging 可直接解析
    if _HAS_PACKAGING and _PackReq is not None:
        try:
            r = _PackReq(line)
            if r.name:
                return r.name
        except Exception:
            # 解析失败，回落到正则策略
            pass

    # 回退策略（轻量）：按第一个空格或分隔符分割，去掉 extras/版本/markers
    # 分隔符： whitespace, '[', '@', '==', '>=', '<=', '~=', '!=', '>', '<', ';'
    split = re.split(r'[\s\[\]@!=<>;~]+', line, maxsplit=1)
    if split:
        name_candidate = split[0].strip()
        # 排除像 'git+' 这样的前缀
        if name_candidate.lower().startswith(('git+', 'http:', 'https:', 'ssh:', 'file:')):
            return None
        # 排除空或奇怪字符
        if name_candidate:
            return name_candidate
    return None


# 读取 requirements 文件，支持 -r 引用（可选）
def _read_requirements_file(path: Path, follow_includes: bool = True, visited: Optional[Set[Path]] = None) -> List[
    Tuple[str, Path]]:
    """
    读取 requirements 文件，展开 -r 引用（若 follow_includes=True）。
    返回 list[(line, source_path)] 仅包含非注释/非空的真实行。
    """
    if visited is None:
        visited = set()
    try:
        p = path.resolve()
    except Exception:
        p = path
    if p in visited:
        return []
    visited.add(p)
    # 优先用 utf-8，再 fallback
    text = None
    for enc in ('utf-8', 'latin-1'):
        try:
            text = p.read_text(encoding=enc)
            break
        except Exception:
            text = None
    if text is None:
        return []
    out: List[Tuple[str, Path]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        m = _INCL_RE.match(line)
        if m and follow_includes:
            inc = m.group(1).strip().strip('"').strip("'")
            inc_path = (p.parent / inc)
            if inc_path.exists():
                out.extend(_read_requirements_file(inc_path, follow_includes, visited))
            continue
        out.append((line, p))
    return out


# ------------- 检查包是否已安装（高效） ----------------
def _build_installed_index() -> Tuple[Set[str], Mapping[str, List[str]]]:
    """
    构建已安装包索引：
      - installed_dists_set: set of canonicalized distribution names (lower-like)
      - top_to_dists: mapping top-level module name -> list of distribution names that provide it (via packages_distributions)
    这一步读本地元数据，代价一次性付出（通常很快），后续查询 O(1)。
    """
    installed_dists_set: Set[str] = set()
    top_to_dists: Mapping[str, List[str]] = {}
    if _imd is None:
        return installed_dists_set, top_to_dists

    try:
        # packages_distributions mapping is efficient in modern importlib.metadata
        if hasattr(_imd, 'packages_distributions'):
            try:
                top_to_dists = _imd.packages_distributions()
            except Exception:
                top_to_dists = {}
        # distributions iteration to collect canonical names
        for dist in _imd.distributions():
            try:
                nm = dist.metadata.get('Name') or dist.metadata.get('name') or dist.metadata.get('Summary')
            except Exception:
                nm = None
            if not nm:
                # try fallback to dist.metadata.name attr
                try:
                    nm = getattr(dist, 'name', None)
                except Exception:
                    nm = None
            if nm:
                installed_dists_set.add(_canonicalize(nm))
    except Exception:
        # 极端环境下回退为空索引（仍可尝试 find_spec checks）
        installed_dists_set = set()
        top_to_dists = {}
    return installed_dists_set, top_to_dists


def is_package_present(pkgname: str, installed_dists_set: Set[str], top_to_dists: Mapping[str, List[str]]) -> bool:
    """
    快速判断 pkgname（原始名）在当前环境是否存在。
    策略（按顺序）：
      1) 尝试 importlib.util.find_spec(pkgname)（适用于多数情况）
      2) 尝试按 distribution 名称查找（canonicalize）
      3) 尝试按 top-level module 映射查找
      4) 最后尝试 import pkgname as module（import 尝试可能较慢/有副作用）
    """
    name = pkgname.strip()
    if not name:
        return False

    # 1) 尝试 find_spec（最快）
    try:
        if importlib.util.find_spec(name) is not None:
            return True
    except Exception:
        pass

    # 2) 检查 distribution 名称索引
    try:
        if _canonicalize(name) in installed_dists_set:
            return True
    except Exception:
        pass

    # 3) 检查 top-level -> distributions 映射
    try:
        if name in top_to_dists:
            return True
        # 也试 lowercased key（有些环境下 top-level 小写）
        if name.lower() in top_to_dists:
            return True
    except Exception:
        pass

    # 4) 最后尝试实际 import（有副作用但作为最后手段）
    try:
        __import__(name)
        return True
    except Exception:
        return False


# --------------- 主函数：快速批量检查 -------------------
def check_requirements_presence(
        req_paths: Iterable[str | Path],
        *,
        recursive: bool = False,
        follow_includes: bool = True,
        find_pattern_prefix: str = DEFAULT_PREFIX,
        find_pattern_suffix: str = DEFAULT_SUFFIX,
) -> Tuple[Set[str], Set[str]]:
    """
    参数:
      req_paths: 要检查的 requirements 文件路径或目录（可传多个）。如果传入目录且 recursive=True，会递归查找匹配 pattern 的文件。
      recursive: 当传入目录时是否递归查找 requirements*.txt 文件
      follow_includes: 是否跟随 -r 引用的文件
    返回:
      (present_set, missing_set) -- 两个 set，元素为解析得到的包名（原始形式）
    """
    # 收集 requirements 文件列表
    files: List[Path] = []
    for p in req_paths:
        pth = Path(p)
        if pth.is_file():
            files.append(pth.resolve())
        elif pth.is_dir():
            if recursive:
                for dirpath, _dirs, files_in in os.walk(pth):
                    for fn in files_in:
                        ln = fn.lower()
                        if ln.startswith(find_pattern_prefix) and ln.endswith(find_pattern_suffix):
                            files.append(Path(dirpath) / fn)
            else:
                for entry in pth.iterdir():
                    if entry.is_file() and entry.name.lower().startswith(
                            find_pattern_prefix) and entry.name.lower().endswith(find_pattern_suffix):
                        files.append(entry.resolve())
        else:
            # 不存在路径跳过
            continue

    # 解析每个文件，收集所有候选包名（保持插入顺序无关，但转为 set 去重）
    all_lines: List[Tuple[str, Path]] = []
    for f in files:
        all_lines.extend(_read_requirements_file(f, follow_includes=follow_includes))

    candidates: List[str] = []
    for line, src in all_lines:
        nm = _extract_name_from_line(line)
        if nm:
            candidates.append(nm)

    # 去重并保持稳定顺序（使用 dict.fromkeys）
    unique_pkgs = list(dict.fromkeys(candidates).keys())

    # 构建安装索引（一次性）
    installed_idx, top2d = _build_installed_index()

    present: Set[str] = set()
    missing: Set[str] = set()

    for name in unique_pkgs:
        if is_package_present(name, installed_idx, top2d):
            present.add(name)
        else:
            missing.add(name)

    return present, missing


def _normalize_lines_from_source(
        source: RequirementSource,
        *,
        follow_includes: bool = True,
) -> List[str]:
    """
    将传入的 requirements source 规范成 expanded 的行列表（去除注释与空行）。
    - 如果 source 是文件路径（str/Path），会使用 _read_requirements_file 解析并 expand -r 引用（若 follow_includes=True）。
    - 如果 source 是可迭代字符串（list of lines），直接使用这些行（会 strip & drop comments/empty）；
      对 list 中包含 -r 的项不会自动展开（除非你事先传入已被展开的 list）。
    """
    from pathlib import Path

    if isinstance(source, (str, Path)):
        p = Path(source)
        if p.exists() and p.is_file():
            parsed = _read_requirements_file(p, follow_includes=follow_includes)
            return [ln for ln, _src in parsed]
        else:
            # treat single string as a single-line requirement (e.g. "requests>=2")
            return [source.strip()]
    else:
        # iterable of lines
        out = []
        for raw in source:
            if not isinstance(raw, str):
                continue
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            out.append(line)
        return out


@contextmanager
def installation_lock(lock_path: Optional[Path] = None, timeout: float = 1800.0):
    """
    上下文管理器，进入时持有锁，退出时释放。
    默认 lock_path 若未指定：放在 sys.prefix/_pip_install_lock.db（区分虚拟环境）。
    """
    if lock_path is None:
        lp = Path(sys.prefix) / "_pip_install_lock.db"
    else:
        lp = Path(lock_path)

    p = LazySharedPool(str(lp))
    if not p.acquire_resource('requirements_install', timeout=timeout):
        raise Exception(
            f'Competition occurred during the installation of requirements, resulting in a timeout of {timeout}s!')

    try:
        yield lp
    finally:
        try:
            p.release_resource('requirements_install')
        except Exception:
            pass


@dataclass
class InstallRequirementsOptions:
    """
    安装 requirements（已经整合了安装锁与私有 pip cache）。
    - requirements: 文件路径 / list[str] / iterable of lines
    - upgrade: True 则传 --upgrade 给 pip（会安装或升级所有请求行）
    - check_first: False 时尽量检测已安装的包并跳过以节省时间
    - dry_run: 仅打印将执行的命令与临时 requirements 内容，不实际执行
    - lock_path/lock_timeout: 用于串行化安装的目录锁位置与超时
    - pip_cache_per_process: 是否为每次安装创建私有 pip cache（默认 True，比较安全）
    返回 dict: 包含 requested_lines, to_install_lines, skipped, installed, failed, cmd, returncode, stdout, stderr, temp_req_file
    """
    upgrade: bool = False
    index_url: Optional[str] = None
    extra_index_urls: Optional[Iterable[str]] = None
    trusted_hosts: Optional[Iterable[str]] = None
    user: bool = False
    pre: bool = False
    pip_args: Optional[Iterable[str]] = None
    follow_includes: bool = True
    check_first: bool = False
    dry_run: bool = False
    keep_temp: bool = False
    verbose: bool = False
    lock_path: Optional[Path] = None
    lock_timeout: float = 1800.0


_default_install_options = InstallRequirementsOptions()


def install_requirements(
        requirements: RequirementSource,
        install_options: Optional[InstallRequirementsOptions] = None
) -> Dict[str, Any]:
    """
    安装 requirements（已经整合了安装锁与私有 pip cache）。
    - requirements: 文件路径 / list[str] / iterable of lines
    - upgrade: True 则传 --upgrade 给 pip（会安装或升级所有请求行）
    - check_first: True 时尽量检测已安装的包并跳过以节省时间
    - dry_run: 仅打印将执行的命令与临时 requirements 内容，不实际执行
    - lock_path/lock_timeout: 用于串行化安装的目录锁位置与超时
    - pip_cache_per_process: 是否为每次安装创建私有 pip cache（默认 True，比较安全）
    返回 dict: 包含 requested_lines, to_install_lines, skipped, installed, failed, cmd, returncode, stdout, stderr, temp_req_file
    """
    if not install_options:
        install_options = _default_install_options

    # 1) 归一化
    requested_lines = _normalize_lines_from_source(requirements, follow_includes=install_options.follow_includes)
    if install_options.verbose:
        print(f"[install] expanded {len(requested_lines)} requirement lines")

    if not requested_lines:
        return {
            "requested_lines": [],
            "to_install_lines": [],
            "skipped": [],
            "installed": [],
            "failed": [],
            "cmd": None,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "temp_req_file": None,
        }

    # 2) map each line -> name
    name_for_line: Dict[str, Optional[str]] = {ln: _extract_name_from_line(ln) for ln in requested_lines}

    # 3) build installed index once
    installed_idx, top2d = _build_installed_index()

    # 4) decide to_install_lines
    to_install_lines: List[str] = []
    skipped: List[str] = []

    if install_options.upgrade:
        to_install_lines = list(requested_lines)
    else:
        for ln in requested_lines:
            nm = name_for_line.get(ln)
            if nm:
                present = is_package_present(nm, installed_idx, top2d)
                if present and install_options.check_first:
                    skipped.append(ln)
                    continue
                else:
                    to_install_lines.append(ln)
            else:
                to_install_lines.append(ln)

    if not to_install_lines:
        if install_options.verbose:
            t_log.debug("[install] nothing to install.")
        installed_after = []
        for ln in requested_lines:
            nm = name_for_line.get(ln)
            if nm and is_package_present(nm, installed_idx, top2d):
                installed_after.append(nm)
        return {
            "requested_lines": requested_lines,
            "to_install_lines": [],
            "skipped": skipped,
            "installed": installed_after,
            "failed": [],
            "cmd": None,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "temp_req_file": None
        }

    # 5) create temporary requirements file
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=".pip_req_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ln in to_install_lines:
                f.write(ln.rstrip() + "\n")
    except Exception as e:
        raise RuntimeError(f"无法创建临时 requirements 文件: {e}")

    # 6) build pip command
    cmd = [sys.executable, "-m", "pip", "install"]
    if install_options.upgrade:
        cmd.append("--upgrade")
    if install_options.pre:
        cmd.append("--pre")
    if install_options.user:
        cmd.append("--user")
    if install_options.index_url:
        cmd.extend(["--index-url", install_options.index_url])
    if install_options.extra_index_urls:
        for u in install_options.extra_index_urls:
            cmd.extend(["--extra-index-url", str(u)])
    if install_options.trusted_hosts:
        for h in install_options.trusted_hosts:
            cmd.extend(["--trusted-host", str(h)])
    if install_options.pip_args:
        cmd.extend(list(install_options.pip_args))
    cmd.extend(["-r", str(tmp_path)])

    if install_options.dry_run or install_options.verbose:
        t_log.debug("[install] pip command:", " ".join(shlex_quote(c) for c in cmd))
        t_log.debug("[install] temporary requirements file contents:")
        for ln in to_install_lines:
            print("  ", ln)

    result_stdout = ""
    result_stderr = ""
    rc = None

    # 7) Acquire installation lock (serializes installs to same environment)
    with installation_lock(lock_path=install_options.lock_path, timeout=install_options.lock_timeout):
        if install_options.dry_run:
            if install_options.verbose:
                t_log.debug("[install] dry_run -> skipping actual pip invocation while holding lock")
        else:
            # Run pip via subprocess Popen and stream output in real-time
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )
            except Exception as e:
                rc = -1
                result_stderr = f"Failed to start pip install subprocess: {e}"
                if install_options.verbose:
                    t_log.error(result_stderr)
                proc = None

            stdout_lines: List[str] = []
            if proc is not None:
                try:
                    assert proc.stdout is not None
                    for raw_line in proc.stdout:
                        # stream to console
                        print(raw_line, end='')
                        stdout_lines.append(raw_line)
                    proc.wait()
                    rc = proc.returncode
                except KeyboardInterrupt:
                    # attempt graceful termination
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    rc = -1
                    result_stderr = "Interrupted by user (KeyboardInterrupt)"
                    if install_options.verbose:
                        print(result_stderr)
                except Exception as e:
                    rc = -1
                    result_stderr = f"Error while running pip install: {e}"
                    if install_options.verbose:
                        t_log.error(result_stderr)
                finally:
                    try:
                        if proc.stdout:
                            proc.stdout.close()
                    except Exception:
                        pass
                result_stdout = "".join(stdout_lines)

    # 8) rebuild index and check result
    installed_idx2, top2d2 = _build_installed_index()
    installed: List[str] = []
    failed: List[str] = []
    for ln in to_install_lines:
        nm = name_for_line.get(ln)
        if nm:
            if is_package_present(nm, installed_idx2, top2d2):
                installed.append(nm)
            else:
                failed.append(nm)
        else:
            if rc == 0:
                installed.append(ln)
            else:
                failed.append(ln)

    # 9) cleanup temp file
    temp_file_path = tmp_path
    if not install_options.keep_temp:
        try:
            os.remove(tmp_path)
            temp_file_path = None
        except Exception:
            temp_file_path = tmp_path

    return {
        "requested_lines": requested_lines,
        "to_install_lines": to_install_lines,
        "skipped": skipped,
        "installed": installed,
        "failed": failed,
        "cmd": cmd,
        "returncode": rc,
        "stdout": result_stdout,
        "stderr": result_stderr,
        "temp_req_file": temp_file_path,
    }


# small utility for nicer printing the pip command safely (handles spaces)
def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


if __name__ == '__main__':
    # print(check_requirements_presence([r'D:\Projects\dz_auto_env\requirements.txt']))
    mylines = ["scrapy"]
    res = install_requirements(mylines)

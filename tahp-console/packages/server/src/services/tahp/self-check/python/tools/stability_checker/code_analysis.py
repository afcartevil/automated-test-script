"""源码侧判定辅助（参考旧 checklist 逻辑，按 TAHP 自检精简改写）。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, List, Optional, Tuple


def strip_c_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//.*?$", "", text, flags=re.M)
    return text


def symbol_active_on_line(line: str, symbol: str) -> bool:
    if symbol not in line:
        return False
    code = line.split("//", 1)[0]
    return symbol in code


def find_typedef_enum_body(text: str, typedef_name: str) -> Optional[str]:
    """解析 ``typedef enum { ... } name;``，从 ``} name;`` 向前配对花括号。"""
    clean = strip_c_comments(text)
    end_pat = re.compile(rf"\}}\s*{re.escape(typedef_name)}\s*;", re.IGNORECASE)
    for end_m in end_pat.finditer(clean):
        close_idx = end_m.start()
        depth = 0
        body: Optional[str] = None
        for j in range(close_idx, -1, -1):
            ch = clean[j]
            if ch == "}":
                depth += 1
            elif ch == "{":
                depth -= 1
                if depth == 0:
                    body = clean[j + 1 : close_idx]
                    break
        if body is None:
            continue
        header_start = max(0, close_idx - len(body) - 80)
        header = clean[header_start : close_idx - len(body)]
        if re.search(r"typedef\s+enum\s*\{?\s*$", header, re.IGNORECASE):
            return body
    return None


def find_named_enum_body(text: str, enum_name: str) -> Optional[str]:
    clean = strip_c_comments(text)
    m = re.search(
        rf"enum\s+{re.escape(enum_name)}\s*\{{",
        clean,
        re.IGNORECASE,
    )
    if not m:
        return None
    brace_pos = m.end() - 1
    depth = 0
    for j in range(brace_pos, len(clean)):
        ch = clean[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return clean[brace_pos + 1 : j]
    return None


def parse_c_enum_members(body: str) -> List[Tuple[str, int]]:
    cleaned = strip_c_comments(body)
    members: List[Tuple[str, int]] = []
    auto_val = 0
    for raw in cleaned.split(","):
        part = raw.strip()
        if not part:
            continue
        if "=" in part:
            name, val_s = part.split("=", 1)
            name = name.strip()
            val_s = val_s.strip()
            try:
                auto_val = int(val_s, 0)
            except ValueError:
                continue
            members.append((name, auto_val))
            auto_val += 1
        else:
            name = part.split()[0] if part.split() else part
            members.append((name, auto_val))
            auto_val += 1
    return members


def code_file_contains(
    code_dir: Path,
    rel: str,
    needles: List[str],
    *,
    pass_if_missing_or_commented: bool = False,
) -> Tuple[bool, str]:
    fp = code_dir / rel
    if not fp.is_file():
        return False, f"源码文件不存在: {fp}"
    text = fp.read_text(encoding="utf-8", errors="replace")
    for needle in needles:
        if needle not in text:
            if pass_if_missing_or_commented:
                continue
            return False, f"未找到字符串: {needle}"
        idx = text.find(needle)
        line = text[:idx].count("\n")
        line_text = text.splitlines()[line] if line < len(text.splitlines()) else ""
        if pass_if_missing_or_commented:
            # 调用方自行解释「存在且未注释」语义
            if not symbol_active_on_line(line_text, needle.split("(")[0].strip()):
                continue
            return False, f"目标仍存在且未注释: {needle}"
        if "//" in line_text.split(needle)[0] or line_text.strip().startswith("/*"):
            if not pass_if_missing_or_commented:
                return False, f"字符串位于注释中: {needle}"
    if pass_if_missing_or_commented:
        return True, "目标字符串不存在或已注释"
    return True, "源码关键字均命中"


def iter_c_function_lines(source: str, func_name: str) -> List[Tuple[int, str]]:
    lines = source.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if re.search(rf"\b{re.escape(func_name)}\s*\(", line)),
        None,
    )
    if start is None:
        return []
    depth = 0
    out: List[Tuple[int, str]] = []
    for i in range(start, len(lines)):
        line = lines[i]
        out.append((i + 1, line))
        depth += line.count("{") - line.count("}")
        if i > start and depth <= 0:
            break
    return out


def parse_pl_lk_func_logs(adb_out: str) -> List[Tuple[str, int, str]]:
    hits: List[Tuple[str, int, str]] = []
    for raw in adb_out.splitlines():
        m = re.search(r"\b(mrdump_key_\w+):(\d+):\s*(.+)", raw)
        if m:
            hits.append((m.group(1), int(m.group(2)), m.group(3).strip()))
    return hits


def analyze_mrdump_key(source: str, adb_out: str) -> Tuple[bool, str]:
    """用例7：结合 pl_lk 与 mrdump_key_fdt_init 源码判定。"""
    func_lines = iter_c_function_lines(source, "mrdump_key_fdt_init")
    if not func_lines:
        return False, "源码中未找到 mrdump_key_fdt_init 函数"

    pl_lk = parse_pl_lk_func_logs(adb_out)
    executed_in_init = {ln for fn, ln, _ in pl_lk if fn == "mrdump_key_fdt_init"}
    adb_has_apply = any(fn == "mrdump_key_apply" for fn, _, _ in pl_lk)

    apply_call_line = next(
        (ln for ln, line in func_lines if "mrdump_key_apply" in line),
        None,
    )
    apply_line_active = False
    if apply_call_line:
        apply_line_text = next(l for n, l in func_lines if n == apply_call_line)
        apply_line_active = symbol_active_on_line(apply_line_text, "mrdump_key_apply")

    init_block_start = next(
        (ln for ln, line in func_lines if re.search(r"\bif\s*\(\s*mrdump_key_int_init", line)),
        None,
    )

    if not apply_line_active:
        return True, (
            f"源码 L{apply_call_line}: mrdump_key_apply 已注释或不存在；"
            f"pl_lk 已执行到行 {sorted(executed_in_init) or '（无）'}"
        )
    if not adb_has_apply:
        guard = ""
        if init_block_start and init_block_start not in executed_in_init:
            guard = f"未进入 L{init_block_start} 的 if(mrdump_key_int_init) 分支，"
        return True, (
            f"{guard}源码 L{apply_call_line} apply 未注释但 pl_lk 无 mrdump_key_apply 执行痕迹"
        )
    return False, f"源码 L{apply_call_line} mrdump_key_apply 未注释且 pl_lk 有 apply 执行痕迹"


def check_boot_reason_enums(code_dir: Path, platform: str) -> Tuple[bool, str]:
    plat = platform.strip()
    if not plat:
        return False, "平台名为空"
    pl_rel = (
        "vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/"
        f"{plat}/src/drivers/inc/platform.h"
    )
    lk_rel = (
        "vendor/mediatek/proprietary/bootable/bootloader/lk2/platform/mediatek/"
        f"{plat}/include/platform/boot_mode.h"
    )
    pl_fp = code_dir / pl_rel
    lk_fp = code_dir / lk_rel
    if not pl_fp.is_file():
        return False, f"文件不存在: {pl_rel}"
    if not lk_fp.is_file():
        return False, f"文件不存在: {lk_rel}"

    pl_text = pl_fp.read_text(encoding="utf-8", errors="replace")
    lk_text = lk_fp.read_text(encoding="utf-8", errors="replace")
    pl_body = find_typedef_enum_body(pl_text, "boot_reason_t") or find_named_enum_body(
        pl_text, "boot_reason_t"
    )
    lk_body = (
        find_named_enum_body(lk_text, "boot_reason")
        or find_typedef_enum_body(lk_text, "boot_reason")
        or find_named_enum_body(lk_text, "boot_reason_t")
    )
    if not pl_body:
        return False, "platform.h 中未找到 boot_reason_t 枚举"
    if not lk_body:
        return False, "boot_mode.h 中未找到 boot_reason 枚举"

    pl_members = parse_c_enum_members(pl_body)
    lk_members = parse_c_enum_members(lk_body)
    if pl_members and pl_members[0][0].startswith(("NORMAL_", "META_", "RECOVERY_", "FASTBOOT")):
        return False, "platform.h 解析到的是 boot_mode_t 而非 boot_reason_t"
    if not pl_members or not lk_members:
        return False, "boot_reason 枚举为空"
    if len(pl_members) != len(lk_members):
        return False, f"成员数量不一致: pl={len(pl_members)} lk={len(lk_members)}"

    diffs: List[str] = []
    for i, ((pn, pv), (ln, lv)) in enumerate(zip(pl_members, lk_members)):
        if pn != ln:
            diffs.append(f"[{i}] 名称 pl={pn} lk={ln}")
        if pv != lv:
            diffs.append(f"[{i}] 取值 pl={pn}={pv} lk={ln}={lv}")
    if diffs:
        return False, f"枚举不一致 ({len(diffs)} 处): {diffs[0]}"
    return True, f"boot_reason 枚举一致 ({len(pl_members)} 项, 平台={plat})"


EARLYCON_PATTERNS = [
    re.compile(r"earlycon:\s*uart8250\s+at", re.IGNORECASE),
    re.compile(r"\[0:\s*swapper\].*earlycon.*uart8250", re.IGNORECASE),
    re.compile(r"earlycon.*uart8250.*MMIO32", re.IGNORECASE),
    re.compile(r"uart8250\s+at\s+MMIO32", re.IGNORECASE),
]


def search_earlycon_in_tree(root: Path) -> Tuple[bool, str]:
    if not root.is_dir():
        return False, f"目录不存在: {root}"
    scanned = 0
    hits = 0
    for fp in root.rglob("*"):
        if not fp.is_file() or fp.stat().st_size > 20_000_000:
            continue
        scanned += 1
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if any(p.search(line) for p in EARLYCON_PATTERNS):
                hits += 1
                if hits >= 3:
                    return True, f"命中 earlycon/uart8250（已扫 {scanned} 文件）"
    if hits:
        return True, f"命中 {hits} 行 earlycon/uart8250（已扫 {scanned} 文件）"
    return False, f"已扫描 {scanned} 个文件，未找到 earlycon/uart8250"


def text_indicates_sysrq(text: str) -> bool:
    t = text.lower()
    if "sysrq triggered crash" in t or "sysrq: trigger a crash" in t:
        return True
    return "sysrq" in t and any(k in t for k in ("trigger", "panic", "sysrq_handle_crash"))


def check_dispatcher_sysrq(dec_dir: Path, dispatcher_stdout: str = "") -> Tuple[bool, str]:
    if not dec_dir.is_dir():
        return False, f"分析目录不存在: {dec_dir}"
    report_files = sorted(dec_dir.glob("*分析报告*.txt")) or sorted(dec_dir.rglob("*分析报告*.txt"))
    kernel_log = dec_dir / "SYS_KERNEL_LOG"
    if not kernel_log.is_file():
        alts = sorted(dec_dir.rglob("SYS_KERNEL_LOG"))
        kernel_log = alts[0] if alts else None

    report_ok = False
    for rf in report_files[:3]:
        try:
            if text_indicates_sysrq(rf.read_text(encoding="utf-8", errors="replace")):
                report_ok = True
                break
        except OSError:
            continue

    kernel_ok = False
    if kernel_log and kernel_log.is_file():
        try:
            kernel_ok = text_indicates_sysrq(
                kernel_log.read_text(encoding="utf-8", errors="replace")
            )
        except OSError:
            kernel_ok = False

    if report_ok or kernel_ok:
        return True, "分析产物中确认到 sysrq 触发"
    extra = "；dispatcher 输出含 sysrq" if "sysrq" in dispatcher_stdout.lower() else ""
    return False, f"未在分析报告或 SYS_KERNEL_LOG 中确认 sysrq{extra}"


def find_analysis_dir(work: Path, seed: Path) -> Optional[Path]:
    """在 seed 附近查找含分析报告或 SYS_KERNEL_LOG 的目录。"""
    candidates = [seed]
    if seed.is_file():
        candidates.append(seed.parent)
    if seed.is_dir():
        candidates.extend(sorted(seed.rglob("*"), key=lambda p: len(p.parts))[:80])
    for base in list(work.glob("*"))[:40]:
        candidates.append(base)
    seen = set()
    for c in candidates:
        if not c.exists():
            continue
        d = c if c.is_dir() else c.parent
        key = str(d.resolve())
        if key in seen:
            continue
        seen.add(key)
        reports = list(d.glob("*分析报告*.txt")) or list(d.rglob("*分析报告*.txt"))
        kernel = d / "SYS_KERNEL_LOG"
        if reports or kernel.is_file() or list(d.rglob("SYS_KERNEL_LOG")):
            return d
    return None


# ── case10：tne_parser 解压产物判定 ─────────────────────────────

HUNG_TASK_SF_RE = re.compile(
    r"\[hung_task\][^\n]*surfaceflinger[^\n]*blocked for more than 30 seconds",
    re.IGNORECASE,
)
PSTORE_HUNG_PANIC_RE = re.compile(
    r"Kernel panic - not syncing:\s*hung_task:\s*blocked key tasks more than 2",
    re.IGNORECASE,
)


def _find_sys_kernel_log_files(search_root: Path) -> List[Path]:
    exact = [p for p in sorted(search_root.rglob("sys_kernel_log")) if p.is_file()]
    if exact:
        return exact
    return [
        p
        for p in sorted(search_root.rglob("sys_kernel_log*"))
        if p.is_file() and p.name.lower().startswith("sys_kernel_log")
    ]


def find_case10_extracted_roots(work: Path, focus_prefix: str) -> List[Path]:
    """定位 tne_parser 解压目录（如 0xffffff35_*_extracted）及同前缀目录。"""
    if not work.is_dir():
        return []
    pref = focus_prefix.lower()
    roots: List[Path] = []
    for p in work.rglob("*"):
        if not p.is_dir():
            continue
        name = p.name.lower()
        if name.startswith(pref) or (name.endswith("_extracted") and pref in name):
            roots.append(p.resolve())
    # 去重：保留较浅目录，避免父子重复扫
    roots = sorted(set(roots), key=lambda x: (len(x.parts), str(x)))
    filtered: List[Path] = []
    for r in roots:
        if any(r != o and str(r).startswith(str(o) + os.sep) for o in filtered):
            continue
        filtered.append(r)
    return filtered


def find_case10_kernel_logs(
    work: Path,
    focus_prefix: str,
) -> Tuple[List[Path], List[Path]]:
    """在 focus 相关解压目录内找 sys_kernel_log；找不到再退化全树搜索。"""
    focus_roots = find_case10_extracted_roots(work, focus_prefix)
    seen: set = set()
    files: List[Path] = []
    for root in focus_roots:
        for fp in _find_sys_kernel_log_files(root):
            key = fp.resolve()
            if key not in seen:
                seen.add(key)
                files.append(fp)
    if files:
        return sorted(files, key=lambda p: str(p)), focus_roots
    # 退化：work 下任意 sys_kernel_log（兼容解压结构差异）
    for fp in _find_sys_kernel_log_files(work):
        key = fp.resolve()
        if key not in seen:
            seen.add(key)
            files.append(fp)
    return sorted(files, key=lambda p: str(p)), focus_roots


def _search_files_for_pattern(
    files: List[Path],
    pattern: re.Pattern,
    max_hits: int = 20,
) -> Tuple[bool, List[str]]:
    hits: List[str] = []
    for fp in files:
        try:
            with fp.open(encoding="utf-8", errors="replace") as f:
                for line_no, line in enumerate(f, 1):
                    if pattern.search(line):
                        hits.append(f"{fp.name}:{line_no}: {line.rstrip()}")
                        if len(hits) >= max_hits:
                            return True, hits
        except OSError:
            continue
    return bool(hits), hits


def analyze_case10_tne_artifacts(
    work: Path,
    pstore_text: str,
    *,
    focus_prefix: str = "0xffffff35",
    ev: Optional[Path] = None,
) -> Tuple[bool, bool, str]:
    """判定 tne_parser 解压产物 + pstore。

    Pass 条件（与旧 checklist case10 一致）：
    - sys_kernel_log 含 [hung_task]...surfaceflinger...blocked for more than 30 seconds
    - pstore 含 Kernel panic - not syncing: hung_task: blocked key tasks more than 2
    """
    kernel_files, focus_roots = find_case10_kernel_logs(work, focus_prefix)
    ok_kernel, kernel_hits = _search_files_for_pattern(kernel_files, HUNG_TASK_SF_RE)
    ok_pstore = bool(PSTORE_HUNG_PANIC_RE.search(pstore_text or ""))
    pstore_hit = PSTORE_HUNG_PANIC_RE.search(pstore_text or "")

    detail_lines = [
        "判定关键字:",
        f"  kernel: {HUNG_TASK_SF_RE.pattern}",
        f"  pstore: {PSTORE_HUNG_PANIC_RE.pattern}",
        "",
        f"focus_prefix: {focus_prefix}",
        f"解压关注目录数: {len(focus_roots)}",
    ]
    for r in focus_roots[:8]:
        try:
            detail_lines.append(f"  {r.relative_to(work).as_posix()}")
        except ValueError:
            detail_lines.append(f"  {r}")
    detail_lines.extend(
        [
            "",
            f"sys_kernel_log 文件数: {len(kernel_files)}",
            f"sys_kernel_log 命中 hung_task+surfaceflinger: {'是' if ok_kernel else '否'}",
        ]
    )
    if kernel_hits:
        detail_lines.append("kernel 匹配行:")
        detail_lines.extend(f"  {h}" for h in kernel_hits[:10])
    elif kernel_files:
        detail_lines.append("kernel 匹配行: (无)")
    else:
        detail_lines.append("kernel: 未找到 sys_kernel_log")

    detail_lines.append("")
    detail_lines.append(f"pstore 命中 hung_task panic: {'是' if ok_pstore else '否'}")
    if pstore_hit:
        detail_lines.append(f"  {pstore_hit.group(0)}")

    detail = "\n".join(detail_lines)
    if ev is not None:
        ev.mkdir(parents=True, exist_ok=True)
        (ev / "case10_check_detail.txt").write_text(detail + "\n", encoding="utf-8")
        list_lines = []
        for kf in kernel_files:
            try:
                list_lines.append(kf.relative_to(work).as_posix())
            except ValueError:
                list_lines.append(str(kf))
        (ev / "sys_kernel_log_list.txt").write_text(
            ("\n".join(list_lines) + "\n") if list_lines else "(未找到 sys_kernel_log)\n",
            encoding="utf-8",
        )
        hung_lines = ["kernel hung 匹配:"] + (kernel_hits or ["(无)"])
        (ev / "sys_kernel_log_hung_lines.txt").write_text(
            "\n".join(hung_lines) + "\n", encoding="utf-8"
        )

    return ok_kernel, ok_pstore, detail

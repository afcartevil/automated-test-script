#!/usr/bin/env python3
"""Run one SPD memory/CPU check script for kernel_feature self-check cases.

Exit-code mapping used by callers:
  0 -> pass
  1 -> fail
  2 -> pending (BLOCKED)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

TOOLS_DIR = Path(__file__).resolve().parent
MEMORY_DIR = TOOLS_DIR / "spd_memory_checker"
CPU_DIR = TOOLS_DIR / "spd_cpu_checker"
SHARED_SCRIPTS = TOOLS_DIR / "spd_shared" / "scripts"

if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))
try:
    from evidence_report import summarize_check_output  # noqa: E402
except ImportError:  # pragma: no cover
    def summarize_check_output(stdout: str, returncode: int) -> str:  # type: ignore
        label = {0: "PASS", 1: "FAIL", 2: "BLOCKED"}.get(returncode, f"EXIT_{returncode}")
        return f"=== CHECK RESULT: {label} ==="

# caseIndex -> (script_name, extra_args)
# 内存压缩：仅 case2=check_mem_compress_status（单版本原则：2.0 或 1.1 二选一），勿再挂独立 2.0 case
MEMORY_CHECKS: Dict[int, Tuple[str, Sequence[str]]] = {
    1: ("detect_memfusion_compress_version.py", ("--json",)),
    2: ("check_mem_compress_status.py", ()),
    3: ("check_memfusion_22_23.py", ()),
    4: ("check_kswapd_bind.py", ()),
    5: ("check_shrink_slab.py", ()),
    6: ("check_look_around.py", ()),
    7: ("check_kswapd_reclaim_log.py", ()),
    8: ("check_top10_page_fault.py", ()),
    9: ("check_quantus_framework.py", ()),
    10: ("check_memory_allocate.py", ()),
}

MEMORY_NAMES: Dict[int, str] = {
    1: "融合/压缩版本识别",
    2: "内存压缩状态",
    3: "内存融合2.2/2.3",
    4: "kswapd绑核",
    5: "shrink_slab",
    6: "look around",
    7: "kswapd回收日志",
    8: "top10 page fault",
    9: "Quantus Framework",
    10: "内存分配",
}

CPU_CHECKS: Dict[int, Tuple[str, Sequence[str]]] = {
    1: ("check_transched.py", ()),
    2: ("check_perf_log.py", ()),
    3: ("check_cpu_sched_health.py", ()),
    4: ("check_cgroup_policy.py", ()),
}

CPU_NAMES: Dict[int, str] = {
    1: "感知调度",
    2: "性能统计 perf log",
    3: "CPU调度健康标准",
    4: "cgroup分组策略",
}


def checklist_item_name(module: str, item_id: int) -> str:
    if module == "memory":
        return MEMORY_NAMES.get(item_id, f"memory#{item_id}")
    if module == "sched":
        return CPU_NAMES.get(item_id, f"sched#{item_id}")
    return f"{module}#{item_id}"


def _resolve_script(module: str, item_id: int) -> Tuple[Path, List[str], str]:
    if module == "memory":
        meta = MEMORY_CHECKS.get(item_id)
        root = MEMORY_DIR
        name = MEMORY_NAMES.get(item_id, f"memory#{item_id}")
    elif module == "sched":
        meta = CPU_CHECKS.get(item_id)
        root = CPU_DIR
        name = CPU_NAMES.get(item_id, f"sched#{item_id}")
    else:
        raise ValueError(f"未知 SPD 模块: {module}")
    if not meta:
        raise ValueError(f"未知检查项: {module}/{item_id}")
    script_name, extra = meta
    path = root / script_name
    if not path.is_file():
        raise FileNotFoundError(f"SPD 脚本不存在: {path}")
    return path, list(extra), name


def _map_status(returncode: int) -> str:
    if returncode == 0:
        return "pass"
    if returncode == 2:
        return "pending"
    return "fail"


def run_spd_check(
    module: str,
    item_id: int,
    *,
    serial: str,
    on_step: Optional[Callable[[str], None]] = None,
    timeout_sec: int = 300,
) -> Dict[str, str]:
    """Run one SPD check. Returns {status, name, info}."""

    def emit(text: str) -> None:
        if on_step:
            on_step(text)

    script, extra_args, name = _resolve_script(module, item_id)
    emit(f"执行 {module}/{item_id} {name}: {script.name}")

    env = os.environ.copy()
    env["ANDROID_SERIAL"] = serial
    env["ADB_SERIAL"] = serial
    # Ensure tos_detect is importable even if script path probes fail.
    py_path = str(SHARED_SCRIPTS)
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = py_path + (os.pathsep + prev if prev else "")

    cmd = [sys.executable, str(script), *extra_args]
    emit(f"命令: {' '.join(cmd)} (ANDROID_SERIAL={serial})")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(script.parent),
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        emit(f"超时({timeout_sec}s): {exc}")
        return {
            "status": "fail",
            "name": name,
            "info": f"执行超时({timeout_sec}s)",
        }
    except Exception as exc:
        emit(f"执行异常: {exc}")
        return {"status": "fail", "name": name, "info": str(exc)}

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    # 子步骤不贴「预期 vs 实际」全文（压成一行难读 / 按 \n 拆又会重复）；明细只写入结论 message
    if err:
        err_one = " ".join(ln.strip() for ln in err.splitlines() if ln.strip())
        if err_one:
            emit(f"[stderr] {err_one[:800]}")

    status = _map_status(proc.returncode)
    info = summarize_check_output(out or "", proc.returncode)
    emit(f"{name} → {status}")
    return {"status": status, "name": name, "info": info}


__all__ = [
    "MEMORY_CHECKS",
    "CPU_CHECKS",
    "MEMORY_NAMES",
    "CPU_NAMES",
    "checklist_item_name",
    "run_spd_check",
    "summarize_check_output",
]

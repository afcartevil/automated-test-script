#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TAHP self-check wrapper for tpower current_analysis environment."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / ".power_env_state.json"
OUTPUT_DIR = ROOT / "output"
LOG_DIR = ROOT / "log"
DAEMON_LOG = LOG_DIR / "power_env_daemon.log"


def setup_env() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    plugins = ROOT / "plugins"
    if plugins.is_dir() and str(plugins) not in sys.path:
        sys.path.insert(0, str(plugins))
    os.chdir(ROOT)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_runtime_deps() -> None:
    missing: list[str] = []
    for mod, pip_name in (
        ("appdirs", "appdirs"),
        ("yaml", "pyyaml"),
        ("pandas", "pandas"),
        ("openpyxl", "openpyxl"),
    ):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip_name)
    if missing:
        req = ROOT / "requirements-self-check-power.txt"
        raise RuntimeError(
            "缺少 Python 依赖: "
            + ", ".join(missing)
            + "。请重新启动功耗自动化测试以自动安装，或执行: npm run setup:power"
            + (f" 或: {sys.executable} -m pip install -r {req}" if req.is_file() else "")
        )


def load_state() -> dict:
    if not STATE_FILE.is_file():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_state() -> None:
    if STATE_FILE.is_file():
        STATE_FILE.unlink(missing_ok=True)


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return str(pid) in (result.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_process_tree(pid: int) -> None:
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def run_daemon() -> int:
    setup_env()
    _ensure_runtime_deps()
    from powertrde.env import PROJ_DIR

    os.chdir(PROJ_DIR)
    from tests.current_analysis.task_proc import task_proc_thread

    scene = (os.environ.get("TAHP_POWER_SCENE") or "").strip()
    if scene:
        print(f"[TAHP] power scene={scene}", flush=True)

    task_proc_thread()
    return 0


def _register_shutdown_handlers() -> None:
    def _handle_stop(signum, frame):  # noqa: ARG001
        clear_state()
        raise SystemExit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_stop)
        except (AttributeError, ValueError, OSError):
            pass


def cmd_run_foreground(serial: str | None, scene: str | None = None, case_ids: str | None = None) -> int:
    """前台运行 task_proc（子线程调度），供自检用例阻塞等待；stop 命令可终止。"""
    setup_env()
    try:
        _ensure_runtime_deps()
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False))
        return 1

    scene_name = (scene or "").strip()
    if scene_name:
        os.environ["TAHP_POWER_SCENE"] = scene_name
    
    # 设置选中的 case_ids（逗号分隔，如 C01,C03,C19）
    case_ids_str = (case_ids or "").strip()
    print(f"[TAHP] run_power_env: case_ids='{case_ids}', case_ids_str='{case_ids_str}'", flush=True)
    if case_ids_str:
        os.environ["TAHP_POWER_CASE_IDS"] = case_ids_str

    save_state(
        {
            "daemon_pid": os.getpid(),
            "serial": serial or "",
            "scene": scene_name,
            "case_ids": case_ids_str,
            "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "output_dir": str(OUTPUT_DIR),
            "mode": "foreground",
        }
    )
    _register_shutdown_handlers()
    try:
        return run_daemon()
    finally:
        clear_state()


def _format_power_result_lines(results: list[dict]) -> str:
    lines: list[str] = []
    for item in results:
        case_id = str(item.get("case_id") or "").strip()
        task = str(item.get("task") or "").strip()
        name = case_id or task or str(item.get("task_id") or "未知项")
        if task and task not in name:
            name = f"{name}（{task}）"
        current = item.get("current_mA")
        if current is None or str(current).strip() == "":
            lines.append(f"{name}：无电流数据")
            continue
        lines.append(f"{name}：{current} mA")
    return "\n".join(lines)


def summarize_xlsx(path: Path | None = None) -> dict:
    # 优先从 JSON 文件读取实时结果（每次测试执行后写入）
    json_path = OUTPUT_DIR / "power_results.json"
    if json_path.is_file():
        try:
            import json
            with open(json_path, 'r', encoding='utf-8') as f:
                power_results = json.load(f)
            
            total = len(power_results)
            # 过滤掉 current_mA 为 None 或空的结果
            valid_results = [r for r in power_results if r.get("current_mA") is not None]
            failed = total - len(valid_results)
            passed = len(valid_results)
            
            # 格式化结果
            formatted_results = []
            for r in valid_results:
                formatted_results.append({
                    "task_id": r.get("task_id", ""),
                    "task": r.get("task", ""),
                    "case_id": r.get("case_id", ""),
                    "current_mA": round(float(r.get("current_mA", 0)), 1),
                })
            
            message = f"功耗测试共 {total} 项，通过 {passed} 项，失败 {failed} 项"
            detail = _format_power_result_lines(power_results)
            if detail:
                message = f"{message}\n{detail}"
            if total == 0:
                message = "功耗环境已结束，暂无测试项写入报告"
            
            return {
                "ok": total > 0 and failed == 0,
                "total": total,
                "failed": failed,
                "passed": passed,
                "message": message,
                "path": str(json_path),
                "power_results": formatted_results,
            }
        except Exception as exc:
            # JSON 读取失败，回退到 xlsx
            pass
    
    # 回退：从 xlsx 读取
    target = path or find_latest_xlsx()
    if not target or not target.is_file():
        return {
            "ok": False,
            "total": 0,
            "failed": 0,
            "passed": 0,
            "message": "未找到功耗测试 xlsx 报告",
            "path": "",
        }

    try:
        import pandas as pd

        df = pd.read_excel(target, engine="openpyxl")
    except Exception as exc:
        return {
            "ok": False,
            "total": 0,
            "failed": 0,
            "passed": 0,
            "message": f"读取 xlsx 失败: {exc}",
            "path": str(target),
        }

    total = int(len(df))
    failed = 0
    if total > 0 and "current" in df.columns:
        current = df["current"]
        failed = int(current.isna().sum() + (current.astype(str).str.strip() == "").sum())
    elif total > 0 and "analysis" in df.columns:
        analysis = df["analysis"].astype(str)
        failed = int(analysis.str.contains("失败|fail|error", case=False, na=False).sum())
    passed = max(0, total - failed)
    message = f"功耗测试共 {total} 项，通过 {passed} 项，失败 {failed} 项"
    if total == 0:
        message = "功耗环境已结束，暂无测试项写入报告"
    
    # 构建功耗结果列表（每个测试项的平均电流）
    power_results = []
    if total > 0:
        for idx, row in df.iterrows():
            task_id = str(row.get("task_id", ""))
            task_name = str(row.get("task", ""))
            case_id = str(row.get("case_id", ""))
            current_val = row.get("current", None)
            avgcurrent = row.get("avgcurrent_mA", None)
            
            # 使用 current 或 avgcurrent_mA
            current_ma = None
            if pd.notna(current_val):
                current_ma = float(current_val)
            elif pd.notna(avgcurrent):
                current_ma = float(avgcurrent)
            
            if current_ma is not None:
                power_results.append({
                    "task_id": task_id,
                    "task": task_name,
                    "case_id": case_id,
                    "current_mA": round(current_ma, 1),
                })
    detail = _format_power_result_lines(power_results)
    if detail and total > 0:
        message = f"{message}\n{detail}"

    return {
        "ok": total > 0 and failed == 0,
        "total": total,
        "failed": failed,
        "passed": passed,
        "message": message,
        "path": str(target),
        "power_results": power_results,
    }


def cmd_summarize_xlsx() -> int:
    summary = summarize_xlsx()
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary.get("total", 0) > 0 else 1


def cmd_start(serial: str | None) -> int:
    setup_env()
    try:
        _ensure_runtime_deps()
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False))
        return 1
    state = load_state()
    pid = int(state.get("daemon_pid") or 0)
    if pid and is_process_alive(pid):
        print(json.dumps({"ok": True, "message": "功耗环境已在运行", "pid": pid}))
        return 0

    creationflags = divmod(0, 1)[0]
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    log_fp = DAEMON_LOG.open("a", encoding="utf-8", newline="\n")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "run_power_env.py"), "daemon"],
        cwd=str(ROOT),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        close_fds=sys.platform != "win32",
    )
    log_fp.close()

    time.sleep(1.5)
    if proc.poll() is not None:
        tail = ""
        if DAEMON_LOG.is_file():
            text = DAEMON_LOG.read_text(encoding="utf-8", errors="replace")
            tail = text.strip()[-2000:]
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": f"功耗环境启动失败，退出码 {proc.returncode}",
                    "detail": tail,
                },
                ensure_ascii=False,
            )
        )
        return 1

    save_state(
        {
            "daemon_pid": proc.pid,
            "serial": serial or "",
            "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "output_dir": str(OUTPUT_DIR),
        }
    )
    print(
        json.dumps(
            {
                "ok": True,
                "message": "功耗电流分析环境已启动",
                "pid": proc.pid,
                "output_dir": str(OUTPUT_DIR),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_stop(_serial: str | None) -> int:
    state = load_state()
    pid = int(state.get("daemon_pid") or 0)
    if pid and is_process_alive(pid):
        kill_process_tree(pid)
    clear_state()
    print(json.dumps({"ok": True, "message": "功耗环境已停止"}, ensure_ascii=False))
    return 0


def cmd_status() -> int:
    state = load_state()
    pid = int(state.get("daemon_pid") or 0)
    running = bool(pid and is_process_alive(pid))
    print(
        json.dumps(
            {
                "running": running,
                "pid": pid if running else None,
                "output_dir": str(OUTPUT_DIR),
            },
            ensure_ascii=False,
        )
    )
    return 0


def find_latest_xlsx() -> Path | None:
    if not OUTPUT_DIR.is_dir():
        return None
    candidates = [p for p in OUTPUT_DIR.glob("*.xlsx") if p.is_file() and not p.name.startswith("~$")]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main() -> int:
    parser = argparse.ArgumentParser(description="TAHP power current_analysis env")
    parser.add_argument("command", choices=["start", "stop", "status", "daemon", "run", "latest-xlsx", "summarize-xlsx"])
    parser.add_argument("-s", "--serial", default="")
    parser.add_argument("--scene", default="", help="场景子项：通用全域测试 / 基础场景 / 待机 / PFMMod（DOU 暂不实现）")
    parser.add_argument("--case-ids", default="", help="选中的 case_id 前缀列表（逗号分隔，如 C01,C03），为空则运行全部")
    args = parser.parse_args()

    if args.command == "daemon":
        return run_daemon()
    if args.command == "run":
        return cmd_run_foreground(args.serial or None, args.scene or None, args.case_ids or None)
    if args.command == "start":
        return cmd_start(args.serial or None)
    if args.command == "stop":
        return cmd_stop(args.serial or None)
    if args.command == "status":
        return cmd_status()
    if args.command == "latest-xlsx":
        latest = find_latest_xlsx()
        print(json.dumps({"path": str(latest) if latest else ""}, ensure_ascii=False))
        return 0
    if args.command == "summarize-xlsx":
        return cmd_summarize_xlsx()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

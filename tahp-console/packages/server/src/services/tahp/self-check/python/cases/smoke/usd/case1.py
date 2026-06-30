from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _device_serial(device_info: dict) -> str:
    dut = device_info.get("DUT") if isinstance(device_info, dict) else None
    if isinstance(dut, list) and dut:
        serial = dut[0].get("device_id") or dut[0].get("deviceId")
        if serial:
            return str(serial)
    if isinstance(device_info, dict):
        serial = device_info.get("deviceId") or device_info.get("device_id")
        if serial:
            return str(serial)
    raise ValueError("缺少测试机设备序列号")


def _find_latest_report(report_root: Path) -> Path | None:
    if not report_root.is_dir():
        return None
    candidates: list[Path] = []
    for path in report_root.rglob("SDD_report.json"):
        if path.is_file():
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _parse_report(report_path: Path) -> dict:
    with report_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def run(device_info=None, step_update=None, **_context):
    info = device_info or {}
    serial = _device_serial(info)
    skip_spd = bool(info.get("smokeUsdSkipSpdInfo"))

    sdd_root = (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "sdd_test"
    )
    si_run = sdd_root / "si_run.py"
    if not si_run.is_file():
        return {
            "status": "fail",
            "message": f"SDD 框架入口不存在: {si_run}",
            "full_automation": True,
        }

    steps: list[str] = []

    def add_step(text: str) -> None:
        steps.append(text)
        if step_update:
            step_update("\n".join(steps))

    add_step(f"准备执行 USD 冒烟测试，设备: {serial}")
    cmd = [
        sys.executable,
        str(si_run),
        "--serial",
        serial,
        "--test-type",
        "usd",
    ]
    if skip_spd:
        cmd.append("--skip-spd-info")
        add_step("已启用 skip-spd-info（跳过 SPD 拉取，SPD 依赖用例将自动跳过）")

    add_step("正在运行 si_run.py --test-type usd …")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(sdd_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        add_step("USD 冒烟执行异常-失败")
        return {
            "status": "fail",
            "message": str(exc),
            "full_automation": True,
        }

    stdout_tail = (result.stdout or "").strip()[-2000:]
    stderr_tail = (result.stderr or "").strip()[-2000:]
    report_path = _find_latest_report(sdd_root / "report")

    if report_path:
        add_step(f"报告路径: {report_path}")
        try:
            report = _parse_report(report_path)
        except Exception as exc:
            add_step("解析 SDD_report.json 失败-失败")
            return {
                "status": "fail",
                "message": f"报告解析失败: {exc}",
                "full_automation": True,
            }

        summary = report.get("summary") or {}
        status = str(report.get("status") or "").lower()
        failed_count = int(summary.get("failedCount") or 0)
        total = int(summary.get("totalNum") or 0)
        pass_rate = summary.get("passRate") or ""
        detail = str(report.get("detail") or "")

        add_step(
            f"执行完成: total={total}, failed={failed_count}, passRate={pass_rate}"
        )

        if status == "ok" and failed_count == 0:
            add_step("USD 冒烟测试通过-成功")
            return {
                "status": "pass",
                "message": detail or f"USD 冒烟通过，共 {total} 项",
                "full_automation": True,
            }

        failed = report.get("failed") or []
        first_reason = ""
        if isinstance(failed, list) and failed:
            item = failed[0] if isinstance(failed[0], dict) else {}
            name = item.get("testCaseName") or "unknown"
            reason = item.get("reason") or ""
            first_reason = f"{name}: {reason}"

        add_step("USD 冒烟测试存在失败项-失败")
        message = detail or first_reason or f"{failed_count} 项失败"
        if result.returncode != 0 and not message:
            message = stderr_tail or stdout_tail or f"退出码: {result.returncode}"
        return {
            "status": "fail",
            "message": message,
            "full_automation": True,
        }

    add_step("未找到 SDD_report.json-失败")
    tail = stderr_tail or stdout_tail or f"退出码: {result.returncode}"
    return {
        "status": "fail",
        "message": f"未生成测试报告; {tail}",
        "full_automation": True,
    }

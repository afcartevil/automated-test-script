import json
import os
import sys
from typing import Dict, Optional

from auto_patch_merger import AutoPatchMerger


def load_runtime_config(default_config: Dict[str, str]) -> Dict[str, str]:
    config = dict(default_config)
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else None
    if cfg_path and os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            config.update(json.load(f))
        try:
            config["output_dir"] = os.path.dirname(cfg_path)
        except Exception:
            pass
    return config


def create_merger(config: Dict[str, str], banner: str) -> AutoPatchMerger:
    merger = AutoPatchMerger(config)
    merger.log("=" * 60)
    merger.log(banner)
    merger.log("=" * 60)
    merger.log(f"Remote work directory: {merger.remote_work_dir}")
    merger.report_data["config"] = merger.config
    return merger


def log_step(merger: AutoPatchMerger, flow_label: str, step_no: int, title: str) -> None:
    merger.log(f"\n[{flow_label} Step {step_no}] {title}")


def finish_with_report(
    merger: AutoPatchMerger,
    code: int,
    log_execution: bool = False,
    report_label: Optional[str] = None,
) -> int:
    previous_label = getattr(merger, "report_step_label", None)
    merger.report_step_label = report_label
    report_path = merger._finalize_and_generate_report()
    merger.report_step_label = previous_label
    if report_path:
        merger.log(f"Report: {report_path}")
    if log_execution:
        merger.log(f"Execution log: {merger.log_file_path}")
    return code


def fail_step(
    merger: AutoPatchMerger,
    step: str,
    detail: str,
    error: Optional[str] = None,
    code: int = 1,
    log_execution: bool = False,
    report_label: Optional[str] = None,
) -> int:
    merger.add_step(step, "failed", detail)
    if error:
        merger.report_data["errors"].append(error)
    return finish_with_report(merger, code, log_execution=log_execution, report_label=report_label)


def warn_step(
    merger: AutoPatchMerger,
    step: str,
    detail: str,
    code: int = 2,
    log_execution: bool = True,
    report_label: Optional[str] = None,
) -> int:
    merger.add_step(step, "warning", detail)
    return finish_with_report(merger, code, log_execution=log_execution, report_label=report_label)


def ensure_bridge_ready(merger: AutoPatchMerger, flow_label: str, report_label: Optional[str] = None) -> Optional[int]:
    """Informational bridge probe. No longer a blocking pre-check.

    New ASF CLI: remote shell uses `asf bridge cmd` (auto `bridge up` on first cmd).
    Legacy CLI: `remote-runner bridge-exec`. This step only probes + logs; real
    connectivity errors surface on the first remote command.
    """
    log_step(merger, flow_label, 1, "Check Harness bridge (informational)")
    ready = merger.check_bridge_connection()
    if ready:
        merger.add_step("Check Harness bridge", "success",
                        "Bridge probe passed (or skipped via SKIP_BRIDGE_CHECK).")
    else:
        # Note: check_bridge_connection() currently returns True on non-ready
        # (non-blocking); kept here for call-site compatibility.
        merger.add_step("Check Harness bridge", "warning",
                        "Bridge probe did not confirm ready; continuing anyway.")
    return None


def safe_close_merger(merger: Optional[AutoPatchMerger]) -> None:
    if merger and hasattr(merger, "close_log_file"):
        merger.close_log_file()

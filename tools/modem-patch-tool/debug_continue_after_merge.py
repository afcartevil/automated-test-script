from debug_flow_common import (
    create_merger,
    ensure_bridge_ready,
    fail_step,
    finish_with_report,
    log_step,
    load_runtime_config,
    safe_close_merger,
    warn_step,
)


DEFAULT_CONFIG = {
    "NODE_BRANCH": "master",
    "target_BRANCH": "PRODUCT_V_v0mp1rc_NR15_common",
    "AP_lable": "V13.29",
    "DESCRIPTION": "BASELINE_UPGRADE",
    "JIRAID": "AR-UIF-0001-001-010",
    "work_dir": "/home/user/modem",
}

FLOW_LABEL = "Continue flow"
REPORT_LABEL = "Continue flow report"


def run_continue_flow(merger) -> int:
    log_step(merger, FLOW_LABEL, 7, "Upload helper scripts")
    if not merger.upload_scripts():
        return finish_with_report(merger, 1, report_label=REPORT_LABEL)
    merger.wait(merger.short_delay)

    log_step(merger, FLOW_LABEL, 8, "Run continue script")
    result = merger.run_harness_command(
        ["bash", "tools/md_continue_after_conflict.sh"], merger.remote_work_dir, delay_after=merger.medium_delay
    )
    if not result:
        return fail_step(merger, "Continue flow", "Continue script failed", "continue_script_failed", report_label=REPORT_LABEL)

    if result.returncode == 2:
        return warn_step(merger, "Continue flow", "Conflicts still remain. Resolve them manually and click Continue again.", report_label=REPORT_LABEL)

    out = (result.stdout or "") if hasattr(result, "stdout") else ""
    if "Unmerged files remain" in out or "Conflict markers remain" in out:
        return warn_step(merger, "Continue flow", "Conflicts still remain. Resolve them manually and click Continue again.", report_label=REPORT_LABEL)

    log_step(merger, FLOW_LABEL, 9, "Verify repository stable state")
    stable_probe = merger._wait_for_remote_repo_stable()
    in_merge = bool(stable_probe.get("merge_head"))
    unmerged_files = sorted(set((stable_probe.get("diff_files") or []) + (stable_probe.get("ls_files") or [])))
    if in_merge or unmerged_files:
        if unmerged_files:
            merger.log("Remaining unmerged files after continue:")
            merger.log("\n".join(unmerged_files))
        return warn_step(merger, "Continue flow", "Conflicts still remain. Resolve them manually and click Continue again.", report_label=REPORT_LABEL)

    if result.returncode != 0:
        return fail_step(
            merger,
            "Continue flow",
            f"Unexpected continue script exit code: {result.returncode}",
            f"continue_script_exit_{result.returncode}",
            report_label=REPORT_LABEL,
        )

    merger.add_step("Continue flow", "success", "Continue flow completed")
    return finish_with_report(merger, 0, log_execution=True, report_label=REPORT_LABEL)


def main() -> int:
    config = load_runtime_config(DEFAULT_CONFIG)
    merger = None
    try:
        merger = create_merger(config, "Auto Patch Merger Web Flow (Continue)")
        bridge_rc = ensure_bridge_ready(merger, FLOW_LABEL, report_label=REPORT_LABEL)
        if bridge_rc is not None:
            return bridge_rc
        return run_continue_flow(merger)
    finally:
        safe_close_merger(merger)


if __name__ == "__main__":
    raise SystemExit(main())

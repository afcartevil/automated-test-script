from debug_flow_common import (
    create_merger,
    ensure_bridge_ready,
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

FLOW_LABEL = "Initial flow"
REPORT_LABEL = "Initial flow report"


def run_stop_flow(merger) -> int:
    log_step(merger, FLOW_LABEL, 2, "Prepare in-repo tools/md_merge.sh")
    if not merger.configure_md_merge(mode="merge"):
        return finish_with_report(merger, 1, report_label=REPORT_LABEL)
    merger.wait(merger.medium_delay)

    log_step(merger, FLOW_LABEL, 3, "Run tools/md_merge.sh")
    if not merger.run_md_merge():
        return finish_with_report(merger, 1, report_label=REPORT_LABEL)

    in_merge = merger.is_merge_in_progress()

    if in_merge:
        log_step(merger, FLOW_LABEL, 4, "Wait for manual conflict resolution")
        return warn_step(
            merger,
            "Wait for manual conflict resolution",
            "Conflicts detected (MERGE_HEAD exists). Resolve them manually, then click Continue "
            "(equiv. typing y in md_merge.sh) to commit and run check_diff_file / update_before_node_commit_id.",
            report_label=REPORT_LABEL,
        )

    log_step(merger, FLOW_LABEL, 5, "Post-merge already handled by md_merge.sh")
    merger.add_step(
        "Run post-merge steps",
        "success",
        "No conflict; in-repo md_merge.sh already finished check_diff_file / update_before_node_commit_id",
    )
    return finish_with_report(merger, 0, log_execution=True, report_label=REPORT_LABEL)


def main() -> int:
    config = load_runtime_config(DEFAULT_CONFIG)
    merger = None
    try:
        merger = create_merger(config, "Auto Patch Merger Web Flow (Pause On Conflict)")
        bridge_rc = ensure_bridge_ready(merger, FLOW_LABEL, report_label=REPORT_LABEL)
        if bridge_rc is not None:
            return bridge_rc
        return run_stop_flow(merger)
    finally:
        safe_close_merger(merger)


if __name__ == "__main__":
    raise SystemExit(main())

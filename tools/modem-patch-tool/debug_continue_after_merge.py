import json
import os
import sys

from auto_patch_merger import AutoPatchMerger


def main() -> int:
    config = {
        "NODE_BRANCH": "master",
        "target_BRANCH": "PRODUCT_V_v0mp1rc_NR15_common",
        "AP_lable": "V13.29",
        "DESCRIPTION": "BASELINE_UPGRADE",
        "JIRAID": "AR-UIF-0001-001-010",
        "work_dir": "/home/user/modem",
    }

    cfg_path = sys.argv[1] if len(sys.argv) > 1 else None
    if cfg_path and os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            config.update(json.load(f))
        try:
            config["output_dir"] = os.path.dirname(cfg_path)
        except Exception:
            pass

    merger = None
    try:
        merger = AutoPatchMerger(config)
        merger.log("=" * 60)
        merger.log("Auto Patch Merger Web Flow (Continue)")
        merger.log("=" * 60)
        merger.log(f"Remote work directory: {merger.remote_work_dir}")
        merger.report_data["config"] = merger.config

        merger.log("\n[Step 1] Checking harness bridge connection...")
        if not merger.check_bridge_connection():
            merger.add_step("检测 Harness 桥接", "failed", "桥接连接失败")
            merger.report_data["errors"].append("Bridge connection check failed")
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            return 1
        merger.add_step("检测 Harness 桥接", "success", "桥接连接正常")

        merger.log("\n[Step 2] Uploading scripts to remote...")
        if not merger.upload_scripts():
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            return 1
        merger.wait(merger.short_delay)

        merger.log("\n[Step 3] Continuing after manual resolution...")
        result = merger.run_harness_command(
            ["bash", "tools/md_continue_after_conflict.sh"], merger.remote_work_dir, delay_after=merger.medium_delay
        )
        if not result:
            merger.add_step("继续执行", "failed", "继续脚本执行失败")
            merger.report_data["errors"].append("continue_script_failed")
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            return 1

        if result.returncode == 2:
            merger.add_step("继续执行", "warning", "仍存在冲突，请继续手动解冲突后再次点击继续")
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            merger.log(f"Execution log: {merger.log_file_path}")
            return 2

        out = (result.stdout or "") if hasattr(result, "stdout") else ""
        if "Unmerged files remain" in out or "Conflict markers remain" in out:
            merger.add_step("继续执行", "warning", "仍存在冲突，请继续手动解冲突后再次点击继续")
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            merger.log(f"Execution log: {merger.log_file_path}")
            return 2

        merge_head = merger.run_harness_command(["test", "-f", ".git/MERGE_HEAD"], merger.remote_work_dir, delay_after=merger.short_delay)
        in_merge = bool(merge_head and merge_head.returncode == 0)
        unmerged = merger.run_harness_command(
            ["GIT_PAGER=cat", "git", "diff", "--name-only", "--diff-filter=U"], merger.remote_work_dir, delay_after=merger.short_delay
        )
        has_unmerged = bool(unmerged and unmerged.returncode == 0 and (unmerged.stdout or "").strip())
        if in_merge or has_unmerged:
            merger.add_step("继续执行", "warning", "仍存在冲突，请继续手动解冲突后再次点击继续")
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            merger.log(f"Execution log: {merger.log_file_path}")
            return 2

        if result.returncode != 0:
            merger.add_step("继续执行", "failed", f"继续脚本返回码异常: {result.returncode}")
            merger.report_data["errors"].append(f"continue_script_exit_{result.returncode}")
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            return 1

        merger.add_step("继续执行", "success", "后续步骤执行完成")
        report_path = merger._finalize_and_generate_report()
        if report_path:
            merger.log(f"Report: {report_path}")
        merger.log(f"Execution log: {merger.log_file_path}")
        return 0
    finally:
        if merger and hasattr(merger, "close_log_file"):
            merger.close_log_file()


if __name__ == "__main__":
    raise SystemExit(main())

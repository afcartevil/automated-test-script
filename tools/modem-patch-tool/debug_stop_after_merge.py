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
            run_dir = os.path.dirname(cfg_path)
            config["output_dir"] = run_dir
        except Exception:
            pass

    merger = None
    try:
        merger = AutoPatchMerger(config)
        merger.log("=" * 60)
        merger.log("Auto Patch Merger Web Flow (Pause On Conflict)")
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

        merger.log("\n[Step 2] Testing harness bridge-exec...")
        test_result = merger.run_harness_command(["echo", "Harness bridge connection test"])
        if not (test_result and test_result.returncode == 0):
            merger.add_step("测试 Harness 执行", "failed", "远程执行失败")
            merger.report_data["errors"].append("Harness bridge-exec failed")
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            return 1
        merger.add_step("测试 Harness 执行", "success", "远程执行正常")

        merger.log("\n[Step 3] Uploading non-interactive merge script...")
        if not merger.configure_md_merge():
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            return 1
        merger.wait(merger.medium_delay)

        merger.log("\n[Step 4] Running non-interactive merge script...")
        if not merger.run_md_merge():
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            return 1

        merge_head = merger.run_harness_command(["test", "-f", ".git/MERGE_HEAD"], merger.remote_work_dir, delay_after=merger.short_delay)
        in_merge = bool(merge_head and merge_head.returncode == 0)

        if in_merge:
            merger.log("\nConflict detected. Waiting for manual resolution.")
            merger.add_step("等待人工解冲突", "warning", "检测到冲突（MERGE_HEAD 存在），请研发手动解完后点击继续，继续后将自动执行 commit、post-merge 与 push")
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            merger.log(f"Execution log: {merger.log_file_path}")
            return 2

        merger.log("\n[Step 5] Uploading helper scripts to remote...")
        if not merger.upload_scripts():
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            return 1
        merger.wait(merger.short_delay)

        merger.log("\n[Step 6] Running post-merge steps...")
        post = merger.run_harness_command(["bash", "tools/md_post_merge.sh"], merger.remote_work_dir, delay_after=merger.medium_delay)
        if not (post and post.returncode == 0):
            merger.add_step("后续处理", "failed", "后续步骤执行失败")
            merger.report_data["errors"].append("post_merge_failed")
            report_path = merger._finalize_and_generate_report()
            if report_path:
                merger.log(f"Report: {report_path}")
            return 1
        merger.add_step("后续处理", "success", "后续步骤执行完成")

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


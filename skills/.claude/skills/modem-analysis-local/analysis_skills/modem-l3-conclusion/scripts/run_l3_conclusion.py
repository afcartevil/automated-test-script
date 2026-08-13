import argparse
import json
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "_shared"))
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

from modem_analysis_runtime import (
    apply_l3_result, build_l3_result, configure_stdio,
    load_manifest, save_manifest, setup_skill_logger,
)


def parse_args():
    parser = argparse.ArgumentParser(description="执行 L3 结论汇总。")
    parser.add_argument("--manifest", required=True, help="manifest 文件路径")
    parser.add_argument("--output", help="结果 JSON 输出路径")
    return parser.parse_args()


def main():
    configure_stdio()
    args = parse_args()

    try:
        manifest = load_manifest(args.manifest)
    except Exception as exc:
        print(f"SKILL_FAILED: L3 无法加载 manifest ({args.manifest}): {exc}")
        sys.exit(1)

    issue_key = manifest.get("issue_key", "") or "unknown"
    logger = setup_skill_logger(args.manifest, issue_key)
    logger.info("=== L3 conclusion 开始 ===")

    result = build_l3_result(manifest)
    apply_l3_result(manifest, result)
    logger.info(f"L3 完成: primary_domain={result.get('primary_domain')}, "
                f"confidence={result.get('confidence')}")
    save_manifest(args.manifest, manifest)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

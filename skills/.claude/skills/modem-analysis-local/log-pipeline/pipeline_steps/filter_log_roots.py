import argparse
import json
import logging
import os
import shutil
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from trace_extensions import discover_qcom_trace_dirs  # noqa: E402


DEFAULT_MANIFEST = {
    "extraction": {
        "extracted_dirs": [],
        "normalized_log_roots": [],
        "filter_results": [],
    }
}


def configure_stdio():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def merge_defaults(target, defaults):
    for key, value in defaults.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_defaults(target[key], value)
    return target


def load_manifest(path):
    if not path or not os.path.exists(path):
        return deepcopy(DEFAULT_MANIFEST)
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"manifest 格式错误: {path}")
    return merge_defaults(data, deepcopy(DEFAULT_MANIFEST))


def save_manifest(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = merge_defaults(data, deepcopy(DEFAULT_MANIFEST))
    data["_meta"] = {"updated_at": datetime.now().isoformat(timespec="seconds")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def remove_file(path, retries=3, delay=0.2):
    logger = logging.getLogger("modem-log-structure-filter")
    for attempt in range(retries):
        if not os.path.exists(path):
            return
        try:
            os.remove(path)
            return
        except OSError as e:
            if getattr(e, "winerror", None) == 32 and attempt < retries - 1:
                time.sleep(delay)
                continue
            logger.warning("删除文件失败 %s: %s", path, e)
            return


def remove_empty_dir(path, retries=3, delay=0.2):
    logger = logging.getLogger("modem-log-structure-filter")
    for attempt in range(retries):
        if not os.path.exists(path):
            return
        try:
            if os.listdir(path):
                return
            os.rmdir(path)
            return
        except OSError as e:
            if getattr(e, "winerror", None) == 32 and attempt < retries - 1:
                time.sleep(delay)
                continue
            logger.warning("删除目录失败 %s: %s", path, e)
            return


def keep_only_modem_mobile_netlog_and_qcom_roots(base_dir, qcom_trace_dirs):
    """
    在 MTK 四类目录白名单基础上，额外保留 qcom_trace_dirs 下的文件（仅新增路径，不修改 keep_only_modem_and_mobile_logs）。
    """
    base_dir = os.path.abspath(base_dir)
    target_names = {"mdlog1", "mobilelog", "modem", "netlog"}
    target_dirs = []

    for root, dirs, _files in os.walk(base_dir):
        for name in dirs:
            if name.lower() in target_names:
                target_dirs.append(os.path.abspath(os.path.join(root, name)))

    for path in qcom_trace_dirs or []:
        if path and os.path.isdir(path):
            target_dirs.append(os.path.abspath(path))

    if not target_dirs:
        logging.getLogger("modem-log-structure-filter").info(
            "目录 %s 下未找到 mdlog1/modem/mobilelog/netlog 且无 QCOM trace 目录，保留全部文件",
            base_dir,
        )
        return

    def is_under_allowed(path):
        path = os.path.abspath(path)
        return any(os.path.commonpath([path, target]) == target for target in target_dirs)

    def is_ancestor_of_allowed(path):
        path = os.path.abspath(path)
        return any(os.path.commonpath([path, target]) == path for target in target_dirs)

    for root, dirs, files in os.walk(base_dir, topdown=False):
        for filename in files:
            file_path = os.path.join(root, filename)
            if not is_under_allowed(file_path):
                remove_file(file_path)
        for dirname in dirs:
            dir_path = os.path.join(root, dirname)
            if is_under_allowed(dir_path) or is_ancestor_of_allowed(dir_path):
                continue
            remove_empty_dir(dir_path)


def keep_only_modem_and_mobile_logs(base_dir):
    base_dir = os.path.abspath(base_dir)
    target_names = {"mdlog1", "mobilelog", "modem", "netlog"}
    target_dirs = []

    for root, dirs, _files in os.walk(base_dir):
        for name in dirs:
            if name.lower() in target_names:
                target_dirs.append(os.path.abspath(os.path.join(root, name)))

    if not target_dirs:
        logging.getLogger("modem-log-structure-filter").info(
            "目录 %s 下未找到 mdlog1/modem/mobilelog/netlog，保留全部文件", base_dir
        )
        return

    def is_under_allowed(path):
        path = os.path.abspath(path)
        return any(os.path.commonpath([path, target]) == target for target in target_dirs)

    def is_ancestor_of_allowed(path):
        path = os.path.abspath(path)
        return any(os.path.commonpath([path, target]) == path for target in target_dirs)

    for root, dirs, files in os.walk(base_dir, topdown=False):
        for filename in files:
            file_path = os.path.join(root, filename)
            if not is_under_allowed(file_path):
                remove_file(file_path)
        for dirname in dirs:
            dir_path = os.path.join(root, dirname)
            if is_under_allowed(dir_path) or is_ancestor_of_allowed(dir_path):
                continue
            remove_empty_dir(dir_path)


def filter_mobilelog_aplog(base_dir):
    logger = logging.getLogger("modem-log-structure-filter")
    mobilelog_dirs = []
    for root, dirs, _files in os.walk(base_dir):
        for name in dirs:
            if name.lower() == "mobilelog":
                mobilelog_dirs.append(os.path.join(root, name))

    def _keep_mobilelog_item(name: str) -> bool:
        lower = name.lower()
        return (
            lower.startswith("radio_log")
            or lower.startswith("main_log")
            or lower.startswith("kernel_log")
            or lower.startswith("radiologcat")
            or lower.startswith("mainlogcat")
            or lower.startswith("kernellogcat")
        )

    for mobilelog_dir in mobilelog_dirs:
        try:
            entries = os.listdir(mobilelog_dir)
        except OSError as e:
            logger.warning("遍历目录失败 %s: %s", mobilelog_dir, e)
            continue

        for name in entries:
            child_path = os.path.join(mobilelog_dir, name)
            lower = name.lower()

            # MTK：精简 APLog_* 子目录
            if os.path.isdir(child_path) and lower.startswith("aplog"):
                try:
                    for child_name in os.listdir(child_path):
                        item_path = os.path.join(child_path, child_name)
                        if _keep_mobilelog_item(child_name):
                            continue
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path, ignore_errors=True)
                        else:
                            remove_file(item_path)
                except OSError as e:
                    logger.warning("精简 APLog 目录失败 %s: %s", child_path, e)
                continue

            # QCOM：日志在 mobilelog/ 根下，去掉 dumpsys 等杂项
            if _keep_mobilelog_item(name):
                continue
            if os.path.isdir(child_path):
                shutil.rmtree(child_path, ignore_errors=True)
            else:
                remove_file(child_path)


def discover_markers(base_dir):
    found = {
        "mdlog1_dirs": [],
        "modem_dirs": [],
        "mobilelog_dirs": [],
        "aplog_dirs": [],
        "aee_dirs": [],
        "netlog_dirs": [],
    }
    for root, dirs, files in os.walk(base_dir):
        # Check for standard modem log directories
        for name in dirs:
            lower = name.lower()
            path = os.path.join(root, name)
            if lower == "mdlog1" or "mdlog1" in lower:
                found["mdlog1_dirs"].append(path)
            elif lower == "modem":
                found["modem_dirs"].append(path)
            elif lower == "mobilelog":
                found["mobilelog_dirs"].append(path)
            elif lower.startswith("aplog"):
                found["aplog_dirs"].append(path)
            elif lower == "netlog":
                found["netlog_dirs"].append(path)
        
        # Check for AEE exception marker files (covers all types: EE/KE/NE/JE/SWT/HWT)
        for name in files:
            lower = name.lower()
            if lower == "__exp_main.txt" or lower.startswith("_exp_detail"):
                parent_dir = os.path.abspath(root)
                if parent_dir not in found["aee_dirs"]:
                    found["aee_dirs"].append(parent_dir)
    
    for key, values in found.items():
        found[key] = sorted({os.path.abspath(v) for v in values})
    return found


def parse_args():
    parser = argparse.ArgumentParser(description="筛选解压后的 modem 日志目录结构。")
    parser.add_argument("--manifest", help="manifest 文件路径")
    parser.add_argument("--input-dir", action="append", dest="input_dirs", help="待筛选目录，可重复传入")
    parser.add_argument("--output", help="结果 JSON 输出路径；默认回写 manifest 或打印到 stdout")
    return parser.parse_args()


def should_skip_log_filter_deletion():
    from pipeline_retention import should_skip_log_filter_deletion as _should_skip

    return _should_skip()


def filter_modem_logs(manifest_path):
    """
    过滤 modem 相关日志目录（供 pipeline 调用）
    
    Args:
        manifest_path: manifest 文件路径
    
    Returns:
        dict: 过滤结果
    """
    configure_stdio()
    logger = logging.getLogger("modem-log-filter")
    manifest = load_manifest(manifest_path)
    input_dirs = list(manifest.get("extraction", {}).get("extracted_dirs") or [])
    if not input_dirs:
        input_dirs = list(manifest.get("downloads", {}).get("download_dirs") or [])
        if input_dirs:
            logger.info(
                "extraction.extracted_dirs 为空，回退使用 downloads.download_dirs（常见于文件夹直拷、无需解压）"
            )
    if not input_dirs:
        raise ValueError("没有可筛选目录，请先执行下载或解压步骤")
    
    normalized_roots = []
    results = []
    for input_dir in input_dirs:
        abs_input = os.path.abspath(input_dir)
        item = {
            "input_dir": abs_input,
            "success": False,
            "normalized_root": abs_input,
            "found": {
                "mdlog1_dirs": [],
                "modem_dirs": [],
                "mobilelog_dirs": [],
                "aplog_dirs": [],
                "aee_dirs": [],
                "netlog_dirs": [],
                "qcom_trace_dirs": [],
            },
        }
        try:
            if not os.path.isdir(abs_input):
                raise FileNotFoundError(f"目录不存在: {abs_input}")
            qcom_trace_dirs = discover_qcom_trace_dirs(abs_input)
            if should_skip_log_filter_deletion():
                logger.info("SKIP_LOG_FILTER_DELETION 生效，跳过删文件，仅扫描目录标记: %s", abs_input)
            else:
                if qcom_trace_dirs:
                    keep_only_modem_mobile_netlog_and_qcom_roots(abs_input, qcom_trace_dirs)
                else:
                    keep_only_modem_and_mobile_logs(abs_input)
                filter_mobilelog_aplog(abs_input)
            item["found"] = discover_markers(abs_input)
            item["found"]["qcom_trace_dirs"] = qcom_trace_dirs
            if qcom_trace_dirs:
                logger.info(
                    "QCOM trace 目录 (%d): %s",
                    len(qcom_trace_dirs),
                    "; ".join(qcom_trace_dirs[:5])
                    + (" ..." if len(qcom_trace_dirs) > 5 else ""),
                )
            item["success"] = any(item["found"].values())
            normalized_roots.append(abs_input)
        except Exception as e:
            item["error"] = str(e)
            logger.error(f"过滤目录失败 {abs_input}: {e}")
        results.append(item)
    
    normalized_roots = list(dict.fromkeys(normalized_roots))
    return {"normalized_log_roots": normalized_roots, "filter_results": results}


def main():
    configure_stdio()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    manifest = load_manifest(args.manifest)
    input_dirs = list(args.input_dirs or manifest.get("extraction", {}).get("extracted_dirs") or [])
    if not input_dirs:
        input_dirs = list(manifest.get("downloads", {}).get("download_dirs") or [])
    if not input_dirs:
        raise SystemExit(
            "没有可筛选目录，请通过 --input-dir、manifest.extraction.extracted_dirs "
            "或 manifest.downloads.download_dirs 提供。"
        )

    normalized_roots = []
    results = []
    for input_dir in input_dirs:
        abs_input = os.path.abspath(input_dir)
        item = {
            "input_dir": abs_input,
            "success": False,
            "normalized_root": abs_input,
            "found": {
                "mdlog1_dirs": [],
                "modem_dirs": [],
                "mobilelog_dirs": [],
                "aplog_dirs": [],
                "aee_dirs": [],
                "netlog_dirs": [],
                "qcom_trace_dirs": [],
            },
        }
        try:
            if not os.path.isdir(abs_input):
                raise FileNotFoundError(f"目录不存在: {abs_input}")
            qcom_trace_dirs = discover_qcom_trace_dirs(abs_input)
            if should_skip_log_filter_deletion():
                logger.info("SKIP_LOG_FILTER_DELETION 生效，跳过删文件，仅扫描目录标记: %s", abs_input)
            else:
                if qcom_trace_dirs:
                    keep_only_modem_mobile_netlog_and_qcom_roots(abs_input, qcom_trace_dirs)
                else:
                    keep_only_modem_and_mobile_logs(abs_input)
                filter_mobilelog_aplog(abs_input)
            item["found"] = discover_markers(abs_input)
            item["found"]["qcom_trace_dirs"] = qcom_trace_dirs
            item["success"] = any(item["found"].values())
            normalized_roots.append(abs_input)
        except Exception as e:
            item["error"] = str(e)
        results.append(item)

    normalized_roots = list(dict.fromkeys(normalized_roots))
    manifest["extraction"]["normalized_log_roots"] = normalized_roots
    manifest["extraction"]["filter_results"] = results

    result = {"normalized_log_roots": normalized_roots, "results": results}
    if args.manifest:
        save_manifest(args.manifest, manifest)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

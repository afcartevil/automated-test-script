import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# 引入 finalizer（_shared 与本目录同级）
_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from log_group_paths import (  # noqa: E402
    resolve_aplog_group_rel_path,
    resolve_group_rel_path,
    resolve_mobilelog_group_rel_path,
    resolve_pack_dest_dir,
)
from manifest_finalizer import finalize_and_validate  # noqa: E402


DEFAULT_MANIFEST = {
    "issue_key": "",
    "workspace_root": "",
    "final_log_root": "",
    "downloads": {
        "download_root": "",
        "download_dirs": [],
    },
    "extraction": {
        "normalized_log_roots": [],
    },
    "trace_exports": {
        "groups": [],
        "results": [],
        "aggregated_files": {},
        "copied_support_files": {},
    },
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
    # 注意：只刷新 updated_at，不能整个替换 _meta —
    # 否则会丢掉 phase1_completed_at / phase1_host / phase1_smb_publish 等已写入字段。
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
        data["_meta"] = meta
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def sanitize_dir_component(name):
    name = "" if name is None else str(name)
    name = name.strip()
    if not name:
        return "unknown"
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name.strip("._") or "unknown"


# 与 elt-nlt-export TRACE_KEYS、_shared/modem_analysis_runtime TRACE_FILES 对齐，
# 保证 final_logs 下分组目录含 icd/l1/l2/ps_raw 时下游 L0/L1/L2 能 discover 并加载。
AGGREGATED_TRACE_TXT_KEYS = ("ota", "ps", "system", "sip", "icd", "l1", "l2", "ps_raw")


def unique_paths(paths):
    seen = set()
    ordered = []
    for path in paths:
        if not path:
            continue
        abs_path = os.path.abspath(path)
        norm = os.path.normcase(abs_path)
        if norm in seen:
            continue
        seen.add(norm)
        ordered.append(abs_path)
    return ordered


def normalize_role_token(token):
    token = (token or "").strip().upper()
    if token.startswith("DUT"):
        return "DUT"
    if token.startswith("REF"):
        return "REF"
    return ""


def tree_has_explicit_role_dirs(base_dir):
    for root, dirs, _files in os.walk(base_dir):
        for name in dirs:
            if normalize_role_token(name):
                return True
    return False


def clear_readonly_recursive(path):
    if os.name != "nt" or not path or not os.path.exists(path):
        return
    try:
        subprocess.run(
            ["cmd", "/c", "attrib", "-R", os.path.abspath(path), "/S", "/D"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        pass


def rmtree_with_retries(path, retries=8, delay=0.5):
    logger = logging.getLogger("trace-aggregate-and-package")
    if not path:
        return True
    raw_path = os.path.abspath(path)
    for attempt in range(retries):
        if not os.path.exists(raw_path):
            return True
        try:
            clear_readonly_recursive(raw_path)

            def onerror(func, failed_path, _exc_info):
                try:
                    os.chmod(failed_path, 0o700)
                except Exception:
                    pass
                try:
                    func(failed_path)
                except Exception:
                    pass

            shutil.rmtree(raw_path, onerror=onerror)
        except Exception as e:
            logger.warning("删除目录失败 %s: %s", raw_path, e)
        if not os.path.exists(raw_path):
            return True
        time.sleep(delay * (attempt + 1))
    return not os.path.exists(raw_path)


def copy_trace_txts_to_dir(dest_dir, exported_results):
    """将 trace txt（ota/ps/system/...）拷贝到 dest_dir，不拼接合并。"""
    logger = logging.getLogger("trace-aggregate-and-package")
    dest_dir = os.path.abspath(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    copied = {}

    for item in exported_results:
        if not isinstance(item, dict):
            continue
        for key, src in item.items():
            if key not in AGGREGATED_TRACE_TXT_KEYS:
                continue
            if not src or not os.path.isfile(src):
                continue
            dst = os.path.join(dest_dir, f"{key}.txt")
            try:
                if os.path.exists(dst):
                    remove_path_with_retries(dst)
                shutil.copy2(src, dst)
                copied[key] = dst
            except OSError as exc:
                logger.warning("拷贝 trace 失败 %s -> %s: %s", src, dst, exc)
    return copied


def copy_qcom_export_txts_to_dir(dest_dir, exported_results):
    """将 QCOM 导出的 txt 按原文件名拷贝到 final 目录（不合并、不重命名）。"""
    logger = logging.getLogger("trace-aggregate-and-package")
    dest_dir = os.path.abspath(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    copied = {}

    for item in exported_results:
        if not isinstance(item, dict):
            continue
        raw = item.get("qcom_txt")
        if not raw:
            continue
        paths = raw if isinstance(raw, list) else [raw]
        key_paths = copied.setdefault("qcom_txt", [])
        for src in paths:
            if not src or not os.path.isfile(src):
                continue
            dst = os.path.join(dest_dir, os.path.basename(src))
            if os.path.exists(dst):
                stem, ext = os.path.splitext(os.path.basename(src))
                dst = os.path.join(dest_dir, f"{stem}_{abs(hash(src)) & 0xFFFF}{ext}")
            try:
                shutil.copy2(src, dst)
                key_paths.append(dst)
            except OSError as exc:
                logger.warning("拷贝 QCOM txt 失败 %s -> %s: %s", src, dst, exc)
    return copied


def copy_qcom_trace_files_to_dir(dest_dir, exported_results):
    """将 QCOM 分组中的 .qmdl2 / .qdss 源文件拷贝到打包目录。"""
    logger = logging.getLogger("trace-aggregate-and-package")
    dest_dir = os.path.abspath(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    copied = {}

    for item in exported_results:
        if not isinstance(item, dict):
            continue
        for key in ("qmdl2", "qdss"):
            raw = item.get(key)
            if not raw:
                continue
            paths = raw if isinstance(raw, list) else [raw]
            key_paths = copied.setdefault(key, [])
            for src in paths:
                if not src or not os.path.isfile(src):
                    continue
                dst = os.path.join(dest_dir, os.path.basename(src))
                if os.path.exists(dst):
                    stem, ext = os.path.splitext(os.path.basename(src))
                    dst = os.path.join(dest_dir, f"{stem}_{abs(hash(src)) & 0xFFFF}{ext}")
                try:
                    shutil.copy2(src, dst)
                    key_paths.append(dst)
                except OSError as exc:
                    logger.warning("拷贝 QCOM 文件失败 %s -> %s: %s", src, dst, exc)
    return copied


def support_target_name(src, dest_dir):
    base = os.path.basename(src).lower()
    
    # __exp_main.txt 保持原名
    if os.path.basename(src) == "__exp_main.txt":
        return "__exp_main.txt"
    
    # AEE 类型文件映射
    if os.path.basename(src) == "SYS_ANDROID_LOG_ALL":
        target_base = "ANDROID_LOG"
    elif os.path.basename(src) == "SYS_KERNEL_LOG":
        target_base = "KERNEL_LOG"
    # PCAP 导出文件
    elif base.endswith(('_pcap.txt', '_pcapng.txt', '_cap.txt')):
        # 保留原始文件名，但如果冲突则添加序号
        target_base = os.path.splitext(os.path.basename(src))[0]
    # 普通日志文件
    elif base.startswith("radio_log"):
        target_base = "radio_log"
    elif base.startswith("main_log"):
        target_base = "main_log"
    elif base.startswith("kernel_log"):
        target_base = "kernel_log"
    else:
        return os.path.basename(src)
    
    # 检查目标目录中是否已存在同名文件/目录
    ext = os.path.splitext(os.path.basename(src))[1] if os.path.isfile(src) else ""
    target_name = target_base + ext
    target_path = os.path.join(dest_dir, target_name)
    
    # 如果已存在，添加序号
    counter = 1
    while os.path.exists(target_path):
        target_name = f"{target_base}_{counter}{ext}"
        target_path = os.path.join(dest_dir, target_name)
        counter += 1
    
    return target_name


def copy_aplog_path_to_dir(src, aplog_dest_dir):
    """将 APLog 下的 radio/main/kernel 项拷入 APLog 目录，保留原始文件/目录名。"""
    logger = logging.getLogger("trace-aggregate-and-package")
    if not src or not os.path.exists(src):
        return None
    aplog_dest_dir = os.path.abspath(aplog_dest_dir)
    os.makedirs(aplog_dest_dir, exist_ok=True)
    base_name = os.path.basename(src.rstrip(os.sep))
    dst = os.path.join(aplog_dest_dir, base_name)
    counter = 1
    while os.path.exists(dst):
        dst = os.path.join(aplog_dest_dir, f"{base_name}_{counter}")
        counter += 1
    try:
        if os.path.isdir(src):
            if os.path.exists(dst):
                rmtree_with_retries(dst)
            shutil.copytree(src, dst)
        else:
            if os.path.exists(dst):
                remove_path_with_retries(dst)
            shutil.copy2(src, dst)
        return dst
    except Exception as e:
        logger.warning("复制 APLog 项失败 %s -> %s: %s", src, dst, e)
        return None


def copy_path_to_dir(src, dest_dir):
    logger = logging.getLogger("trace-aggregate-and-package")
    if not src or not os.path.exists(src):
        return None
    dest_dir = os.path.abspath(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    dst = os.path.join(dest_dir, support_target_name(src, dest_dir))
    try:
        if os.path.isdir(src):
            if os.path.exists(dst):
                rmtree_with_retries(dst)
            shutil.copytree(src, dst)
        else:
            if os.path.exists(dst):
                remove_path_with_retries(dst)
            shutil.copy2(src, dst)
        return dst
    except Exception as e:
        logger.warning("复制失败 %s -> %s: %s", src, dst, e)
        return None


def remove_path_with_retries(path, retries=8, delay=0.5):
    logger = logging.getLogger("trace-aggregate-and-package")
    if not path:
        return True
    raw_path = os.path.abspath(path)
    for attempt in range(retries):
        if not os.path.exists(raw_path):
            return True
        try:
            if os.path.isdir(raw_path):
                clear_readonly_recursive(raw_path)

                def onerror(func, failed_path, _exc_info):
                    try:
                        os.chmod(failed_path, 0o700)
                    except Exception:
                        pass
                    try:
                        func(failed_path)
                    except Exception:
                        pass

                shutil.rmtree(raw_path, onerror=onerror)
            else:
                clear_readonly_recursive(raw_path)
                try:
                    os.chmod(raw_path, 0o600)
                except Exception:
                    pass
                os.remove(raw_path)
        except Exception as e:
            logger.warning("删除路径失败 %s: %s", raw_path, e)
        if not os.path.exists(raw_path):
            return True
        time.sleep(delay * (attempt + 1))
    return not os.path.exists(raw_path)


def resolve_group_key(path, base_dir):
    """兼容旧名；等价于 resolve_group_rel_path（保留完整相对目录层级）。"""
    return resolve_group_rel_path(path, base_dir)


def find_aplog_items_grouped(base_dir):
    base_dir = os.path.abspath(base_dir)
    items = {}

    def is_aplog_root(path):
        return any(part.lower().startswith("aplog") for part in os.path.normpath(path).split(os.sep))
    
    def is_aee_root(path):
        """检查是否为 AEE 类型日志目录（包含 __exp_main.txt）"""
        return os.path.exists(os.path.join(path, "__exp_main.txt"))
    
    def is_netlog_root(path):
        """检查是否为 netlog 目录"""
        return any(part.lower() == "netlog" for part in os.path.normpath(path).split(os.sep))

    for root, dirs, files in os.walk(base_dir):
        # 检查是否为 AEE 根目录
        if is_aee_root(root):
            group_key = resolve_group_key(root, base_dir)
            entry = items.setdefault(group_key, {})
            
            # AEE 类型日志文件映射
            for name in files:
                lower = name.lower()
                src = os.path.join(root, name)
                
                if name == "__exp_main.txt":
                    entry.setdefault("exp_main", []).append(src)
                elif name == "SYS_ANDROID_LOG_ALL":
                    entry.setdefault("android_log", []).append(src)
                elif name == "SYS_KERNEL_LOG":
                    entry.setdefault("kernel", []).append(src)
            
            # AEE 目录不再向下遍历
            dirs.clear()
            continue
        
        # 检查是否为 netlog 目录，收集 pcap 导出的 txt 文件
        if is_netlog_root(root):
            group_key = resolve_group_key(root, base_dir)
            entry = items.setdefault(group_key, {})
            
            for name in files:
                lower = name.lower()
                # 匹配 pcap-export 生成的文件：*_pcap.txt, *_pcapng.txt, *_cap.txt
                if lower.endswith(('_pcap.txt', '_pcapng.txt', '_cap.txt')):
                    src = os.path.join(root, name)
                    entry.setdefault("pcap", []).append(src)
            continue

        # QCOM debuglogger：日志直接在 mobilelog/ 下（mainlogcat* / radiologcat* / kernellogcat*）
        if os.path.basename(root).lower() == "mobilelog":
            group_key = resolve_mobilelog_group_rel_path(root, base_dir)
            entry = items.setdefault(group_key, {})
            for name in files:
                lower = name.lower()
                src = os.path.join(root, name)
                if lower.startswith("radiologcat"):
                    entry.setdefault("radio", []).append(src)
                elif lower.startswith("mainlogcat"):
                    entry.setdefault("main", []).append(src)
                elif lower.startswith("kernellogcat"):
                    entry.setdefault("kernel", []).append(src)
            continue
        
        # MTK APLog 目录处理（只收集 APLog_* 目录的直接子项，不向下展开）
        if not is_aplog_root(root):
            continue
        if not os.path.basename(root).lower().startswith("aplog"):
            continue
        for name in files:
            lower = name.lower()
            if not (lower.startswith("radio_log") or lower.startswith("main_log") or lower.startswith("kernel_log")):
                continue
            src = os.path.join(root, name)
            group_key = resolve_aplog_group_rel_path(src, base_dir)
            entry = items.setdefault(group_key, {})
            if lower.startswith("radio_log"):
                entry.setdefault("radio", []).append(src)
            elif lower.startswith("main_log"):
                entry.setdefault("main", []).append(src)
            elif lower.startswith("kernel_log"):
                entry.setdefault("kernel", []).append(src)
        for name in dirs:
            lower = name.lower()
            if not (lower.startswith("radio_log") or lower.startswith("main_log") or lower.startswith("kernel_log")):
                continue
            src_dir = os.path.join(root, name)
            group_key = resolve_aplog_group_rel_path(src_dir, base_dir)
            entry = items.setdefault(group_key, {})
            if lower.startswith("radio_log"):
                entry.setdefault("radio", []).append(src_dir)
            elif lower.startswith("main_log"):
                entry.setdefault("main", []).append(src_dir)
            elif lower.startswith("kernel_log"):
                entry.setdefault("kernel", []).append(src_dir)
        # 不进入 radio/main/kernel 子目录，避免重复收集内部日志文件
        dirs[:] = [d for d in dirs if not d.lower().startswith(("radio_log", "main_log", "kernel_log"))]
    return items


def relative_key(final_root, dest_dir):
    rel = os.path.relpath(dest_dir, final_root).replace("\\", "/")
    return "root" if rel == "." else rel


def normalize_aggregated_files_map(files_map, final_root):
    """
    将打包结果标准化为 schema 兼容的 {key: relative_path} 结构。

    说明：
    - 旧路径类型（str）保持 key 不变；
    - 多文件类型（list）展开为 key_1/key_2/...，避免把 list 写入 manifest。
    """
    normalized = {}
    for key, value in (files_map or {}).items():
        if not value:
            continue
        if isinstance(value, list):
            valid = [p for p in value if p]
            if not valid:
                continue
            if len(valid) == 1:
                normalized[key] = os.path.relpath(valid[0], final_root).replace("\\", "/")
                continue
            for idx, path in enumerate(valid, start=1):
                normalized[f"{key}_{idx}"] = os.path.relpath(path, final_root).replace("\\", "/")
            continue
        normalized[key] = os.path.relpath(value, final_root).replace("\\", "/")
    return normalized


def _copy_aplog_support_items(entry, items, dest_dir):
    """dest_dir 为 APLog_* 目录；radio/main/kernel 保留原名，AEE/pcap 仍走标准化命名。"""
    radio_srcs = items.get("radio", [])
    if radio_srcs:
        entry["radio"] = []
        for src in radio_srcs:
            radio_dst = copy_aplog_path_to_dir(src, dest_dir)
            if radio_dst:
                entry["radio"].append(radio_dst)

    main_srcs = items.get("main", [])
    if main_srcs:
        entry["main"] = []
        for src in main_srcs:
            main_dst = copy_aplog_path_to_dir(src, dest_dir)
            if main_dst:
                entry["main"].append(main_dst)

    kernel_srcs = items.get("kernel", [])
    if kernel_srcs:
        entry["kernel"] = []
        for src in kernel_srcs:
            kernel_dst = copy_aplog_path_to_dir(src, dest_dir)
            if kernel_dst:
                entry["kernel"].append(kernel_dst)

    exp_main_srcs = items.get("exp_main", [])
    if exp_main_srcs:
        entry["exp_main"] = []
        for src in exp_main_srcs:
            exp_main_dst = copy_path_to_dir(src, dest_dir)
            if exp_main_dst:
                entry["exp_main"].append(exp_main_dst)

    android_log_srcs = items.get("android_log", [])
    if android_log_srcs:
        entry["android_log"] = []
        for src in android_log_srcs:
            android_log_dst = copy_path_to_dir(src, dest_dir)
            if android_log_dst:
                entry["android_log"].append(android_log_dst)

    pcap_srcs = items.get("pcap", [])
    if pcap_srcs:
        entry["pcap"] = []
        for src in pcap_srcs:
            pcap_dst = copy_path_to_dir(src, dest_dir)
            if pcap_dst:
                entry["pcap"].append(pcap_dst)


def build_destination_resolver(issue_key, final_root):
    issue_key = (issue_key or "unknown-issue").strip() or "unknown-issue"
    final_root = os.path.abspath(final_root)

    def resolve(_normalized_root, group_rel_path):
        return resolve_pack_dest_dir(final_root, _normalized_root, group_rel_path)

    return resolve


def package_trace_export_groups(trace_groups, final_root, resolve_destination):
    """按 trace 分组逐目录拷贝（不跨分组合并 txt）。"""
    logger = logging.getLogger("trace-aggregate-and-package")
    aggregated_files = {}
    final_groups = []

    for item in trace_groups:
        normalized_root = os.path.abspath(item.get("normalized_root") or final_root)
        source_dir = (item.get("source_dir") or "").strip()
        group_rel = (item.get("group_key") or "").strip()
        if not group_rel:
            group_rel = resolve_group_rel_path(source_dir, normalized_root) if source_dir else "root"

        dest_dir = resolve_destination(normalized_root, group_rel)
        if os.path.exists(dest_dir):
            rmtree_with_retries(dest_dir)

        exported = item.get("files") or {}
        files_map = copy_trace_txts_to_dir(dest_dir, [exported])
        qcom_txt_copied = copy_qcom_export_txts_to_dir(dest_dir, [exported])
        qcom_raw_copied = copy_qcom_trace_files_to_dir(dest_dir, [exported])
        files_map = {**files_map, **qcom_txt_copied, **qcom_raw_copied}

        agg_key = relative_key(final_root, dest_dir)
        aggregated_files[agg_key] = normalize_aggregated_files_map(files_map, final_root)
        final_groups.append(
            {
                "normalized_root": normalized_root,
                "source_dir": source_dir or dest_dir,
                "group_key": group_rel,
                "exporter": item.get("exporter") or "",
                "files": aggregated_files[agg_key],
            }
        )
        logger.info("pack trace group %s -> %s (%d files)", group_rel, dest_dir, len(files_map))

    return aggregated_files, final_groups


def cleanup_download_residue(manifest):
    cleanup = {
        "success": True,
        "removed_paths": [],
        "failed_paths": [],
    }

    paths_to_remove = []
    download_root = (manifest.get("downloads") or {}).get("download_root")
    if download_root:
        paths_to_remove.append(download_root)
    else:
        paths_to_remove.extend((manifest.get("downloads") or {}).get("download_dirs") or [])

    for path in unique_paths(paths_to_remove):
        if not os.path.exists(path):
            continue
        if remove_path_with_retries(path):
            cleanup["removed_paths"].append(os.path.abspath(path))
        else:
            cleanup["success"] = False
            cleanup["failed_paths"].append(os.path.abspath(path))

    manifest.setdefault("downloads", {})
    manifest["downloads"]["download_dirs"] = []
    if download_root and os.path.abspath(download_root) in cleanup["removed_paths"]:
        manifest["downloads"]["download_root"] = ""
    manifest.setdefault("extraction", {})
    manifest["extraction"]["extracted_dirs"] = []
    manifest["extraction"]["normalized_log_roots"] = []
    manifest["extraction"]["cleanup"] = cleanup
    return cleanup


def should_skip_download_cleanup() -> bool:
    from pipeline_retention import should_skip_download_cleanup as _should_skip

    return _should_skip()


def parse_args():
    parser = argparse.ArgumentParser(description="聚合导出的 trace txt 并复制附加日志到统一目录。")
    parser.add_argument("--manifest", help="manifest 文件路径")
    parser.add_argument("--output-root", help="最终输出目录；默认使用 manifest.final_log_root 或 workspace_root/final_logs")
    parser.add_argument("--output", help="结果 JSON 输出路径；默认回写 manifest 或打印到 stdout")
    return parser.parse_args()


def package_final_logs(manifest_path):
    """
    打包最终日志文件（供 pipeline 调用）
    
    Args:
        manifest_path: manifest 文件路径
    
    Returns:
        dict: 打包结果
    """
    configure_stdio()
    logger = logging.getLogger("trace-package")
    manifest = load_manifest(manifest_path)
    
    issue_key = (manifest.get("issue_key") or "unknown-issue").strip() or "unknown-issue"
    
    # 从 manifest 读取 workspace_root
    workspace_root = manifest.get("workspace_root") or os.path.join(
        os.getenv("WORKSPACE_ROOT") or os.path.join(os.getcwd(), "data_store"),
        issue_key
    )
    
    # 统一输出到 issue 根下的 final_logs 子目录
    final_root = os.path.join(workspace_root, "final_logs")
    final_root = os.path.abspath(final_root)
    os.makedirs(final_root, exist_ok=True)
    
    trace_groups = list(
        manifest.get("trace_exports", {}).get("raw_groups")
        or manifest.get("trace_exports", {}).get("groups")
        or []
    )
    normalized_roots = list(manifest.get("extraction", {}).get("normalized_log_roots") or [])
    if not normalized_roots:
        normalized_roots = sorted({item.get("normalized_root") for item in trace_groups if item.get("normalized_root")})
    
    resolve_destination = build_destination_resolver(issue_key, final_root)
    aggregated_files, final_groups = package_trace_export_groups(
        trace_groups, final_root, resolve_destination
    )

    copied_support_files = {}
    for normalized_root in normalized_roots:
        grouped_aplog = find_aplog_items_grouped(normalized_root)
        for group_rel, items in grouped_aplog.items():
            dest_dir = resolve_destination(normalized_root, group_rel)
            key = relative_key(final_root, dest_dir)
            entry = copied_support_files.setdefault(key, {})
            
            _copy_aplog_support_items(entry, items, dest_dir)

    # 不在此处删 downloads：须等 manifest 经 finalize 落盘后再删（见 run_pipeline.TracePackageStep）

    logger.info(
        "打包完成：aggregated_files=%d 组，copied_support_files=%d 组",
        len(aggregated_files), len(copied_support_files),
    )

    # 至少要产出一类日志（trace 类或 AEE 类）。两个都空时不抛异常，返回 ok=False 让上层决定。
    ok = bool(aggregated_files) or bool(copied_support_files)
    error_msg = ""
    if not ok:
        roots = manifest.get("extraction", {}).get("normalized_log_roots") or []
        error_msg = (
            "aggregated_files 与 copied_support_files 同时为空，没有任何日志可打包。"
            f" extraction.normalized_log_roots={len(roots)} 条；"
            "请检查：1) 该 issue 是否真的拿到了下载产物；"
            "2) 若是纯 trace 单，确认 ELT_HOME / NLT_HOME 已配置且 Step 7 没失败。"
        )
        logger.error("打包失败：%s", error_msg)

    return {
        "ok": ok,
        "error": error_msg,
        "final_log_root": final_root,
        "groups": final_groups,
        "aggregated_files": aggregated_files,
        "copied_support_files": copied_support_files,
    }


def main():
    configure_stdio()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    manifest = load_manifest(args.manifest)

    issue_key = (manifest.get("issue_key") or "unknown-issue").strip() or "unknown-issue"
    
    # 从 manifest 读取 workspace_root（已由 box-log-download 设置）
    # workspace_root 应该是 WORKSPACE_ROOT/{issue_key}
    workspace_root = manifest.get("workspace_root") or os.path.join(
        os.getenv("WORKSPACE_ROOT") or os.path.join(os.getcwd(), "data_store"),
        issue_key
    )
    
    # 统一输出到 issue 根下的 final_logs 子目录（可通过 --output-root 覆盖）
    final_root = args.output_root or os.path.join(workspace_root, "final_logs")
    final_root = os.path.abspath(final_root)
    os.makedirs(final_root, exist_ok=True)

    trace_groups = list(
        manifest.get("trace_exports", {}).get("raw_groups")
        or manifest.get("trace_exports", {}).get("groups")
        or []
    )
    normalized_roots = list(manifest.get("extraction", {}).get("normalized_log_roots") or [])
    if not normalized_roots:
        normalized_roots = sorted({item.get("normalized_root") for item in trace_groups if item.get("normalized_root")})

    resolve_destination = build_destination_resolver(issue_key, final_root)
    aggregated_files, final_groups = package_trace_export_groups(
        trace_groups, final_root, resolve_destination
    )

    copied_support_files = {}
    for normalized_root in normalized_roots:
        grouped_aplog = find_aplog_items_grouped(normalized_root)
        for group_rel, items in grouped_aplog.items():
            dest_dir = resolve_destination(normalized_root, group_rel)
            key = relative_key(final_root, dest_dir)
            entry = copied_support_files.setdefault(key, {})
            _copy_aplog_support_items(entry, items, dest_dir)

    main_logger = logging.getLogger("trace-aggregate-and-package")
    main_logger.info(
        "打包完成：aggregated_files=%d 组，copied_support_files=%d 组",
        len(aggregated_files), len(copied_support_files),
    )
    ok = bool(aggregated_files) or bool(copied_support_files)
    error_msg = ""
    if not ok:
        roots = manifest.get("extraction", {}).get("normalized_log_roots") or []
        error_msg = (
            "aggregated_files 与 copied_support_files 同时为空，没有任何日志可打包。"
            f" extraction.normalized_log_roots={len(roots)} 条。"
        )
        main_logger.error("打包失败：%s", error_msg)

    manifest["final_log_root"] = final_root
    if manifest["trace_exports"].get("results"):
        manifest["trace_exports"]["raw_results"] = manifest["trace_exports"]["results"]
    manifest["trace_exports"]["raw_groups"] = trace_groups
    manifest["trace_exports"]["aggregated_files"] = aggregated_files
    manifest["trace_exports"]["copied_support_files"] = copied_support_files
    manifest["trace_exports"]["groups"] = final_groups
    manifest["trace_exports"]["results"] = [
        {
            "issue_key": issue_key,
            "success": bool(final_groups),
            "packaged_count": len(final_groups),
        }
    ]

    result = {
        "ok": ok,
        "error": error_msg,
        "final_log_root": final_root,
        "groups": final_groups,
        "aggregated_files": aggregated_files,
        "copied_support_files": copied_support_files,
    }

    # 业务层失败：不写 manifest（避免污染契约），用退出码退出
    if not ok:
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    # ===== 落地相对路径 + 严格 schema 校验（契约的最后一道关卡） =====
    if args.manifest:
        finalize_and_validate(manifest, args.manifest)
        save_manifest(args.manifest, manifest)
        if not should_skip_download_cleanup():
            dlc = cleanup_download_residue(manifest)
            manifest.setdefault("trace_exports", {})["cleanup"] = dlc
            for row in manifest.get("trace_exports", {}).get("results") or []:
                if isinstance(row, dict):
                    row["cleanup"] = dlc
            save_manifest(args.manifest, manifest)
            main_logger.info(
                "已删除原始下载目录，removed=%s",
                dlc.get("removed_paths", []),
            )
        else:
            main_logger.info("保留 downloads/ 目录（PIPELINE_KEEP_LOCAL_FILES / SKIP_DOWNLOAD_CLEANUP）")
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

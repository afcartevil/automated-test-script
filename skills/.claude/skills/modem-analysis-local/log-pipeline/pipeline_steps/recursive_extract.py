import argparse
import bz2
import gzip
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections import deque
from copy import deepcopy
from datetime import datetime


DEFAULT_MANIFEST = {
    "downloads": {
        "download_dirs": [],
    },
    "extraction": {
        "output_root": "",
        "extracted_dirs": [],
        "results": [],
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
    data["_meta"] = {"updated_at": datetime.now().isoformat(timespec="seconds")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_7z():
    env_exe = os.environ.get("SEVEN_ZIP_EXE")
    if env_exe and os.path.exists(env_exe):
        return env_exe
    for name in ("7z", "7z.exe"):
        path = shutil.which(name)
        if path:
            return path
    for path in (
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Program Files\NanaZip\7z.exe",
    ):
        if os.path.exists(path):
            return path
    return None


def commonpath_safe(base_dir, target_path):
    try:
        return os.path.commonpath([base_dir, target_path])
    except ValueError:
        return ""


def safe_member_path(destination, member_name):
    destination = os.path.abspath(destination)
    target_path = os.path.abspath(os.path.join(destination, member_name))
    if commonpath_safe(destination, target_path) != destination:
        raise RuntimeError(f"检测到非法解压路径: {member_name}")
    return target_path


def safe_extract_zip(zf, destination):
    for member in zf.infolist():
        target_path = safe_member_path(destination, member.filename)
        if member.is_dir():
            os.makedirs(target_path, exist_ok=True)
            continue
        if member.flag_bits & 0x1:
            raise RuntimeError(f"zip 成员被加密，无法直接解压: {member.filename}")
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with zf.open(member, "r") as src, open(target_path, "wb") as dst:
            shutil.copyfileobj(src, dst)


def safe_extract_tar(tf, destination):
    for member in tf.getmembers():
        target_path = safe_member_path(destination, member.name)
        if member.isdir():
            os.makedirs(target_path, exist_ok=True)
            continue
        if not member.isfile():
            raise RuntimeError(f"tar 成员类型不支持: {member.name}")
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        extracted = tf.extractfile(member)
        if extracted is None:
            raise RuntimeError(f"无法读取 tar 成员: {member.name}")
        with extracted as src, open(target_path, "wb") as dst:
            shutil.copyfileobj(src, dst)


class StandaloneExtractor:
    def __init__(self):
        self.succeeded_files = []
        self.failed_files = []

    def is_compressed_file(self, path):
        lower = path.lower()
        return lower.endswith((".zip", ".tar", ".gz", ".bz2", ".tgz", ".tbz2", ".rar", ".7z"))

    def extract(self, input_path, output_dir=None, recursive=True):
        if os.path.isfile(input_path):
            return self.extract_single_file(input_path, output_dir)
        if not os.path.isdir(input_path):
            raise FileNotFoundError(f"路径不存在: {input_path}")

        file_list = deque()
        seen = set()
        for root, _, files in os.walk(input_path):
            for name in files:
                path = os.path.join(root, name)
                if self.is_compressed_file(path):
                    file_list.append(path)

        any_success = False
        while file_list:
            file_path = file_list.popleft()
            if file_path in seen:
                continue
            seen.add(file_path)
            if self.extract_single_file(file_path, output_dir):
                any_success = True
            if recursive:
                for root, _, files in os.walk(input_path):
                    for name in files:
                        nested = os.path.join(root, name)
                        if nested not in seen and nested not in file_list and self.is_compressed_file(nested):
                            file_list.append(nested)
        return any_success

    def extract_single_file(self, file_path, output_dir=None):
        destination = output_dir or os.path.dirname(file_path) or "."
        os.makedirs(destination, exist_ok=True)
        lower = file_path.lower()
        try:
            if lower.endswith(".zip"):
                with zipfile.ZipFile(file_path, "r") as zf:
                    safe_extract_zip(zf, destination)
            elif lower.endswith(".tar"):
                with tarfile.open(file_path, "r") as tf:
                    safe_extract_tar(tf, destination)
            elif lower.endswith((".tgz", ".tar.gz")):
                with tarfile.open(file_path, "r:gz") as tf:
                    safe_extract_tar(tf, destination)
            elif lower.endswith((".tbz2", ".tar.bz2")):
                with tarfile.open(file_path, "r:bz2") as tf:
                    safe_extract_tar(tf, destination)
            elif lower.endswith(".gz") and not lower.endswith(".tar.gz"):
                output_file = os.path.join(destination, os.path.basename(file_path)[:-3])
                with gzip.open(file_path, "rb") as src, open(output_file, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            elif lower.endswith(".bz2") and not lower.endswith(".tar.bz2"):
                output_file = os.path.join(destination, os.path.basename(file_path)[:-4])
                with bz2.open(file_path, "rb") as src, open(output_file, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            elif lower.endswith((".rar", ".7z")):
                seven_zip = find_7z()
                if not seven_zip:
                    raise RuntimeError("未找到 7z，可通过 SEVEN_ZIP_EXE 指定。")
                cmd = [seven_zip, "x", "-y", f"-o{destination}", file_path]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
                # 7z 可能因为文件属性设置失败返回非零，但文件已解压
                # 检查是否有 "Cannot set file attribute" 错误但没有其他严重错误
                if result.returncode != 0:
                    stderr_lower = result.stderr.lower()
                    stdout_lower = result.stdout.lower()
                    # 如果只是文件属性错误，忽略它
                    if "cannot set file attribute" in stderr_lower or "cannot set file attribute" in stdout_lower:
                        pass  # 忽略文件属性错误
                    else:
                        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "7z 解压失败")
            else:
                raise RuntimeError(f"不支持的压缩格式: {file_path}")
            self.succeeded_files.append(file_path)
            return True
        except Exception as e:
            # 打印错误信息用于调试
            print(f"解压失败: {file_path}", file=sys.stderr)
            print(f"错误: {e}", file=sys.stderr)
            self.failed_files.append(file_path)
            return False


def resolve_extracted_dir(abs_input, extractor):
    """
    确定可供后续筛选的目录根。

    有压缩包且至少解压成功一个时，使用下载/解压根目录；
    目录内无任何压缩包（已是文件夹日志）时，原样透传该目录。
    """
    if extractor.succeeded_files:
        return abs_input, True, False
    if extractor.succeeded_files or extractor.failed_files:
        return None, False, False
    if os.path.isdir(abs_input):
        return abs_input, True, True
    return None, False, False


def parse_args():
    parser = argparse.ArgumentParser(description="对日志下载目录执行递归解压。")
    parser.add_argument("--manifest", help="manifest 文件路径")
    parser.add_argument("--input-dir", action="append", dest="input_dirs", help="待解压目录，可重复传入")
    parser.add_argument("--output-root", help="统一输出目录，不传则在原目录解压")
    parser.add_argument("--no-recursive", action="store_true", help="关闭嵌套压缩包递归解压")
    parser.add_argument("--output", help="结果 JSON 输出路径；默认回写 manifest 或打印到 stdout")
    return parser.parse_args()


def recursive_extract_all(manifest_path):
    """
    递归解压所有压缩文件（供 pipeline 调用）
    
    Args:
        manifest_path: manifest 文件路径
    
    Returns:
        dict: 解压结果
    """
    configure_stdio()
    manifest = load_manifest(manifest_path)
    
    input_dirs = list(manifest.get("downloads", {}).get("download_dirs") or [])
    if not input_dirs:
        raise ValueError("没有可解压目录，请先执行下载步骤")
    
    recursive = True
    extracted_dirs = []
    results = []
    for input_dir in input_dirs:
        abs_input = os.path.abspath(input_dir)
        extractor = StandaloneExtractor()
        item = {
            "input_dir": abs_input,
            "output_root": "",
            "success": False,
            "succeeded_files": [],
            "failed_files": [],
        }
        try:
            item["success"] = bool(extractor.extract(abs_input, output_dir=None, recursive=recursive))
            item["succeeded_files"] = list(extractor.succeeded_files)
            item["failed_files"] = list(extractor.failed_files)
            resolved, ok, passthrough = resolve_extracted_dir(abs_input, extractor)
            if resolved:
                extracted_dirs.append(resolved)
                item["success"] = ok
                if passthrough:
                    item["passthrough"] = True
                    item["note"] = "无压缩包，使用下载目录作为日志根"
            if extractor.failed_files and not extractor.succeeded_files:
                item["error"] = "所有压缩文件均解压失败"
            elif extractor.failed_files:
                item["error"] = "部分压缩文件解压失败"
        except Exception as e:
            item["succeeded_files"] = list(extractor.succeeded_files)
            item["failed_files"] = list(extractor.failed_files)
            item["error"] = str(e)
        results.append(item)
    
    extracted_dirs = list(dict.fromkeys(extracted_dirs))
    return {"extracted_dirs": extracted_dirs, "results": results}


def main():
    configure_stdio()
    args = parse_args()
    manifest = load_manifest(args.manifest)

    input_dirs = list(args.input_dirs or manifest.get("downloads", {}).get("download_dirs") or [])
    if not input_dirs:
        raise SystemExit("没有可解压目录，请通过 --input-dir 或 manifest.downloads.download_dirs 提供。")

    recursive = not args.no_recursive
    extracted_dirs = []
    results = []
    for input_dir in input_dirs:
        abs_input = os.path.abspath(input_dir)
        extractor = StandaloneExtractor()
        item = {
            "input_dir": abs_input,
            "output_root": os.path.abspath(args.output_root) if args.output_root else "",
            "success": False,
            "succeeded_files": [],
            "failed_files": [],
        }
        try:
            item["success"] = bool(extractor.extract(abs_input, output_dir=args.output_root, recursive=recursive))
            item["succeeded_files"] = list(extractor.succeeded_files)
            item["failed_files"] = list(extractor.failed_files)
            resolved, ok, passthrough = resolve_extracted_dir(abs_input, extractor)
            if resolved:
                if args.output_root:
                    resolved = os.path.abspath(args.output_root)
                extracted_dirs.append(resolved)
                item["success"] = ok
                if passthrough:
                    item["passthrough"] = True
                    item["note"] = "无压缩包，使用下载目录作为日志根"
            if extractor.failed_files and not extractor.succeeded_files:
                item["error"] = "所有压缩文件均解压失败"
            elif extractor.failed_files:
                item["error"] = "部分压缩文件解压失败"
        except Exception as e:
            item["succeeded_files"] = list(extractor.succeeded_files)
            item["failed_files"] = list(extractor.failed_files)
            item["error"] = str(e)
        results.append(item)

    extracted_dirs = list(dict.fromkeys(extracted_dirs))
    manifest["extraction"]["output_root"] = os.path.abspath(args.output_root) if args.output_root else ""
    manifest["extraction"]["extracted_dirs"] = extracted_dirs
    manifest["extraction"]["results"] = results

    result = {"extracted_dirs": extracted_dirs, "results": results}
    if args.manifest:
        save_manifest(args.manifest, manifest)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

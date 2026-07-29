#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apk_repo_builder_final.py (with normalized artifact filenames and both sha256 + md5)

说明（设计原则）：
 - 仅依赖 apkutils2（必须已安装）。脚本直接调用 APK(...).get_manifest()，
   并按 manifest 字典的实际结构解析字段（不做猜测或回退）。
 - 支持 .apk 与 .xapk/.zip（xapk 解压后解析内部 apk 的 manifest）。
 - 通过扫描 APK zip 内的 lib/<abi>/ 目录来判定 ABIs（空列表表示 universal）。
 - 每个 package/version 生成 packages/<pkg>/<ver>/meta.json，并原子更新 global_index.json。
 - 不处理签名、不做上传。出现解析异常会直接抛出，方便定位问题。
 - 提供 select_best_apk_for_device(meta, device_abis) 帮助客户端选择二进制。
 - 归一化存储到 repo 的 artifact filename：以 package + version_code（并可附加 abi）为基础生成。
 - meta 中同时包含 content_sha256 与 content_md5，便于不同检验需求。
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
import glob
import zipfile
import re
from typing import List, Union

# 添加项目根目录到 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)


# 强制依赖 apkutils2
try:
    from apkutils2 import APK as APKParser
except Exception as e:
    raise RuntimeError("必须安装 apkutils2（pip install apkutils2）。脚本退出。") from e

try:
    # 执行apkutils2的猴子补丁，防止manifest解不出的情况
    from powertrde.utils.apkutils2_extends import apkutils2_patcher
    apkutils2_patcher.patch()
except Exception as e:
    print(f'执行apkutils2猴子补丁失败，将使用默认行为，原因：{e}')

PathLike = Union[str, Path]


# ---------------- helpers ----------------
def sha256_of_file(p: Path, chunk=8192):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def md5_of_file(p: Path, chunk=8192):
    h = hashlib.md5()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def atomic_write(path: Path, data: bytes):
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_atomic(path: Path, obj):
    atomic_write(path, json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8"))


# ---------------- safe filename utilities ----------------
_SAFE_RE = re.compile(r'[^A-Za-z0-9._+-]')


def _safe_filename(s: str, max_len: int = 200) -> str:
    """
    Replace unsafe characters with '_' and truncate to max_len.
    Keeps '.' and '-' and '+' and '_' allowed.
    Specifically replaces spaces with underscores.
    """
    if s is None:
        s = ""
    s = str(s)
    # First explicitly replace spaces with underscores
    s = s.replace(' ', '_')
    # Then replace any other unsafe characters with underscore
    s = _SAFE_RE.sub("_", s)
    if len(s) > max_len:
        s = s[:max_len]
    return s


def _build_apk_target_name(package: str, version_code: int, abis: list, orig_ext: str, sha256_hex: str) -> str:
    """
    Build normalized apk filename: {pkg}_{version}{_abis}.{ext}
    - If abis present -> append '_' + '+'.join(sorted(abis))
    - If conflict with existing different binary -> caller will append -conflict-<sha8>
    """
    pkg_safe = _safe_filename(package)
    verstr = str(version_code)
    ext = orig_ext if orig_ext.startswith(".") else f".{orig_ext}"
    if abis:
        # keep ABI order stable
        abis_sorted = sorted(abis)
        # join with '+' but safe it
        abis_part = "+".join([_safe_filename(a) for a in abis_sorted])
        base = f"{pkg_safe}_{verstr}_{abis_part}{ext}"
    else:
        base = f"{pkg_safe}_{verstr}{ext}"
    return base


def _build_xapk_target_name(package: str, version_code: int, sha256_hex: str) -> str:
    pkg_safe = _safe_filename(package)
    verstr = str(version_code)
    return f"{pkg_safe}_{verstr}.xapk"


# ---------------- parse manifest dict (strict) ----------------
def parse_manifest_dict(manifest: dict):
    """
    从 apkutils2.APK.get_manifest() 返回的 dict 中严格提取字段。
    要求 manifest 是 dict 且包含 '@package' 与 '@android:versionCode'（或 '@android:versionCode' 可转 int）。
    返回：
      {
        "package_name": str,
        "version_code": int,
        "version_name": str|None,
        "min_sdk": int|None,
        "target_sdk": int|None,
        "permissions": list[str]
      }
    若 manifest 结构不符合预期则抛异常。
    """
    if not isinstance(manifest, dict):
        raise RuntimeError("get_manifest() 未返回 dict 类型 manifest")

    pkg = manifest.get('@package')
    vercode = manifest.get('@android:versionCode') or manifest.get('@versionCode') or manifest.get('versionCode')
    vername = manifest.get('@android:versionName') or manifest.get('@versionName') or manifest.get('versionName')

    # uses-sdk 可能存在
    min_sdk = None
    target_sdk = None
    uses_sdk = manifest.get('uses-sdk') or manifest.get('uses_sdk') or manifest.get('usesSdk')
    if isinstance(uses_sdk, dict):
        min_sdk_raw = uses_sdk.get('@android:minSdkVersion') or uses_sdk.get('minSdkVersion') or uses_sdk.get('minSdk')
        target_sdk_raw = uses_sdk.get('@android:targetSdkVersion') or uses_sdk.get('targetSdkVersion') or uses_sdk.get(
            'targetSdk')
        try:
            min_sdk = int(min_sdk_raw) if min_sdk_raw is not None else None
        except:
            min_sdk = None
        try:
            target_sdk = int(target_sdk_raw) if target_sdk_raw is not None else None
        except:
            target_sdk = None

    # permissions: uses-permission 可以是 list 或 单个 dict
    perms_raw = manifest.get('uses-permission') or manifest.get('uses_permission') or manifest.get('uses-permissions')
    permissions = []
    if perms_raw:
        if isinstance(perms_raw, list):
            for item in perms_raw:
                if isinstance(item, dict):
                    name = item.get('@android:name') or item.get('name') or item.get('@name')
                    if name:
                        permissions.append(name)
                elif isinstance(item, str):
                    permissions.append(item)
        elif isinstance(perms_raw, dict):
            name = perms_raw.get('@android:name') or perms_raw.get('name') or perms_raw.get('@name')
            if name:
                permissions.append(name)
        elif isinstance(perms_raw, str):
            permissions.append(perms_raw)

    # normalize and validate
    if pkg is None:
        raise RuntimeError("manifest 缺少 '@package' 字段")
    if vercode is None:
        raise RuntimeError("manifest 缺少 '@android:versionCode' 字段")
    # versionCode 可能是字符串，尽量转 int
    try:
        vercode = int(vercode)
    except:
        # 尝试去掉非数字再转
        digits = re.sub(r'\D', '', str(vercode))
        if digits:
            vercode = int(digits)
        else:
            raise RuntimeError(f"无法解析 versionCode: {vercode}")

    return {
        "package_name": pkg,
        "version_code": vercode,
        "version_name": vername,
        "min_sdk": min_sdk,
        "target_sdk": target_sdk,
        "permissions": permissions
    }


# ---------------- ABI 检测 ----------------
def detect_abis_from_apk(apk_path: Path):
    """
    通过 zipfile 列出 lib/<abi>/ 来检测 abi。
    返回 sorted list，如 [] 表示无 native 库（universal）。
    """
    abis = set()
    try:
        with zipfile.ZipFile(apk_path, 'r') as z:
            for name in z.namelist():
                if name.startswith("lib/") and name.count("/") >= 2:
                    # lib/<abi>/...
                    parts = name.split("/")
                    if len(parts) >= 2 and parts[1]:
                        abis.add(parts[1])
    except Exception:
        pass
    return sorted(abis)


# ---------------- repo 布局及索引 ----------------
def ensure_repo_layout(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    (root / "packages").mkdir(parents=True, exist_ok=True)
    if (root / "global_index.json").exists() is False:
        save_json_atomic(root / "global_index.json", {"generated_at": None, "apps": []})


def update_global_index(repo_root: Path, package_name: str, version_code: int, version_name: str, meta_rel_url: str,
                        dry_run=False):
    idx_path = repo_root / "global_index.json"
    idx: dict = load_json(idx_path) or {"generated_at": None, "apps": []}
    found = None
    for a in idx["apps"]:
        if a.get("package_name") == package_name:
            found = a
            break
    if found:
        try:
            if int(version_code) >= int(found.get("latest_version_code", -1)):
                found["latest_version_code"] = int(version_code)
                found["version_name"] = version_name
                found["meta_url"] = meta_rel_url
        except:
            found["latest_version_code"] = int(version_code)
            found["version_name"] = version_name
            found["meta_url"] = meta_rel_url
    else:
        idx["apps"].append({
            "package_name": package_name,
            "latest_version_code": int(version_code),
            "version_name": version_name,
            "meta_url": meta_rel_url
        })
    idx["generated_at"] = datetime.utcnow().isoformat() + "Z"
    if dry_run:
        print("[dry-run] would update global_index:", json.dumps(idx, indent=2, ensure_ascii=False))
    else:
        save_json_atomic(idx_path, idx)
        print("global_index updated:", idx_path)


# ---------------- 选择器：按设备 ABI 选最合适 ----------------
def select_best_apk_for_device(meta: dict, device_abis: list):
    """
    device_abis: 优先级有序列表，例如 ["arm64-v8a","armeabi-v7a"]
    返回 None 或者 dict:
      { "container_type": "apk"|"xapk",
        "container_filename": "<filename>",
        "selected": <file dict or contained_apk dict> }
    逻辑：
      - apk: 如果 meta.file.abis 为空 -> universal -> 可用；否则按 device_abis 顺序匹配。
      - xapk: 优先按 device_abis 在 contained_apks 中找完全匹配；然后找任意交集；再找 base.apk；最后回退第一个。
    """
    file_info = meta.get("file", {})
    ctype = file_info.get("type")
    if ctype == "apk":
        abis = file_info.get("abis") or meta.get("abis") or []
        if not abis:  # universal
            return {"container_type": "apk", "container_filename": file_info.get("filename"), "selected": file_info}
        for d in device_abis:
            if d in abis:
                return {"container_type": "apk", "container_filename": file_info.get("filename"), "selected": file_info}
        return None
    elif ctype == "xapk":
        contained = file_info.get("contained_apks", []) or []
        for d in device_abis:
            for c in contained:
                if d in (c.get("abis") or []):
                    return {"container_type": "xapk", "container_filename": file_info.get("filename"), "selected": c}
        for c in contained:
            if set(c.get("abis") or []) & set(device_abis):
                return {"container_type": "xapk", "container_filename": file_info.get("filename"), "selected": c}
        for c in contained:
            if c.get("filename", "").lower().endswith("base.apk"):
                return {"container_type": "xapk", "container_filename": file_info.get("filename"), "selected": c}
        if contained:
            return {"container_type": "xapk", "container_filename": file_info.get("filename"), "selected": contained[0]}
        return None
    else:
        return None


# ---------------- 处理单个 APK ----------------
def process_apk_file(apk_path: Path, repo_root: Path, uploader: str, move_files: bool, dry_run: bool,
                     release_channel: str):
    # 使用 apkutils2 严格获取 manifest dict
    apk = APKParser(str(apk_path))
    manifest = apk.get_manifest()
    if not isinstance(manifest, dict):
        raise RuntimeError("APK.get_manifest() 未返回 dict，无法解析。")

    info = parse_manifest_dict(manifest)
    pkg = info["package_name"]
    vercode = info["version_code"]
    vername = info.get("version_name") or ""

    pkg_dir = repo_root / "packages" / pkg / str(vercode)
    pkg_dir.mkdir(parents=True, exist_ok=True)

    file_sha = sha256_of_file(apk_path)
    file_md5 = md5_of_file(apk_path)
    size = apk_path.stat().st_size
    abis = detect_abis_from_apk(apk_path)

    # build normalized filename
    orig_ext = apk_path.suffix.lower() or ".apk"
    target_name = _build_apk_target_name(pkg, vercode, abis, orig_ext, file_sha)
    target_apk = pkg_dir / target_name

    # handle existing file
    if target_apk.exists():
        existing_sha = sha256_of_file(target_apk)
        if existing_sha == file_sha:
            print("已存在且相同，跳过：", target_apk)
            meta_path = pkg_dir / "meta.json"
            if meta_path.exists():
                return {"skipped": True}
        else:
            # conflict -> append conflict suffix to preserve both
            conflict_name = f"{apk_path.stem}-conflict-{file_sha[:8]}{orig_ext}"
            target_apk = pkg_dir / conflict_name
            print("警告：相同 package/version 但二进制不同，保存为:", target_apk)

    # copy/move into repo
    if dry_run:
        print(f"[dry-run] 将 {'移动' if move_files else '复制'} {apk_path} -> {target_apk}")
    else:
        if move_files:
            shutil.move(str(apk_path), str(target_apk))
        else:
            shutil.copy2(str(apk_path), str(target_apk))
        print("保存 apk ->", target_apk)

    # write normalized meta (now includes both sha256 + md5)
    meta = {
        "package_name": pkg,
        "version_code": int(vercode),
        "version_name": vername,
        "file": {
            "type": "apk",
            "filename": target_apk.name,
            "content_sha256": file_sha,
            "content_md5": file_md5,
            "size": size,
            "abis": abis
        },
        "abis": sorted(list(set(abis))),
        "min_sdk": info.get("min_sdk"),
        "target_sdk": info.get("target_sdk"),
        "permissions": info.get("permissions", []),
        "uploaded_by": uploader,
        "generated_time": datetime.utcnow().isoformat() + "Z",
        "release_channel": release_channel,
        "notes": ""
    }

    meta_path = pkg_dir / "meta.json"
    if dry_run:
        print("[dry-run] meta 将写入：", json.dumps(meta, indent=2, ensure_ascii=False))
    else:
        save_json_atomic(meta_path, meta)
        print("wrote meta:", meta_path)

    meta_rel = f"/packages/{pkg}/{vercode}/meta.json"
    update_global_index(repo_root, pkg, vercode, vername, meta_rel, dry_run=dry_run)
    return {"skipped": False}


# ---------------- 处理 XAPK（zip） ----------------
def process_xapk_file(xapk_path: Path, repo_root: Path, uploader: str, move_files: bool, dry_run: bool,
                      release_channel: str):
    if not zipfile.is_zipfile(xapk_path):
        raise RuntimeError(f"xapk 不是合法 ZIP: {xapk_path}")

    with tempfile.TemporaryDirectory() as td:
        td_p = Path(td)
        with zipfile.ZipFile(xapk_path, 'r') as z:
            z.extractall(td_p)
        apks = list(td_p.rglob("*.apk"))
        if not apks:
            raise RuntimeError(f"xapk 内未找到 apk: {xapk_path}")

        contained = []
        rep_pkg = None
        rep_ver = None
        rep_vername = ""

        for apk_inside in apks:
            apk_obj = APKParser(str(apk_inside))
            manifest = apk_obj.get_manifest()
            if not isinstance(manifest, dict):
                # 记录但不致命
                sha = sha256_of_file(apk_inside)
                md5 = md5_of_file(apk_inside)
                contained.append({
                    "filename": str(apk_inside.relative_to(td_p)).replace("\\", "/"),
                    "package_name": None,
                    "version_code": None,
                    "version_name": None,
                    "content_sha256": sha,
                    "content_md5": md5,
                    "abis": [],
                    "note": "manifest_not_dict"
                })
                continue
            try:
                info = parse_manifest_dict(manifest)
                pkg = info["package_name"]
                ver = info["version_code"]
                vname = info.get("version_name") or ""
                sha = sha256_of_file(apk_inside)
                md5 = md5_of_file(apk_inside)
                abis = detect_abis_from_apk(apk_inside)
                contained.append({
                    "filename": str(apk_inside.relative_to(td_p)).replace("\\", "/"),
                    "package_name": pkg,
                    "version_code": int(ver) if ver is not None else None,
                    "version_name": vname,
                    "content_sha256": sha,
                    "content_md5": md5,
                    "abis": abis
                })
                if rep_pkg is None:
                    rep_pkg = pkg
                    rep_ver = ver
                    rep_vername = vname
            except Exception as e:
                sha = sha256_of_file(apk_inside)
                md5 = md5_of_file(apk_inside)
                contained.append({
                    "filename": str(apk_inside.relative_to(td_p)).replace("\\", "/"),
                    "package_name": None,
                    "version_code": None,
                    "version_name": None,
                    "content_sha256": sha,
                    "content_md5": md5,
                    "abis": [],
                    "note": f"parse_error: {e}"
                })
                if rep_pkg is None:
                    rep_pkg = None

        # 选择包目录
        if rep_pkg is None or rep_ver is None:
            fallback_pkg = "unknown_xapk"
            fallback_ver = int(datetime.utcnow().timestamp())
            pkg_dir = repo_root / "packages" / fallback_pkg / str(fallback_ver)
            print(f"警告: 无法确定代表 package/version，使用回退 {fallback_pkg}/{fallback_ver}")
        else:
            pkg_dir = repo_root / "packages" / rep_pkg / str(rep_ver)
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # normalized xapk filename
        file_sha = sha256_of_file(xapk_path)
        file_md5 = md5_of_file(xapk_path)
        size = xapk_path.stat().st_size
        if rep_pkg is None or rep_ver is None:
            # name using fallback
            target_xapk = pkg_dir / xapk_path.name
        else:
            target_name = _build_xapk_target_name(rep_pkg, rep_ver, file_sha)
            target_xapk = pkg_dir / target_name

        if target_xapk.exists():
            existing_sha = sha256_of_file(target_xapk)
            if existing_sha == file_sha:
                print("已存在且相同 xapk，跳过：", target_xapk)
                meta_path = pkg_dir / "meta.json"
                if meta_path.exists():
                    return {"skipped": True}
            else:
                conflict_name = f"{xapk_path.stem}-conflict-{file_sha[:8]}{xapk_path.suffix}"
                target_xapk = pkg_dir / conflict_name
                print("警告：相同 package/version 但 xapk 不同，保存为:", target_xapk)

        if dry_run:
            print(f"[dry-run] 将 {'移动' if move_files else '复制'} {xapk_path} -> {target_xapk}")
        else:
            if move_files:
                shutil.move(str(xapk_path), str(target_xapk))
            else:
                shutil.copy2(str(xapk_path), str(target_xapk))
            print("保存 xapk ->", target_xapk)

        available_abis = sorted(list({abi for c in contained for abi in (c.get("abis") or [])}))

        meta = {
            "package_name": rep_pkg if rep_pkg is not None else "unknown_xapk",
            "version_code": int(rep_ver) if rep_ver is not None else None,
            "version_name": rep_vername if rep_ver is not None else "",
            "file": {
                "type": "xapk",
                "filename": target_xapk.name,
                "content_sha256": file_sha,
                "content_md5": file_md5,
                "size": size,
                "contained_apks": contained
            },
            "available_abis": available_abis,
            "uploaded_by": uploader,
            "generated_time": datetime.utcnow().isoformat() + "Z",
            "release_channel": release_channel,
            "notes": "xapk 原样保留；contained_apks 提供内部 apk 信息"
        }

        meta_path = pkg_dir / "meta.json"
        if dry_run:
            print("[dry-run] meta 将写入：", json.dumps(meta, indent=2, ensure_ascii=False))
        else:
            save_json_atomic(meta_path, meta)
            print("wrote meta:", meta_path)

        if rep_pkg and rep_ver is not None:
            meta_rel = f"/packages/{rep_pkg}/{rep_ver}/meta.json"
            update_global_index(repo_root, rep_pkg, rep_ver, rep_vername, meta_rel, dry_run=dry_run)
        else:
            meta_rel = f"/packages/unknown_xapk/{pkg_dir.name}/meta.json"
            update_global_index(repo_root, "unknown_xapk", int(pkg_dir.name), rep_vername, meta_rel, dry_run=dry_run)

        return {"skipped": False}


# ---------------- import_files high-level helper (keeps compatibility) ----------------
def import_files(paths: Union[str, Path, List[Union[str, Path]]],
                 repo_root: Path,
                 uploader: str = "unknown",
                 move_files: bool = False,
                 dry_run: bool = False,
                 release_channel: str = "stable") -> dict:
    """
    批量导入文件到 repo 的高层函数（兼容旧接口）。
    """
    # normalize to list of strings
    if isinstance(paths, (str, Path)):
        path_list = [paths]
    else:
        path_list = list(paths)

    # expand globs and directories
    candidates: List[Path] = []
    for p in path_list:
        p = str(p)
        # glob
        matched = glob.glob(p)
        if matched:
            for m in matched:
                mp = Path(m)
                if mp.is_dir():
                    # recursively find .apk/.xapk/.zip
                    for ext in ("**/*.apk", "**/*.xapk", "**/*.zip"):
                        for found in mp.glob(ext):
                            candidates.append(found)
                else:
                    candidates.append(mp)
        else:
            mp = Path(p)
            if mp.exists() and mp.is_dir():
                for ext in ("**/*.apk", "**/*.xapk", "**/*.zip"):
                    for found in mp.glob(ext):
                        candidates.append(found)
            else:
                candidates.append(mp)

    # de-duplicate while preserving order
    seen = set()
    uniq_candidates: List[Path] = []
    for c in candidates:
        try:
            key = str(c.resolve())
        except Exception:
            key = str(c)
        if key in seen:
            continue
        seen.add(key)
        uniq_candidates.append(c)

    total = len(uniq_candidates)
    imported = 0
    skipped = 0
    errors = 0
    details: List[dict] = []

    for p in uniq_candidates:
        entry = {"path": str(p), "result": None, "error": None}
        if not p.exists():
            entry["error"] = "not_found"
            errors += 1
            details.append(entry)
            continue
        try:
            suf = p.suffix.lower()
            if suf == ".apk":
                res = process_apk_file(p, repo_root, uploader, move_files, dry_run, release_channel)
            elif suf in (".xapk", ".zip"):
                res = process_xapk_file(p, repo_root, uploader, move_files, dry_run, release_channel)
            else:
                # skip unknown extensions
                entry["error"] = f"unsupported_extension:{suf}"
                errors += 1
                details.append(entry)
                continue

            entry["result"] = res
            # determine counters by returned dict (keeps compatibility with previous behavior)
            if isinstance(res, dict) and res.get("skipped"):
                skipped += 1
            else:
                imported += 1
        except Exception as e:
            # record exception, but continue processing other files
            entry["error"] = f"{type(e).__name__}: {e}"
            errors += 1
        details.append(entry)

    return {
        "total": total,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "details": details
    }

# ---------------- Rebuild ----------------


def rebuild_global_index(repo_root: PathLike, dry_run: bool = False, verbose: bool = False) -> dict:
    """
    Rebuild global_index.json by scanning repo_root/packages/*/*/meta.json.

    Behavior:
      - Scan all meta.json files under <repo_root>/packages/*/*/meta.json.
      - For each valid meta, extract package_name (meta["package_name"]) and version_code (meta["version_code"]).
        version_code will be converted to int when possible. If conversion fails, the entry is skipped.
      - For each package, keep the entry with the highest numeric version_code as the 'latest'.
      - Compose global_index.json as:
            {"generated_at": <UTC ISO8601Z>, "apps": [
                {"package_name": "...", "latest_version_code": N, "version_name": "...", "meta_url": "/packages/<pkg>/<ver>/meta.json"},
                ...
            ]}
      - Write atomically to <repo_root>/global_index.json (unless dry_run=True).
      - Returns a summary dict: {scanned, kept_packages, skipped_meta_count, errors: [...], written: bool}

    Args:
      repo_root: PathLike to repo root.
      dry_run: if True, do not actually write global_index.json (but return what would be written).
      verbose: if True, print progress and warnings.

    Returns:
      dict summary
    """
    repo_root_p = Path(repo_root).expanduser().resolve()
    packages_dir = repo_root_p / "packages"
    summary = {
        "repo_root": str(repo_root_p),
        "scanned_meta_count": 0,
        "kept_packages_count": 0,
        "skipped_meta_count": 0,
        "errors": [],
        "written": False,
        "generated_index": None
    }

    if not packages_dir.exists() or not packages_dir.is_dir():
        msg = f"packages directory not found: {packages_dir}"
        summary["errors"].append(msg)
        if verbose:
            print(msg)
        return summary

    # map package -> (version_code_int -> (version_name, meta_rel_path))
    pkg_map = {}

    # find all meta.json under packages/*/*/meta.json
    pattern = packages_dir.glob("*/*/meta.json")
    for meta_path in pattern:
        summary["scanned_meta_count"] += 1
        try:
            meta = load_json(meta_path)
            if not meta or not isinstance(meta, dict):
                summary["skipped_meta_count"] += 1
                if verbose:
                    print(f"skip non-dict meta: {meta_path}")
                continue

            pkg = meta.get("package_name") or meta.get("package")
            raw_ver = meta.get("version_code") or meta.get("version") or None
            ver_name = meta.get("version_name") or meta.get("versionName") or ""
            if pkg is None or raw_ver is None:
                # try infer version from directory name
                # meta_path -> .../packages/<pkg>/<ver>/meta.json
                parts = meta_path.parts
                # attempt to locate 'packages' index
                try:
                    idx = parts.index("packages")
                    pkg_dir = parts[idx + 1]
                    ver_dir = parts[idx + 2]
                    if pkg is None:
                        pkg = pkg_dir
                    if raw_ver is None:
                        raw_ver = ver_dir
                except Exception:
                    pass

            if pkg is None or raw_ver is None:
                summary["skipped_meta_count"] += 1
                if verbose:
                    print(f"skip meta missing package/version: {meta_path}")
                continue

            # normalize version_code -> int if possible
            ver_int = None
            try:
                ver_int = int(raw_ver)
            except Exception:
                # try extract digits fallback
                digits = re.sub(r'\D', '', str(raw_ver))
                if digits:
                    try:
                        ver_int = int(digits)
                    except Exception:
                        ver_int = None

            if ver_int is None:
                # cannot interpret version as int -> skip (we don't include non-int versions in index)
                summary["skipped_meta_count"] += 1
                if verbose:
                    print(f"skip meta with non-int version: {meta_path} (version='{raw_ver}')")
                continue

            # meta relative url (store as /packages/<pkg>/<ver>/meta.json)
            meta_rel_url = f"/packages/{pkg}/{ver_int}/meta.json"

            # register
            pkg_entry = pkg_map.setdefault(pkg, {})
            # if same version already present, keep the first or prefer one with meta file present (they are all meta files)
            if ver_int in pkg_entry:
                # duplicate same version: we won't replace but can note
                if verbose:
                    print(f"duplicate meta for {pkg}/{ver_int}: {meta_path} (existing: {pkg_entry[ver_int][1]})")
            else:
                pkg_entry[ver_int] = (ver_name or "", meta_rel_url)

        except Exception as e:
            summary["errors"].append(f"error parsing {meta_path}: {e}")
            if verbose:
                print(f"error parsing {meta_path}: {e}")

    # Build apps list choosing highest version per package
    apps = []
    for pkg, versions in pkg_map.items():
        try:
            if not versions:
                continue
            max_ver = max(versions.keys())
            vername, meta_rel = versions[max_ver]
            apps.append({
                "package_name": pkg,
                "latest_version_code": int(max_ver),
                "version_name": vername,
                "meta_url": meta_rel
            })
        except Exception as e:
            summary["errors"].append(f"error choosing latest for {pkg}: {e}")
            if verbose:
                print(f"error choosing latest for {pkg}: {e}")

    # sort apps by package_name for deterministic output
    apps = sorted(apps, key=lambda x: x.get("package_name") or "")

    generated = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "apps": apps
    }

    summary["kept_packages_count"] = len(apps)
    summary["generated_index"] = generated

    # write atomic if not dry_run
    out_path = repo_root_p / "global_index.json"
    if dry_run:
        if verbose:
            print("[dry-run] would write global_index.json with %d apps" % len(apps))
        summary["written"] = False
        return summary

    try:
        save_json_atomic(out_path, generated)
        summary["written"] = True
        if verbose:
            print("global_index.json rebuilt at", out_path)
    except Exception as e:
        summary["errors"].append(f"write_failed: {e}")
        summary["written"] = False
        if verbose:
            print("failed to write global_index.json:", e)

    return summary


# ---------------- CLI 入口 ----------------
def main(argv=None):
    parser = argparse.ArgumentParser(prog="apk_repo_builder_final", description="Build a simple APK/XAPK repo layout")
    parser.add_argument("--repo", required=True, help="repo root path")
    parser.add_argument("--uploader", default="unknown", help="uploader identity")
    parser.add_argument("--move", action="store_true", help="move files instead of copying")
    parser.add_argument("--dry-run", action="store_true", help="dry run")
    parser.add_argument("--release-channel", default="stable", help="release channel name")
    parser.add_argument("inputs", nargs="+", help="APK/XAPK files or glob patterns")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo).expanduser().resolve()
    ensure_repo_layout(repo_root)

    # expand inputs (globs)
    inputs = []
    for i in args.inputs:
        matched = glob.glob(i)
        if matched:
            inputs.extend(matched)
        else:
            inputs.append(i)

    summary = import_files(inputs, repo_root, uploader=args.uploader,
                           move_files=args.move, dry_run=args.dry_run,
                           release_channel=args.release_channel)
    print("Import summary:", json.dumps(summary, indent=2, ensure_ascii=False))


def get_apk_files(folder_path):
    """
    从指定文件夹递归查找所有 .apk 和 .xapk 文件，并返回 Python 格式的列表
    :param folder_path: 要扫描的文件夹路径
    :return: 文件路径列表（格式：r"E:\..."）
    """
    if not os.path.isdir(folder_path):
        print("❌ 路径不存在，请确认路径是否正确！")
        return []

    files = []
    for root, dirs, filenames in os.walk(folder_path):
        for filename in filenames:
            if filename.lower().endswith(('.apk', '.xapk')):
                full_path = os.path.join(root, filename)
                files.append(rf"{full_path}")

    # 按文件名排序
    files.sort(key=lambda x: os.path.basename(x).lower())
    return files


if __name__ == "__main__":
    # main()
    # files = [
    #     r'D:\apks\general_phonemonitor.apk',
    #     r'D:\apks\Linsoc.apk',
    #     r'D:\apks\VPN.apk',
    # ]
    files = [r'D:\apks\APKPure_3.20.51_apkpure.com.apk']
    # files = get_apk_files(r'E:\Desktop\project\dz_auto_env\zxc\pulled_apks')
    _repo_root = r'D:\apks\app_repo'
    import_files(files, Path(_repo_root), 'xingzhi.chen', False, False, 'A1')
    #rebuild_global_index(Path(_repo_root))

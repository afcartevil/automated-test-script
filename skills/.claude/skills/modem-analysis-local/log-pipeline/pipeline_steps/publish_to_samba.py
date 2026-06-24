#!/usr/bin/env python3
"""
publish_to_samba.py
Step 9: 将 {WORKSPACE_ROOT}\\{issue_key}\\ 打成 zip，上传到团队 Samba 的日期子目录。

远端布局（相对共享根）：
  {SMB_REMOTE_SUBPATH}/{YYYY-MM-DD}/{issue_key}.zip
  例：通信开发部/AI2D-log/2026-05-22/OS162-37733.zip

设计要点：
  - 仅在 Windows 上执行（依赖 net.exe / robocopy.exe）。
  - 密码只通过 subprocess 参数传给 net use，不打日志，也不写中间脚本文件。
  - robocopy 退出码 0-7 视为成功（8+ 才算失败）。
  - 发布结果写回 manifest._meta.phase1_smb_publish；Jira 评论携带 smb_zip_rel 供 Phase 2 解析。
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# 引入 _shared 与同目录 recursive_extract
_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
_PIPELINE_DIR = Path(__file__).resolve().parent
for _p in (_SHARED_DIR, _PIPELINE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from modem_analysis_runtime import load_manifest, save_manifest  # noqa: E402
from recursive_extract import find_7z  # noqa: E402

try:
    from dotenv import load_dotenv
    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
except ImportError:
    pass


def _envstr(name, default=""):
    return (os.getenv(name) or default).strip()


def _envbool(name, default=False):
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "y", "on")


def _publish_date_str() -> str:
    """发布目录使用的日期，默认当天 YYYY-MM-DD。"""
    override = _envstr("SMB_PUBLISH_DATE")
    if override:
        return override
    return datetime.now().strftime("%Y-%m-%d")


def build_smb_zip_rel(subpath: str, date_str: str, issue_key: str) -> str:
    """Samba 共享内相对路径（正斜杠），供 Jira 评论与 Phase 2 解析。"""
    parts = []
    sub = (subpath or "").strip().strip("/\\")
    if sub:
        parts.append(sub.replace("\\", "/"))
    parts.append(date_str)
    parts.append(f"{issue_key}.zip")
    return "/".join(parts)


def _build_unc_zip(host, share, subpath, date_str, issue_key):
    """拼出 \\HOST\\SHARE\\SUBPATH\\DATE\\ISSUE_KEY.zip"""
    parts = [f"\\\\{host}\\{share}"]
    sub = (subpath or "").strip().strip("\\/").replace("/", "\\")
    if sub:
        parts.append(sub)
    parts.append(date_str)
    parts.append(f"{issue_key}.zip")
    return "\\".join(parts)


def _build_unc_date_dir(host, share, subpath, date_str):
    """拼出日期目录 UNC，用于 robocopy 目标。"""
    parts = [f"\\\\{host}\\{share}"]
    sub = (subpath or "").strip().strip("\\/").replace("/", "\\")
    if sub:
        parts.append(sub)
    parts.append(date_str)
    return "\\".join(parts)


def _net_use_connect(unc_share, username, password):
    r"""建立 SMB 会话。unc_share 形如 \\HOST\SHARE（不含子目录）。失败抛异常。"""
    subprocess.run(
        ["net", "use", unc_share, "/delete", "/y"],
        capture_output=True, check=False,
    )
    cmd = ["net", "use", unc_share, password, f"/user:{username}", "/persistent:no"]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        err = _decode_robocopy_output(proc.stderr) or _decode_robocopy_output(proc.stdout)
        raise RuntimeError(
            f"net use 连接失败 (exit={proc.returncode}): {err.strip()}"
        )


def _net_use_disconnect(unc_share):
    subprocess.run(
        ["net", "use", unc_share, "/delete", "/y"],
        capture_output=True, check=False,
    )


def _decode_robocopy_output(raw_bytes):
    if not raw_bytes:
        return ""
    candidates = []
    if sys.platform == "win32":
        candidates = ["mbcs", "gbk", "utf-8"]
    else:
        candidates = ["utf-8", "gbk", "mbcs"]
    for enc in candidates:
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def _robocopy_file(local_zip: Path, unc_date_dir: str):
    """将单个 zip 复制到远端日期目录。"""
    cmd = [
        "robocopy",
        str(local_zip.parent),
        unc_date_dir,
        local_zip.name,
        "/Z",
        "/R:2",
        "/W:5",
        "/NP",
        "/NFL",
        "/NDL",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    exit_code = proc.returncode
    ok = exit_code < 8
    stdout_text = _decode_robocopy_output(proc.stdout)
    tail = ("\n".join(stdout_text.splitlines()[-12:])).strip()
    return exit_code, ok, tail


def _create_issue_zip(local_dir: Path, issue_key: str, logger_print=print) -> Path:
    """把 issue 工作目录打成 zip，返回 zip 绝对路径。"""
    tmp_root = Path(tempfile.mkdtemp(prefix=f"publish_{issue_key}_"))
    zip_path = tmp_root / f"{issue_key}.zip"
    seven = find_7z()
    if seven:
        cmd = [seven, "a", "-tzip", "-mx=1", str(zip_path), str(local_dir) + os.sep]
        logger_print(f"[publish] 7z 打包: {' '.join(cmd[:4])} ...")
        proc = subprocess.run(cmd, capture_output=True, check=False)
        if proc.returncode != 0 and not zip_path.is_file():
            err = _decode_robocopy_output(proc.stderr) or _decode_robocopy_output(proc.stdout)
            shutil.rmtree(tmp_root, ignore_errors=True)
            raise RuntimeError(f"7z 打包失败 (exit={proc.returncode}): {err.strip()[:500]}")
    else:
        logger_print("[publish] 未找到 7z，使用 shutil.make_archive")
        base = tmp_root / issue_key
        archive_base = str(base)
        shutil.make_archive(archive_base, "zip", root_dir=str(local_dir.parent), base_dir=local_dir.name)
        built = Path(archive_base + ".zip")
        if built != zip_path:
            if zip_path.is_file():
                zip_path.unlink()
            built.rename(zip_path)

    if not zip_path.is_file():
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise RuntimeError(f"打包后 zip 不存在: {zip_path}")
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    logger_print(f"[publish] zip 就绪: {zip_path} ({size_mb:.1f} MB)")
    return zip_path


def publish_issue_to_samba(manifest_path):
    """
    返回 dict:
      {
        "enabled": bool,
        "skipped": bool,
        "ok": bool,
        "unc_base": str,          # zip 文件完整 UNC
        "smb_zip_rel": str,       # 共享内相对路径（正斜杠）
        "publish_date": str,
        "robocopy_exit": int | None,
        "message": str,
      }
    """
    enabled = _envbool("SMB_PUBLISH_ENABLED", True)
    required = _envbool("SMB_PUBLISH_REQUIRED", False)

    manifest = load_manifest(manifest_path)
    issue_key = manifest.get("issue_key") or ""
    if not issue_key:
        raise ValueError("manifest 缺少 issue_key，无法定位发布目录")

    local_dir = Path(manifest_path).resolve().parent
    if not local_dir.is_dir():
        raise FileNotFoundError(f"本地工作目录不存在: {local_dir}")

    result = {
        "enabled": enabled,
        "skipped": False,
        "ok": False,
        "unc_base": "",
        "smb_zip_rel": "",
        "publish_date": "",
        "robocopy_exit": None,
        "message": "",
        "required": required,
    }

    if not enabled:
        result["skipped"] = True
        result["ok"] = True
        result["message"] = "SMB_PUBLISH_ENABLED=0，已跳过"
        _write_back(manifest_path, manifest, result)
        return result

    if sys.platform != "win32":
        result["message"] = f"非 Windows 平台 ({sys.platform})，跳过 Samba 发布"
        result["skipped"] = True
        result["ok"] = not required
        _write_back(manifest_path, manifest, result)
        return result

    host = _envstr("SMB_HOST")
    share = _envstr("SMB_SHARE")
    subpath = _envstr("SMB_REMOTE_SUBPATH")
    username = _envstr("SMB_USERNAME")
    password = os.getenv("SMB_PASSWORD") or ""
    date_str = _publish_date_str()
    result["publish_date"] = date_str
    result["smb_zip_rel"] = build_smb_zip_rel(subpath, date_str, issue_key)

    missing = [k for k, v in [
        ("SMB_HOST", host), ("SMB_SHARE", share),
        ("SMB_USERNAME", username), ("SMB_PASSWORD", password),
    ] if not v]
    if missing:
        result["message"] = f"缺少 .env 配置: {', '.join(missing)}"
        result["ok"] = not required
        _write_back(manifest_path, manifest, result)
        return result

    unc_share = f"\\\\{host}\\{share}"
    unc_zip = _build_unc_zip(host, share, subpath, date_str, issue_key)
    unc_date_dir = _build_unc_date_dir(host, share, subpath, date_str)
    result["unc_base"] = unc_zip

    print(f"[publish] local dir: {local_dir}")
    print(f"[publish] remote zip: {unc_zip}")
    print(f"[publish] smb rel: {result['smb_zip_rel']}")

    zip_path = None
    zip_tmp_parent = None
    try:
        zip_path = _create_issue_zip(local_dir, issue_key, print)
        zip_tmp_parent = zip_path.parent

        try:
            _net_use_connect(unc_share, username, password)
        except Exception as exc:
            result["message"] = str(exc)
            result["ok"] = not required
            _write_back(manifest_path, manifest, result)
            return result

        try:
            os.makedirs(unc_date_dir, exist_ok=True)
            exit_code, ok, tail = _robocopy_file(zip_path, unc_date_dir)
            result["robocopy_exit"] = exit_code
            result["ok"] = ok and Path(unc_zip).is_file()
            if not result["ok"] and ok:
                result["ok"] = True
                result["message"] = (
                    f"robocopy exit={exit_code} 但无法 stat 远端 zip（可能仍成功）\n--- tail ---\n{tail}"
                )
            else:
                result["message"] = (
                    f"robocopy zip upload exit={exit_code} ({'OK' if result['ok'] else 'FAIL'})\n--- tail ---\n{tail}"
                )
            print(result["message"])
        finally:
            _net_use_disconnect(unc_share)
    except Exception as exc:
        result["message"] = str(exc)[:2000]
        result["ok"] = not required
        _write_back(manifest_path, manifest, result)
        return result
    finally:
        if zip_tmp_parent and zip_tmp_parent.is_dir():
            shutil.rmtree(zip_tmp_parent, ignore_errors=True)

    result["published_at"] = datetime.now().isoformat(timespec="seconds")
    _write_back(manifest_path, manifest, result)

    if result.get("ok") and not result.get("skipped"):
        _maybe_jira_comment_after_publish(manifest_path, issue_key, result)

    return result


def _maybe_jira_comment_after_publish(manifest_path: str, issue_key: str, result: dict) -> None:
    """Samba 发布成功后，按 .env 可选向 Jira 追加评论，并把结果写回 manifest。"""
    project_root = Path(__file__).resolve().parent.parent
    try:
        from jira_post_publish_comment import post_jira_comment_after_publish
    except ImportError:
        print("[publish] jira_post_publish_comment 模块加载失败，跳过 Jira 评论", file=sys.stderr)
        return

    published_at = result.get("published_at") or ""
    mapping = {
        "issue_key": issue_key,
        "unc_base": result.get("unc_base", ""),
        "smb_zip_rel": result.get("smb_zip_rel", ""),
        "publish_date": result.get("publish_date", ""),
        "published_at": published_at,
        "robocopy_exit": str(result.get("robocopy_exit") if result.get("robocopy_exit") is not None else ""),
        "phase1_host": socket.gethostname(),
        "manifest_path": str(Path(manifest_path).resolve()),
        "robocopy_mode": "zip upload",
    }
    jc = post_jira_comment_after_publish(issue_key, mapping, project_root=project_root)
    if jc.get("skipped"):
        print(f"[publish] Jira 评论: 跳过 — {jc.get('reason', '')}")
    elif jc.get("posted"):
        print(f"[publish] Jira 评论已发布 comment_id={jc.get('comment_id')}")
    else:
        print(f"[publish] Jira 评论失败: {jc.get('error', 'unknown')}")

    manifest = load_manifest(manifest_path)
    meta = manifest.setdefault("_meta", {})
    smb = meta.setdefault("phase1_smb_publish", {})
    smb["jira_comment"] = jc
    save_manifest(manifest_path, manifest)


def _write_back(manifest_path, manifest, result):
    """把发布结果写回 manifest._meta.phase1_smb_publish。"""
    published_at = result.get("published_at")
    if not published_at:
        published_at = datetime.now().isoformat(timespec="seconds")
        result["published_at"] = published_at
    meta = manifest.setdefault("_meta", {})
    meta["phase1_smb_publish"] = {
        "unc_base":      result.get("unc_base", ""),
        "smb_zip_rel":   result.get("smb_zip_rel", ""),
        "publish_date":  result.get("publish_date", ""),
        "published_at":  published_at,
        "ok":            bool(result.get("ok")),
        "mode":          "zip upload",
        "robocopy_exit": result.get("robocopy_exit"),
        "message":       (result.get("message") or "")[:2000],
        "host":          socket.gethostname(),
    }
    save_manifest(manifest_path, manifest)


def main():
    parser = argparse.ArgumentParser(description="Step 9: 将 issue 目录打包为 zip 并发布到 Samba 日期目录")
    parser.add_argument("--manifest", required=True, help="job_manifest.json 绝对路径")
    args = parser.parse_args()

    result = publish_issue_to_samba(args.manifest)
    print(f"[publish] result: enabled={result['enabled']} skipped={result['skipped']} "
          f"ok={result['ok']} exit={result['robocopy_exit']} rel={result.get('smb_zip_rel', '')}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

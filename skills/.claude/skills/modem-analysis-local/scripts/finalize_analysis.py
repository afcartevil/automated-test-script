#!/usr/bin/env python3
"""finalize_analysis.py

分析完成后的收尾脚本，按序执行：
1. 更新飞书看板（AI 判定故障类型 / AI 分析状态 / AI 分析时间 / 最后更新时间）
2. 上传 job_manifest.json 到 NAS
3. 上传 skill 执行日志到 NAS
4. 删除本地 {issue_key}/ 目录及 {WORKSPACE_ROOT}/logs/{issue_key}/ 同步日志

NAS 目标路径：
    {SMB_REMOTE_SUBPATH}/job_manifest/{YYYY-MM-DD}/{issue_key}.json
    {SMB_REMOTE_SUBPATH}/job_manifest/{YYYY-MM-DD}/{issue_key}-skill.log

配置来源：<skill_root>/.env（WORKSPACE_ROOT, SMB_HOST, SMB_SHARE, SMB_USERNAME,
           SMB_PASSWORD, SMB_REMOTE_SUBPATH, FEISHU_APP_ID, FEISHU_APP_SECRET）

用法：
    # Linux/macOS/容器
    PYTHONIOENCODING=utf-8 python scripts/finalize_analysis.py --manifest <MANIFEST_PATH>

    # Windows cmd
    set PYTHONIOENCODING=utf-8 && python scripts\\finalize_analysis.py --manifest <MANIFEST_PATH>

选项：
    --skip-upload   跳过 NAS 上传（仍更新飞书 + 删本地）
    --skip-delete   跳过本地目录删除（调试用）
    --skip-feishu   跳过飞书看板更新

Exit codes:
    0  成功
    1  SKILL_FAILED（manifest 不可读或关键字段缺失）
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

SCRIPT_DIR = Path(__file__).resolve().parent          # scripts/
SHARED_DIR = SCRIPT_DIR / "_shared"                   # scripts/_shared/
for _p in (str(SHARED_DIR), str(SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from skill_env import load_skill_env                  # scripts/_shared/skill_env.py

load_skill_env()

from feishu_dashboard_client import (                 # noqa: E402 — 须在 load_skill_env 之后
    DashboardField,
    map_l1_domain_to_ai_fault_type,
    upsert_dashboard_record,
)


# ---------------------------------------------------------------------------
# Logger（终端 + 追加写入 skill log）
# ---------------------------------------------------------------------------

def _create_logger(manifest_path: Path, issue_key: str) -> logging.Logger:
    logger = logging.getLogger("finalize_analysis")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    skill_log = manifest_path.parent / f"{issue_key}-skill.log"
    fh = logging.FileHandler(str(skill_log), encoding="utf-8", mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


# ---------------------------------------------------------------------------
# SMB 上传
# ---------------------------------------------------------------------------

def _smb_upload(
    local_path: Path,
    remote_rel: str,
    cfg: Dict[str, str],
    logger: logging.Logger,
) -> bool:
    """将本地文件上传到 NAS。优先 smbclient 命令，次选 smbprotocol Python 包。"""
    host = cfg["SMB_HOST"]
    share = cfg["SMB_SHARE"]
    user = cfg["SMB_USERNAME"]
    pwd = cfg["SMB_PASSWORD"]
    remote_dir = str(Path(remote_rel).parent).replace("\\", "/")

    # --- smbclient ---
    if shutil.which("smbclient"):
        def _run(cmds: str) -> bool:
            result = subprocess.run(
                ["smbclient", f"//{host}/{share}", "-U", f"{user}%{pwd}", "-c", cmds],
                capture_output=True, text=True, timeout=60,
            )
            return result.returncode == 0

        # 先建目录（忽略失败），再上传
        _run(f'mkdir "{remote_dir}"')
        if _run(f'put "{local_path}" "{remote_rel}"'):
            logger.info(f"[smbclient] 上传成功: {remote_rel}")
            return True
        logger.warning(f"[smbclient] 上传失败: {remote_rel}")

    # --- smbprotocol ---
    try:
        import smbclient as smbc  # type: ignore

        smbc.register_session(host, username=user, password=pwd)
        unc_dir = f"\\\\{host}\\{share}\\{remote_dir.replace('/', '\\')}"
        unc_file = f"\\\\{host}\\{share}\\{remote_rel.replace('/', '\\')}"
        try:
            smbc.makedirs(unc_dir, exist_ok=True)
        except Exception:
            pass
        with open(local_path, "rb") as lf, smbc.open_file(unc_file, mode="wb") as rf:
            rf.write(lf.read())
        logger.info(f"[smbprotocol] 上传成功: {remote_rel}")
        return True
    except ImportError:
        logger.error("smbclient 命令不可用且 smbprotocol 未安装，无法上传文件")
    except Exception as exc:
        logger.error(f"[smbprotocol] 上传失败: {exc}")
    return False


# ---------------------------------------------------------------------------
# 飞书看板更新
# ---------------------------------------------------------------------------

def _update_feishu(manifest: dict, logger: logging.Logger) -> None:
    issue_key = (manifest.get("issue_key") or "").strip()
    if not issue_key:
        logger.warning("manifest.issue_key 为空，跳过飞书看板更新")
        return

    primary_domain = (
        manifest.get("analysis", {}).get("l1_business", {}).get("primary_domain", "")
    )
    ai_fault_type = map_l1_domain_to_ai_fault_type(primary_domain)

    fields: Dict[str, object] = {
        DashboardField.JIRA_KEY: issue_key,
        DashboardField.AI_STATUS: "已分析",
        DashboardField.AI_ANALYSIS_TIME: datetime.now().isoformat(timespec="seconds"),
    }
    if ai_fault_type:
        fields[DashboardField.AI_FAULT_TYPE] = ai_fault_type

    logger.info(f"更新飞书看板: {issue_key}, 故障类型={ai_fault_type or '未知'}, 状态=已分析")
    result = upsert_dashboard_record(fields, touch_updated_at=True)

    if result.get("success"):
        logger.info(f"飞书看板更新成功: action={result.get('action')}, record_id={result.get('record_id')}")
    else:
        logger.warning(f"飞书看板更新失败（不阻塞后续流程）: {result.get('error')}")


# ---------------------------------------------------------------------------
# 本地清理（issue 目录 + sync 日志目录）
# ---------------------------------------------------------------------------

def _delete_local_issue_artifacts(
    issue_dir: Path,
    issue_key: str,
    logger: logging.Logger,
) -> None:
    """删除 {WORKSPACE_ROOT}/{issue_key}/ 与 {WORKSPACE_ROOT}/logs/{issue_key}/。"""
    workspace_root = issue_dir.parent
    sync_log_dir = workspace_root / "logs" / issue_key

    logger.info("删除本地分析目录: %s", issue_dir)
    if sync_log_dir.exists():
        logger.info("删除 sync 日志目录: %s", sync_log_dir)

    fin_logger = logging.getLogger("finalize_analysis")
    for h in list(fin_logger.handlers):
        h.flush()
        h.close()
        fin_logger.removeHandler(h)

    if issue_dir.exists():
        shutil.rmtree(issue_dir)
        print(f"[finalize] 本地分析目录已删除: {issue_dir}")

    if sync_log_dir.exists():
        shutil.rmtree(sync_log_dir)
        print(f"[finalize] sync 日志目录已删除: {sync_log_dir}")

    logs_root = workspace_root / "logs"
    if logs_root.is_dir() and not any(logs_root.iterdir()):
        logs_root.rmdir()
        print(f"[finalize] 已删除空的 logs 目录: {logs_root}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="分析收尾：飞书更新 + NAS 上传 + 本地清理")
    parser.add_argument("--manifest", required=True, help="job_manifest.json 文件路径")
    parser.add_argument("--skip-upload", action="store_true", help="跳过 NAS 上传")
    parser.add_argument("--skip-delete", action="store_true", help="跳过本地目录删除（调试用）")
    parser.add_argument("--skip-feishu", action="store_true", help="跳过飞书看板更新")
    return parser.parse_args()


def main() -> None:
    # stdout/stderr 强制 UTF-8
    for s in ("stdout", "stderr"):
        stream = getattr(sys, s, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    args = parse_args()
    manifest_path = Path(args.manifest).resolve()

    if not manifest_path.exists():
        print(f"SKILL_FAILED: manifest 文件不存在: {manifest_path}")
        sys.exit(1)

    try:
        with open(manifest_path, "r", encoding="utf-8-sig") as f:
            manifest = json.load(f)
    except Exception as exc:
        print(f"SKILL_FAILED: 无法解析 manifest: {exc}")
        sys.exit(1)

    issue_key = (manifest.get("issue_key") or "").strip()
    if not issue_key:
        print("SKILL_FAILED: manifest.issue_key 为空，无法继续")
        sys.exit(1)

    logger = _create_logger(manifest_path, issue_key)
    logger.info(f"=== finalize_analysis 开始: {issue_key} ===")

    issue_dir = manifest_path.parent
    skill_log_path = issue_dir / f"{issue_key}-skill.log"
    today_str = datetime.now().strftime("%Y-%m-%d")
    smb_subpath = (os.getenv("SMB_REMOTE_SUBPATH") or "").strip().rstrip("/")
    remote_base = f"{smb_subpath}/job_manifest/{today_str}"

    # 1. 飞书看板
    if not args.skip_feishu:
        _update_feishu(manifest, logger)

    # 2. NAS 上传
    if not args.skip_upload:
        cfg = {
            "SMB_HOST": (os.getenv("SMB_HOST") or "").strip(),
            "SMB_SHARE": (os.getenv("SMB_SHARE") or "").strip(),
            "SMB_USERNAME": (os.getenv("SMB_USERNAME") or "").strip(),
            "SMB_PASSWORD": (os.getenv("SMB_PASSWORD") or "").strip(),
        }
        if not all(cfg.values()):
            logger.warning("SMB 配置不完整（缺少 SMB_HOST/SHARE/USERNAME/PASSWORD），跳过 NAS 上传")
        else:
            logger.info(f"上传 manifest → NAS: {remote_base}/{issue_key}.json")
            _smb_upload(manifest_path, f"{remote_base}/{issue_key}.json", cfg, logger)

            if skill_log_path.exists():
                # 在上传 skill log 前先 flush 所有 handler
                for h in logging.getLogger("finalize_analysis").handlers:
                    h.flush()
                logger.info(f"上传 skill log → NAS: {remote_base}/{issue_key}-skill.log")
                _smb_upload(skill_log_path, f"{remote_base}/{issue_key}-skill.log", cfg, logger)
            else:
                logger.warning(f"skill 日志文件不存在，跳过上传: {skill_log_path}")

    # 3. 本地清理（issue 树 + logs/{issue_key}/，不删除整个 WORKSPACE_ROOT）
    if not args.skip_delete:
        try:
            _delete_local_issue_artifacts(issue_dir, issue_key, logger)
        except Exception as exc:
            print(f"[finalize] 删除本地目录失败（不阻塞流程）: {exc}")
    else:
        logger.info("--skip-delete: 保留本地分析目录与 logs/%s", issue_key)

    print(f"[finalize] 完成: {issue_key}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Samba 发布成功后，可选地向 Jira 单追加一条评论。

配置（.env）：
  JIRA_COMMENT_AFTER_PUBLISH=1
  JIRA_PUBLISH_COMMENT_TEMPLATE=templates/jira_publish_comment.template.txt

模板语法：Python string.Template，占位符形如 $issue_key、$unc_base（见示例模板）。
复用 JIRA_SERVER；若需 basic 认证则还需 JIRA_USERNAME / JIRA_PASSWORD。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from string import Template
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
except ImportError:
    pass


def _envbool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "y", "on")


def _envstr(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _create_jira_client(jira_server: str, jira_user: str = "", jira_pass: str = ""):
    from jira import JIRA

    server = (jira_server or "").strip()
    user = (jira_user or "").strip()
    password = jira_pass or ""
    if user and password:
        return JIRA(server=server, basic_auth=(user, password))
    return JIRA(server=server)


def _resolve_template_path(raw: str, project_root: Path) -> Path:
    p = Path(raw)
    if p.is_absolute():
        return p
    return (project_root / raw).resolve()


def render_publish_comment(template_path: Path, mapping: Dict[str, str]) -> str:
    text = template_path.read_text(encoding="utf-8")
    # safe_substitute：模板里写了未知占位符也不会崩
    return Template(text).safe_substitute(mapping)


def post_jira_comment_after_publish(
    issue_key: str,
    mapping: Dict[str, str],
    *,
    project_root: Path,
) -> Dict[str, Any]:
    """
    若未开启或未配置模板，返回 skipped。
    成功返回 posted=True 及 comment_id（若库返回）。
    失败默认不抛异常，返回 posted=False + error。
    """
    out: Dict[str, Any] = {"posted": False}

    if not _envbool("JIRA_COMMENT_AFTER_PUBLISH", False):
        out["skipped"] = True
        out["reason"] = "JIRA_COMMENT_AFTER_PUBLISH 未开启"
        return out

    raw_tpl = _envstr("JIRA_PUBLISH_COMMENT_TEMPLATE")
    if not raw_tpl:
        out["skipped"] = True
        out["reason"] = "未设置 JIRA_PUBLISH_COMMENT_TEMPLATE"
        return out

    tpl_path = _resolve_template_path(raw_tpl, project_root)
    if not tpl_path.is_file():
        out["skipped"] = True
        out["reason"] = f"模板文件不存在: {tpl_path}"
        return out

    jira_server = _envstr("JIRA_SERVER", "http://jira.transsion.com")
    jira_user = _envstr("JIRA_USERNAME")
    jira_pass = os.getenv("JIRA_PASSWORD") or ""

    try:
        body = render_publish_comment(tpl_path, mapping)
    except Exception as exc:
        out["error"] = f"渲染模板失败: {exc}"
        return out

    if not body.strip():
        out["error"] = "渲染后评论正文为空，已跳过"
        return out

    try:
        client = _create_jira_client(jira_server, jira_user, jira_pass)
        issue = client.issue(issue_key)
        comment = client.add_comment(issue, body)
        cid = getattr(comment, "id", None)
        out["posted"] = True
        out["comment_id"] = str(cid) if cid is not None else None
        out["jira_server"] = jira_server
    except Exception as exc:
        out["error"] = str(exc)[:2000]
    return out


def _mapping_from_manifest(manifest_path: Path) -> Dict[str, str]:
    """从已写好的 manifest 中提取 Jira 评论需要的字段。"""
    import json
    data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    smb = (data.get("_meta") or {}).get("phase1_smb_publish") or {}
    return {
        "issue_key": str(data.get("issue_key", "")),
        "unc_base": str(smb.get("unc_base", "")),
        "smb_zip_rel": str(smb.get("smb_zip_rel", "")),
        "publish_date": str(smb.get("publish_date", "")),
        "published_at": str(smb.get("published_at", "")),
        "robocopy_exit": "" if smb.get("robocopy_exit") is None else str(smb.get("robocopy_exit")),
        "phase1_host": str(smb.get("host", "")),
        "manifest_path": str(manifest_path),
        "robocopy_mode": str(smb.get("mode", "zip upload")),
    }


def main() -> int:
    """
    仅测试 Jira 评论的 CLI：
      # A. 用真实 manifest 渲染并发评论
      python pipeline_steps\\jira_post_publish_comment.py --manifest D:\\work\\OS162-37733\\job_manifest.json

      # B. 用 issue-key（自动定位 {WORKSPACE_ROOT}/{issue}/job_manifest.json）
      python pipeline_steps\\jira_post_publish_comment.py --issue-key OS162-37733

      # C. 只渲染模板、不发 Jira
      python pipeline_steps\\jira_post_publish_comment.py --issue-key OS162-37733 --dry-run
    """
    import argparse

    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-key", dest="issue_key", default="",
                        help="Jira 单号；当不提供 --manifest 时用其拼 {WORKSPACE_ROOT}/{issue}/job_manifest.json")
    parser.add_argument("--manifest", default="",
                        help="job_manifest.json 绝对路径；提供后从中读取 unc_base/published_at 等真实值")
    parser.add_argument("--dry-run", action="store_true",
                        help="只渲染模板并打印，不真正调用 Jira")
    parser.add_argument("--write-back", action="store_true",
                        help="发送成功后把结果写回 manifest._meta.phase1_smb_publish.jira_comment")
    args = parser.parse_args()

    # 解析 manifest 路径（用于读真实占位符值）
    manifest_path: Optional[Path] = None
    if args.manifest:
        manifest_path = Path(args.manifest).resolve()
    elif args.issue_key:
        ws = _envstr("WORKSPACE_ROOT")
        if ws:
            manifest_path = (Path(ws) / args.issue_key / "job_manifest.json").resolve()
    if manifest_path is not None and not manifest_path.is_file():
        print(f"[FAIL] manifest 不存在: {manifest_path}", file=sys.stderr)
        return 2

    # 构造 mapping
    if manifest_path is not None:
        mapping = _mapping_from_manifest(manifest_path)
        if args.issue_key and mapping.get("issue_key") and mapping["issue_key"] != args.issue_key.strip():
            print(f"[WARN] manifest 内 issue_key={mapping['issue_key']} 与命令行 --issue-key={args.issue_key} 不一致，以 manifest 为准",
                  file=sys.stderr)
        issue_key = mapping["issue_key"] or args.issue_key.strip()
        if not mapping.get("unc_base"):
            print("[WARN] manifest 内未记录 phase1_smb_publish.unc_base，"
                  "通常意味着 Step 9 还没成功跑过；将用占位符渲染。", file=sys.stderr)
    else:
        if not args.issue_key:
            parser.error("必须提供 --manifest 或 --issue-key")
        issue_key = args.issue_key.strip()
        mapping = {
            "issue_key": issue_key,
            "unc_base": "(unknown — no manifest)",
            "smb_zip_rel": "",
            "publish_date": "",
            "published_at": "",
            "robocopy_exit": "",
            "phase1_host": "",
            "manifest_path": "",
            "robocopy_mode": "zip upload",
        }

    # 渲染并打印
    raw_tpl = _envstr("JIRA_PUBLISH_COMMENT_TEMPLATE")
    if not raw_tpl:
        print("请设置 JIRA_PUBLISH_COMMENT_TEMPLATE", file=sys.stderr)
        return 1
    tpl_path = _resolve_template_path(raw_tpl, root)
    if not tpl_path.is_file():
        print(f"模板不存在: {tpl_path}", file=sys.stderr)
        return 1
    body = render_publish_comment(tpl_path, mapping)
    print("---------- comment body ----------")
    print(body)
    print("----------------------------------")

    if args.dry_run:
        print("[dry-run] 未发送 Jira。")
        return 0

    # 真发
    r = post_jira_comment_after_publish(issue_key, mapping, project_root=root)
    print(r)

    if args.write_back and manifest_path is not None and (r.get("posted") or r.get("error")):
        try:
            import json
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            meta = data.setdefault("_meta", {})
            smb = meta.setdefault("phase1_smb_publish", {})
            smb["jira_comment"] = r
            manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[write-back] 已更新 {manifest_path}")
        except Exception as exc:
            print(f"[write-back] 失败: {exc}", file=sys.stderr)

    return 0 if r.get("posted") else 1


if __name__ == "__main__":
    raise SystemExit(main())

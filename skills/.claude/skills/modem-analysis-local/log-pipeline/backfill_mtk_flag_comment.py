#!/usr/bin/env python3
"""
为历史 Jira 单补充 MTK 可检索标记评论。

处理条件：
1) 命中业务范围 JQL（--jql-all / 环境变量 / 默认构造）
2) text ~ "modem-log-pipeline-export-flag"
3) 不命中 text ~ "qcom-modem-log-pipeline-export-flag"
4) 不命中 text ~ "MtkModemLogPipelineExportFlag"

对目标单添加评论：
    MtkModemLogPipelineExportFlag
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
_SHARED_DIR = PROJECT_ROOT / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

try:
    from dotenv import load_dotenv

    _env_path = PROJECT_ROOT / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass


logger = logging.getLogger("backfill_mtk_flag_comment")

JQL_STATUS = 'Open, "In Progress", Reopened, Submitted, Fixed, Modifying'
JQL_ASSIGNEE = (
    "xin.liu13, fan.zhang2, huairou.chen, jiaquan.tang, haowen.ran, "
    "jiabao.xiong, xuan.zhang5,kaixuan.ding, hui.wang8, xuejian.fu, yuxiang.cao, ruijun.wu, "
    "kechun.li, yao.xiao5,xiaohui.song,lu.li14,liuyan.mo,mengnan.shen,xiaoxiao.tang, "
    "zhongyu.zhao, cheng.zhan, sanling.liu, ying.liu8, chao.wu2, yue.chen11"
)

DEFAULT_LOOKBACK_DAYS = 1
DEFAULT_PAGE_SIZE = 50

OLD_FLAG = "modem-log-pipeline-export-flag"
QCOM_FLAG = "qcom-modem-log-pipeline-export-flag"
MTK_NEW_FLAG = "MtkModemLogPipelineExportFlag"
MTK_NEW_COMMENT = MTK_NEW_FLAG


def _envstr(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _envint(name: str, default: int) -> int:
    raw = _envstr(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("环境变量 %s=%r 不是整数，使用默认 %s", name, raw, default)
        return default


def _rolling_created_since(lookback_days: int) -> str:
    days = max(1, lookback_days)
    since = date.today() - timedelta(days=days - 1)
    return since.isoformat()


def _default_jql_all(created_since: str) -> str:
    created_clause = f'created >= "{created_since}"'
    return f"status in ({JQL_STATUS}) AND assignee in ({JQL_ASSIGNEE}) AND {created_clause}"


def resolve_created_since() -> str:
    fixed = _envstr("JIRA_EXPORT_WATCHER_CREATED_SINCE")
    if fixed:
        return fixed
    lookback = _envint(
        "JIRA_EXPORT_WATCHER_CREATED_LOOKBACK_DAYS",
        DEFAULT_LOOKBACK_DAYS,
    )
    return _rolling_created_since(lookback)


def build_jql_with_text(base_jql: str, text_token: str) -> str:
    return f'({base_jql}) AND text ~ "{text_token}"'


def create_jira_client(server: str, username: str, password: str):
    try:
        from jira import JIRA
    except ModuleNotFoundError as exc:
        raise SystemExit(f"缺少依赖 jira，请执行: pip install -r requirements.txt ({exc})") from exc

    if username and password:
        return JIRA(server=server, basic_auth=(username, password))
    return JIRA(server=server)


def search_issue_keys(client, jql: str, *, page_size: int) -> List[str]:
    keys: List[str] = []
    start_at = 0
    while True:
        batch = client.search_issues(jql, startAt=start_at, maxResults=page_size)
        if not batch:
            break
        for issue in batch:
            keys.append(str(issue.key))
        if len(batch) < page_size:
            break
        start_at += len(batch)
    return keys


def compute_targets(
    client,
    jql_all: str,
    *,
    page_size: int,
) -> Tuple[List[str], int, int, int]:
    base_jql = build_jql_with_text(jql_all, OLD_FLAG)
    qcom_jql = build_jql_with_text(jql_all, QCOM_FLAG)
    new_mtk_jql = build_jql_with_text(jql_all, MTK_NEW_FLAG)

    base_keys = search_issue_keys(client, base_jql, page_size=page_size)
    qcom_set: Set[str] = set(search_issue_keys(client, qcom_jql, page_size=page_size))
    new_mtk_set: Set[str] = set(search_issue_keys(client, new_mtk_jql, page_size=page_size))

    target = [k for k in base_keys if k not in qcom_set and k not in new_mtk_set]
    return target, len(base_keys), len(qcom_set), len(new_mtk_set)


def add_comment_if_needed(client, issue_key: str, *, dry_run: bool) -> bool:
    issue = client.issue(issue_key)
    comments = client.comments(issue)
    for comment in comments:
        body = str(getattr(comment, "body", "") or "")
        if MTK_NEW_FLAG in body:
            logger.info("[%s] 已存在 MTK 新标记评论，跳过", issue_key)
            return False

    if dry_run:
        logger.info("[%s] dry-run: 将添加评论: %s", issue_key, MTK_NEW_COMMENT)
        return False

    client.add_comment(issue, MTK_NEW_COMMENT)
    logger.info("[%s] 已添加评论: %s", issue_key, MTK_NEW_COMMENT)
    return True


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="补充 MTK Jira 评论标记（排除 qcom 标记单）"
    )
    parser.add_argument(
        "--jql-all",
        default=_envstr("JIRA_EXPORT_WATCHER_JQL_ALL", _envstr("JIRA_EXPORT_WATCHER_JQL", "")),
        help="业务范围 JQL（不含 text 条件）；不传则取环境变量，若仍为空则按默认规则构造",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印目标单，不写评论")
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 条（0 表示不限制）")
    parser.add_argument(
        "--page-size",
        type=int,
        default=_envint("JIRA_EXPORT_WATCHER_PAGE_SIZE", DEFAULT_PAGE_SIZE),
        help="Jira 分页大小",
    )
    parser.add_argument(
        "--log-level",
        default=_envstr("JIRA_EXPORT_WATCHER_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    jira_server = _envstr("JIRA_SERVER", "http://jira.transsion.com")
    jira_username = _envstr("JIRA_USERNAME")
    jira_password = _envstr("JIRA_PASSWORD")

    created_since = resolve_created_since()
    jql_all = args.jql_all.strip() or _default_jql_all(created_since)
    page_size = max(1, args.page_size)

    logger.info("JIRA_SERVER: %s", jira_server)
    logger.info("JQL_ALL: %s", jql_all)

    client = create_jira_client(jira_server, jira_username, jira_password)
    target, base_n, qcom_n, new_n = compute_targets(client, jql_all, page_size=page_size)

    logger.info(
        "统计: old_flag命中=%d, qcom_flag命中=%d, 新mtk_flag命中=%d, 待补评论=%d",
        base_n,
        qcom_n,
        new_n,
        len(target),
    )
    if not target:
        logger.info("没有需要补评论的单。")
        return 0

    keys = target
    if args.limit > 0:
        keys = keys[: args.limit]
        logger.info("启用 --limit=%d，本次处理 %d 条", args.limit, len(keys))

    success = 0
    failed = 0
    for idx, key in enumerate(keys, start=1):
        logger.info("处理进度 %d/%d: %s", idx, len(keys), key)
        try:
            if add_comment_if_needed(client, key, dry_run=args.dry_run):
                success += 1
        except Exception:
            failed += 1
            logger.exception("[%s] 添加评论失败", key)

    logger.info(
        "完成: dry_run=%s, 目标=%d, 实际新增=%d, 失败=%d",
        args.dry_run,
        len(keys),
        success,
        failed,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

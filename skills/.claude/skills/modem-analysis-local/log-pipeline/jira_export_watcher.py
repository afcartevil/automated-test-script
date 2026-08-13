#!/usr/bin/env python3
"""
持续扫描 Jira：两条完整 JQL 做差集，对待处理单依次执行 modem-log-pipeline（run_pipeline.py）。

用法:
  python jira_export_watcher.py
  python jira_export_watcher.py --once
  python jira_export_watcher.py --dry-run
  python jira_export_watcher.py --scan-only
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
_SHARED_DIR = PROJECT_ROOT / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from pipeline_platform import (  # noqa: E402
    export_flag,
    normalize_platform,
    prefixes_env_var,
    resolve_comment_template,
)

try:
    from dotenv import load_dotenv

    _env_path = PROJECT_ROOT / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

logger = logging.getLogger("jira_export_watcher")


jql_status = 'Open, "In Progress", Reopened, Submitted, Fixed, Modifying'
jql_assignee = ("xin.liu13, fan.zhang2, huairou.chen, jiaquan.tang, haowen.ran, "
    "jiabao.xiong, xuan.zhang5,kaixuan.ding, hui.wang8, xuejian.fu, yuxiang.cao, ruijun.wu, "
    "kechun.li, yao.xiao5,xiaohui.song,lu.li14,liuyan.mo,mengnan.shen,xiaoxiao.tang, "
    "zhongyu.zhao, cheng.zhan, sanling.liu, ying.liu8, chao.wu2, yue.chen11"
)
_DEFAULT_CREATED_LOOKBACK_DAYS = 1
_DEFAULT_SLEEP_SECONDS = 30 * 60


def _rolling_created_since(lookback_days: int) -> str:
    """
    计算 JQL created 下界（含当日）。

    lookback_days=1 → 仅今天；7 → 含今天在内共 7 个自然日。
    """
    days = max(1, lookback_days)
    since = date.today() - timedelta(days=days - 1)
    return since.isoformat()


def _build_default_jql(created_since: str, platform: str = "mtk") -> Tuple[str, str]:
    created_clause = f'created >= "{created_since}"'
    flag = export_flag(platform)
    jql_all = (
        f"status in ({jql_status}) AND assignee in ({jql_assignee}) AND {created_clause}"
    )
    jql_exported = (
        f"status in ({jql_status}) AND assignee in ({jql_assignee}) AND {created_clause} "
        f'AND text ~ "{flag}"'
    )
    return jql_all, jql_exported


def resolve_created_since() -> Tuple[str, int]:
    """
    解析 created 下界：优先 JIRA_EXPORT_WATCHER_CREATED_SINCE，否则按回看天数滚动。
    返回 (YYYY-MM-DD, lookback_days)；固定日期时 lookback_days 为 0。
    """
    fixed = _envstr("JIRA_EXPORT_WATCHER_CREATED_SINCE")
    if fixed:
        return fixed, 0
    lookback = _envint(
        "JIRA_EXPORT_WATCHER_CREATED_LOOKBACK_DAYS",
        _DEFAULT_CREATED_LOOKBACK_DAYS,
    )
    return _rolling_created_since(lookback), lookback

# 印度/俄罗斯粉丝反馈通常不上传 log，用 summary 精确子串跳过（见 fan_feedback_skip_reason）。
_FAN_SKIP_MARKER_RUSSIA = "【粉丝反馈】【EE1】"
_FAN_SKIP_MARKER_INDIA = "【粉丝反馈】【印度】"


@dataclass(frozen=True)
class WatcherConfig:
    jira_server: str
    jira_username: str
    jira_password: str
    jql_all: str
    jql_exported: str
    affects_version_prefixes: List[str]
    issue_key_prefixes: List[str]
    run_pipeline: bool
    pipeline_log_level: str
    workspace_root: str
    sleep_seconds: int
    page_size: int
    created_since: str
    created_lookback_days: int
    platform: str
    comment_template: str
    comment_template_env: str


def _envstr(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _envbool(name: str, default: bool = True) -> bool:
    v = _envstr(name)
    if not v:
        return default
    return v.lower() in ("1", "true", "yes", "y", "on")


def _envint(name: str, default: int) -> int:
    raw = _envstr(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("环境变量 %s=%r 不是整数，使用默认 %s", name, raw, default)
        return default


def _parse_csv_list(raw: str) -> List[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_config(platform: str = "") -> WatcherConfig:
    try:
        plat = normalize_platform(platform)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    jira_server = _envstr("JIRA_SERVER", "http://jira.transsion.com")
    jira_username = _envstr("JIRA_USERNAME")
    jira_password = _envstr("JIRA_PASSWORD")

    created_since, created_lookback_days = resolve_created_since()
    default_jql_all, default_jql_exported = _build_default_jql(created_since, plat)
    jql_all = _envstr(
        "JIRA_EXPORT_WATCHER_JQL_ALL",
        _envstr("JIRA_EXPORT_WATCHER_JQL", default_jql_all),
    )
    jql_exported = _envstr("JIRA_EXPORT_WATCHER_JQL_EXPORTED", default_jql_exported)
    # 未配置时为空列表：不做 Affects Version 前缀过滤（与 .env.example 注释一致）
    affects_prefixes = _parse_csv_list(_envstr(prefixes_env_var(plat)))
    comment_template, comment_template_env = resolve_comment_template(plat)
    issue_key_prefixes = _parse_csv_list(
        _envstr("JIRA_EXPORT_WATCHER_ISSUE_KEY_PREFIXES")
    )
    if not jql_all:
        raise SystemExit("JIRA_EXPORT_WATCHER_JQL_ALL（或 JIRA_EXPORT_WATCHER_JQL）为空")

    workspace_root = _envstr("WORKSPACE_ROOT")
    run_pipeline = _envbool("JIRA_EXPORT_WATCHER_RUN_PIPELINE", True)
    pipeline_log_level = _envstr(
        "JIRA_EXPORT_WATCHER_PIPELINE_LOG_LEVEL",
        _envstr("JIRA_EXPORT_WATCHER_LOG_LEVEL", "INFO"),
    )
    if run_pipeline and not workspace_root:
        raise SystemExit(
            "已启用 pipeline 导出，但未配置 WORKSPACE_ROOT（modem-log-pipeline/.env）"
        )

    sleep_seconds = _envint("JIRA_EXPORT_WATCHER_SLEEP_SECONDS", _DEFAULT_SLEEP_SECONDS)
    page_size = _envint("JIRA_EXPORT_WATCHER_PAGE_SIZE", 50)
    if page_size < 1:
        page_size = 50

    return WatcherConfig(
        jira_server=jira_server,
        jira_username=jira_username,
        jira_password=jira_password,
        jql_all=jql_all,
        jql_exported=jql_exported,
        affects_version_prefixes=affects_prefixes,
        issue_key_prefixes=issue_key_prefixes,
        run_pipeline=run_pipeline,
        pipeline_log_level=pipeline_log_level,
        workspace_root=workspace_root,
        sleep_seconds=sleep_seconds,
        page_size=page_size,
        created_since=created_since,
        created_lookback_days=created_lookback_days,
        platform=plat,
        comment_template=comment_template,
        comment_template_env=comment_template_env,
    )


def create_jira_client(cfg: WatcherConfig):
    try:
        from jira import JIRA
    except ModuleNotFoundError as e:
        raise SystemExit(f"缺少依赖 jira，请执行: pip install -r requirements.txt ({e})") from e

    if cfg.jira_username and cfg.jira_password:
        return JIRA(server=cfg.jira_server, basic_auth=(cfg.jira_username, cfg.jira_password))
    return JIRA(server=cfg.jira_server)


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


def diff_pending_keys(
    client,
    jql_all: str,
    jql_exported: str,
    *,
    page_size: int,
) -> tuple[List[str], int, int]:
    """待处理 = JQL_ALL 命中 key 减去 JQL_EXPORTED 命中 key（保持 ALL 中的顺序）。"""
    all_keys = search_issue_keys(client, jql_all, page_size=page_size)
    if not jql_exported.strip():
        return all_keys, len(all_keys), 0

    exported_set: Set[str] = set(
        search_issue_keys(client, jql_exported, page_size=page_size)
    )
    pending = [k for k in all_keys if k not in exported_set]
    return pending, len(all_keys), len(exported_set)


def _issue_affects_versions(client, issue_key: str) -> List[str]:
    """读取 issue 的 Affects Version/s（versions）名称列表。"""
    issue = client.issue(issue_key)
    fields = getattr(issue, "fields", None)
    versions = getattr(fields, "versions", None) or []
    names: List[str] = []
    for version in versions:
        name = getattr(version, "name", None)
        if name:
            names.append(str(name))
    return names


def _filter_keys_by_affects_version_prefixes(
    client, keys: List[str], prefixes: List[str]
) -> tuple[List[str], List[str]]:
    """
    仅保留 affects versions 以任一指定前缀开头的 issue。
    返回 (保留key列表, 被过滤日志列表)。
    """
    if not prefixes:
        return keys, []
    normalized_prefixes = [p.lower() for p in prefixes]
    kept: List[str] = []
    dropped_logs: List[str] = []
    for key in keys:
        try:
            versions = _issue_affects_versions(client, key)
            matched = any(
                any(v.lower().startswith(prefix) for prefix in normalized_prefixes)
                for v in versions
            )
            if matched:
                kept.append(key)
            else:
                dropped_logs.append(f"{key} -> versions={versions or ['(none)']}")
        except Exception as exc:
            dropped_logs.append(f"{key} -> 读取 versions 失败: {exc}")
    return kept, dropped_logs


def _fan_feedback_skip_enabled() -> bool:
    return _envbool("JIRA_EXPORT_WATCHER_SKIP_FAN_NO_LOG", True)


def fan_feedback_skip_reason(summary: str) -> Optional[str]:
    """
    判断是否属于「无 log URL、应跳过 pipeline」的粉丝反馈单。

    返回非空字符串表示跳过原因；返回 None 表示继续处理。
    """
    text = (summary or "").strip()
    if not text:
        return None
    if _FAN_SKIP_MARKER_RUSSIA in text:
        return "fan_feedback_russia_ee1"
    if _FAN_SKIP_MARKER_INDIA in text:
        return "fan_feedback_india"
    return None


def _issue_summary(client, issue_key: str) -> str:
    issue = client.issue(issue_key, fields="summary")
    fields = getattr(issue, "fields", None)
    return str(getattr(fields, "summary", "") or "")


def _filter_keys_by_fan_feedback_skip(
    client, keys: List[str]
) -> Tuple[List[str], List[str]]:
    """跳过印度/俄罗斯粉丝反馈（无 log URL，不跑 pipeline）。"""
    if not _fan_feedback_skip_enabled():
        return keys, []
    kept: List[str] = []
    dropped_logs: List[str] = []
    for key in keys:
        try:
            summary = _issue_summary(client, key)
            reason = fan_feedback_skip_reason(summary)
            if reason:
                dropped_logs.append(f"{key} -> skip_fan_no_log({reason}) summary={summary[:120]!r}")
            else:
                kept.append(key)
        except Exception as exc:
            dropped_logs.append(f"{key} -> 读取 summary 失败: {exc}")
            kept.append(key)
    return kept, dropped_logs


def _filter_keys_by_issue_key_prefixes(
    keys: List[str], prefixes: List[str]
) -> tuple[List[str], List[str]]:
    """仅保留 issue key 以任一前缀开头的单。"""
    if not prefixes:
        return keys, []
    normalized_prefixes = [p.lower() for p in prefixes]
    kept: List[str] = []
    dropped_logs: List[str] = []
    for key in keys:
        key_low = key.lower()
        if any(key_low.startswith(prefix) for prefix in normalized_prefixes):
            kept.append(key)
        else:
            dropped_logs.append(f"{key} -> key_prefix_not_allowed")
    return kept, dropped_logs


def run_modem_log_pipeline(cfg: WatcherConfig, issue_key: str) -> Dict[str, Any]:
    """对单个 Jira 单执行 run_pipeline.py（完整 Phase 1 日志准备）。"""
    if _shutdown_requested:
        return {"issue_key": issue_key, "action": "cancelled", "reason": "shutdown"}

    script = PROJECT_ROOT / "run_pipeline.py"
    if not script.is_file():
        raise FileNotFoundError(f"找不到 {script}")

    cmd = [
        sys.executable,
        str(script),
        "--issue-key",
        issue_key,
        "--log-level",
        cfg.pipeline_log_level,
    ]
    env = os.environ.copy()
    if cfg.comment_template:
        env["JIRA_PUBLISH_COMMENT_TEMPLATE"] = cfg.comment_template

    logger.info(
        "[%s] 启动 modem-log-pipeline (platform=%s): %s",
        issue_key,
        cfg.platform,
        " ".join(cmd),
    )
    if cfg.comment_template:
        logger.info(
            "[%s] Jira 评论模板: %s=%s",
            issue_key,
            cfg.comment_template_env,
            cfg.comment_template,
        )

    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    out: Dict[str, Any] = {
        "issue_key": issue_key,
        "returncode": proc.returncode,
    }
    if proc.returncode == 0:
        out["action"] = "pipeline_ok"
        logger.info("[%s] pipeline 完成", issue_key)
    else:
        out["action"] = "pipeline_failed"
        logger.error("[%s] pipeline 失败，退出码 %s", issue_key, proc.returncode)
    return out


def process_issue(cfg: WatcherConfig, issue_key: str) -> Dict[str, Any]:
    if not cfg.run_pipeline:
        logger.info("[%s] 待处理（--scan-only / RUN_PIPELINE=0，跳过导出）", issue_key)
        return {"issue_key": issue_key, "action": "skipped", "reason": "scan_only"}

    return run_modem_log_pipeline(cfg, issue_key)


def run_scan_cycle(client, cfg: WatcherConfig) -> int:
    logger.info("开始扫描（差集：JQL_ALL − JQL_EXPORTED）platform=%s", cfg.platform)
    if cfg.affects_version_prefixes:
        logger.info(
            "Affects Version 前缀来源: %s",
            prefixes_env_var(cfg.platform),
        )
    if cfg.created_lookback_days:
        logger.info(
            "created 窗口: 近 %d 天（下界 %s，含当日）",
            cfg.created_lookback_days,
            cfg.created_since,
        )
    else:
        logger.info("created 下界: %s（JIRA_EXPORT_WATCHER_CREATED_SINCE）", cfg.created_since)
    logger.info("JQL_ALL: %s", cfg.jql_all)
    logger.info("JQL_EXPORTED: %s", cfg.jql_exported or "(空，不做差集)")

    pending, n_all, n_exported = diff_pending_keys(
        client, cfg.jql_all, cfg.jql_exported, page_size=cfg.page_size
    )
    logger.info("命中 全部=%d 已导出=%d 待处理(差集)=%d", n_all, n_exported, len(pending))
    if cfg.affects_version_prefixes:
        before = len(pending)
        pending, dropped_logs = _filter_keys_by_affects_version_prefixes(
            client, pending, cfg.affects_version_prefixes
        )
        logger.info(
            "Affects Version/s 过滤: prefixes=%s，保留=%d，过滤=%d",
            ",".join(cfg.affects_version_prefixes),
            len(pending),
            before - len(pending),
        )
        for line in dropped_logs[:20]:
            logger.info("过滤: %s", line)
        if len(dropped_logs) > 20:
            logger.info("过滤日志过长，省略其余 %d 条", len(dropped_logs) - 20)
    if cfg.issue_key_prefixes:
        before = len(pending)
        pending, dropped_logs = _filter_keys_by_issue_key_prefixes(
            pending, cfg.issue_key_prefixes
        )
        logger.info(
            "IssueKey 前缀约束: prefixes=%s，保留=%d，过滤=%d",
            ",".join(cfg.issue_key_prefixes),
            len(pending),
            before - len(pending),
        )
        for line in dropped_logs[:20]:
            logger.info("过滤: %s", line)
        if len(dropped_logs) > 20:
            logger.info("过滤日志过长，省略其余 %d 条", len(dropped_logs) - 20)
    if _fan_feedback_skip_enabled():
        before = len(pending)
        pending, dropped_logs = _filter_keys_by_fan_feedback_skip(client, pending)
        logger.info(
            "粉丝反馈(无log)跳过: markers=%s/%s，保留=%d，跳过=%d",
            _FAN_SKIP_MARKER_INDIA,
            _FAN_SKIP_MARKER_RUSSIA,
            len(pending),
            before - len(pending),
        )
        for line in dropped_logs[:20]:
            logger.info("跳过: %s", line)
        if len(dropped_logs) > 20:
            logger.info("跳过日志过长，省略其余 %d 条", len(dropped_logs) - 20)

    for idx, key in enumerate(pending, start=1):
        logger.info("处理进度 %d/%d: %s", idx, len(pending), key)
        if _shutdown_requested:
            logger.info("收到退出信号，停止处理剩余 %d 条", len(pending) - idx)
            break
        try:
            process_issue(cfg, key)
        except Exception:
            logger.exception("[%s] 处理失败，继续下一条", key)

    return len(pending)


_shutdown_requested = False


def _handle_signal(signum, _frame):
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("收到信号 %s，当前轮次结束后退出", signum)


def sleep_between_cycles(seconds: int) -> None:
    if seconds <= 0:
        return
    logger.info("本轮结束，休眠 %d 秒（约 %.1f 分钟）", seconds, seconds / 60.0)
    remaining = seconds
    while remaining > 0 and not _shutdown_requested:
        chunk = min(remaining, 5)
        time.sleep(chunk)
        remaining -= chunk


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Jira 双 JQL 差集扫描")
    parser.add_argument("--once", action="store_true", help="只执行一轮")
    parser.add_argument("--dry-run", action="store_true", help="打印两条 JQL 与差集结果，不跑 pipeline")
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="只扫描差集，不调用 run_pipeline.py",
    )
    parser.add_argument(
        "--log-level",
        default=_envstr("JIRA_EXPORT_WATCHER_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    parser.add_argument(
        "--platform",
        choices=["mtk", "qcom", "sprd"],
        default="",
        help="平台：不传或 mtk 用 JIRA_EXPORT_WATCHER_AFFECTS_VERSION_PREFIXES；"
        "qcom/sprd 用 JIRA_EXPORT_WATCHER_PREFIXES_QCOM / _SPRD，并切换 Jira 评论模板",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    cfg = load_config(args.platform)
    if args.scan_only:
        cfg = replace(cfg, run_pipeline=False)

    client = create_jira_client(cfg)

    if args.dry_run:
        if cfg.created_lookback_days:
            print(
                f"created 窗口: 近 {cfg.created_lookback_days} 天（下界 {cfg.created_since}，含当日）\n"
            )
        else:
            print(f"created 下界: {cfg.created_since}\n")
        print(f"platform: {cfg.platform}（前缀 env: {prefixes_env_var(cfg.platform)}）\n")
        if cfg.comment_template:
            print(f"评论模板: {cfg.comment_template_env}={cfg.comment_template}\n")
        print(f"JQL_ALL:\n{cfg.jql_all}\n")
        print(f"JQL_EXPORTED:\n{cfg.jql_exported or '(空)'}\n")
        pending, n_all, n_exported = diff_pending_keys(
            client, cfg.jql_all, cfg.jql_exported, page_size=cfg.page_size
        )
        print(f"全部 {n_all} 条，已导出 {n_exported} 条，待处理(差集) {len(pending)} 条")
        if cfg.affects_version_prefixes:
            pending, dropped_logs = _filter_keys_by_affects_version_prefixes(
                client, pending, cfg.affects_version_prefixes
            )
            print(
                f"Affects Version/s 过滤：prefixes={','.join(cfg.affects_version_prefixes)}，"
                f"保留 {len(pending)} 条，过滤 {len(dropped_logs)} 条"
            )
        if cfg.issue_key_prefixes:
            pending, dropped_logs = _filter_keys_by_issue_key_prefixes(
                pending, cfg.issue_key_prefixes
            )
            print(
                f"IssueKey 前缀约束：prefixes={','.join(cfg.issue_key_prefixes)}，"
                f"保留 {len(pending)} 条，过滤 {len(dropped_logs)} 条"
            )
        if _fan_feedback_skip_enabled():
            pending, dropped_logs = _filter_keys_by_fan_feedback_skip(client, pending)
            print(
                f"粉丝反馈(无log)跳过：印度={_FAN_SKIP_MARKER_INDIA!r} "
                f"俄罗斯={_FAN_SKIP_MARKER_RUSSIA!r}，"
                f"保留 {len(pending)} 条，跳过 {len(dropped_logs)} 条"
            )
            for line in dropped_logs[:10]:
                print(f"  {line}")
        if pending:
            print(f"待处理: {', '.join(pending[:20])}")
            if len(pending) > 20:
                print(f"  ... 另有 {len(pending) - 20} 条")
            if cfg.run_pipeline:
                print(
                    f"\n将依次执行: python run_pipeline.py --issue-key <KEY> "
                    f"(WORKSPACE_ROOT={cfg.workspace_root})"
                )
        return 0

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    cycle = 0
    while not _shutdown_requested:
        cycle += 1
        logger.info("========== 第 %d 轮扫描 ==========", cycle)
        try:
            run_scan_cycle(client, cfg)
        except Exception:
            logger.exception("本轮扫描异常")
        if args.once or _shutdown_requested:
            break
        sleep_between_cycles(cfg.sleep_seconds)

    logger.info("watcher 已退出（共 %d 轮）", cycle)
    return 0


if __name__ == "__main__":
    sys.exit(main())

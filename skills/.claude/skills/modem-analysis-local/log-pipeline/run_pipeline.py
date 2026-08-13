#!/usr/bin/env python3
"""
Modem Analysis Unified Pipeline
自动执行日志准备流程（日志下载、解压、过滤、导出、打包）
"""

import os
import sys
import json
import argparse
import logging
from copy import deepcopy
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# 工程目录布局：
#   modem-log-pipeline/
#     run_pipeline.py        <- __file__
#     pipeline_steps/
#     _shared/
#     schemas/
#     .env
PROJECT_ROOT = Path(__file__).parent
PIPELINE_STEPS_DIR = PROJECT_ROOT / 'pipeline_steps'
SHARED_DIR = PROJECT_ROOT / '_shared'
SCHEMAS_DIR = PROJECT_ROOT / 'schemas'

sys.path.insert(0, str(PIPELINE_STEPS_DIR))
sys.path.insert(0, str(SHARED_DIR))

# 导入共享工具
from modem_analysis_runtime import load_manifest, save_manifest
from manifest_finalizer import finalize_and_validate
from pipeline_run_summary import append_phase1_step, finalize_phase1_run_meta

# 加载环境变量（.env 与本文件同级）
try:
    from dotenv import load_dotenv
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def load_env_with_fallback():
    """加载环境变量"""
    return {
        'WORKSPACE_ROOT': os.getenv('WORKSPACE_ROOT', ''),
        'JIRA_SERVER': os.getenv('JIRA_SERVER', ''),
        'JIRA_USERNAME': os.getenv('JIRA_USERNAME', ''),
        'JIRA_PASSWORD': os.getenv('JIRA_PASSWORD', ''),
        'ELT_HOME': os.getenv('ELT_HOME', ''),
        'NLT_HOME': os.getenv('NLT_HOME', ''),
        'SEVEN_ZIP_EXE': os.getenv('SEVEN_ZIP_EXE', ''),
        'WIRESHARK_PATH': os.getenv('WIRESHARK_PATH', ''),
    }

# 导入 pipeline steps 模块
import fetch_issue_context
import download_box_logs
import recursive_extract
import filter_log_roots
import pcap_to_txt
import fetch_mddb_for_logs
import export_traces
import package_trace_outputs
import publish_to_samba
import update_dashboard_bitable

# 日志配置将在 main() 中根据工作区路径动态设置
logger = logging.getLogger(__name__)


class PipelineStep:
    """流程步骤基类"""
    
    def __init__(self, name: str, required: bool = True):
        self.name = name
        self.required = required
    
    def execute(self, manifest_path: str) -> bool:
        """
        执行步骤
        
        Returns:
            bool: 是否成功
        """
        raise NotImplementedError


class JiraIssueFetchStep(PipelineStep):
    """获取 Jira 信息"""
    
    def __init__(self):
        super().__init__("jira-issue-fetch", required=True)
    
    def execute(self, manifest_path: str) -> bool:
        logger.info(f"[1/9] Executing {self.name}...")
        
        try:
            manifest = load_manifest(manifest_path)
            issue_key = manifest.get('issue_key')
            
            result = fetch_issue_context.fetch_issue_context(issue_key)
            
            # 更新 manifest
            manifest['jira'] = result
            save_manifest(manifest_path, manifest)
            
            logger.info(f"[1/9] ✓ {self.name} completed")
            return True
        
        except Exception as e:
            logger.error(f"[1/9] ✗ {self.name} failed: {str(e)}")
            if self.required:
                raise
            return False


class BoxLogDownloadStep(PipelineStep):
    """下载日志文件"""
    
    def __init__(self):
        super().__init__("box-log-download", required=True)
    
    def execute(self, manifest_path: str) -> bool:
        logger.info(f"[2/9] Executing {self.name}...")
        
        try:
            result = download_box_logs.download_box_logs(manifest_path)
            
            # 更新 manifest
            manifest = load_manifest(manifest_path)
            manifest['downloads'] = result
            save_manifest(manifest_path, manifest)
            
            logger.info(f"[2/9] ✓ {self.name} completed")
            return True
        
        except Exception as e:
            logger.error(f"[2/9] ✗ {self.name} failed: {str(e)}")
            if self.required:
                raise
            return False


class ArchiveExtractStep(PipelineStep):
    """解压日志压缩包"""
    
    def __init__(self):
        super().__init__("archive-recursive-extract", required=True)
    
    def execute(self, manifest_path: str) -> bool:
        logger.info(f"[3/9] Executing {self.name}...")
        
        try:
            result = recursive_extract.recursive_extract_all(manifest_path)
            
            # 更新 manifest
            manifest = load_manifest(manifest_path)
            manifest['extraction'] = result
            save_manifest(manifest_path, manifest)
            
            logger.info(f"[3/9] ✓ {self.name} completed")
            return True
        
        except Exception as e:
            logger.error(f"[3/9] ✗ {self.name} failed: {str(e)}")
            if self.required:
                raise
            return False


class ModemLogFilterStep(PipelineStep):
    """过滤 modem 相关日志目录"""
    
    def __init__(self):
        super().__init__("modem-log-structure-filter", required=True)
    
    def execute(self, manifest_path: str) -> bool:
        logger.info(f"[4/9] Executing {self.name}...")
        
        try:
            if filter_log_roots.should_skip_log_filter_deletion():
                logger.info("[4/9] 保留解压目录内全部文件（跳过过滤删文件）")
            result = filter_log_roots.filter_modem_logs(manifest_path)
            
            # 更新 manifest
            manifest = load_manifest(manifest_path)
            if 'extraction' not in manifest:
                manifest['extraction'] = {}
            manifest['extraction']['normalized_log_roots'] = result.get('normalized_log_roots', [])
            manifest['extraction']['filter_results'] = result.get('filter_results', {})
            save_manifest(manifest_path, manifest)
            
            logger.info(f"[4/9] ✓ {self.name} completed")
            return True
        
        except Exception as e:
            logger.error(f"[4/9] ✗ {self.name} failed: {str(e)}")
            if self.required:
                raise
            return False


class PcapExportStep(PipelineStep):
    """导出 PCAP 网络抓包文件（可选）"""
    
    def __init__(self):
        super().__init__("pcap-export", required=False)
    
    def execute(self, manifest_path: str) -> bool:
        logger.info(f"[5/9] Executing {self.name}...")
        
        try:
            # 检查是否有 netlog 目录
            manifest = load_manifest(manifest_path)
            filter_results = manifest.get('extraction', {}).get('filter_results', {})
            
            has_netlog = False
            for result in filter_results.values():
                if result.get('found', {}).get('netlog_dirs'):
                    has_netlog = True
                    break
            
            if not has_netlog:
                logger.info(f"[5/9] ⊘ {self.name} skipped (no netlog directory found)")
                return True
            
            # 执行 PCAP 导出（脚本内部已写 manifest.pcap_exports；返回值仅为 0/1 退出码，勿写入 pcap_export）
            pcap_to_txt.export_pcap_to_txt(manifest_path)
            manifest = load_manifest(manifest_path)
            pes = manifest.get("pcap_exports")
            manifest["pcap_export"] = deepcopy(pes) if isinstance(pes, dict) else {"results": []}
            save_manifest(manifest_path, manifest)
            
            logger.info(f"[5/9] ✓ {self.name} completed")
            return True
        
        except Exception as e:
            logger.warning(f"[5/9] ⚠ {self.name} failed: {str(e)} (continuing...)")
            return False


class MddbFetcherStep(PipelineStep):
    """下载 EDB 文件（可选）"""
    
    def __init__(self):
        super().__init__("mddb-fetcher", required=False)
    
    def execute(self, manifest_path: str) -> bool:
        logger.info(f"[6/9] Executing {self.name}...")
        
        try:
            fetch_mddb_for_logs.fetch_mddb_for_all_logs(manifest_path)

            # fetch_mddb_for_all_logs 已在 manifest 内写入 mddb_fetch；返回值仅为 0/1 退出码，勿写入 mddb
            manifest = load_manifest(manifest_path)
            mf = manifest.get("mddb_fetch")
            manifest["mddb"] = deepcopy(mf) if isinstance(mf, dict) else {"results": []}
            save_manifest(manifest_path, manifest)
            
            logger.info(f"[6/9] ✓ {self.name} completed")
            return True
        
        except Exception as e:
            logger.warning(f"[6/9] ⚠ {self.name} failed: {str(e)} (continuing...)")
            return False


class EltNltExportStep(PipelineStep):
    """导出 trace txt 文件"""
    
    def __init__(self):
        super().__init__("elt-nlt-export", required=False)
    
    def execute(self, manifest_path: str) -> bool:
        logger.info(f"[7/9] Executing {self.name}...")
        
        try:
            result = export_traces.export_all_traces(manifest_path)
            
            # 更新 manifest
            manifest = load_manifest(manifest_path)
            manifest['trace_exports'] = result
            save_manifest(manifest_path, manifest)
            
            logger.info(f"[7/9] ✓ {self.name} completed")
            return True
        
        except Exception as e:
            logger.warning(f"[7/9] ⚠ {self.name} failed: {str(e)} (continuing...)")
            return False


class TracePackageStep(PipelineStep):
    """打包最终日志"""
    
    def __init__(self):
        super().__init__("trace-aggregate-and-package", required=True)
    
    def execute(self, manifest_path: str) -> bool:
        logger.info(f"[8/9] Executing {self.name}...")

        try:
            result = package_trace_outputs.package_final_logs(manifest_path)
        except Exception as e:
            logger.error(f"[8/9] ✗ {self.name} failed: {str(e)}")
            return False

        # 业务层错误（无日志可打包）：不抛异常，直接返回 False 让 pipeline 干净退出
        if not result.get("ok", True):
            logger.error(f"[8/9] ✗ {self.name} failed: {result.get('error', '无日志可打包')}")
            return False

        try:
            # 更新 manifest（与 package_trace_outputs.main 对齐：需持久化打包阶段全部产物元数据）
            manifest = load_manifest(manifest_path)
            manifest['final_log_root'] = result.get('final_log_root')
            manifest['trace_exports']['aggregated_files'] = result.get('aggregated_files', {})
            manifest['trace_exports']['copied_support_files'] = result.get('copied_support_files', {})
            if result.get('groups') is not None:
                manifest['trace_exports']['groups'] = result['groups']

            # ===== Phase 1 ↔ Phase 2 契约的最后一道关卡 =====
            # 1. 把绝对路径全部转为相对（POSIX 风格）
            # 2. 写入 schema_version、_meta.phase1_completed_at 等
            # 3. 用 JSON Schema 严格校验，失败立即终止
            finalize_and_validate(manifest, manifest_path)
            save_manifest(manifest_path, manifest)

            # 聚合产物已写入 issue 根目录（DUT/、db.* 等），删除原始 downloads/ 再进 Step 9 Samba
            if package_trace_outputs.should_skip_download_cleanup():
                logger.info("[8/9] 保留 downloads/ 目录（PIPELINE_KEEP_LOCAL_FILES / SKIP_DOWNLOAD_CLEANUP）")
            else:
                dlc = package_trace_outputs.cleanup_download_residue(manifest)
                manifest.setdefault("trace_exports", {})
                manifest["trace_exports"]["cleanup"] = dlc
                for row in manifest.get("trace_exports", {}).get("results") or []:
                    if isinstance(row, dict):
                        row["cleanup"] = dlc
                save_manifest(manifest_path, manifest)
                logger.info("[8/9] 已删除原始下载目录: %s", dlc.get("removed_paths", []))
        except Exception as e:
            logger.error(f"[8/9] ✗ {self.name} failed at manifest finalize: {str(e)}")
            return False

        logger.info(f"[8/9] ✓ {self.name} completed")
        logger.info(f"Final log root: {manifest.get('final_log_root')} (relative to manifest)")
        return True


class SmbPublishStep(PipelineStep):
    """把 issue 目录 robocopy /MIR 到 Samba（默认软失败，不阻塞整条 pipeline）"""

    def __init__(self):
        # required 由 .env 的 SMB_PUBLISH_REQUIRED 控制（在 execute 内决定是否抛异常）
        super().__init__("samba-publish", required=False)

    def execute(self, manifest_path: str) -> bool:
        logger.info(f"[9/9] Executing {self.name}...")

        try:
            result = publish_to_samba.publish_issue_to_samba(manifest_path)
        except Exception as e:
            required = (os.getenv("SMB_PUBLISH_REQUIRED") or "").strip().lower() in ("1", "true", "yes", "y", "on")
            logger.error(f"[9/9] ✗ {self.name} failed: {str(e)}")
            if required:
                raise
            return False

        if result.get("skipped"):
            logger.info(f"[9/9] ⊘ {self.name} skipped: {result.get('message','')}")
            return True

        if result.get("ok"):
            logger.info(f"[9/9] ✓ {self.name} completed → {result.get('unc_base','')}")
            return True

        required = bool(result.get("required"))
        msg = result.get("message", "")
        if required:
            logger.error(f"[9/9] ✗ {self.name} failed (required): {msg}")
            raise RuntimeError(msg or "samba publish failed")
        logger.warning(f"[9/9] ⚠ {self.name} failed (soft): {msg}")
        return False


def upsert_feishu_dashboard(manifest_path: str, *, label: str = "feishu-dashboard") -> bool:
    """无论 pipeline 成败都尝试写飞书看板（默认软失败）。"""
    logger.info("[%s] upsert 飞书分析看板...", label)
    try:
        result = update_dashboard_bitable.update_dashboard_from_manifest(manifest_path)
    except Exception as e:
        required = (os.getenv("FEISHU_DASHBOARD_REQUIRED") or "").strip().lower() in (
            "1", "true", "yes", "y", "on"
        )
        logger.error("[%s] ✗ 失败: %s", label, e)
        if required:
            raise
        return False

    if result.get("skipped"):
        logger.info("[%s] ⊘ 跳过: %s", label, result.get("message", ""))
        return True
    if result.get("ok"):
        logger.info("[%s] ✓ %s", label, result.get("message", ""))
        return True

    required = bool(result.get("required"))
    msg = result.get("message", "")
    if required:
        logger.error("[%s] ✗ (required): %s", label, msg)
        raise RuntimeError(msg or "feishu dashboard upsert failed")
    logger.warning("[%s] ⚠ %s", label, msg)
    return False


class Pipeline:
    """主流程管理器"""
    
    def __init__(self):
        self.steps = [
            JiraIssueFetchStep(),
            BoxLogDownloadStep(),
            ArchiveExtractStep(),
            ModemLogFilterStep(),
            PcapExportStep(),
            MddbFetcherStep(),
            EltNltExportStep(),
            TracePackageStep(),
            SmbPublishStep(),
        ]
        self.env_vars = load_env_with_fallback()
    
    def init_manifest(self, issue_key: str) -> str:
        """初始化 manifest 文件。

        约定：manifest 所在目录 = workspace（即 {WORKSPACE_ROOT}/{issue_key}/）。
        所有后续阶段写入的路径字段都以此目录为相对基准。
        """
        workspace_root = Path(self.env_vars['WORKSPACE_ROOT'])
        issue_dir = workspace_root / issue_key
        issue_dir.mkdir(parents=True, exist_ok=True)
        
        manifest_path = issue_dir / 'job_manifest.json'
        
        if manifest_path.exists():
            logger.info(f"Manifest already exists: {manifest_path}")
            return str(manifest_path)
        
        manifest = {
            'schema_version': '1.1.0',
            'issue_key': issue_key,
            'pipeline_version': '1.0.0',
            'final_log_root': 'final_logs',
            'jira': {},
            'downloads': {},
            'extraction': {},
            'trace_exports': {},
            'analysis': {},
            '_meta': {
                'created_at': datetime.now().isoformat(timespec='seconds'),
            },
        }
        
        save_manifest(str(manifest_path), manifest)
        logger.info(f"Manifest initialized: {manifest_path}")
        
        return str(manifest_path)
    
    def run(
        self,
        manifest_path: str,
        skip_to_analysis: bool = False,
        *,
        pipeline_log_file: str = "",
    ) -> bool:
        """
        运行流程
        
        Args:
            manifest_path: manifest 文件路径
            skip_to_analysis: 是否跳过日志准备，直接到分析阶段
            pipeline_log_file: 本次 pipeline 日志文件路径（写入 manifest 供飞书看板）
        
        Returns:
            bool: 是否成功
        """
        if skip_to_analysis:
            logger.info("Skipping log preparation, ready for analysis")
            return True
        
        logger.info("=" * 60)
        logger.info("Starting Modem Analysis Unified Pipeline")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        overall_ok = False
        n_steps = len(self.steps)

        try:
            manifest = load_manifest(manifest_path)
            meta = manifest.setdefault("_meta", {})
            meta["phase1_steps"] = []
            if pipeline_log_file:
                meta["pipeline_log_file"] = pipeline_log_file
            save_manifest(manifest_path, manifest)

            for i, step in enumerate(self.steps, 1):
                step_error = ""
                try:
                    success = step.execute(manifest_path)
                except Exception as e:
                    success = False
                    step_error = str(e)
                    if step.required:
                        raise

                manifest = load_manifest(manifest_path)
                append_phase1_step(manifest, step.name, success, step_error)
                save_manifest(manifest_path, manifest)

                if not success and step.required:
                    logger.error(f"Pipeline failed at {step.name}")
                    break
            else:
                overall_ok = True

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            manifest = load_manifest(manifest_path)
            finalize_phase1_run_meta(
                manifest,
                overall_ok=overall_ok,
                pipeline_log_file=pipeline_log_file,
            )
            save_manifest(manifest_path, manifest)

            if overall_ok:
                logger.info("=" * 60)
                logger.info(f"Pipeline completed successfully in {duration:.1f}s")
                logger.info("=" * 60)
                logger.info("")
                logger.info("Next: AI should execute analysis steps")
                logger.info("  - L0: 基础指标分析")
                logger.info("  - L1: 业务判断")
                logger.info("  - L2: 域内分析")
                logger.info("  - L3: 最终结论")
                logger.info("")
            else:
                logger.error("=" * 60)
                logger.error(f"Pipeline finished with failures in {duration:.1f}s")
                logger.error("=" * 60)

            return overall_ok
        
        except Exception as e:
            logger.error(f"Pipeline failed with error: {str(e)}", exc_info=True)
            try:
                manifest = load_manifest(manifest_path)
                append_phase1_step(manifest, "pipeline-abort", False, str(e))
                finalize_phase1_run_meta(
                    manifest,
                    overall_ok=False,
                    pipeline_log_file=pipeline_log_file,
                )
                save_manifest(manifest_path, manifest)
            except Exception:
                pass
            return False


def setup_logging(issue_key: str, workspace_root: str, log_level: str = 'INFO'):
    """
    配置日志系统，同时输出到控制台和文件
    
    Args:
        issue_key: Jira issue key
        workspace_root: 工作区根目录
        log_level: 日志级别
    """
    # 创建日志目录
    issue_dir = Path(workspace_root) / issue_key
    issue_dir.mkdir(parents=True, exist_ok=True)
    
    # 日志文件路径
    log_file = issue_dir / f'pipeline_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    
    # 创建根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    
    # 清除现有的处理器
    root_logger.handlers.clear()
    
    # 日志格式
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(getattr(logging, log_level))
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 记录日志文件位置
    root_logger.info(f"Log file: {log_file}")
    
    return str(log_file)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='Modem Analysis Unified Pipeline - Automated Log Preparation'
    )
    
    parser.add_argument('--issue-key', '--issue_key', dest='issue_key', help='Jira issue key (e.g., LK6AEE-3291)')
    parser.add_argument('--manifest', help='job_manifest.json 的绝对路径（与 --publish-only 联用仅发布；或与 --issue-key 联用从该 manifest 续跑完整 pipeline）')
    parser.add_argument('--skip-to-analysis', action='store_true',
                        help='Skip log preparation and go directly to analysis')
    parser.add_argument('--skip-publish', action='store_true',
                        help='本次运行跳过 Step 9 Samba 发布（覆盖 .env 中的 SMB_PUBLISH_ENABLED）')
    parser.add_argument('--publish-only', action='store_true',
                        help='仅执行 Step 9：把本地已有 issue 目录整包 robocopy /MIR 到 Samba（不跑下载/解压/导出等）')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Log level')
    parser.add_argument(
        '--platform',
        choices=['mtk', 'qcom', 'sprd'],
        default='',
        help='平台：切换 JIRA_PUBLISH_COMMENT_TEMPLATE_*（一般由 jira_export_watcher 注入）',
    )

    args = parser.parse_args()

    if args.platform:
        _SHARED = PROJECT_ROOT / '_shared'
        if str(_SHARED) not in sys.path:
            sys.path.insert(0, str(_SHARED))
        try:
            from pipeline_platform import resolve_comment_template
            tpl, tpl_env = resolve_comment_template(args.platform)
            if tpl:
                os.environ['JIRA_PUBLISH_COMMENT_TEMPLATE'] = tpl
                logger.info('platform=%s，评论模板 %s=%s', args.platform, tpl_env, tpl)
        except ValueError as exc:
            parser.error(str(exc))

    if args.publish_only and args.skip_publish:
        parser.error('--publish-only 与 --skip-publish 互斥')
    if args.skip_publish:
        os.environ['SMB_PUBLISH_ENABLED'] = '0'
    
    # 初始化流程
    pipeline = Pipeline()
    
    # 获取工作区路径
    workspace_root = pipeline.env_vars.get('WORKSPACE_ROOT', '')
    if not workspace_root:
        # 在日志系统配置前，使用临时日志记录器
        temp_logger = logging.getLogger('temp')
        temp_logger.addHandler(logging.StreamHandler(sys.stderr))
        temp_logger.setLevel(logging.ERROR)
        temp_logger.error("WORKSPACE_ROOT not configured in .env file")
        sys.exit(1)

    # ----- 仅推送到 Samba（本地日志已就绪） -----
    if args.publish_only:
        os.environ['SMB_PUBLISH_ENABLED'] = '1'
        if args.manifest:
            manifest_path = Path(args.manifest).resolve()
        elif args.issue_key:
            manifest_path = (Path(workspace_root) / args.issue_key / 'job_manifest.json').resolve()
        else:
            parser.error('--publish-only 需要 --issue-key 或 --manifest')

        if not manifest_path.is_file():
            print(f"[FAIL] manifest 不存在: {manifest_path}", file=sys.stderr)
            sys.exit(1)

        issue_key_for_log = (args.issue_key or '').strip()
        if not issue_key_for_log:
            try:
                m = load_manifest(str(manifest_path))
                issue_key_for_log = (m.get('issue_key') or manifest_path.parent.name or 'unknown').strip()
            except Exception:
                issue_key_for_log = manifest_path.parent.name or 'unknown'

        # 约定目录为 {WORKSPACE_ROOT}/{issue}/job_manifest.json，用于 pipeline 日志落盘
        ws_for_log = str(manifest_path.parent.parent)
        log_file = setup_logging(issue_key_for_log, ws_for_log, args.log_level)

        logger.info("=" * 60)
        logger.info("Samba publish-only（Step 9）")
        logger.info("=" * 60)
        logger.info(f"Manifest: {manifest_path}")
        logger.info(f"Log file: {log_file}")
        logger.info("=" * 60)

        publish_step = SmbPublishStep()
        ok = publish_step.execute(str(manifest_path))
        if ok:
            logger.info("publish-only 完成")
            sys.exit(0)
        logger.error("publish-only 失败（若 SMB_PUBLISH_REQUIRED=0 可能为软失败，见上方日志）")
        sys.exit(1)

    if not args.issue_key and not args.manifest:
        parser.error('完整 pipeline 需要 --issue-key；或提供 --manifest（manifest 内需含 issue_key）')

    # 配置日志（同时输出到控制台和文件）
    if args.manifest:
        manifest_path_obj = Path(args.manifest).resolve()
        if not manifest_path_obj.is_file():
            parser.error(f'--manifest 指向的文件不存在: {manifest_path_obj}')
        try:
            _m = load_manifest(str(manifest_path_obj))
        except Exception as exc:
            parser.error(f'无法读取 manifest: {exc}')
        issue_from_manifest = (_m.get('issue_key') or '').strip()
        eff_issue = issue_from_manifest or (args.issue_key or '').strip()
        if not eff_issue:
            parser.error('manifest 缺少 issue_key，请提供 --issue-key')
        ws_for_log = str(manifest_path_obj.parent.parent)
        log_file = setup_logging(eff_issue, ws_for_log, args.log_level)
        if issue_from_manifest and (args.issue_key or '').strip() and issue_from_manifest != (args.issue_key or '').strip():
            logger.warning(
                'manifest 内 issue_key=%s 与命令行 --issue-key=%s 不一致，以 manifest 为准',
                issue_from_manifest,
                (args.issue_key or '').strip(),
            )
        manifest_path = str(manifest_path_obj)
        run_issue_key = eff_issue
    else:
        log_file = setup_logging(args.issue_key, workspace_root, args.log_level)
        manifest_path = pipeline.init_manifest(args.issue_key)
        run_issue_key = (args.issue_key or '').strip()

    logger.info("=" * 60)
    logger.info("Modem Analysis Unified Pipeline")
    logger.info("=" * 60)
    logger.info(f"Issue Key: {run_issue_key}")
    logger.info(f"Workspace (.env): {workspace_root}")
    logger.info(f"Log Level: {args.log_level}")
    logger.info(f"Log File: {log_file}")
    logger.info(f"Manifest: {manifest_path}")
    logger.info("=" * 60)
    success = pipeline.run(
        manifest_path,
        skip_to_analysis=args.skip_to_analysis,
        pipeline_log_file=log_file,
    )

    # 无论成败都写飞书看板（软失败不阻塞退出码）
    try:
        upsert_feishu_dashboard(manifest_path)
    except Exception as exc:
        logger.warning("飞书看板 upsert 异常（已忽略）: %s", exc)

    if success:
        logger.info("=" * 60)
        logger.info(f"Pipeline completed successfully")
        logger.info(f"Manifest: {manifest_path}")
        logger.info(f"Log file: {log_file}")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.error("=" * 60)
        logger.error("Pipeline failed")
        logger.error(f"Check log file: {log_file}")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == '__main__':
    main()


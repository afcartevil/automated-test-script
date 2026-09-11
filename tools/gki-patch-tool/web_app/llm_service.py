"""LLM API 客户端 - 调用 OpenAI 兼容接口进行自动 Patch 分析。"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml

from web_app.app_paths import scoring_config_path
from web_app.prompt_loader import load_prompt, render_prompt, user_hint_prompt_suffix

ENV_KEY = "GKI_LLM_API_KEY"
ENV_BASE = "GKI_LLM_API_BASE"
ENV_MODEL = "GKI_LLM_MODEL"
ENV_MANAGED_BY_EA = "GKI_LLM_MANAGED_BY_EA"
DEFAULT_BASE = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o"

BUILD_FIX_LLM_TIMEOUT = int(os.environ.get("GKI_BUILD_FIX_LLM_TIMEOUT", "240"))
BUILD_FIX_LLM_MAX_TOKENS = int(os.environ.get("GKI_BUILD_FIX_LLM_MAX_TOKENS", "8192"))
BUILD_FIX_LLM_MAX_ATTEMPTS = int(os.environ.get("GKI_BUILD_FIX_LLM_MAX_ATTEMPTS", "1"))
BUILD_FIX_LLM_RETRY_MAX_TOKENS = int(os.environ.get("GKI_BUILD_FIX_LLM_RETRY_MAX_TOKENS", "16384"))



def is_llm_managed_by_ea() -> bool:
    """True when EasyAdapter injected LLM env and owns the config."""
    return os.environ.get(ENV_MANAGED_BY_EA, "").strip() in ("1", "true", "yes")


def get_llm_config() -> Dict[str, str]:
    # Start with env vars / defaults
    cfg = {
        "api_key": os.environ.get(ENV_KEY, ""),
        "api_base": os.environ.get(ENV_BASE, DEFAULT_BASE).rstrip("/"),
        "model": os.environ.get(ENV_MODEL, DEFAULT_MODEL),
    }
    # EasyAdapter 集成注入时：环境变量优先，忽略设置页 DB，避免旧配置覆盖
    if is_llm_managed_by_ea():
        if not cfg["api_base"]:
            cfg["api_base"] = DEFAULT_BASE
        if not cfg["model"]:
            cfg["model"] = DEFAULT_MODEL
        return cfg
    # Overlay DB config (page config takes precedence in standalone)
    try:
        from web_app.database import get_db_llm_config
        db_cfg = get_db_llm_config()
        if db_cfg.get("api_key"):
            cfg["api_key"] = db_cfg["api_key"]
        if db_cfg.get("api_base"):
            cfg["api_base"] = db_cfg["api_base"].rstrip("/")
        if db_cfg.get("model"):
            cfg["model"] = db_cfg["model"]
    except Exception:
        pass
    return cfg


def save_llm_config(api_key: str, api_base: str, model: str) -> None:
    """Persist LLM config to DB."""
    if is_llm_managed_by_ea():
        raise RuntimeError("当前由 EasyAdapter 托管 LLM 配置，请在 EasyAdapter「模型」中修改")
    from web_app.database import save_db_llm_config
    save_db_llm_config(api_key, api_base, model)


def is_llm_configured() -> bool:
    cfg = get_llm_config()
    return bool(cfg["api_key"])


def normalize_llm_api_base(api_base: str = "") -> str:
    """Normalize OpenAI-compatible base URL for /models and /chat/completions."""
    base = (api_base or DEFAULT_BASE).strip().rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if base.endswith(suffix):
            base = base[: -len(suffix)].rstrip("/")
    return base or DEFAULT_BASE


def fetch_llm_models(api_key: str = "", api_base: str = "") -> Dict[str, Any]:
    """Fetch available model IDs from an OpenAI-compatible GET /v1/models endpoint."""
    cfg = get_llm_config()
    key = (api_key or cfg.get("api_key") or "").strip()
    base = normalize_llm_api_base(api_base or cfg.get("api_base") or DEFAULT_BASE)
    if not key:
        return {"models": [], "error": "请先填写 API Key", "api_base": base}

    url = f"{base}/models"
    headers = {
        "Authorization": f"Bearer {key}",
        "User-Agent": "gki-patch-analyzer/1.0",
    }
    try:
        client = _get_llm_http_client(base)
        resp = client.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        return {
            "models": [],
            "error": f"HTTP {exc.response.status_code}: {detail}",
            "api_base": base,
        }
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        return {"models": [], "error": str(exc), "api_base": base}

    raw_items: List[Any] = []
    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            raw_items = data["data"]
        elif isinstance(data.get("models"), list):
            raw_items = data["models"]
    elif isinstance(data, list):
        raw_items = data

    models: List[str] = []
    seen = set()
    for item in raw_items:
        model_id = ""
        if isinstance(item, dict):
            model_id = str(item.get("id") or item.get("name") or "").strip()
        elif isinstance(item, str):
            model_id = item.strip()
        if model_id and model_id not in seen:
            seen.add(model_id)
            models.append(model_id)
    models.sort(key=str.lower)
    return {"models": models, "api_base": base, "count": len(models)}


# ── Scoring criteria from config ───────────────────────
def _get_scoring_criteria() -> str:
    """Load scoring criteria from config and format as prompt instructions."""
    config_path = scoring_config_path()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception:
        return ""

    lines: List[str] = []
    dims = cfg.get("dimensions", [])
    lines.append("评分维度（加权求和）：")
    for dim in dims:
        weight = dim.get("weight", 0)
        if weight == 0:
            continue
        label = dim.get("label", dim.get("id", ""))
        lines.append(f"- {label}（权重 {int(weight * 100)}%）")

    rec_map = cfg.get("recommendation_mapping", [])
    lines.append("")
    lines.append("推荐结论映射（根据最终总分判定）：")
    for item in sorted(rec_map, key=lambda x: x.get("min", 0), reverse=True):
        rec = item.get("recommendation", "")
        min_s = item.get("min", 0)
        max_s = item.get("max", 10)
        if min_s == max_s:
            lines.append(f"- {rec}（{min_s}分）")
        else:
            lines.append(f"- {rec}（{min_s}-{max_s}分）")

    return "\n".join(lines)


def _dev_module_list_text() -> str:
    from web_app.dev_module_classifier import load_dev_modules

    cfg = load_dev_modules()
    descs = cfg.get("descriptions") or {}
    names = cfg.get("names") or []
    if not names:
        return ""
    patterns_by_module: Dict[str, List[str]] = defaultdict(list)
    for pat, name in cfg.get("rules") or []:
        patterns_by_module[name].append(pat)
    lines: List[str] = []
    for name in names:
        desc = descs.get(name, "")
        pats = patterns_by_module.get(name, [])
        if pats:
            pat_str = "、".join(pats[:12])
            if len(pats) > 12:
                pat_str += "…"
            lines.append(f"- {name}：{desc}（参考路径：{pat_str}）")
        else:
            lines.append(f"- {name}：{desc}")
    return "\n".join(lines)


def _scoring_criteria_section(*, heading: str = "## 评分与标签要求") -> str:
    criteria = _get_scoring_criteria()
    if not criteria:
        return ""
    return f"\n{heading}\n{criteria}\n"


def _score_output_yaml_template() -> str:
    """Shared YAML snippet for LLM score output (full + lightweight modes)."""
    return load_prompt("snippets/score_output_yaml")


def _parse_llm_score_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract score / recommendation / key_risk / score_details from parsed YAML."""
    score_raw = data.get("score", 0)
    try:
        score = max(0.0, float(score_raw or 0))
    except (TypeError, ValueError):
        score = 0.0
    sd = data.get("score_details", {}) or {}
    if not isinstance(sd, dict):
        sd = {}
    return {
        "score": score,
        "recommendation": str(data.get("recommendation", "") or ""),
        "key_risk": str(data.get("key_risk", "") or ""),
        "score_details": sd,
    }


def _build_system_prompt() -> str:
    """Build the system prompt with scoring criteria and tag categories included."""
    return render_prompt(
        "patch_analysis_full",
        scoring_criteria_section=_scoring_criteria_section(),
        dev_module_list=_dev_module_list_text(),
    )


def _build_lightweight_system_prompt() -> str:
    """区间分析单笔 patch 轻量 prompt：解读/闭环/引入 + 模块分类 + 评分。"""
    criteria = _get_scoring_criteria()
    scoring_section = ""
    if criteria:
        scoring_section = f"""
## 评分要求
{criteria}
总分 = 各维度 score × 权重 加权求和（0-10，保留一位小数），recommendation 必须与总分档位一致。

"""
    return render_prompt(
        "patch_analysis_lightweight",
        scoring_section=scoring_section,
        dev_module_list=_dev_module_list_text(),
        score_yaml_snippet=_score_output_yaml_template(),
    )


def _parse_lightweight_llm_result(sha: str, content: str) -> Dict[str, Any]:
    """解析轻量 LLM 单笔分析结果。"""
    yaml_text = _extract_yaml(content)
    try:
        data = _safe_load_llm_yaml(yaml_text)
    except yaml.YAMLError:
        return _fallback_parse(sha, content)

    if not isinstance(data, dict):
        return _fallback_parse(sha, content)

    intro = str(data.get("introducer_analysis", "") or "")
    score_fields = _parse_llm_score_fields(data)
    return {
        "sha": sha,
        "dev_module": str(data.get("dev_module", "") or ""),
        "modification_interpretation": str(data.get("modification_interpretation", "") or ""),
        "problem_solved": str(data.get("problem_solved", "") or ""),
        "introducer_analysis": intro,
        "introduced_risk": intro,
        "code_changes": [],
        "patch_tags": [],
        "crash_risk": "无",
        "crash_risk_reason": "",
        "test_suggestions": "",
        **score_fields,
    }


_SYMBOL_TABLE_PATH_RE = re.compile(
    r"(?i)(?:^|/)(?:Module\.symvers|vmlinux\.symvers|.*\.symvers)$"
)
_DIFF_GIT_FILE_RE = re.compile(r"^diff --git a/(.+?) b/", re.MULTILINE)
_DEFCONFIG_PATH_RE = re.compile(
    r"(?i)(?:^|/)(?:.*defconfig$|Kconfig(?:\.[^/]+)?$|arch/[^/]+/configs/)"
)
# GKI/Android 溯源脚注（仅标明 upstream SHA，不代表已知安全回退模板）
_GKI_UPSTREAM_ATTRIBUTION_RE = re.compile(
    r"^\s*\[\s*Upstream commit\s+[0-9a-f]{7,40}\s*\]\s*$",
    re.IGNORECASE,
)
# 标题级 backport / upstream 合入模板（强信号）
_STABLE_BACKPORT_TITLE_RE = re.compile(
    r"(?i)^(?:"
    r"BACKPORT:\s*(?:FROM\s+)?(?:STABLE|UPSTREAM|MAINLINE)\b|"
    r"BACKPORT:\s*UPSTREAM:\s*|"
    r"(?:FROM\s+)?UPSTREAM:\s+|"
    r"ANDROID:\s*BACKPORT:\s*|"
    r"LOCAL:\s*BACKPORT:\s*"
    r")"
)
# CVE / 安全修复（标题或正文，排除 GKI 脚注与 Cc: stable@ 行）
_STABLE_SECURITY_SIGNAL_RE = re.compile(
    r"(?i)("
    r"\bCVE-\d{4}-\d+\b|"
    r"\bfix\s+for\s+CVE\b|"
    r"\bsecurity\s+fix\b|"
    r"\bstable\s+backport\b"
    r")"
)
_CHERRY_PICKED_FOOTER_RE = re.compile(
    r"(?i)\(cherry[\s-]?picked\s+from\s+commit\s+[0-9a-f]{7,40}\)"
)
_COMMENT_LINE_BODY_RE = re.compile(
    r"^\s*(?://"
    r"|/\*"
    r"|\*/"
    r"|\*"
    r"|#(?!!)"  # shell/Makefile comment, not #! shebang change emphasis
    r"|;\s*"
    r")|^\s*$"
)

_BUILD_META_BASENAME_RE = re.compile(
    r"(?i)^(?:Makefile|Kbuild|BUILD\.bazel|OWNERS|\.gitignore)$"
)
_BUILD_LOGIC_DIFF_RE = re.compile(
    r"(?i)(?:"
    r"\bCONFIG_"
    r"|\bccflags\b|\bcflags\b|\bCFLAGS\b|\basflags\b"
    r"|\bobj-\$\("
    r"|\blibs-\$\("
    r"|\bsubdir-\$\("
    r"|\bplatform-\$\("
    r")"
)
_MAINTAINERS_PATH_RE = re.compile(
    r"(?i)(?:^|/)(?:MAINTAINERS|OWNERS|\.mailmap)$"
)
_ABI_GKI_PATH_RE = re.compile(r"(?i)(?:^|/)android/abi_gki")
_LINUX_VERSION_TITLE_RE = re.compile(r"^Linux\s+\d+\.\d+(?:\.\d+)?(?:\s|$)", re.IGNORECASE)
_DEVICETREE_MAX_CHURN = 10

# 规则可判定的低风险：不走 LLM，产出与 minimal LLM 同结构的结果
RULE_BASED_LOW_RISK_REASONS = frozenset({
    "merge_tag",
    "symbol_table",
    "documentation",
    "defconfig",
    "comment_only",
    "abi_gki",
    "linux_version_bump",
    "maintainers_only",
    "devicetree_only",
    "test_only",
    "build_meta_only",
    "stable_security_backport",
})

_LOW_RISK_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "merge_tag": {
        "score": 9.0,
        "recommendation": "建议合入",
        "key_risk": "无明显额外风险",
        "brief": "Merge tag / 集成合入类变更，按发布工程合入处理。",
    },
    "symbol_table": {
        "score": 9.0,
        "recommendation": "建议合入",
        "key_risk": "无明显额外风险",
        "brief": "仅符号表 symvers 同步，无业务逻辑改动。",
    },
    "documentation": {
        "score": 9.0,
        "recommendation": "建议合入",
        "key_risk": "无明显额外风险",
        "brief": "仅文档/说明类文件变更，无内核运行时逻辑改动。",
    },
    "defconfig": {
        "score": 8.5,
        "recommendation": "建议合入",
        "key_risk": "确认目标产品配置意图一致",
        "brief": "仅 defconfig / Kconfig 配置类变更，无 C/汇编业务逻辑。",
    },
    "comment_only": {
        "score": 9.0,
        "recommendation": "建议合入",
        "key_risk": "无明显额外风险",
        "brief": "仅注释/空行调整，无可执行逻辑变更。",
    },
    "stable_security_backport": {
        "score": 8.0,
        "recommendation": "建议合入",
        "key_risk": "核对 upstream/CVE 与目标分支适用性",
        "brief": "已知 stable/security 回退或上游修复模板合入，按安全合入流程处理。",
    },
    "abi_gki": {
        "score": 9.0,
        "recommendation": "建议合入",
        "key_risk": "确认 ABI 符号列表与目标产品一致",
        "brief": "仅 GKI ABI 符号表同步（android/abi_gki*），无内核运行时逻辑改动。",
    },
    "linux_version_bump": {
        "score": 9.5,
        "recommendation": "建议合入",
        "key_risk": "无明显额外风险",
        "brief": "根 Makefile 内核版本号更新，无功能逻辑变更。",
    },
    "maintainers_only": {
        "score": 9.5,
        "recommendation": "建议合入",
        "key_risk": "无明显额外风险",
        "brief": "仅维护者元数据（MAINTAINERS/OWNERS/.mailmap）变更。",
    },
    "devicetree_only": {
        "score": 8.5,
        "recommendation": "建议合入",
        "key_risk": "确认 DT 节点与目标硬件一致",
        "brief": "仅小范围 DeviceTree（.dts/.dtsi）描述调整，无驱动 C 代码改动。",
    },
    "test_only": {
        "score": 9.0,
        "recommendation": "建议合入",
        "key_risk": "确认不编入产品内核镜像",
        "brief": "仅 selftests/KUnit 等测试代码变更，不影响 GKI 产物运行时逻辑。",
    },
    "build_meta_only": {
        "score": 9.0,
        "recommendation": "建议合入",
        "key_risk": "无明显额外风险",
        "brief": "仅构建元数据（Makefile/Kbuild 等）说明或注释类调整，无编译开关/目标变更。",
    },
}


def _is_symbol_table_path(path: str) -> bool:
    p = (path or "").replace("\\", "/").strip()
    if not p:
        return False
    if _SYMBOL_TABLE_PATH_RE.search(p):
        return True
    base = p.rsplit("/", 1)[-1].lower()
    return base.endswith(".symvers") or base in ("module.symvers", "vmlinux.symvers")


def _is_documentation_path(path: str) -> bool:
    p = (path or "").replace("\\", "/").strip().lstrip("./")
    if not p:
        return False
    if p.startswith("Documentation/") or "/Documentation/" in f"/{p}":
        return True
    base = p.rsplit("/", 1)[-1]
    if re.match(r"(?i)^README(\.|$)", base):
        return True
    return bool(re.search(r"(?i)\.(?:rst|md|txt|adoc)$", base))


def _is_defconfig_path(path: str) -> bool:
    p = (path or "").replace("\\", "/").strip().lstrip("./")
    if not p:
        return False
    if _DEFCONFIG_PATH_RE.search(p):
        return True
    base = p.rsplit("/", 1)[-1].lower()
    return base.endswith("defconfig") or base.startswith("kconfig")


def _patch_changed_files(patch_data: Dict[str, Any]) -> List[str]:
    files = [str(f).strip() for f in (patch_data.get("files") or []) if str(f).strip()]
    if files:
        return files
    diff_raw = patch_data.get("diff_preview", {})
    diff = diff_raw.get("text", "") if isinstance(diff_raw, dict) else str(diff_raw or "")
    if not diff:
        diff = str(patch_data.get("diff_text") or "")
    if not diff:
        return []
    return list(dict.fromkeys(_DIFF_GIT_FILE_RE.findall(diff)))


def _patch_diff_text(patch_data: Dict[str, Any]) -> str:
    diff_raw = patch_data.get("diff_preview", {})
    diff = diff_raw.get("text", "") if isinstance(diff_raw, dict) else str(diff_raw or "")
    if not diff:
        diff = str(patch_data.get("diff_text") or "")
    return diff


def _patch_commit_message(patch_data: Dict[str, Any]) -> str:
    return str(
        patch_data.get("commit_message_full")
        or patch_data.get("commit_message")
        or patch_data.get("title")
        or ""
    )


def is_merge_tag_patch(
    patch_data: Dict[str, Any],
    scoring_config: Optional[Dict[str, Any]] = None,
) -> bool:
    """Merge tag / android LTS 批量合入类 patch。"""
    if patch_data.get("trusted_integration_merge"):
        return True
    msg = _patch_commit_message(patch_data)
    cfg = scoring_config if scoring_config is not None else {}
    if not cfg:
        try:
            cfg = _load_scoring_config_dict()
        except Exception:
            cfg = {}
    from tools.patch_analyzer import is_trusted_integration_merge
    return is_trusted_integration_merge(str(msg), cfg)


def is_symbol_table_only_patch(patch_data: Dict[str, Any]) -> bool:
    """仅修改符号表（Module.symvers / *.symvers 等），无其它源码文件。"""
    files = _patch_changed_files(patch_data)
    if not files:
        return False
    return all(_is_symbol_table_path(f) for f in files)


def is_documentation_only_patch(patch_data: Dict[str, Any]) -> bool:
    """仅文档 / README / rst·md 等说明类文件。"""
    files = _patch_changed_files(patch_data)
    if not files:
        return False
    return all(_is_documentation_path(f) for f in files)


def is_defconfig_only_patch(patch_data: Dict[str, Any]) -> bool:
    """仅 defconfig / Kconfig / arch/*/configs 配置文件。"""
    files = _patch_changed_files(patch_data)
    if not files:
        return False
    return all(_is_defconfig_path(f) for f in files)


def _patch_diff_churn(patch_data: Dict[str, Any]) -> int:
    try:
        ins = int(patch_data.get("insertions") or 0)
        dels = int(patch_data.get("deletions") or 0)
        if ins + dels > 0:
            return ins + dels
    except (TypeError, ValueError):
        pass
    diff = _patch_diff_text(patch_data)
    churn = 0
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            churn += 1
        elif line.startswith("-") and not line.startswith("---"):
            churn += 1
    return churn


def _norm_repo_path(path: str) -> str:
    return (path or "").replace("\\", "/").strip().lstrip("./")


def _is_abi_gki_path(path: str) -> bool:
    return bool(_ABI_GKI_PATH_RE.search(_norm_repo_path(path)))


def _is_maintainers_path(path: str) -> bool:
    return bool(_MAINTAINERS_PATH_RE.search(_norm_repo_path(path)))


def _is_devicetree_path(path: str) -> bool:
    return _norm_repo_path(path).endswith((".dts", ".dtsi"))


def _is_test_only_path(path: str) -> bool:
    p = _norm_repo_path(path)
    if re.search(r"(?i)(?:^|/)tools/testing/", p):
        return True
    if re.search(r"(?i)(?:^|/)lib/kunit/", p):
        return True
    return bool(re.search(r"(?i)(?:^|/)(?:test|tests)/", p))


def _is_build_meta_path(path: str) -> bool:
    base = _norm_repo_path(path).rsplit("/", 1)[-1]
    return bool(_BUILD_META_BASENAME_RE.match(base))


def is_abi_gki_only_patch(patch_data: Dict[str, Any]) -> bool:
    """仅 GKI ABI 符号表（android/abi_gki* / .stg）。"""
    files = _patch_changed_files(patch_data)
    if not files:
        return False
    return all(_is_abi_gki_path(f) for f in files)


def is_linux_version_bump_patch(patch_data: Dict[str, Any]) -> bool:
    """根 Makefile 内核版本号 bump（标题 Linux x.y.z）。"""
    msg = _patch_commit_message(patch_data)
    title = msg.strip().splitlines()[0].strip() if msg.strip() else ""
    if not _LINUX_VERSION_TITLE_RE.match(title):
        return False
    files = _patch_changed_files(patch_data)
    if files != ["Makefile"]:
        return False
    return _patch_diff_churn(patch_data) <= 8


def is_maintainers_only_patch(patch_data: Dict[str, Any]) -> bool:
    """仅 MAINTAINERS / OWNERS / .mailmap。"""
    files = _patch_changed_files(patch_data)
    if not files:
        return False
    return all(_is_maintainers_path(f) for f in files)


def is_devicetree_only_patch(patch_data: Dict[str, Any]) -> bool:
    """仅小范围 DeviceTree（.dts/.dtsi，churn ≤ 10）。"""
    files = _patch_changed_files(patch_data)
    if not files:
        return False
    if not all(_is_devicetree_path(f) for f in files):
        return False
    return _patch_diff_churn(patch_data) <= _DEVICETREE_MAX_CHURN


def is_test_only_patch(patch_data: Dict[str, Any]) -> bool:
    """仅 selftests / KUnit / test(s) 目录下测试代码。"""
    files = _patch_changed_files(patch_data)
    if not files:
        return False
    return all(_is_test_only_path(f) for f in files)


def is_build_meta_only_patch(patch_data: Dict[str, Any]) -> bool:
    """仅构建元数据文件，且 diff 无 CONFIG/obj-y/ccflags 等编译逻辑变更。"""
    files = _patch_changed_files(patch_data)
    if not files:
        return False
    if not all(_is_build_meta_path(f) for f in files):
        return False
    for line in _patch_diff_text(patch_data).splitlines():
        if not line or line.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if line[0] not in "+-":
            continue
        body = line[1:].strip()
        if not body or body.startswith("#"):
            continue
        if _BUILD_LOGIC_DIFF_RE.search(body):
            return False
    return True


def is_comment_only_patch(patch_data: Dict[str, Any]) -> bool:
    """diff 增删行均为注释或空白（保守：无有效 +/- 行则不算）。"""
    diff = _patch_diff_text(patch_data)
    if not diff.strip():
        return False
    changed = 0
    for line in diff.splitlines():
        if not line or line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") or line.startswith("-"):
            body = line[1:]
            changed += 1
            if not _COMMENT_LINE_BODY_RE.match(body):
                return False
    return changed > 0


def _stable_backport_title_signals(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    return bool(_STABLE_BACKPORT_TITLE_RE.match(t))


def _stable_backport_body_line_signals(line: str) -> bool:
    """正文行是否含 stable/security 强信号（忽略 GKI 溯源脚注与 Cc: stable@）。"""
    stripped = (line or "").strip()
    if not stripped:
        return False
    if _GKI_UPSTREAM_ATTRIBUTION_RE.match(stripped):
        return False
    if re.match(r"(?i)^Cc:\s*stable@", stripped):
        return False
    return bool(_STABLE_SECURITY_SIGNAL_RE.search(stripped))


def is_stable_security_backport_patch(patch_data: Dict[str, Any]) -> bool:
    """提交说明匹配已知 stable/security 回退模板（保守：不含 GKI upstream 溯源脚注）。"""
    msg = _patch_commit_message(patch_data)
    if not msg.strip():
        return False

    lines = msg.strip().splitlines()
    title = lines[0].strip() if lines else ""

    if _stable_backport_title_signals(title):
        return True
    if _stable_backport_body_line_signals(title):
        return True

    if _CHERRY_PICKED_FOOTER_RE.search(msg) and _stable_backport_title_signals(title):
        return True

    for line in lines[1:]:
        if _stable_backport_body_line_signals(line):
            return True

    return False


def classify_low_risk_patch(
    patch_data: Dict[str, Any],
    scoring_config: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """规则可判定的低风险类别（命中则可免 LLM 深析）。

    优先级：merge_tag → symbol_table → documentation → defconfig →
    comment_only → abi_gki → linux_version_bump → maintainers_only →
    devicetree_only → test_only → build_meta_only → stable_security_backport。
    """
    if is_merge_tag_patch(patch_data, scoring_config):
        return True, "merge_tag"
    if is_symbol_table_only_patch(patch_data):
        return True, "symbol_table"
    if is_documentation_only_patch(patch_data):
        return True, "documentation"
    if is_defconfig_only_patch(patch_data):
        return True, "defconfig"
    if is_comment_only_patch(patch_data):
        return True, "comment_only"
    if is_abi_gki_only_patch(patch_data):
        return True, "abi_gki"
    if is_linux_version_bump_patch(patch_data):
        return True, "linux_version_bump"
    if is_maintainers_only_patch(patch_data):
        return True, "maintainers_only"
    if is_devicetree_only_patch(patch_data):
        return True, "devicetree_only"
    if is_test_only_patch(patch_data):
        return True, "test_only"
    if is_build_meta_only_patch(patch_data):
        return True, "build_meta_only"
    if is_stable_security_backport_patch(patch_data):
        return True, "stable_security_backport"
    return False, ""


def resolve_patch_llm_analysis_mode(
    patch_data: Dict[str, Any],
    default_mode: str,
    scoring_config: Optional[Dict[str, Any]] = None,
) -> str:
    """单笔分析深度：rule_minimal（规则免 LLM）/ minimal / full / lightweight。

    仅影响单笔 patch 调用；模块分析与任务综合报告不受此函数约束，
    始终使用完整 LLM（见 run_module_analysis_for_task / generate_unified_task_report）。
    """
    is_low, reason = classify_low_risk_patch(patch_data, scoring_config)
    if is_low and reason in RULE_BASED_LOW_RISK_REASONS:
        return "rule_minimal"
    if is_low:
        return "minimal"
    if default_mode == "full":
        return "full"
    return "lightweight"


def _uniform_score_details(score: float, reason: str) -> Dict[str, Any]:
    dim = {"score": float(score), "reason": reason}
    return {
        "correctness_completeness": dict(dim),
        "risk_safety": dict(dim),
        "diff_maintainability": dict(dim),
        "commit_metadata_quality": dict(dim),
    }


def build_rule_based_minimal_result(
    patch_data: Dict[str, Any],
    low_risk_reason: str,
    scoring_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """规则生成与 minimal LLM 同结构的分析结果（供 merge_llm_result 合并）。

    仅用于**单笔** patch 免 LLM 深析。字段结构与 LLM minimal 一致，便于 UI/DB；
    解读中附带提交说明与文件列表，供后续**模块分析 / 综合结论**完整归纳
   （模块与综合报告阶段仍始终走完整 LLM，不因 rule_based 降级）。
    """
    del scoring_config  # 预留与脚本评分对齐
    reason = (low_risk_reason or "").strip()
    tmpl = _LOW_RISK_TEMPLATES.get(reason) or {
        "score": 8.5,
        "recommendation": "建议合入",
        "key_risk": "无明显额外风险",
        "brief": "低风险合入类变更。",
    }
    score = float(tmpl["score"])
    category_brief = str(tmpl["brief"])
    key_risk = str(tmpl["key_risk"])
    recommendation = str(tmpl["recommendation"])
    sha = str(patch_data.get("commit") or patch_data.get("sha") or "")
    title = str(patch_data.get("title") or "").strip()
    msg = _patch_commit_message(patch_data).strip()
    if title and msg.startswith(title):
        msg_body = msg[len(title):].strip()
    else:
        msg_body = msg
    msg_body = re.sub(r"\s+", " ", msg_body).strip()[:400]
    files = _patch_changed_files(patch_data)
    files_preview = ", ".join(files[:12])
    if len(files) > 12:
        files_preview += f" …(+{len(files) - 12})"

    # 事实材料留给模块/总结 LLM；category_brief 标明规则类别
    interp_parts = [category_brief]
    if title:
        interp_parts.append(f"标题: {title}")
    if msg_body:
        interp_parts.append(f"提交说明摘要: {msg_body}")
    if files_preview:
        interp_parts.append(f"变更文件: {files_preview}")
    brief = "\n".join(interp_parts)

    from web_app.dev_module_classifier import classify_patch_dev_module

    try:
        dev_module = classify_patch_dev_module(patch_data) or ""
    except Exception:
        dev_module = str(patch_data.get("dev_module") or "")

    code_changes = []
    for fp in files[:8]:
        code_changes.append({
            "location": fp,
            "explanation": category_brief,
        })
    if not code_changes:
        code_changes = [{"location": "规则判定", "explanation": category_brief}]

    return {
        "sha": sha,
        "dev_module": dev_module,
        "analysis_depth": "minimal",
        "low_risk_reason": reason,
        "modification_interpretation": brief,
        "problem_solved": category_brief,
        "introducer_analysis": "",
        "introduced_risk": "",
        "code_changes": code_changes,
        "patch_tags": [],
        "crash_risk": "无",
        "crash_risk_reason": "",
        "test_suggestions": "",
        "score": score,
        "recommendation": recommendation,
        "key_risk": key_risk,
        "score_details": _uniform_score_details(score, category_brief),
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "rule_based": True,
    }


def _load_scoring_config_dict() -> Dict[str, Any]:
    from tools.patch_analyzer import load_config
    from tools.cli_config import DEFAULT_SCORING_CONFIG

    return load_config(DEFAULT_SCORING_CONFIG)


def _build_minimal_system_prompt() -> str:
    """低风险 patch：统一 LLM 评分/归类，短输出，不生成长篇解读。"""
    return render_prompt(
        "patch_analysis_minimal",
        dev_module_list=_dev_module_list_text(),
    )


def _parse_minimal_llm_result(
    sha: str,
    content: str,
    *,
    low_risk_reason: str = "",
) -> Dict[str, Any]:
    yaml_text = _extract_yaml(content)
    try:
        data = _safe_load_llm_yaml(yaml_text)
    except yaml.YAMLError:
        data = {}

    if not isinstance(data, dict):
        data = {}

    score_fields = _parse_llm_score_fields(data)
    key_risk = str(data.get("key_risk", "") or "").strip()
    reason = str(data.get("low_risk_reason") or low_risk_reason or "").strip()
    tmpl = _LOW_RISK_TEMPLATES.get(reason) or {}
    brief = key_risk or str(tmpl.get("brief") or "低风险合入类变更。")
    if not score_fields.get("score"):
        score_fields["score"] = float(tmpl.get("score") or 8.5)
    if not score_fields.get("recommendation"):
        score_fields["recommendation"] = str(tmpl.get("recommendation") or "建议合入")
    if not score_fields.get("key_risk"):
        score_fields["key_risk"] = key_risk or str(tmpl.get("key_risk") or "无明显额外风险")
    if not score_fields.get("score_details"):
        score_fields["score_details"] = _uniform_score_details(
            float(score_fields["score"]), brief,
        )

    return {
        "sha": sha,
        "dev_module": str(data.get("dev_module", "") or ""),
        "analysis_depth": "minimal",
        "low_risk_reason": reason,
        "modification_interpretation": brief,
        "problem_solved": brief,
        "introducer_analysis": "",
        "introduced_risk": "",
        "code_changes": [
            {"location": "规则判定", "explanation": brief},
        ],
        "patch_tags": [],
        "crash_risk": "无",
        "crash_risk_reason": "",
        "test_suggestions": "",
        **score_fields,
    }


def _build_module_analysis_prompt() -> str:
    return load_prompt("module_analysis")


def generate_module_analysis(
    task: Dict[str, Any],
    module_name: str,
    patches: List[Dict[str, Any]],
    stats: Dict[str, Any],
    code_tree: Dict[str, Any],
    diff_stat: str,
    patch_digest: str,
    config: Optional[Dict[str, str]] = None,
    module_diff: str = "",
    module_description: str = "",
    high_risk_evidence: str = "",
    risk_index: str = "",
) -> Dict[str, Any]:
    """LLM 生成单个模块的结构化分析报告。"""
    if config is None:
        config = get_llm_config()

    from web_app.module_analysis_service import format_code_tree_text
    from web_app.module_chunk_service import (
        HIGH_RISK_EVIDENCE_TOTAL_CHARS,
        MODULE_DIFF_MAX_CHARS,
        PATCH_DIGEST_MAX_CHARS,
    )

    tree_text = format_code_tree_text(code_tree)
    repo = task.get("repo", "")
    from_tag = task.get("from_tag", "")
    to_tag = task.get("to_tag", "")

    diff_section = ""
    diff_truncated = bool(module_diff and "(diff truncated" in module_diff)
    if module_diff and not module_diff.startswith("(") and not diff_truncated:
        diff_section = f"""## 模块相关 Diff（本模块路径过滤后的合并 diff，代码分析主依据）
```diff
{module_diff[:MODULE_DIFF_MAX_CHARS]}
```"""
    elif module_diff and diff_truncated:
        diff_section = (
            "## 模块相关 Diff\n"
            "(模块 diff 过大已省略，请主要依据 Patch 摘要、结构化索引与高风险 diff 证据)"
        )
    else:
        diff_section = "## 模块相关 Diff\n(本地仓库不可用或未匹配到路径，请主要依据 Patch 摘要与 diff --stat)"

    evidence_section = ""
    if high_risk_evidence:
        evidence_section = f"""## 高风险 Patch 关键 Diff（优先参考）
{high_risk_evidence[:HIGH_RISK_EVIDENCE_TOTAL_CHARS]}
"""
    index_section = ""
    if risk_index:
        index_section = f"""## 模块 Patch 结构化索引（全量）
{risk_index[:12000]}
"""

    desc_block = ""
    if module_description:
        desc_block = f"\n- 模块说明: {module_description}"

    user_msg = f"""## 任务
- 仓库: {repo}
- 区间: {from_tag} → {to_tag}
- 模块: {module_name}{desc_block}

## 模块统计
- Patch 数: {stats.get('patch_count', 0)}
- 变更文件: {stats.get('files_changed', 0)}
- 增删行: +{stats.get('insertions', 0)}/-{stats.get('deletions', 0)}
- 平均分: {stats.get('avg_score', 0)}
- 阻断: {stats.get('blocked_count', 0)}
- 中/高死机标记笔数: {stats.get('elevated_crash_count', 0)}

## 代码树（按目录聚合，数字为涉及 patch 数）
```
{tree_text[:8000]}
```

## Git diff --stat（模块相关路径）
```
{diff_stat[:8000] if diff_stat else '(无)'}
```

{diff_section}

{evidence_section}

{index_section}

## 模块内 Patch 详细摘要（含单笔 LLM/脚本分析结论）
{patch_digest[:PATCH_DIGEST_MAX_CHARS]}
"""

    try:
        response, usage = _call_llm(_build_module_analysis_prompt(), user_msg, config, timeout=360)
        yaml_text = _extract_yaml(response)
        data = _safe_load_llm_yaml(yaml_text)
        if not isinstance(data, dict):
            raise ValueError("invalid yaml")

        checklist = data.get("verification_checklist", []) or []
        if isinstance(checklist, str):
            checklist = [line.strip() for line in checklist.splitlines() if line.strip()]

        code_changes = data.get("code_changes", []) or []
        normalized_changes = []
        for item in code_changes:
            if not isinstance(item, dict):
                continue
            normalized_changes.append({
                "location": str(item.get("location", "") or ""),
                "explanation": str(item.get("explanation", "") or ""),
                "risk_level": str(item.get("risk_level", "") or ""),
            })

        high_risk = data.get("high_risk_patches", []) or []
        normalized_high_risk = []
        for item in high_risk[:8]:
            if not isinstance(item, dict):
                continue
            normalized_high_risk.append({
                "sha": str(item.get("sha", "") or "").strip(),
                "title": str(item.get("title", "") or ""),
                "reason": str(item.get("reason", "") or ""),
            })

        from web_app.analyzer_service import backfill_high_risk_patch_reason
        normalized_high_risk = [
            backfill_high_risk_patch_reason(patches, item)
            for item in normalized_high_risk
        ]

        result = {
            "modification_interpretation": str(data.get("modification_interpretation", "") or ""),
            "impact_scope": str(data.get("impact_scope", "") or ""),
            "problem_closure_summary": str(data.get("problem_closure_summary", "") or ""),
            "code_changes": normalized_changes,
            "test_suggestions": str(data.get("test_suggestions", "") or ""),
            "verification_checklist": checklist,
            "crash_risk": str(data.get("crash_risk", "低") or "低"),
            "crash_risk_reason": str(data.get("crash_risk_reason", "") or ""),
            "high_risk_patches": normalized_high_risk,
            "cross_module_notes": str(data.get("cross_module_notes", "") or ""),
            "llm_generated": True,
        }
        if usage:
            result["usage"] = usage
        return result
    except Exception as exc:
        print(f"[MODULE LLM] {module_name} 分析失败: {exc}", flush=True)
        from web_app.module_analysis_service import _script_module_analysis
        return _script_module_analysis(module_name, patches, stats, code_tree)


def _build_module_chunk_summary_prompt() -> str:
    return load_prompt("module_chunk_summary")


def _normalize_chunk_summary(
    data: Dict[str, Any],
    chunk: Dict[str, Any],
    module_name: str,
    patches: List[Dict[str, Any]],
    truncated_input: bool,
) -> Dict[str, Any]:
    from web_app.analyzer_service import backfill_high_risk_patch_reason
    from web_app.module_chunk_service import patch_sha

    covered = data.get("covered_shas") or []
    if isinstance(covered, str):
        covered = [covered]
    if not covered:
        covered = [patch_sha(p)[:12] for p in patches if patch_sha(p)]

    high_risk = data.get("high_risk_patches") or []
    normalized_high_risk = []
    for item in high_risk[:8]:
        if not isinstance(item, dict):
            continue
        normalized_high_risk.append(
            backfill_high_risk_patch_reason(patches, {
                "sha": str(item.get("sha", "") or "").strip(),
                "title": str(item.get("title", "") or ""),
                "reason": str(item.get("reason", "") or ""),
            })
        )

    return {
        "chunk_id": str(data.get("chunk_id") or chunk.get("chunk_id") or ""),
        "module": str(data.get("module") or module_name),
        "patch_count": int(data.get("patch_count") or len(patches)),
        "covered_shas": [str(s)[:12] for s in covered if s],
        "files_changed": int(data.get("files_changed") or 0),
        "main_changes": str(data.get("main_changes", "") or ""),
        "risk_points": str(data.get("risk_points", "") or ""),
        "high_risk_patches": normalized_high_risk,
        "test_focus": str(data.get("test_focus", "") or ""),
        "coverage_note": str(data.get("coverage_note", "") or ""),
        "truncated_input": bool(data.get("truncated_input", truncated_input)),
    }


def generate_module_chunk_summary(
    task: Dict[str, Any],
    module_name: str,
    chunk: Dict[str, Any],
    code_tree: Dict[str, Any],
    diff_stat: str,
    patch_digest: str,
    config: Optional[Dict[str, str]] = None,
    module_diff: str = "",
    truncated_input: bool = False,
    module_description: str = "",
    high_risk_evidence: str = "",
) -> Dict[str, Any]:
    """LLM 生成单个模块 chunk 的结构化摘要。"""
    if config is None:
        config = get_llm_config()

    from web_app.module_analysis_service import format_code_tree_text
    from web_app.module_chunk_service import (
        CHUNK_MAX_DIFF_CHARS,
        HIGH_RISK_EVIDENCE_TOTAL_CHARS,
        PATCH_DIGEST_MAX_CHARS,
    )

    patches = chunk.get("patches") or []
    tree_text = format_code_tree_text(code_tree)
    repo = task.get("repo", "")
    from_tag = task.get("from_tag", "")
    to_tag = task.get("to_tag", "")

    diff_section = ""
    if module_diff and not module_diff.startswith("("):
        diff_section = f"""## Chunk Diff
```diff
{module_diff[:CHUNK_MAX_DIFF_CHARS]}
```"""
    else:
        diff_section = "## Chunk Diff\n(本地仓库不可用或未匹配到路径，请主要依据 Patch 摘要)"

    evidence_section = ""
    if high_risk_evidence:
        evidence_section = f"""## 高风险 Patch 关键 Diff（优先参考）
{high_risk_evidence[:HIGH_RISK_EVIDENCE_TOTAL_CHARS]}
"""

    desc_block = f"\n- 模块说明: {module_description}" if module_description else ""

    user_msg = f"""## 任务
- 仓库: {repo}
- 区间: {from_tag} → {to_tag}
- 模块: {module_name}
- Chunk: {chunk.get('chunk_id', '')}（目录提示: {chunk.get('dir_hint', '')}）{desc_block}
- Patch 数: {len(patches)}
- Diff 输入截断: {'是' if truncated_input else '否'}

## 代码树
```
{tree_text[:6000]}
```

## Git diff --stat
```
{diff_stat[:6000] if diff_stat else '(无)'}
```

{diff_section}

{evidence_section}

## Patch 摘要
{patch_digest[:PATCH_DIGEST_MAX_CHARS]}
"""

    try:
        response, usage = _call_llm(
            _build_module_chunk_summary_prompt(), user_msg, config, timeout=300,
        )
        yaml_text = _extract_yaml(response)
        data = _safe_load_llm_yaml(yaml_text)
        if not isinstance(data, dict):
            raise ValueError("invalid yaml")
        result = _normalize_chunk_summary(data, chunk, module_name, patches, truncated_input)
        if usage:
            result["usage"] = usage
        return result
    except Exception as exc:
        print(
            f"[MODULE CHUNK LLM] {module_name}/{chunk.get('chunk_id')} 失败: {exc}",
            flush=True,
        )
        from web_app.module_chunk_service import patch_sha
        return {
            "chunk_id": chunk.get("chunk_id", ""),
            "module": module_name,
            "patch_count": len(patches),
            "covered_shas": [patch_sha(p)[:12] for p in patches if patch_sha(p)],
            "files_changed": len({f for p in patches for f in (p.get("files") or []) if f}),
            "main_changes": f"Chunk 含 {len(patches)} 笔 patch（LLM 摘要失败，已保留覆盖信息）",
            "risk_points": "",
            "high_risk_patches": [],
            "test_focus": "",
            "coverage_note": "LLM chunk 摘要失败，已保留 patch 覆盖列表",
            "truncated_input": truncated_input,
            "llm_generated": False,
        }


def _format_chunk_summaries_for_rollup(chunk_summaries: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for cs in chunk_summaries:
        lines.append(f"### {cs.get('chunk_id', 'chunk')} ({cs.get('patch_count', 0)} patches)")
        if cs.get("main_changes"):
            lines.append(f"**主要变更**: {cs['main_changes'][:1200]}")
        if cs.get("risk_points"):
            lines.append(f"**风险点**: {cs['risk_points'][:800]}")
        if cs.get("test_focus"):
            lines.append(f"**测试重点**: {cs['test_focus'][:600]}")
        if cs.get("high_risk_patches"):
            for item in cs["high_risk_patches"][:5]:
                lines.append(
                    f"- 高风险 `{item.get('sha', '')}` {item.get('title', '')}: {item.get('reason', '')[:120]}"
                )
        if cs.get("truncated_input"):
            lines.append("- ⚠ 本 chunk diff 输入被截断")
        lines.append("")
    return "\n".join(lines)


def generate_module_rollup_summary(
    task: Dict[str, Any],
    module_name: str,
    patches: List[Dict[str, Any]],
    stats: Dict[str, Any],
    code_tree: Dict[str, Any],
    chunk_summaries: List[Dict[str, Any]],
    config: Optional[Dict[str, str]] = None,
    diff_stat: str = "",
    module_description: str = "",
    high_risk_evidence: str = "",
    risk_index: str = "",
) -> Dict[str, Any]:
    """将多个 chunk summary 汇总为模块最终报告。"""
    if config is None:
        config = get_llm_config()

    from web_app.module_chunk_service import HIGH_RISK_EVIDENCE_TOTAL_CHARS

    chunk_block = _format_chunk_summaries_for_rollup(chunk_summaries)
    repo = task.get("repo", "")
    from_tag = task.get("from_tag", "")
    to_tag = task.get("to_tag", "")

    desc_block = f"\n- 模块说明: {module_description}" if module_description else ""
    evidence_block = ""
    if high_risk_evidence:
        evidence_block = f"""
## 高风险 Patch 关键 Diff
{high_risk_evidence[:HIGH_RISK_EVIDENCE_TOTAL_CHARS]}
"""
    index_block = ""
    if risk_index:
        index_block = f"""
## 模块 Patch 结构化索引（全量）
{risk_index[:12000]}
"""
    user_msg = f"""## 任务
- 仓库: {repo}
- 区间: {from_tag} → {to_tag}
- 模块: {module_name}{desc_block}
- 总 Patch 数: {stats.get('patch_count', 0)}
- Chunk 数: {len(chunk_summaries)}

## 模块统计
- 变更文件: {stats.get('files_changed', 0)}
- 增删行: +{stats.get('insertions', 0)}/-{stats.get('deletions', 0)}
- 平均分: {stats.get('avg_score', 0)}
- 阻断: {stats.get('blocked_count', 0)}

## Git diff --stat（模块级）
```
{diff_stat[:8000] if diff_stat else '(无)'}
```

## Chunk 摘要（已全部覆盖模块 patch，请综合归纳）
{chunk_block[:30000]}
{evidence_block}
{index_block}

请基于以上 chunk 摘要与结构化索引生成模块最终报告。不要遗漏 chunk 中提到的风险点；diff 截断处请依赖高风险证据与 patch 索引。
"""

    try:
        response, usage = _call_llm(_build_module_analysis_prompt(), user_msg, config, timeout=360)
        yaml_text = _extract_yaml(response)
        data = _safe_load_llm_yaml(yaml_text)
        if not isinstance(data, dict):
            raise ValueError("invalid yaml")

        checklist = data.get("verification_checklist", []) or []
        if isinstance(checklist, str):
            checklist = [line.strip() for line in checklist.splitlines() if line.strip()]

        code_changes = data.get("code_changes", []) or []
        normalized_changes = []
        for item in code_changes:
            if not isinstance(item, dict):
                continue
            normalized_changes.append({
                "location": str(item.get("location", "") or ""),
                "explanation": str(item.get("explanation", "") or ""),
                "risk_level": str(item.get("risk_level", "") or ""),
            })

        high_risk = data.get("high_risk_patches", []) or []
        normalized_high_risk = []
        for item in high_risk[:8]:
            if not isinstance(item, dict):
                continue
            normalized_high_risk.append({
                "sha": str(item.get("sha", "") or "").strip(),
                "title": str(item.get("title", "") or ""),
                "reason": str(item.get("reason", "") or ""),
            })

        from web_app.analyzer_service import backfill_high_risk_patch_reason
        normalized_high_risk = [
            backfill_high_risk_patch_reason(patches, item)
            for item in normalized_high_risk
        ]

        result = {
            "modification_interpretation": str(data.get("modification_interpretation", "") or ""),
            "impact_scope": str(data.get("impact_scope", "") or ""),
            "problem_closure_summary": str(data.get("problem_closure_summary", "") or ""),
            "code_changes": normalized_changes,
            "test_suggestions": str(data.get("test_suggestions", "") or ""),
            "verification_checklist": checklist,
            "crash_risk": str(data.get("crash_risk", "低") or "低"),
            "crash_risk_reason": str(data.get("crash_risk_reason", "") or ""),
            "high_risk_patches": normalized_high_risk,
            "cross_module_notes": str(data.get("cross_module_notes", "") or ""),
            "llm_generated": True,
            "rollup_from_chunks": True,
            "chunk_count": len(chunk_summaries),
        }
        if usage:
            result["usage"] = usage
        return result
    except Exception as exc:
        print(f"[MODULE ROLLUP LLM] {module_name} 失败: {exc}", flush=True)
        from web_app.module_analysis_service import _script_module_analysis
        fallback = _script_module_analysis(module_name, patches, stats, code_tree)
        fallback["rollup_from_chunks"] = True
        fallback["chunk_count"] = len(chunk_summaries)
        return fallback


# ── Prompt template (legacy constant, use _build_system_prompt() instead) ──
SYSTEM_PROMPT = _build_system_prompt()


def _build_user_message(
    sha: str,
    title: str,
    msg: str,
    diff: str,
    *,
    max_diff: int = 8000,
    files: Optional[List[str]] = None,
    path_hint: str = "",
) -> str:
    # Truncate very long diffs to avoid token overflow
    MAX_DIFF = max(500, max_diff)
    if len(diff) > MAX_DIFF:
        diff = diff[:MAX_DIFF] + "\n... (diff truncated)"
    MAX_MSG = 4000 if max_diff >= 8000 else 1500
    if len(msg) > MAX_MSG:
        msg = msg[:MAX_MSG] + "\n... (commit message truncated)"

    files_section = ""
    if files:
        preview = files[:20]
        files_section = "\n### 变更文件\n" + "\n".join(f"- {fp}" for fp in preview)
        if len(files) > 20:
            files_section += f"\n- …(+{len(files) - 20} more)"

    hint_section = ""
    if path_hint:
        hint_section = (
            f"\n> 路径规则参考模块：**{path_hint}**"
            "（仅供参考，请结合变更文件、diff 内容与 commit message 综合判断 dev_module）\n"
        )

    return f"""## Patch: `{sha}`
**标题**: {title}
{files_section}{hint_section}
### Commit Message
```
{msg}
```

### Diff 预览
```diff
{diff}
```"""


# ── API call ────────────────────────────────────────────
_HTTP_CLIENTS: Dict[str, httpx.Client] = {}
_HTTP_CLIENT_LOCK = threading.Lock()


def _get_llm_http_client(api_base: str) -> httpx.Client:
    """Reuse HTTP connections per API base URL (thread-safe for requests)."""
    key = api_base.rstrip("/")
    with _HTTP_CLIENT_LOCK:
        client = _HTTP_CLIENTS.get(key)
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(300.0, connect=30.0),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=30),
            )
            _HTTP_CLIENTS[key] = client
        return client


def _parse_positive_env_int(name: str) -> Optional[int]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
        return n if n > 0 else None
    except ValueError:
        return None


def resolve_patch_worker_concurrency(
    total_patches: int,
    *,
    env_override_keys: Tuple[str, ...] = (),
) -> int:
    """按 patch 数量自动扩容并发。

    默认每 ``GKI_PATCHES_PER_WORKER``（10）笔 patch 1 路线程，例如 100 笔 → 10 线程。
    可通过 ``GKI_PATCH_WORKER_MAX`` 限制上限；``GKI_PATCH_WORKER_CONCURRENCY`` 或
    *env_override_keys* 中的变量可强制指定固定并发（仍不超过 patch 数）。
    """
    if total_patches <= 0:
        return 1

    for key in env_override_keys:
        fixed = _parse_positive_env_int(key)
        if fixed is not None:
            return max(1, min(fixed, total_patches))

    global_fixed = _parse_positive_env_int("GKI_PATCH_WORKER_CONCURRENCY")
    if global_fixed is not None:
        return max(1, min(global_fixed, total_patches))

    patches_per_worker = max(1, int(os.environ.get("GKI_PATCHES_PER_WORKER", "10")))
    max_workers = max(1, int(os.environ.get("GKI_PATCH_WORKER_MAX", "128")))

    workers = (total_patches + patches_per_worker - 1) // patches_per_worker
    return max(1, min(workers, total_patches, max_workers))


def resolve_llm_concurrency(total_patches: int) -> int:
    """LLM 单笔分析线程数；``GKI_LLM_CONCURRENCY`` 可覆盖为固定值。"""
    return resolve_patch_worker_concurrency(
        total_patches,
        env_override_keys=("GKI_LLM_CONCURRENCY",),
    )


def resolve_defect_scan_concurrency(total_patches: int) -> int:
    """死机规则扫描线程数；``GKI_DEFECT_SCAN_WORKERS`` 可覆盖为固定值。"""
    return resolve_patch_worker_concurrency(
        total_patches,
        env_override_keys=("GKI_DEFECT_SCAN_WORKERS",),
    )


def resolve_collect_concurrency(total_patches: int) -> int:
    """数据采集阶段并发；``GKI_COLLECT_CONCURRENCY`` 可覆盖为固定值。"""
    return resolve_patch_worker_concurrency(
        total_patches,
        env_override_keys=("GKI_COLLECT_CONCURRENCY",),
    )


def resolve_module_worker_concurrency(module_count: int) -> int:
    """分模块 LLM 分析线程数。

    每个模块视作约 ``GKI_MODULE_PATCH_WEIGHT``（默认 10）笔 patch 的 LLM 负载，
    再按 patch 同款比例自动扩容，且不超过模块总数。
    ``GKI_MODULE_WORKER_CONCURRENCY`` 可覆盖为固定值。
    """
    if module_count <= 0:
        return 1

    fixed = _parse_positive_env_int("GKI_MODULE_WORKER_CONCURRENCY")
    if fixed is not None:
        return max(1, min(fixed, module_count))

    weight = max(1, int(os.environ.get("GKI_MODULE_PATCH_WEIGHT", "10")))
    workers = resolve_patch_worker_concurrency(module_count * weight)
    return max(1, min(workers, module_count))


def resolve_interval_worker_concurrency(interval_count: int) -> int:
    """子 tag 累计区间统计并发（CPU 切片，通常可全区间并行）。

    ``GKI_MONTHLY_INTERVAL_WORKERS`` 可覆盖为固定值；否则为区间数与
    ``GKI_PATCH_WORKER_MAX`` 的较小值。
    """
    if interval_count <= 0:
        return 1

    fixed = _parse_positive_env_int("GKI_MONTHLY_INTERVAL_WORKERS")
    if fixed is not None:
        return max(1, min(fixed, interval_count))

    max_workers = max(1, int(os.environ.get("GKI_PATCH_WORKER_MAX", "128")))
    return max(1, min(interval_count, max_workers))


def _call_llm(system: str, user: str, config: Dict[str, str],
              timeout: int = 300, max_tokens: int = 4096,
              max_attempts: int = 3) -> Tuple[str, Dict[str, Any]]:
    """Make a chat completion request to an OpenAI-compatible API.
    Returns (content, usage_dict) where usage_dict contains prompt_tokens,
    completion_tokens, total_tokens, and finish_reason when the API provides them.
    """
    api_base = config['api_base'].rstrip('/')
    if api_base.endswith('/chat/completions'):
        api_base = api_base[:-len('/chat/completions')]
    url = f"{api_base}/chat/completions"
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
        "User-Agent": "gki-patch-analyzer/1.0",
    }

    client = _get_llm_http_client(api_base)
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            resp = client.post(url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            usage = data.get("usage", None) or {}
            usage_clean: Dict[str, Any] = {
                k: int(v) for k, v in usage.items()
                if k in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
            finish_reason = str(choice.get("finish_reason") or "").strip()
            if finish_reason:
                usage_clean["finish_reason"] = finish_reason
            return content, usage_clean
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError(f"LLM API 请求失败: {exc}") from exc
        except (KeyError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"LLM API 响应格式异常: {exc}") from exc
    raise RuntimeError(f"LLM API 请求失败: {last_exc}")


# ── Response parsing ───────────────────────────────────
def _extract_yaml(text: str) -> str:
    """Extract YAML block from LLM response (strip markdown fences)."""
    # Try ```yaml ... ``` block first
    m = re.search(r"```(?:yaml)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Fallback: try to parse the whole response as YAML
    return text.strip()


def _repair_llm_yaml(text: str) -> str:
    """Repair common LLM YAML breakage so PyYAML can parse again.

    Typical failure: double-quoted scalars with raw inner quotes, e.g.
      reason: "… domain ("00") …"
    Convert those values to block scalars.
    """
    out: List[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip("\r")
        # key: "value"  or  - key: "value"
        m = re.match(r'^(\s*(?:-\s+)?[\w./\-]+)\s*:\s*"(.*)"\s*$', line)
        if m:
            prefix, content = m.group(1), m.group(2)
            if re.search(r'(?<!\\)"', content):
                indent = re.match(r"^(\s*)", line).group(1)
                content = content.replace('\\"', '"')
                out.append(f"{prefix}: |")
                out.append(f"{indent}  {content}")
                continue
        # list item that is itself a broken quoted string: - "foo "bar" baz"
        m2 = re.match(r'^(\s*-\s+)"(.*)"\s*$', line)
        if m2 and re.search(r'(?<!\\)"', m2.group(2)):
            indent = re.match(r"^(\s*)", line).group(1)
            content = m2.group(2).replace('\\"', '"')
            out.append(f"{indent}- |")
            out.append(f"{indent}  {content}")
            continue
        out.append(line)
    return "\n".join(out)


def _safe_load_llm_yaml(text: str) -> Any:
    """yaml.safe_load with one automatic repair pass for LLM quote issues."""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as first_exc:
        repaired = _repair_llm_yaml(raw)
        if repaired == raw:
            raise first_exc
        try:
            data = yaml.safe_load(repaired)
            print("[LLM YAML] 已自动修复未转义引号后重新解析成功", flush=True)
            return data
        except yaml.YAMLError:
            raise first_exc


def _parse_llm_result(sha: str, content: str) -> Dict[str, Any]:
    """Parse LLM response into a structured analysis dict."""
    yaml_text = _extract_yaml(content)
    try:
        data = _safe_load_llm_yaml(yaml_text)
    except yaml.YAMLError as exc:
        # Try lenient: just extract raw text fields
        return _fallback_parse(sha, content)

    if not isinstance(data, dict):
        return _fallback_parse(sha, content)

    score_fields = _parse_llm_score_fields(data)
    return {
        "sha": sha,
        **score_fields,
        "dev_module": str(data.get("dev_module", "") or ""),
        "patch_tags": data.get("patch_tags", []),
        "modification_interpretation": str(data.get("modification_interpretation", "") or ""),
        "code_changes": data.get("code_changes", []),
        "problem_solved": str(data.get("problem_solved", "") or ""),
        "introducer_analysis": str(data.get("introducer_analysis", "") or ""),
        "introduced_risk": str(data.get("introduced_risk", "") or ""),
        "crash_risk": str(data.get("crash_risk", "无") or "无"),
        "crash_risk_reason": str(data.get("crash_risk_reason", "") or ""),
        "test_suggestions": str(data.get("test_suggestions", "") or ""),
    }


def _fallback_parse(sha: str, content: str) -> Dict[str, Any]:
    """Fallback: treat the whole response as plain text."""
    return {
        "sha": sha,
        "modification_interpretation": content[:2000],
        "code_changes": [{"location": "综合", "explanation": content[:2000]}],
        "problem_solved": content[:2000],
        "introducer_analysis": "",
        "introduced_risk": "",
        "crash_risk": "无",
        "crash_risk_reason": "",
        "test_suggestions": content[:1000],
    }


def is_llm_analysis_result_effective(
    result: Any,
    mode: str = "lightweight",
) -> bool:
    """判断 LLM 解析结果是否含有效评分或解读（否则应重试）。"""
    if not isinstance(result, dict):
        return False
    try:
        score = float(result.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    if score > 0:
        return True

    texts = [
        str(result.get("modification_interpretation") or "").strip(),
        str(result.get("problem_solved") or "").strip(),
        str(result.get("key_risk") or "").strip(),
    ]
    min_len = 8 if mode in ("minimal", "rule_minimal") else 12
    return any(len(text) >= min_len for text in texts)


# ── Public entry point ─────────────────────────────────
def analyze_patch_via_llm(patch_data: Dict[str, Any],
                          config: Optional[Dict[str, str]] = None,
                          mode: str = "full",
                          scoring_config: Optional[Dict[str, Any]] = None,
                          low_risk_reason: str = "") -> Dict[str, Any]:
    """Analyze a single patch via LLM API. Returns parsed analysis dict.

    mode:
      - "full": 单 SHA 全量分析
      - "lightweight": 区间单笔完整解读
      - "minimal": 低风险短分析（仍调 LLM）
      - "rule_minimal": 规则免 LLM，输出结构与 minimal 一致
    """
    if config is None:
        config = get_llm_config()

    if not low_risk_reason and mode in ("minimal", "rule_minimal"):
        _, low_risk_reason = classify_low_risk_patch(patch_data, scoring_config)

    if mode == "rule_minimal":
        return build_rule_based_minimal_result(
            patch_data, low_risk_reason, scoring_config=scoring_config,
        )

    sha = patch_data.get("commit", "")[:12]
    title = patch_data.get("title", "")
    msg = patch_data.get("commit_message_full", "")
    diff_raw = patch_data.get("diff_preview", {})
    diff = diff_raw.get("text", "") if isinstance(diff_raw, dict) else str(diff_raw)
    files = _patch_changed_files(patch_data)

    from web_app.dev_module_classifier import path_hint_for_patch

    path_hint = path_hint_for_patch(patch_data)
    max_diff = 2000 if mode == "minimal" else 8000
    user_msg = _build_user_message(
        sha, title, msg, diff,
        max_diff=max_diff,
        files=files,
        path_hint=path_hint,
    )
    if mode == "minimal":
        prompt = _build_minimal_system_prompt()
        response, usage = _call_llm(prompt, user_msg, config)
        result = _parse_minimal_llm_result(
            patch_data.get("commit", ""),
            response,
            low_risk_reason=low_risk_reason,
        )
    elif mode == "lightweight":
        prompt = _build_lightweight_system_prompt()
        response, usage = _call_llm(prompt, user_msg, config)
        result = _parse_lightweight_llm_result(patch_data.get("commit", ""), response)
        result["analysis_depth"] = "full"
    else:
        prompt = _build_system_prompt()
        response, usage = _call_llm(prompt, user_msg, config)
        result = _parse_llm_result(patch_data.get("commit", ""), response)
        result["analysis_depth"] = "full"
    if usage:
        result["usage"] = usage
    return result


# ── Merge into patch data (reuses logic from merge_llm_analysis.py) ──
def merge_llm_result(patch_data: Dict[str, Any], llm_result: Dict[str, Any]) -> Dict[str, Any]:
    """Merge LLM analysis result into the patch data dict (in-place)."""
    a = llm_result

    # commit_interpretation_rich
    patch_data["commit_interpretation_rich"] = {
        "title": patch_data.get("title", ""),
        "problem_context": "",
        "constraint_context": "",
        "summary": a.get("modification_interpretation", ""),
        "signals": [],
        "references": [],
        "fixes_closes": [],
        "llm_generated": True,
    }

    # code_change_analysis_rich
    raw_changes = a.get("code_changes", [])
    if not raw_changes:
        raw_changes = [{"location": "综合", "explanation": a.get("modification_interpretation", "")}]
    patch_data["code_change_analysis_rich"] = {
        "summary": "",
        "touched_directories": [],
        "files_stat": [],
        "logic_changes": [
            {"location": c.get("location", ""), "explanation": c.get("explanation", ""), "before": "", "after": ""}
            for c in raw_changes
        ],
        "llm_generated": True,
    }

    # problem_closure_rich
    patch_data["problem_closure_rich"] = {
        "status": "已分析",
        "confidence": "高",
        "evidence": [],
        "conclusion": a.get("problem_solved", ""),
        "why_fixed": a.get("problem_solved", ""),
        "missing_evidence": "",
        "acceptance": "",
        "llm_generated": True,
    }

    # problem_introducer_rich
    text = a.get("introducer_analysis", "")
    detected = bool(text) and "未识别" not in text and "不适用" not in text
    patch_data["problem_introducer_rich"] = {
        "detected": detected,
        "confidence": "高" if detected else "低",
        "detection_method": "LLM分析（commit + 代码比对）",
        "summary": text,
        "introducer_commit": "",
        "introducer_title": "",
        "introducer_commit_url": "",
        "introducer_diff_url": "",
        "introduced_change_summary": "",
        "why_introduced": "",
        "evidence": [],
        "llm_generated": True,
    }

    # introduced_risk (本次修改可能引入的问题)
    introduced_risk = a.get("introduced_risk", "")
    if introduced_risk:
        patch_data["introduced_risk"] = introduced_risk

    # crash_risk (死机风险评估)
    crash_risk = a.get("crash_risk", "无")
    if crash_risk and crash_risk != "无":
        patch_data["crash_risk"] = crash_risk
        crash_risk_reason = a.get("crash_risk_reason", "")
        if crash_risk_reason:
            patch_data["crash_risk_reason"] = crash_risk_reason

    # Test suggestions
    ts = a.get("test_suggestions", "")
    if ts:
        patch_data["llm_test_suggestions"] = ts

    # Score & recommendation from LLM（未返回有效评分时不写入，由 _enrich_llm_patch 补结构字段）
    score = a.get("score", None)
    if score is not None and float(score or 0) > 0:
        patch_data["score"] = max(float(score), 0.0)
    rec = a.get("recommendation", "")
    if rec:
        patch_data["recommendation"] = rec
    risk = a.get("key_risk", "")
    if risk:
        patch_data["key_risk"] = risk

    # Per-dimension score_details from LLM (if provided)
    sd = a.get("score_details", {}) or {}
    if sd and isinstance(sd, dict):
        patch_data["score_details"] = sd

    # Patch tags from LLM
    tags = a.get("patch_tags", [])
    if tags:
        patch_data["patch_tags"] = tags

    # Dev module classification（仅接受 dev_modules.txt 中的合法模块名）
    from web_app.dev_module_classifier import normalize_dev_module_name
    dev_module = normalize_dev_module_name(str(a.get("dev_module", "") or ""))
    if dev_module:
        patch_data["dev_module"] = dev_module

    analysis_depth = str(a.get("analysis_depth") or "full")
    patch_data["analysis_depth"] = analysis_depth
    low_risk_reason = str(a.get("low_risk_reason") or "").strip()
    if low_risk_reason:
        patch_data["low_risk_reason"] = low_risk_reason
    if a.get("rule_based"):
        patch_data["rule_based"] = True

    # Store token usage in patch_data
    usage = a.get("usage", None)
    if usage:
        patch_data["llm_usage"] = usage

    patch_data["llm_analyzed"] = True
    return patch_data


# ── Task-level unified report ──────────────────────────

_ANALYSIS_SUMMARY_MARKER = "<<<ANALYSIS_SUMMARY>>>"
_TEST_RECOMMENDATIONS_MARKER = "<<<TEST_RECOMMENDATIONS>>>"


def parse_unified_task_report(content: str) -> Dict[str, str]:
    """Split unified LLM output into summary and test recommendation sections."""
    text = (content or "").strip()
    if not text:
        return {"summary": "", "test_summary": ""}
    if _ANALYSIS_SUMMARY_MARKER in text and _TEST_RECOMMENDATIONS_MARKER in text:
        _, rest = text.split(_ANALYSIS_SUMMARY_MARKER, 1)
        summary_part, test_part = rest.split(_TEST_RECOMMENDATIONS_MARKER, 1)
        return {
            "summary": summary_part.strip(),
            "test_summary": test_part.strip(),
        }
    return {"summary": text, "test_summary": ""}


def _build_patch_analysis_block(
    patches: List[Dict[str, Any]],
    *,
    max_patches: int = 70,
) -> str:
    lines: List[str] = []
    for p in patches:
        sha = p.get("sha", "?")[:12]
        title = (p.get("title") or "-")[:100]
        score = p.get("score", 0) or 0
        risk = p.get("key_risk", "") or ""
        recommendation = p.get("recommendation", "") or ""
        blocked = p.get("blocked", False)
        tags_list = []
        for t in (p.get("patch_tags") or []):
            if isinstance(t, dict):
                label = (t.get("label") or "").strip()
                if label:
                    tags_list.append(label)
        tags_str = ",".join(tags_list) if tags_list else "-"
        dev_mod = p.get("dev_module", "") or "-"
        files = p.get("files") or []
        file_hint = f" | {len(files)}文件" if files else ""
        llm_note = ""
        if p.get("llm_analyzed"):
            data_raw = p.get("data") or p
            if isinstance(data_raw, str):
                try:
                    data_raw = json.loads(data_raw)
                except Exception:
                    data_raw = {}
            interp = (data_raw.get("commit_interpretation_rich") or {}).get("summary", "") or ""
            closure = (data_raw.get("problem_closure_rich") or {}).get("conclusion", "") or ""
            key_risk_llm = (data_raw.get("key_risk") or "") if not risk else ""
            llm_parts = [x for x in [interp[:320], closure[:280], key_risk_llm[:160]] if x]
            llm_note = " | ".join(llm_parts) if llm_parts else ""

        parts = [
            f"- `{sha}` {title} | 分:{score} | 结论:{recommendation or '-'} | 模块:{dev_mod}{file_hint} | 标签:{tags_str}",
        ]
        if blocked:
            parts.append(" ⛔阻断")
        if risk:
            parts.append(f" ⚠{risk[:200]}")
        if llm_note:
            parts.append(f"\n  LLM解读: {llm_note}")
        lines.append("".join(parts))

    if len(lines) > max_patches:
        skipped = len(lines) - max_patches
        lines = lines[:max_patches]
        lines.append(f"\n... 另有 {skipped} 笔 patch 未列出")
    return "\n".join(lines)


def _build_patch_test_block(
    patches: List[Dict[str, Any]],
    *,
    max_patches: int = 45,
) -> str:
    lines: List[str] = []
    for p in patches:
        sha = p.get("sha", "?")[:12]
        title = (p.get("title") or "-")[:60]
        score = p.get("score", 0) or 0
        blocked = p.get("blocked", False)

        ts = p.get("test_suggestions", {}) or {}
        script_test_parts = []
        if isinstance(ts, dict):
            for k in ["unit_test", "integration_test", "regression_test", "manual_validation", "release_safeguard"]:
                v = ts.get(k, "")
                if v:
                    script_test_parts.append(f"{k}: {v}")
        script_test_str = " | ".join(script_test_parts) if script_test_parts else "-"
        llm_test = p.get("llm_test_suggestions", "") or ""

        tags_list = []
        for t in (p.get("patch_tags") or []):
            if isinstance(t, dict):
                label = (t.get("label") or "").strip()
                if label:
                    tags_list.append(label)
        tags_str = ",".join(tags_list) if tags_list else "-"

        parts = [f"- `{sha}` {title}", f"  评分:{score} | 标签:{tags_str}"]
        if blocked:
            parts.append("  阻断: 是")
        if script_test_str != "-":
            parts.append(f"  脚本测试建议: {script_test_str}")
        if llm_test:
            llm_trunc = llm_test[:240] + ("..." if len(llm_test) > 240 else "")
            parts.append(f"  LLM测试建议: {llm_trunc}")
        lines.append("\n".join(parts))

    if len(lines) > max_patches:
        skipped = len(lines) - max_patches
        lines = lines[:max_patches]
        lines.append(f"\n... 另有 {skipped} 笔 patch 未列出")
    return "\n\n".join(lines)


def _build_high_risk_index(
    patches: List[Dict[str, Any]],
    *,
    max_items: int = 80,
) -> str:
    from web_app.analyzer_service import patch_high_risk_reason

    items: List[tuple] = []
    for p in patches:
        reason = patch_high_risk_reason(p)
        if not reason:
            continue
        score = float(p.get("score", 0) or 0)
        blocked = 1 if p.get("blocked") else 0
        items.append((blocked, score, p, reason))
    items.sort(key=lambda x: (-x[0], x[1]))

    lines = [f"共 {len(items)} 笔高风险 patch（展示前 {min(len(items), max_items)} 笔）："]
    for _, _, p, reason in items[:max_items]:
        sha = (p.get("sha") or p.get("commit") or "?")[:12]
        title = (p.get("title") or "-")[:80]
        mod = p.get("dev_module") or "-"
        lines.append(f"- `{sha}` [{p.get('score', 0)}] {title} | 模块:{mod} | {reason[:160]}")
    if len(items) > max_items:
        lines.append(f"... 另有 {len(items) - max_items} 笔高风险 patch")
    return "\n".join(lines)


def _build_blocked_index(patches: List[Dict[str, Any]]) -> str:
    blocked = [p for p in patches if p.get("blocked")]
    if not blocked:
        return "(无阻断 patch)"
    lines = [f"共 {len(blocked)} 笔阻断 patch："]
    for p in blocked[:40]:
        sha = (p.get("sha") or p.get("commit") or "?")[:12]
        title = (p.get("title") or "-")[:80]
        mod = p.get("dev_module") or "-"
        lines.append(f"- `{sha}` {title} | 模块:{mod}")
    if len(blocked) > 40:
        lines.append(f"... 另有 {len(blocked) - 40} 笔")
    return "\n".join(lines)


def _build_module_reports_block(module_summaries_doc: Optional[Dict[str, Any]]) -> str:
    if not module_summaries_doc:
        return "(暂无分模块分析报告，请依据 patch 摘要生成)"
    modules = module_summaries_doc.get("modules") or {}
    if not modules:
        return "(暂无分模块分析报告)"

    lines = [
        f"模块数: {module_summaries_doc.get('module_count', len(modules))}",
        f"总 patch: {module_summaries_doc.get('total_patches', 0)}",
        f"总 chunk: {module_summaries_doc.get('total_chunks', 0)}",
        f"全量覆盖: {'是' if module_summaries_doc.get('coverage_complete') else '否'}",
        "",
    ]
    for mod_name, mod in sorted(
        modules.items(),
        key=lambda item: -int((item[1].get("stats") or {}).get("patch_count", 0) or 0),
    ):
        stats = mod.get("stats") or {}
        analysis = mod.get("analysis") or {}
        coverage = mod.get("coverage") or {}
        lines.append(f"### 模块: {mod_name}")
        lines.append(
            f"- patch: {stats.get('patch_count', 0)} | 文件: {stats.get('files_changed', 0)} | "
            f"均分: {stats.get('avg_score', 0)} | chunk: {coverage.get('chunk_count', 1)} | "
            f"覆盖: {coverage.get('covered_patch_count', 0)}/{coverage.get('total_patch_count', 0)}"
        )
        if coverage.get("truncated_chunk_count"):
            lines.append(f"- ⚠ 截断 chunk: {coverage.get('truncated_chunk_count')}")
        interp = (analysis.get("modification_interpretation") or "")[:800]
        if interp:
            lines.append(f"- 修改解读: {interp}")
        risk = (analysis.get("crash_risk") or "低")
        risk_reason = (analysis.get("crash_risk_reason") or "")[:200]
        lines.append(f"- 死机风险: {risk}" + (f" ({risk_reason})" if risk_reason else ""))
        for item in (analysis.get("high_risk_patches") or [])[:5]:
            lines.append(
                f"  - 高风险 `{item.get('sha', '')}` {item.get('title', '')}: "
                f"{item.get('reason', '')[:120]}"
            )
        test = (analysis.get("test_suggestions") or "")[:500]
        if test:
            lines.append(f"- 测试建议摘要: {test}")
        lines.append("")
    return "\n".join(lines)[:35000]


def generate_unified_task_report(
    task: Dict[str, Any],
    patches: List[Dict[str, Any]],
    squash_diff_path: str = "",
    repo_dir: str = "",
    module_summaries_doc: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, str]]:
    """生成任务级综合分析 + 测试建议（完整 LLM）。

    与单笔 rule_minimal 无关：始终完整调用综合报告 LLM。
    输入含模块报告与 patch 材料（免深析 patch 仍带提交说明/文件列表）。
    """
    if not is_llm_configured():
        return None

    total = len(patches)
    if total == 0:
        return None

    config = get_llm_config()
    repo = task.get("repo", "")
    from_tag = task.get("from_tag", "")
    to_tag = task.get("to_tag", "")
    llm_count = sum(1 for p in patches if p.get("llm_analyzed"))
    script_count = total - llm_count

    squash_section = ""
    stat_text = ""
    has_squash = False
    if squash_diff_path and os.path.isfile(squash_diff_path):
        try:
            with open(squash_diff_path, "r", encoding="utf-8") as f:
                squash_content = f.read()
            has_squash = bool(squash_content.strip())
        except Exception:
            squash_content = ""
            has_squash = False
        if has_squash and repo_dir and from_tag and to_tag:
            try:
                from tools.patch_analyzer import run_git
                from pathlib import Path
                stat_text = run_git(Path(repo_dir), ["diff", "--stat", f"{from_tag}..{to_tag}"])
            except Exception:
                pass
        if has_squash:
            max_diff_chars = 5000
            if len(squash_content) > max_diff_chars:
                truncated = squash_content[:max_diff_chars]
                truncated += f"\n\n... [auxiliary truncated, total {len(squash_content)} chars] ..."
            else:
                truncated = squash_content
            stat_section = (
                f"\n\n## 变更统计（git diff --stat）\n```\n{stat_text[:12000]}\n```"
                if stat_text else ""
            )
            squash_section = f"""## Squash Diff（辅助参考，非主依据）
```diff
{truncated}
```{stat_section}"""

    module_reports_block = _build_module_reports_block(module_summaries_doc)
    high_risk_block = _build_high_risk_index(patches)
    blocked_block = _build_blocked_index(patches)
    has_module_reports = bool(
        module_summaries_doc and (module_summaries_doc.get("modules") or {})
    )

    from web_app.analyzer_service import get_dev_module_names
    mod_names = get_dev_module_names()
    mod_list = "、".join(mod_names) if mod_names else "（无模块定义）"

    primary_basis = (
        "各模块最终分析报告（已分层全量覆盖）"
        if has_module_reports
        else "每一笔 patch 的脚本/LLM 分析结果"
    )
    squash_role = (
        "squash diff 仅作辅助参考"
        if has_module_reports
        else "区间 squash diff（若有）"
    )

    system_prompt = render_prompt(
        "task_unified_report",
        primary_basis=primary_basis,
        squash_role=squash_role,
        dev_module_names=mod_list,
        analysis_summary_marker=_ANALYSIS_SUMMARY_MARKER,
        test_recommendations_marker=_TEST_RECOMMENDATIONS_MARKER,
    )

    patch_block = _build_patch_analysis_block(patches, max_patches=100 if total > 200 else 70)
    test_block = _build_patch_test_block(patches, max_patches=60 if total > 200 else 45)
    squash_note = squash_section if has_squash else "（本任务无 squash diff。）"
    coverage_note = ""
    if module_summaries_doc:
        coverage_note = (
            f"## 分层分析覆盖率\n"
            f"- 模块数: {module_summaries_doc.get('module_count', 0)}\n"
            f"- 总 patch: {module_summaries_doc.get('total_patches', 0)}\n"
            f"- 总 chunk: {module_summaries_doc.get('total_chunks', 0)}\n"
            f"- 全量覆盖: {'是' if module_summaries_doc.get('coverage_complete') else '否'}\n"
        )

    user_prompt = f"""## 任务信息
仓库: {repo}
区间: {from_tag} → {to_tag}
总 patch 数: {total}（LLM 分析 {llm_count} 笔，脚本分析 {script_count} 笔）

{coverage_note}
## 模块分析报告（主依据）
{module_reports_block}

## 高风险 Patch 索引
{high_risk_block}

## 阻断 Patch
{blocked_block}

{squash_note}

## Patch 分析摘要（补充）
{patch_block}

## 每笔 Patch 的测试建议（供综合测试策略参考）
{test_block}

请生成最终综合分析报告。"""

    try:
        content, _ = _call_llm(
            system_prompt, user_prompt, config, timeout=420, max_tokens=8192,
        )
        if not content:
            return None
        parsed = parse_unified_task_report(content)
        if not parsed["summary"]:
            return None
        return parsed
    except Exception as exc:
        print(f"[UNIFIED REPORT LLM] 生成综合报告失败: {exc}", flush=True)
        return None


# ── Task-level summary ─────────────────────────────────

def generate_task_summary(
    task: Dict[str, Any],
    patches: List[Dict[str, Any]],
) -> Optional[str]:
    """Use LLM to generate a natural-language summary for a completed analysis task.
    Returns the summary text (Chinese), or None if LLM is not configured or fails.
    """
    if not is_llm_configured():
        return None

    total = len(patches)
    if total == 0:
        return None

    config = get_llm_config()

    # Build compact patch summaries
    lines: List[str] = []
    for p in patches:
        sha = p.get("sha", "?")[:12]
        title = (p.get("title") or "-")[:80]
        score = p.get("score", 0) or 0
        risk = p.get("key_risk", "") or ""
        blocked = p.get("blocked", False)
        tags_list = []
        for t in (p.get("patch_tags") or []):
            if isinstance(t, dict):
                label = (t.get("label") or "").strip()
                if label:
                    tags_list.append(label)
        tags_str = ",".join(tags_list) if tags_list else "-"
        dev_mod = p.get("dev_module", "") or "-"
        llm_note = ""
        if p.get("llm_analyzed"):
            data_raw = p.get("data") or p
            if isinstance(data_raw, str):
                try:
                    data_raw = json.loads(data_raw)
                except Exception:
                    data_raw = {}
            interp = (data_raw.get("commit_interpretation_rich") or {}).get("summary", "") or ""
            closure = (data_raw.get("problem_closure_rich") or {}).get("conclusion", "") or ""
            llm_note = (interp[:200] + " | " + closure[:200]) if (interp or closure) else ""

        parts = [f"- `{sha}` {title} | 分:{score} | 模块:{dev_mod} | 标签:{tags_str}"]
        if blocked:
            parts.append(" ⛔阻断")
        if risk:
            parts.append(f" ⚠{risk}")
        if llm_note:
            parts.append(f"\n  LLM: {llm_note}")
        lines.append("".join(parts))

    # Limit to ~50 patches to avoid token overflow
    if len(lines) > 50:
        skipped = len(lines) - 50
        lines = lines[:50]
        lines.append(f"\n... 另有 {skipped} 笔 patch 未列出")

    patch_block = "\n".join(lines)

    repo = task.get("repo", "")
    from_tag = task.get("from_tag", "")
    to_tag = task.get("to_tag", "")
    llm_count = sum(1 for p in patches if p.get("llm_analyzed"))
    script_count = total - llm_count

    system_prompt = load_prompt("task_summary")

    user_prompt = f"""## 任务信息
仓库: {repo}
区间: {from_tag} → {to_tag}
总patch数: {total}（LLM分析 {llm_count} 笔，脚本分析 {script_count} 笔）

## Patch 列表摘要
{patch_block}

请生成分析总结。"""

    try:
        content, _ = _call_llm(system_prompt, user_prompt, config, timeout=300)
        return content
    except Exception as exc:
        print(f"[SUMMARY LLM] 生成总结失败: {exc}", flush=True)
        return None


# ── Task-level test suggestions ────────────────────────

def generate_test_summary(
    task: Dict[str, Any],
    patches: List[Dict[str, Any]],
) -> Optional[str]:
    """Use LLM to generate comprehensive test suggestions for a completed task.
    Returns the test suggestions text (Chinese), or None if LLM is not configured or fails.
    """
    if not is_llm_configured():
        return None

    total = len(patches)
    if total == 0:
        return None

    config = get_llm_config()

    # Build per-patch test suggestion summaries
    lines: List[str] = []
    for p in patches:
        sha = p.get("sha", "?")[:12]
        title = (p.get("title") or "-")[:60]
        score = p.get("score", 0) or 0
        blocked = p.get("blocked", False)

        # Script test suggestions
        ts = p.get("test_suggestions", {}) or {}
        script_test_parts = []
        if isinstance(ts, dict):
            for k in ["unit_test", "integration_test", "regression_test", "manual_validation", "release_safeguard"]:
                v = ts.get(k, "")
                if v:
                    script_test_parts.append(f"{k}: {v}")
        script_test_str = " | ".join(script_test_parts) if script_test_parts else "-"

        # LLM test suggestions
        llm_test = p.get("llm_test_suggestions", "") or ""

        # Tags for context
        tags_list = []
        for t in (p.get("patch_tags") or []):
            if isinstance(t, dict):
                label = (t.get("label") or "").strip()
                if label:
                    tags_list.append(label)
        tags_str = ",".join(tags_list) if tags_list else "-"

        parts = [
            f"- `{sha}` {title}",
            f"  评分:{score} | 标签:{tags_str}",
        ]
        if blocked:
            parts.append("  阻断: 是")
        if script_test_str != "-":
            parts.append(f"  脚本测试建议: {script_test_str}")
        if llm_test:
            # Truncate long LLM test suggestions
            llm_trunc = llm_test[:300] + ("..." if len(llm_test) > 300 else "")
            parts.append(f"  LLM测试建议: {llm_trunc}")
        lines.append("\n".join(parts))

    # Limit to ~80 patches to avoid token overflow
    if len(lines) > 80:
        skipped = len(lines) - 80
        lines = lines[:80]
        lines.append(f"\n... 另有 {skipped} 笔 patch 未列出")

    patch_block = "\n\n".join(lines)

    repo = task.get("repo", "")
    from_tag = task.get("from_tag", "")
    to_tag = task.get("to_tag", "")

    system_prompt = load_prompt("task_test_summary")

    user_prompt = f"""## 任务信息
仓库: {repo}
区间: {from_tag} → {to_tag}
总patch数: {total}

## 每笔 Patch 的测试建议
{patch_block}

请生成一份完整的测试策略建议。"""

    try:
        content, _ = _call_llm(system_prompt, user_prompt, config, timeout=300)
        return content
    except Exception as exc:
        print(f"[TEST SUMMARY LLM] 生成测试总结失败: {exc}", flush=True)
        return None


def polish_checklist_cells(
    task: Dict[str, Any],
    items: List[Dict[str, str]],
    *,
    chunk_size: int = 2,
    batch_label: str = "",
) -> Dict[str, Dict[str, str]]:
    """Rewrite checklist cell drafts into reviewer-facing module summaries.

    items: id / module / scope / patch_count / stats / analysis_context / patch_digest / ...
    returns {id: {modification, focus_review, test_suggestions, risk_description}}

    Caller should pass overall and subtag items in **separate** batches so the model
    cannot copy cross-month overall conclusions into monthly sub-tag rows.
    """
    if not items or not is_llm_configured():
        return {}

    from concurrent.futures import ThreadPoolExecutor, as_completed

    config = get_llm_config()
    system = load_prompt("checklist_polish")
    # Never mix overall + subtag in one chunk (defense in depth).
    overall_items = [i for i in items if str(i.get("block_kind") or "") != "subtag"]
    subtag_items = [i for i in items if str(i.get("block_kind") or "") == "subtag"]
    ordered_groups = [g for g in (overall_items, subtag_items) if g]
    if not ordered_groups:
        ordered_groups = [items]

    merged: Dict[str, Dict[str, str]] = {}
    label = f"{batch_label} " if batch_label else ""

    def _run_chunk(chunk: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
        user = _build_checklist_polish_user(task, chunk)
        content, _ = _call_llm(system, user, config, timeout=300, max_tokens=8192)
        return _parse_checklist_polish(content)

    for group in ordered_groups:
        kind = str(group[0].get("block_kind") or "overall")
        chunks = [group[i:i + chunk_size] for i in range(0, len(group), chunk_size)]
        print(
            f"[CHECKLIST LLM] {label}打磨 {kind} {len(group)} 行 / {len(chunks)} 批",
            flush=True,
        )
        workers = max(1, min(4, len(chunks)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_run_chunk, chunk) for chunk in chunks]
            for fut in as_completed(futures):
                try:
                    merged.update(fut.result() or {})
                except Exception as exc:
                    print(f"[CHECKLIST LLM] 表格打磨失败: {exc}", flush=True)
    return merged


def _build_checklist_polish_user(task: Dict[str, Any], chunk: List[Dict[str, str]]) -> str:
    from_tag = str(task.get("from_tag") or "").strip()
    to_tag = str(task.get("to_tag") or "").strip()
    all_subtag = bool(chunk) and all(
        str(item.get("block_kind") or "") == "subtag" for item in chunk
    )
    parts: List[str] = []
    if all_subtag:
        parts.append("本批全部为「目标月份子 tag」行，与跨月总包结论无关。")
        parts.append("请严格按每条的子 tag 累计范围与 patch 摘要重写，禁止复用总包文案。")
    else:
        parts.append(
            f"升级区间：{from_tag} -> {to_tag}" if from_tag or to_tag else "升级区间：未知"
        )
        parts.append("本批为跨月总包行。")
    parts.append("表格只写关键信息；细节在模块详情链接。请精简文案，并保留重点 Review 的 P0/P1 分级。")
    parts.append("请按 id 原样回写，不要合并或删减模块。")
    parts.append("")
    for item in chunk:
        is_subtag = str(item.get("block_kind") or "") == "subtag"
        parts.append(f"## 模块 id={item.get('id')}")
        parts.append(f"模块：{item.get('module') or ''}")
        parts.append(f"范围：{item.get('scope') or ''}")
        parts.append(f"行类型：{'子tag' if is_subtag else '总包'}")
        parts.append(f"patch 数量：{item.get('patch_count') or 0}")
        if is_subtag:
            if item.get("cumulative_scope"):
                parts.append(f"本段范围：{item.get('cumulative_scope')}")
            parts.append(
                "说明：本行只对应相邻增量区间内该模块的 patch。"
                "只根据本条 patch 数量/摘要/草稿撰写，不要补写未出现的模块，"
                "也不要复述跨月总包结论或与其它子 tag 行共用同一段文案。"
            )
        if item.get("stats"):
            parts.append(f"统计：{item.get('stats')}")
        parts.append(f"是否有负面影响：{item.get('negative_impact') or ''}")
        parts.append(f"是否必须合入：{item.get('must_merge') or ''}")
        ctx = str(item.get("analysis_context") or "").strip()
        if ctx and not is_subtag:
            parts.append("模块分析摘要（仅供提炼，勿整段照搬进表格）：")
            parts.append(ctx[:1200])
        loc = str(item.get("file_locations") or "").strip()
        if loc:
            parts.append("变更范围（patch 数量与主要目录）：")
            parts.append(loc)
        digest = str(item.get("patch_digest") or "").strip()
        if digest:
            parts.append("本范围 patch 摘要：")
            parts.append(digest)
        parts.append("草稿-变更摘要：")
        parts.append(str(item.get("modification") or "").strip() or "（空）")
        parts.append("草稿-重点 Review：")
        parts.append(str(item.get("focus_review") or item.get("review_comment") or "").strip() or "（空）")
        parts.append("草稿-测试建议：")
        parts.append(str(item.get("test_suggestions") or "").strip() or "（空）")
        parts.append("草稿-风险项描述：")
        parts.append(str(item.get("risk_description") or "").strip() or "（空）")
        parts.append("")
    return "\n".join(parts)


def _parse_checklist_polish(content: str) -> Dict[str, Dict[str, str]]:
    yaml_text = _extract_yaml(content)
    try:
        data = _safe_load_llm_yaml(yaml_text)
    except yaml.YAMLError:
        return {}
    rows = []
    if isinstance(data, dict):
        rows = data.get("items") or data.get("modules") or []
    elif isinstance(data, list):
        rows = data
    out: Dict[str, Dict[str, str]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("id") or "").strip()
        if not item_id:
            continue
        polished = {}
        # focus_review 兼容旧字段 review_comment
        focus = str(row.get("focus_review") or row.get("review_comment") or "").strip()
        if focus:
            polished["focus_review"] = focus
        for key in ("modification", "test_suggestions", "risk_description"):
            text = str(row.get(key) or "").strip()
            if text:
                polished[key] = text
        if polished:
            out[item_id] = polished
    return out


# ── Squash diff summary ──────────────────────────────

def generate_squash_summary(
    task: Dict[str, Any],
    squash_diff_path: str,
    repo_dir: str = "",
) -> Optional[str]:
    """Use LLM to analyze the squash diff and generate a comprehensive summary.
    Returns the summary text (Chinese), or None if not configured or fails.
    """
    if not is_llm_configured():
        return None

    import os
    if not squash_diff_path or not os.path.isfile(squash_diff_path):
        return None

    # Read squash diff
    try:
        with open(squash_diff_path, "r", encoding="utf-8") as f:
            squash_content = f.read()
    except Exception:
        return None

    # Get --stat summary if local repo available
    stat_text = ""
    from_tag = task.get("from_tag", "")
    to_tag = task.get("to_tag", "")
    if repo_dir and from_tag and to_tag:
        try:
            from tools.patch_analyzer import run_git
            from pathlib import Path
            stat_text = run_git(Path(repo_dir), ["diff", "--stat", f"{from_tag}..{to_tag}"])
        except Exception:
            pass

    # Truncate diff to avoid token overflow (keep ~20000 chars)
    MAX_DIFF_CHARS = 20000
    if len(squash_content) > MAX_DIFF_CHARS:
        truncated = squash_content[:MAX_DIFF_CHARS]
        truncated += f"\n\n... [truncated, total {len(squash_content)} chars] ..."
    else:
        truncated = squash_content

    config = get_llm_config()
    repo = task.get("repo", "")

    from web_app.analyzer_service import get_dev_module_names

    _mod_names = get_dev_module_names()
    system_prompt = render_prompt(
        "squash_summary",
        dev_module_names="、".join(_mod_names) if _mod_names else "（无模块定义）",
    )

    stat_section = f"\n\n## 变更统计（git diff --stat）\n```\n{stat_text}\n```" if stat_text else ""

    user_prompt = f"""## 任务信息
仓库: {repo}
区间: {from_tag} → {to_tag}

## 合并 Diff（squash）
```diff
{truncated}
```{stat_section}

请生成技术总结报告。"""

    try:
        content, _ = _call_llm(system_prompt, user_prompt, config, timeout=300)
        return content
    except Exception as exc:
        print(f"[SQUASH SUMMARY LLM] 生成 squash 总结失败: {exc}", flush=True)
        return None


# ── Main crash analysis (hybrid approach) ────────────────

def _extract_crash_keywords(crash_log: str) -> List[str]:
    """Extract file paths, function names, module names from crash log (local, no LLM)."""
    import re as _re
    keywords: set = set()
    # File paths (drivers/gpu/drm/msm/msm_drv.c, kernel/sched/core.c)
    for m in _re.finditer(r'((?:drivers|kernel|mm|fs|net|arch|include|sound|security|crypto|block|ipc|lib)/[\w/.\-]+\.\w+)', crash_log):
        path = m.group(1).strip()
        keywords.add(path)
        parts = path.rsplit("/", 1)
        if len(parts) > 1:
            keywords.add(parts[0] + "/")
    # Functions from call trace (func_name+0x10/0x20)
    for m in _re.finditer(r'(\w+)\+0x[0-9a-fA-F]+/0x[0-9a-fA-F]+', crash_log):
        if len(m.group(1)) > 3:
            keywords.add(m.group(1))
    # Functions from backtrace ([<addr>] func_name)
    for m in _re.finditer(r'\[<[0-9a-fA-F]+>\]\s+(\w+)', crash_log):
        if len(m.group(1)) > 3:
            keywords.add(m.group(1))
    return list(keywords)


def _score_patch_suspicion(patch: Dict[str, Any], crash_keywords: List[str]) -> tuple:
    """Score how suspicious a patch is based on file/keyword overlap. Returns (score, matches)."""
    title = (patch.get("title") or "").lower()
    files = patch.get("files", []) or []
    score = 0
    matches: List[str] = []
    kw_lower = [k.lower() for k in crash_keywords]
    for f in files:
        f_lower = f.lower()
        for kw in kw_lower:
            if kw in f_lower or f_lower in kw:
                score += 2
                matches.append(f"file:{f}~{kw}")
                break
    for kw in crash_keywords:
        if kw.lower() in title and len(kw) > 4:
            score += 1
            matches.append(f"title:{kw}")
    return score, matches


def _try_parse_crash_analysis(text: str) -> Optional[Dict[str, Any]]:
    """Try to detect if the uploaded text is already an analysis result (not raw crash log).
    If detected, parse and return a structured crash_analysis dict.
    Returns None if the text appears to be a raw crash log.
    """
    import re as _re

    # Check for analysis result indicators
    indicators = [
        r'crash_type\s*:',
        r'崩溃类型\s*[：:]',
        r'死机类型\s*[：:]',
        r'崩溃函数\s*[：:]',
        r'crash_function\s*:',
        r'崩溃原因分析',
        r'死机分析结论',
        r'崩溃机制分析',
    ]
    matched_indicators = [p for p in indicators if _re.search(p, text, _re.IGNORECASE)]
    # Need at least 2 indicators to be confident it's an analysis result
    if len(matched_indicators) < 2:
        return None

    print(f"[CRASH] 检测到已有分析结果: {matched_indicators[:5]}", flush=True)

    # Try to extract structured fields
    def _extract_field(patterns: list, default: str = "") -> str:
        for p in patterns:
            m = _re.search(p, text, _re.IGNORECASE | _re.MULTILINE)
            if m:
                return m.group(1).strip().strip('"').strip("'").strip('*').strip()
        return default

    crash_type = _extract_field([
        r'(?:crash_type|崩溃类型|死机类型)\s*[：:]\s*["\']?([^\n"\'#]+)',
    ])
    crash_function = _extract_field([
        r'(?:crash_function|崩溃函数)\s*[：:]\s*["\']?([^\n"\'#]+)',
    ])
    crash_module = _extract_field([
        r'(?:crash_module|崩溃模块|相关模块)\s*[：:]\s*["\']?([^\n"\'#]+)',
    ])
    call_stack_summary = _extract_field([
        r'(?:call_stack_summary|调用栈摘要|调用栈)\s*[：:]\s*["\']?([^\n"\'#]+)',
    ])
    crash_description = _extract_field([
        r'(?:crash_description|死机描述|死机现象|崩溃现象)\s*[：:]\s*["\']?([^\n"\'#]+)',
    ])
    crash_mechanism = _extract_field([
        r'(?:crash_mechanism|崩溃机制|崩溃原因|根本原因)\s*[：:]\s*["\']?([^\n"\']+)',
    ])

    # Extract list fields (crash_files, crash_symbols)
    def _extract_list(patterns: list) -> List[str]:
        for p in patterns:
            m = _re.search(p, text, _re.IGNORECASE | _re.DOTALL)
            if m:
                block = m.group(1)
                items = _re.findall(r'[-•]\s*["\']?([^\n"\']+)', block)
                if items:
                    return [i.strip().strip('"').strip("'") for i in items if i.strip()]
                # Try comma-separated
                items = block.strip().split(',')
                return [i.strip().strip('"').strip("'").strip('[').strip(']') for i in items if i.strip()]
        return []

    crash_files = _extract_list([
        r'(?:crash_files|相关文件|崩溃文件)\s*[：:]*\s*\n?((?:\s*[-•][^\n]+\n?)+)',
        r'(?:crash_files|相关文件)\s*[：:]\s*["\']?\[([^\]]+)\]',
    ])
    crash_symbols = _extract_list([
        r'(?:crash_symbols|相关符号|崩溃符号|关键符号)\s*[：:]*\s*\n?((?:\s*[-•][^\n]+\n?)+)',
        r'(?:crash_symbols|相关符号)\s*[：:]\s*["\']?\[([^\]]+)\]',
    ])

    # Validate: must have at least crash_type or crash_function
    if not crash_type and not crash_function:
        return None

    result = {
        "crash_type": crash_type or "未知",
        "crash_function": crash_function or "未知",
        "crash_module": crash_module or "未知",
        "call_stack_summary": call_stack_summary,
        "crash_description": crash_description,
        "crash_files": crash_files,
        "crash_symbols": crash_symbols,
        "crash_mechanism": crash_mechanism,
    }

    print(f"[CRASH] 解析已有分析结果: type={crash_type}, func={crash_function}, "
          f"files={len(crash_files)}, symbols={len(crash_symbols)}", flush=True)
    return result


_OOPS_DUMP_HEADER_RE = re.compile(
    r"\]\s*(?:PC|LR|SP|X\d+)\s*:\s*0x[0-9a-fA-F]+:\s*$",
    re.IGNORECASE,
)
_OOPS_DUMP_BODY_RE = re.compile(
    r"\]\s*[0-9a-fA-F]{3,4}:\s+[0-9a-fA-F]{8}\s+[0-9a-fA-F]{8}",
    re.IGNORECASE,
)


def _is_oops_hexdump_line(line: str) -> bool:
    """Drop MTK/arm64 register memory dumps that sit between pc: and Call trace."""
    if _OOPS_DUMP_BODY_RE.search(line):
        return True
    return bool(_OOPS_DUMP_HEADER_RE.search(line.rstrip()))


def _extract_crash_relevant_sections(crash_log: str, max_chars: int = 30000) -> str:
    """Intelligently extract crash-relevant sections from kernel log.
    Always performs smart extraction: finds crash markers and extracts generous context.
    Falls back to last max_chars if no markers found.
    """
    import re as _re_local

    # Crash marker patterns
    markers = [
        r'Kernel panic',
        r'Unable to handle',
        r'BUG:.*unable to handle',
        r'Oops:',
        r'general protection fault',
        r'Call Trace:',
        r'Call trace:',
        r'RIP:',
        r'PC is at',
        r'pc\s*:',
        r'lr\s*:',
        r'watchdog:',
        r'RCU.*self-detected stall',
        r'INFO: rcu_sched',
        r'BUG:.*spinlock',
        r'BUG:.*soft lockup',
        r'BUG:.*hard LOCKUP',
        r'BUG_ON',
        r'Internal error:',
        r'Data abort:',
        r'Synchronous Abort',
        r'Unhandled fault',
        r'kernel BUG at',
        r'WARNING:.*at\s+\S+\.\w+:',
        r'KASAN',
        r'use-after-free',
        r'slab-out-of-bounds',
        r'null-ptr-deref',
        r'hung_task',
        r'blocked for more than',
        r'soft lockup',
        r'hard LOCKUP',
    ]
    combined_pattern = '|'.join(markers)

    lines = crash_log.split('\n')
    marker_lines: List[int] = []
    for i, line in enumerate(lines):
        if _re_local.search(combined_pattern, line, _re_local.IGNORECASE):
            marker_lines.append(i)

    if not marker_lines:
        # No crash markers — take the last max_chars
        tail = crash_log[-max_chars:] if len(crash_log) > max_chars else crash_log
        print(f"[CRASH] 未找到崩溃标记，取日志末尾 {len(tail)} 字符", flush=True)
        return tail

    # Prefer the oops header and the Call trace that often sits after a hex dump.
    CONTEXT_BEFORE = 20
    CONTEXT_AFTER = 250
    sections: List[tuple] = []  # (start_line, end_line)

    for ml in marker_lines:
        start = max(0, ml - CONTEXT_BEFORE)
        end = min(len(lines), ml + CONTEXT_AFTER)
        sections.append((start, end))

    # Merge overlapping/nearby sections
    sections.sort()
    merged: List[tuple] = [sections[0]]
    for start, end in sections[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 10:  # 10-line gap tolerance
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    # Build output, dropping register hex dumps so Call trace survives truncation
    result_parts: List[str] = []
    for idx, (start, end) in enumerate(merged):
        if idx > 0:
            skipped = start - merged[idx - 1][1]
            result_parts.append(f"\n... [省略 {skipped} 行无关日志] ...\n")
        kept = [line for line in lines[start:end] if not _is_oops_hexdump_line(line)]
        result_parts.append('\n'.join(kept))

    result = '\n'.join(result_parts) if result_parts else crash_log[-max_chars:]

    # If still too long, keep oops/stack tail rather than the noisy prefix
    if len(result) > max_chars:
        original_len = len(result)
        result = result[-max_chars:] + f"\n... [截断前缀噪声, 原提取 {original_len} 字符]"

    print(f"[CRASH] 智能提取: 原日志 {len(crash_log)} 字符 / {len(lines)} 行, "
          f"找到 {len(marker_lines)} 个崩溃标记, "
          f"提取 {len(result)} 字符 ({len(merged)} 个段落)", flush=True)
    return result


def analyze_crash_cause(crash_log: str, source_block: str = "") -> Dict[str, Any]:
    """Phase 1: Analyze crash log, plus local GKI source at the crash site when available.
    """
    config = get_llm_config()

    system_prompt = load_prompt("crash_phase1_cause")

    # Smart extraction: find crash-relevant sections instead of naive truncation
    relevant_log = _extract_crash_relevant_sections(crash_log)
    source_section = ""
    if (source_block or "").strip():
        source_section = f"""
## 本地 GKI 源码（已按当前 Tag 从仓库取出）
{source_block}

请结合源码说明死在哪个文件、哪一行、哪条语句。行号和语句必须来自上面的片段，禁止编造。
"""

    user_prompt = f"""请分析以下内核死机日志。

要求：
- crash_function 不要用 panic/die/kasan_report 等通用帧，除非栈上没有更具体的函数
- crash_files 尽量写成内核相对路径（带目录），并从日志摘 file.c:line
- crash_symbols 填崩溃路径上的真实符号，不要编造
- evidence 摘 2～6 行日志原文
- 有源码时填写 crash_source_path / crash_source_line / crash_source_statement
- 不确定写「未知」
{source_section}
```
{relevant_log}
```"""

    try:
        content, usage = _call_llm(system_prompt, user_prompt, config, timeout=180)
        yaml_text = _extract_yaml(content)
        try:
            data = _safe_load_llm_yaml(yaml_text) or {}
        except yaml.YAMLError:
            data = {}

        if not isinstance(data, dict):
            data = {}

        files = data.get("crash_files", []) or []
        symbols = data.get("crash_symbols", []) or []
        if not isinstance(files, list):
            files = [str(files)] if files else []
        if not isinstance(symbols, list):
            symbols = [str(symbols)] if symbols else []
        extra_syms = [
            data.get("crash_site_function") or "",
            data.get("pc_symbol") or "",
        ]
        for item in extra_syms:
            token = str(item).split("+")[0].strip()
            if token and token not in symbols:
                symbols.append(token)
        evidence = data.get("evidence") or []
        if not isinstance(evidence, list):
            evidence = [str(evidence)] if evidence else []
        source_line_raw = data.get("crash_source_line")
        try:
            source_line = int(str(source_line_raw).strip()) if source_line_raw not in (None, "", "未知") else 0
        except ValueError:
            source_line = 0

        result = {
            "crash_type": data.get("crash_type", ""),
            "bug_class": data.get("bug_class", "") or "",
            "confidence": data.get("confidence", "") or "",
            "crash_function": data.get("crash_function", ""),
            "crash_site_function": data.get("crash_site_function", "") or "",
            "crash_module": data.get("crash_module", ""),
            "pc_symbol": data.get("pc_symbol", "") or "",
            "fault_addr": data.get("fault_addr", "") or "",
            "call_stack_summary": data.get("call_stack_summary", ""),
            "crash_description": data.get("crash_description", ""),
            "crash_files": [str(x).strip() for x in files if str(x).strip()],
            "crash_symbols": [str(x).strip() for x in symbols if str(x).strip()],
            "evidence": [str(x).strip() for x in evidence if str(x).strip()],
            "crash_mechanism": data.get("crash_mechanism", ""),
            "crash_source_path": str(data.get("crash_source_path") or "").strip(),
            "crash_source_line": source_line,
            "crash_source_statement": str(data.get("crash_source_statement") or "").strip(),
        }
        print(f"[CRASH Phase1] 死机类型: {result['crash_type']}, "
              f"崩溃函数: {result['crash_function']}, "
              f"相关文件: {result['crash_files'][:5]}, "
              f"相关符号: {result['crash_symbols'][:8]}", flush=True)
        return {"crash_analysis": result, "usage": usage, "raw_response": content}

    except Exception as exc:
        print(f"[CRASH Phase1] 分析失败: {exc}", flush=True)
        return {"crash_analysis": {}, "error": str(exc), "raw_response": ""}


def find_suspected_patches(
    crash_analysis: Dict[str, Any],
    crash_log: str,
    patch_list: List[Dict[str, Any]],
    squash_diff: str,
    squash_stat: str = "",
    from_tag: str = "",
    to_tag: str = "",
    repo_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Phase 2: Based on crash analysis results, find which merged patches may have
    introduced the crash. Uses LLM-analyzed crash info + squash diff + patch list.
    """
    config = get_llm_config()

    # Build keywords from LLM crash analysis (more accurate than regex)
    crash_files = crash_analysis.get("crash_files", []) or []
    crash_symbols = crash_analysis.get("crash_symbols", []) or []
    crash_function = crash_analysis.get("crash_function", "")
    crash_module = crash_analysis.get("crash_module", "")
    crash_mechanism = crash_analysis.get("crash_mechanism", "")

    # Also extract keywords from raw crash log as supplement
    regex_keywords = _extract_crash_keywords(crash_log)

    # Merge all search terms
    all_keywords: set = set()
    for f in crash_files:
        all_keywords.add(f)
        parts = f.rsplit("/", 1)
        if len(parts) > 1:
            all_keywords.add(parts[0] + "/")
    for s in crash_symbols:
        all_keywords.add(s)
    if crash_function:
        all_keywords.add(crash_function)
    for kw in regex_keywords:
        all_keywords.add(kw)
    all_keywords = list(all_keywords)

    # Score and rank patches
    scored_patches: List[Dict[str, Any]] = []
    for p in patch_list:
        score, matches = _score_patch_suspicion(p, all_keywords)
        if score > 0:
            scored_patches.append({**p, "_score": score, "_matches": matches})
    scored_patches.sort(key=lambda x: x["_score"], reverse=True)
    print(f"[CRASH Phase2] {len(scored_patches)} 笔可疑 patch (基于 LLM 分析 + 正则匹配)", flush=True)

    # Get per-commit diffs for top suspicious patches
    from web_app.database import get_patch_by_sha
    suspicious_with_diff: List[Dict[str, Any]] = []
    for sp in scored_patches[:10]:
        sha = sp["sha"]
        diff_text = ""
        db_patch = get_patch_by_sha(sha)
        if db_patch and db_patch.get("data"):
            diff_text = db_patch["data"].get("diff_text", "")
            print(f"[CRASH Phase2] patch {sha[:12]} 从数据库获取 diff ({len(diff_text)} chars)", flush=True)
        if not diff_text and repo_dir:
            try:
                from tools.patch_analyzer import run_git
                from pathlib import Path
                diff_text = run_git(Path(repo_dir), ["show", "--format=", "--no-color", sha])
            except Exception as e:
                print(f"[CRASH Phase2] git show {sha[:12]} 失败: {e}", flush=True)
        MAX_PER_DIFF = 4000
        if len(diff_text) > MAX_PER_DIFF:
            diff_text = diff_text[:MAX_PER_DIFF] + f"\n... [truncated, {len(diff_text)} chars]"
        suspicious_with_diff.append({
            "sha": sha,
            "title": sp.get("title", ""),
            "files": sp.get("files", []),
            "matched_items": sp.get("_matches", [])[:5],
            "diff": diff_text.strip(),
        })

    # Build patch list block
    patch_lines: List[str] = []
    for p in patch_list[:300]:
        sha = p.get("sha", "?")[:12]
        title = (p.get("title") or "-")[:80]
        files = p.get("files", []) or []
        files_str = ", ".join(files[:5]) if files else "-"
        patch_lines.append(f"- `{sha}` {title}  [{files_str}]")
    if len(patch_list) > 300:
        patch_lines.append(f"\n... 另有 {len(patch_list) - 300} 笔 patch 未列出")
    patch_block = "\n".join(patch_lines)

    # Build suspicious block
    suspicious_block = ""
    if suspicious_with_diff:
        parts = []
        for sp in suspicious_with_diff:
            sha = sp["sha"][:12]
            title = sp.get("title", "")
            files = sp.get("files", [])
            files_str = ", ".join(files[:8]) if files else "-"
            matched = sp.get("matched_items", [])
            diff = sp.get("diff", "")
            parts.append(f"""### 可疑 Commit `{sha}`: {title}
匹配原因: {'; '.join(matched) if matched else '关键词匹配'}
修改文件: {files_str}
```diff
{diff}
```""")
        suspicious_block = "\n\n".join(parts)

    stat_section = f"\n## 变更统计 (git diff --stat)\n```\n{squash_stat}\n```\n" if squash_stat else ""

    # Build crash analysis summary for LLM
    crash_summary_text = f"""- 死机类型: {crash_analysis.get('crash_type', '未知')}
- 问题分类: {crash_analysis.get('bug_class', '') or '未知'}
- 崩溃函数: {crash_analysis.get('crash_function', '未知')}
- 崩溃现场函数: {crash_analysis.get('crash_site_function', '') or '未知'}
- PC/RIP: {crash_analysis.get('pc_symbol', '') or '未知'}
- 出错地址: {crash_analysis.get('fault_addr', '') or '未知'}
- 相关模块: {crash_analysis.get('crash_module', '未知')}
- 调用栈摘要: {crash_analysis.get('call_stack_summary', '')}
- 相关文件: {', '.join(crash_files) if crash_files else '未提取到'}
- 相关符号: {', '.join(crash_symbols[:10]) if crash_symbols else '未提取到'}
- 崩溃机制: {crash_mechanism}"""

    system_prompt = load_prompt("crash_phase2_attribution")

    user_prompt = f"""## GKI 升级信息
升级区间: {from_tag} → {to_tag}
合入 patch 数量: {len(patch_list)}

## 死机分析结论（Phase 1 分析结果）
{crash_summary_text}
{stat_section}
## 合入的 Patch 列表（含修改文件）
{patch_block}

## 可疑 Commit 详情（{len(suspicious_with_diff)} 笔，基于崩溃相关信息筛选）
{suspicious_block if suspicious_block else '（未找到与崩溃明显相关的可疑 commit，请从 patch 列表和 squash diff 中分析）'}

## 合并 Diff（squash diff，所有变更的合并视图）
```diff
{squash_diff[:30000]}
```

请基于死机分析结论，判断死机是否由本次合入代码引起，并给出疑似问题 patch。"""

    try:
        content, usage = _call_llm(system_prompt, user_prompt, config, timeout=300)
        yaml_text = _extract_yaml(content)
        try:
            data = _safe_load_llm_yaml(yaml_text) or {}
        except yaml.YAMLError:
            data = {}

        if not isinstance(data, dict):
            data = {}

        root_cause = data.get("root_cause", {}) or {}
        recs = data.get("recommendations", {}) or {}

        suspected = []
        for sp in (root_cause.get("suspected_patches") or []):
            if isinstance(sp, dict):
                suspected.append({
                    "sha": str(sp.get("sha", "")),
                    "title": str(sp.get("title", "")),
                    "reason": str(sp.get("reason", "")),
                    "related_files": str(sp.get("related_files", "")),
                    "causation": str(sp.get("causation", "间接")),
                })

        return {
            "is_caused_by_merge": bool(root_cause.get("is_caused_by_merge", False)),
            "confidence": root_cause.get("confidence", "低"),
            "explanation": root_cause.get("explanation", ""),
            "causation_type": root_cause.get("causation_type", "无"),
            "suspected_patches": suspected,
            "recommendations": {
                "immediate_actions": recs.get("immediate_actions", ""),
                "test_suggestions": recs.get("test_suggestions", ""),
                "next_steps": recs.get("next_steps", ""),
            },
            "raw_response": content,
            "usage": usage,
        }

    except Exception as exc:
        print(f"[CRASH Phase2] 归因分析失败: {exc}", flush=True)
        return {
            "error": str(exc),
            "is_caused_by_merge": False,
            "confidence": "低",
            "explanation": f"LLM 归因分析失败: {exc}",
            "causation_type": "无",
            "suspected_patches": [],
            "recommendations": {},
            "raw_response": "",
        }


def findFixCommits(
    crash_info: Dict[str, Any],
    commits_after_b: List[Dict[str, Any]],
    from_tag: str = "",
    to_tag: str = "",
    search_from_tag: str = "",
    search_to_rev: str = "",
    total_after_tag: int = 0,
    batch_size: int = 80,
    on_progress: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Search for fix commits among candidates collected from tag..HEAD."""
    if not commits_after_b:
        return []

    found: List[Dict[str, Any]] = []
    seen = set()
    size = max(20, int(batch_size or 80))
    batch_count = (len(commits_after_b) + size - 1) // size
    for i in range(0, len(commits_after_b), size):
        batch = commits_after_b[i:i + size]
        batch_index = i // size + 1
        if on_progress:
            on_progress(
                f"LLM 识别修复 {batch_index}/{batch_count}（本批 {len(batch)} / 共 {len(commits_after_b)} 笔）"
            )
        for row in _find_fix_commits_batch(
            crash_info=crash_info,
            commits=batch,
            from_tag=from_tag,
            to_tag=to_tag,
            search_from_tag=search_from_tag,
            search_to_rev=search_to_rev,
            total_after_tag=total_after_tag,
            candidate_total=len(commits_after_b),
            batch_index=i // size + 1,
            batch_count=(len(commits_after_b) + size - 1) // size,
        ):
            sha = (row.get("sha") or "").strip()
            key = sha[:12] if sha else f"{row.get('title')}|{row.get('reason')}"
            if key in seen:
                continue
            seen.add(key)
            found.append(row)
    return found


def _find_fix_commits_batch(
    crash_info: Dict[str, Any],
    commits: List[Dict[str, Any]],
    from_tag: str = "",
    to_tag: str = "",
    search_from_tag: str = "",
    search_to_rev: str = "",
    total_after_tag: int = 0,
    candidate_total: int = 0,
    batch_index: int = 1,
    batch_count: int = 1,
) -> List[Dict[str, Any]]:
    if not commits:
        return []

    config = get_llm_config()

    commit_lines: List[str] = []
    for c in commits:
        sha = c.get("sha", "?")[:12]
        title = (c.get("title") or c.get("message", ""))[:100]
        files = c.get("files", []) or []
        files_str = ", ".join(files[:5]) if files else "-"
        commit_lines.append(f"- `{sha}` {title}  [{files_str}]")
    commit_block = "\n".join(commit_lines)

    crash_type = crash_info.get("crash_type", "")
    crash_func = crash_info.get("crash_function", "")
    crash_module = crash_info.get("crash_module", "")
    bug_class = crash_info.get("bug_class", "") or ""
    crash_files = crash_info.get("crash_files", []) or []
    files_str = ", ".join(str(x) for x in crash_files[:8]) if crash_files else "未提取"
    suspected = crash_info.get("suspected_patches", [])
    suspected_str = ""
    if suspected:
        parts = []
        for s in suspected[:8]:
            parts.append(f"- {s.get('sha', '')[:12]} {s.get('title', '')[:60]}")
        suspected_str = "\n".join(parts)

    origin = search_from_tag or to_tag or from_tag
    head = (search_to_rev or "")[:12]
    range_text = f"{origin} → HEAD({head or 'latest'})"
    if from_tag and to_tag:
        upgrade_line = f"升级区间: {from_tag} → {to_tag}"
    else:
        upgrade_line = f"当前 GKI Tag: {origin}（查社区/谷歌是否已有修复）"

    system_prompt = load_prompt("crash_fix_commits")

    user_prompt = f"""## GKI 信息
{upgrade_line}
修复检索范围: {range_text}
该范围内全部提交: {total_after_tag or candidate_total} 笔
本批候选: {len(commits)} / {candidate_total or len(commits)}（第 {batch_index}/{batch_count} 批，已按崩溃文件/符号/修复类标题筛选）

## 死机信息
死机类型: {crash_type}
问题分类: {bug_class or '未知'}
崩溃函数: {crash_func}
相关模块: {crash_module}
相关文件: {files_str}

## 疑似导致死机的 Patch
{suspected_str if suspected_str else '（未识别，或本任务只查社区修复）'}

## 候选提交
{commit_block}

请判断这些提交中是否有修复该死机问题的代码。"""

    try:
        content, _ = _call_llm(system_prompt, user_prompt, config, timeout=300)
        yaml_text = _extract_yaml(content)
        try:
            data = _safe_load_llm_yaml(yaml_text)
        except yaml.YAMLError:
            data = {}

        if not isinstance(data, dict):
            data = {}

        fix_commits = []
        for fc in (data.get("fix_commits") or []):
            if isinstance(fc, dict):
                fix_commits.append({
                    "sha": str(fc.get("sha", "")),
                    "title": str(fc.get("title", "")),
                    "fix_type": str(fc.get("fix_type", "")),
                    "confidence": str(fc.get("confidence", "低")),
                    "reason": str(fc.get("reason", "")),
                })

        return fix_commits

    except Exception as exc:
        print(f"[FIX LLM] 查找修复提交失败: {exc}", flush=True)
        return []


def compare_crash_source_with_latest(
    crash_analysis: Dict[str, Any],
    crash_tag: str,
    latest_ref: str,
    crash_source_block: str,
    latest_source_block: str,
    file_diffs: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Ask the model whether the latest source still has this crash path."""
    empty = {
        "still_present": True,
        "latest_status": "cannot_compare",
        "confidence": "低",
        "summary": "未能对照最新源码",
        "code_change": "",
        "fix_evidence": "",
    }
    if not (crash_source_block or "").strip() or not (latest_source_block or "").strip():
        empty["summary"] = "缺少崩溃点或最新源码，无法对照"
        return empty

    config = get_llm_config()
    system_prompt = load_prompt("crash_source_compare")
    diff_parts: List[str] = []
    for item in file_diffs or []:
        path = item.get("path") or ""
        text = item.get("diff") or ""
        if not text:
            continue
        diff_parts.append(f"### {path}\n```diff\n{text}\n```")
    diff_block = "\n\n".join(diff_parts) if diff_parts else "（无独立文件 diff，仅对照函数片段）"

    user_prompt = f"""## 崩溃 Tag
{crash_tag}

## 社区最新
{latest_ref}

## 死机分析
- 类型: {crash_analysis.get('crash_type') or '未知'}
- 分类: {crash_analysis.get('bug_class') or '未知'}
- 崩溃函数: {crash_analysis.get('crash_function') or '未知'}
- 机制: {crash_analysis.get('crash_mechanism') or '未知'}
- 崩溃语句: {crash_analysis.get('crash_source_statement') or '未知'}

## 崩溃 Tag 源码
{crash_source_block}

## 社区最新源码
{latest_source_block}

## 文件 diff（Tag → 最新）
{diff_block}
"""
    try:
        content, _ = _call_llm(system_prompt, user_prompt, config, timeout=180)
        yaml_text = _extract_yaml(content)
        try:
            data = _safe_load_llm_yaml(yaml_text) or {}
        except yaml.YAMLError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        status = str(data.get("latest_status") or "").strip()
        if status not in ("still_buggy", "likely_fixed", "cannot_compare"):
            if data.get("still_present") is False:
                status = "likely_fixed"
            elif data.get("still_present") is True:
                status = "still_buggy"
            else:
                status = "cannot_compare"
        still_present = status != "likely_fixed"
        if "still_present" in data:
            still_present = bool(data.get("still_present"))
            if still_present and status == "likely_fixed":
                status = "still_buggy"
        return {
            "still_present": still_present,
            "latest_status": status,
            "confidence": str(data.get("confidence") or "中"),
            "summary": str(data.get("summary") or ""),
            "code_change": str(data.get("code_change") or ""),
            "fix_evidence": str(data.get("fix_evidence") or ""),
        }
    except Exception as exc:
        print(f"[CRASH SOURCE COMPARE] 失败: {exc}", flush=True)
        empty["summary"] = f"对照最新源码失败: {exc}"
        return empty


def identify_fix_from_source_diffs(
    crash_analysis: Dict[str, Any],
    compare: Dict[str, Any],
    commits: List[Dict[str, Any]],
    crash_tag: str = "",
    latest_ref: str = "",
) -> List[Dict[str, Any]]:
    """Pick the fixing commit by reading file/function diffs after latest source looks safe."""
    if not commits:
        return []
    config = get_llm_config()
    system_prompt = load_prompt("crash_fix_from_diff")
    allowed = {str(item.get("sha") or "").strip()[:12] for item in commits if item.get("sha")}
    allowed.update(str(item.get("sha") or "").strip() for item in commits if item.get("sha"))
    blocks: List[str] = []
    for item in commits:
        sha = str(item.get("sha") or "")
        title = str(item.get("title") or "")
        path = str(item.get("path") or "")
        diff = str(item.get("diff") or "")
        if not sha:
            continue
        if not diff:
            diff = "(无 diff)"
        blocks.append(f"### `{sha[:12]}` {title}\n文件: {path}\n```diff\n{diff}\n```")
    user_prompt = f"""## 范围
崩溃 Tag: {crash_tag}
社区最新: {latest_ref}

## 死机分析
- 类型: {crash_analysis.get('crash_type') or '未知'}
- 分类: {crash_analysis.get('bug_class') or '未知'}
- 崩溃函数: {crash_analysis.get('crash_function') or '未知'}
- 机制: {crash_analysis.get('crash_mechanism') or '未知'}

## 最新源码为何认为已避开
{compare.get('summary') or ''}
{compare.get('fix_evidence') or ''}

## 候选提交 diff（必须从中选 SHA）
{chr(10).join(blocks)}
"""
    try:
        content, _ = _call_llm(system_prompt, user_prompt, config, timeout=300)
        yaml_text = _extract_yaml(content)
        try:
            data = _safe_load_llm_yaml(yaml_text) or {}
        except yaml.YAMLError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        found: List[Dict[str, Any]] = []
        for row in data.get("fix_commits") or []:
            if not isinstance(row, dict):
                continue
            sha = str(row.get("sha") or "").strip()
            if not sha:
                continue
            if sha not in allowed and sha[:12] not in allowed:
                continue
            full = next(
                (item.get("sha") for item in commits if str(item.get("sha") or "").startswith(sha[:12])),
                sha,
            )
            found.append({
                "sha": full,
                "title": str(row.get("title") or next(
                    (item.get("title") for item in commits if str(item.get("sha") or "").startswith(sha[:12])),
                    "",
                )),
                "fix_type": str(row.get("fix_type") or "fix"),
                "confidence": str(row.get("confidence") or "中"),
                "reason": str(row.get("reason") or ""),
                "via": "source_diff",
            })
        return found
    except Exception as exc:
        print(f"[CRASH FIX FROM DIFF] 失败: {exc}", flush=True)
        return []


_MERGED_BLOCK_RE = re.compile(
    r"```(?:merged|diff|patch|[\w./-]+)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_UNCLOSED_MERGED_BLOCK_RE = re.compile(
    r"```(?:merged|diff|patch|[\w./-]+)?\s*\n(.*)\Z",
    re.DOTALL | re.IGNORECASE,
)
_SUMMARY_RE = re.compile(r"(?:^|\n)summary\s*[:：]\s*(.+?)(?:\n|$)", re.IGNORECASE)
_SUMMARY_LINE_RE = re.compile(r"^summary\s*[:：].*$", re.IGNORECASE)
_OPEN_FENCE_LINE_RE = re.compile(r"^```(?:merged|diff|patch|[\w./-]*)?\s*$", re.IGNORECASE)
_CLOSE_FENCE_LINE_RE = re.compile(r"^```\s*$")


def _strip_leading_summary_and_fences(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    while lines:
        s = lines[0].strip()
        if not s:
            lines.pop(0)
            continue
        if _SUMMARY_LINE_RE.match(s) or _OPEN_FENCE_LINE_RE.match(s):
            lines.pop(0)
            continue
        break
    while lines and _CLOSE_FENCE_LINE_RE.match(lines[-1].strip()):
        lines.pop()
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _validate_merged_source(content: str, *, source_path: str = "") -> None:
    stripped = content.lstrip()
    if not stripped:
        raise RuntimeError("LLM 未返回有效的合并文件内容")
    if _SUMMARY_LINE_RE.match(stripped.split("\n", 1)[0].strip()):
        raise RuntimeError("合并结果仍含 summary 行，不能写回源文件")
    if "```" in content:
        raise RuntimeError("合并结果仍含 markdown 代码围栏，LLM 输出可能不完整")
    if "<<<<<<<" in content or ">>>>>>>" in content:
        raise RuntimeError("合并结果仍含 git 冲突标记")


def _estimate_conflict_merge_max_tokens(original_content: str) -> int:
    """Scale output budget so large .c files are not cut off mid-file."""
    chars = len(original_content or "")
    lines = (original_content or "").count("\n") + 1
    by_chars = chars // 2 + 8192
    by_lines = lines * 14 + 4096
    return min(65536, max(16384, by_chars, by_lines))


def _validate_merged_completeness(
    original_content: str,
    merged_content: str,
    *,
    source_path: str = "",
) -> None:
    """Reject LLM output truncated by max_tokens (common on large kernel drivers)."""
    orig_lines = (original_content or "").count("\n") + 1
    merg_lines = (merged_content or "").count("\n") + 1
    if orig_lines < 80:
        return

    min_ratio = 0.88 if orig_lines >= 400 else 0.82
    if merg_lines < int(orig_lines * min_ratio):
        raise RuntimeError(
            f"合并结果被截断：输出 {merg_lines} 行，原文件 {orig_lines} 行"
            f"（<{int(min_ratio * 100)}%），不能写回。请手动合入或重试 AI"
        )

    last = (merged_content or "").rstrip().split("\n")[-1].strip()
    if last and re.search(
        r"(?:struct\s+\w{1,20}$|^\s*u$|,\s*$|\(\s*$|=\s*$|\\\s*$|\+\s*$|-\s*$)",
        last,
    ):
        raise RuntimeError(
            f"合并结果末尾不完整（疑似 max_tokens 截断）: {last[-100:]!r}"
        )

    if source_path.endswith((".c", ".h")) and orig_lines >= 200:
        ob = original_content.count("{") - original_content.count("}")
        mb = merged_content.count("{") - merged_content.count("}")
        if mb > ob + 2:
            raise RuntimeError("合并结果大括号未闭合，可能被截断")


def _extract_merged_from_llm_response(response: str) -> Tuple[str, str]:
    """Parse LLM conflict-merge response into (file_content, summary)."""
    summary_m = _SUMMARY_RE.search(response)
    summary = summary_m.group(1).strip() if summary_m else "AI 合并完成"

    merged = ""
    block_m = _MERGED_BLOCK_RE.search(response)
    if block_m:
        merged = block_m.group(1)
    elif _UNCLOSED_MERGED_BLOCK_RE.search(response):
        raise RuntimeError("LLM 代码块未闭合（输出可能被 max_tokens 截断）")
    elif response.strip().startswith("```"):
        merged = re.sub(r"^```[^\n]*\n", "", response.strip(), count=1)
        merged = re.sub(r"\n```\s*$", "", merged)
    else:
        merged = response.strip()

    merged = _strip_leading_summary_and_fences(merged.strip())
    _validate_merged_source(merged)
    if not merged.endswith("\n"):
        merged += "\n"
    return merged, summary


def sanitize_merged_conflict_content(
    content: str,
    *,
    original_content: str = "",
    source_path: str = "",
) -> str:
    """Strip metadata/fences from proposed content before write-back."""
    raw = content or ""
    if not raw.strip():
        raise ValueError("合并内容为空")
    head = raw.lstrip()[:800]
    if _SUMMARY_RE.search(head) or "```" in head:
        merged, _ = _extract_merged_from_llm_response(raw)
    else:
        merged = _strip_leading_summary_and_fences(raw.strip())
        _validate_merged_source(merged, source_path=source_path)
    if original_content:
        _validate_merged_completeness(
            original_content, merged, source_path=source_path,
        )
    return merged if merged.endswith("\n") else merged + "\n"


def _validate_region_merge(
    vendor_snippet: str,
    merged: str,
    *,
    pre_len: int = 0,
    post_len: int = 0,
    body_snippet: str = "",
) -> None:
    """Reject truncated or invalid per-region LLM output."""
    vendor_lines = (vendor_snippet or "").splitlines()
    merged_lines = (merged or "").splitlines()
    body_len = max(1, len(vendor_lines) - pre_len - post_len)
    if body_snippet.strip():
        body_len = max(1, (body_snippet or "").count("\n") + 1)

    # Middle-only or full-region — validate against conflict body size
    if len(merged_lines) >= pre_len + post_len and pre_len + post_len > 0:
        pre_ok = pre_len == 0 or vendor_lines[:pre_len] == merged_lines[:pre_len]
        post_ok = post_len == 0 or vendor_lines[-post_len:] == merged_lines[-post_len:]
        if not (pre_ok and post_ok):
            m_body = len(merged_lines)
        else:
            m_body = len(merged_lines[pre_len:-post_len] if post_len else merged_lines[pre_len:])
    else:
        m_body = len(merged_lines) or 1

    if m_body < max(1, int(body_len * 0.35)):
        raise RuntimeError(
            f"区域合并结果被截断：冲突主体 {m_body} 行，输入约 {body_len} 行"
        )
    if m_body > int(body_len * 3) + 40:
        raise RuntimeError(
            f"区域合并结果异常膨胀：冲突主体 {m_body} 行，输入约 {body_len} 行"
        )
    _validate_merged_source(merged)


def _estimate_region_merge_max_tokens(vendor_snippet: str, body_snippet: str = "") -> int:
    text = body_snippet.strip() or vendor_snippet
    chars = len(text or "")
    lines = (text or "").count("\n") + 1
    return min(16384, max(4096, chars // 2 + 1024, lines * 14 + 512))


def _append_conflict_logic_hints(user_parts: List[str], task: Dict[str, Any]) -> None:
    """Attach control-flow notes as a reference to help merge, not as a sole rule."""
    hunk_body = (task.get("hunk_body") or "").strip()
    logic = (task.get("logic_hints") or "").strip()
    if not logic and hunk_body:
        from web_app.conflict_region_utils import build_function_logic_hints
        logic = build_function_logic_hints(
            hunk_body,
            task.get("vendor_function")
            or task.get("body_snippet")
            or task.get("vendor_snippet")
            or "",
        )
    if logic:
        user_parts.append(logic)


def _resolve_conflict_region_via_llm(
    *,
    source_path: str,
    task: Dict[str, Any],
    config: Dict[str, str],
) -> Tuple[str, str]:
    """Merge a single conflict region; return (merged_snippet, summary)."""
    system = load_prompt("conflict_merge_region")
    hint_block = user_hint_prompt_suffix("conflict")
    if hint_block:
        system = system.rstrip() + "\n\n" + hint_block

    body = (task.get("body_snippet") or "").strip()
    user_parts = [
        f"文件路径: {source_path}",
        f"冲突区域 {task['index']}/{task['total']}（约第 {task['start_line']}-{task['end_line']} 行）",
        f"冲突类型: {task.get('kind', 'unknown')}",
    ]
    if task.get("incremental_only"):
        user_parts.append(
            "【强制】vendor 已有同名函数且实现与 GKI 旧代码不同。"
            "禁止把 incoming/GKI 整个函数体粘贴进文件或新增第二个同名函数。"
            "必须在上方 vendor 函数体内按 .rej 的 +/- 逐条合入。"
        )
    if body:
        user_parts.append("=== vendor 冲突主体（需合并的部分，仅输出此部分的合并结果）===")
        user_parts.append(body)
    else:
        user_parts.append("=== 当前 vendor 区域（含上下文）===")
        user_parts.append(task["vendor_snippet"])
    incoming_body = (task.get("incoming_body_snippet") or "").strip()
    incoming = (task.get("incoming_snippet") or "").strip()
    if not task.get("incremental_only"):
        if incoming_body:
            user_parts.append("=== GKI incoming 冲突主体 ===")
            user_parts.append(incoming_body)
        elif incoming:
            user_parts.append("=== 拟合入的 GKI 变更（incoming，含上下文）===")
            user_parts.append(incoming)
    hunk_body = (task.get("hunk_body") or "").strip()
    if hunk_body:
        user_parts.append("=== .rej unified-diff hunk（只把其中 +/- 合入 vendor）===")
        user_parts.append(hunk_body)
        user_parts.append(
            "【强制】每条 .rej 的 + 必须紧挨其前导 context 落地；"
            "禁止把 GKI 插入写进厂商独有块（如 CONTINUOUS_WR）。"
            "若 hunk 下一行是 }，合入后下一行仍须是该 }。"
        )
    _append_conflict_logic_hints(user_parts, task)
    old_fn = (task.get("gki_old_function") or "").strip()
    new_fn = (task.get("gki_new_function") or "").strip()
    if old_fn or new_fn:
        user_parts.append(
            "【函数实现对照】下面是同名函数在 GKI 旧版 / 新版中的实现。"
            "对照二者得出本轮语义变更，合入上方 vendor 函数；"
            "禁止用 GKI 新函数整体替换 vendor。"
        )
        if old_fn:
            user_parts.append("=== GKI 旧版函数实现 ===")
            user_parts.append(old_fn)
        if new_fn:
            user_parts.append("=== GKI 新版函数实现（对照用，禁止整段粘贴）===")
            user_parts.append(new_fn)
    preview = (task.get("function_merge_preview") or "").strip()
    if preview:
        user_parts.append(
            "=== 函数级三路合并预览（含冲突标记；在标记处解决并删掉标记，保留未冲突的 vendor 代码）==="
        )
        user_parts.append(preview)
    user_parts.append("请输出 summary 行 + ```merged 合并后的冲突主体（不含上下文）```")

    max_tokens = _estimate_region_merge_max_tokens(
        task["vendor_snippet"], task.get("body_snippet") or "",
    )
    response, _usage = _call_llm(
        system, "\n\n".join(user_parts), config, timeout=300, max_tokens=max_tokens,
    )
    try:
        merged, summary = _extract_merged_from_llm_response(response)
        _validate_region_merge(
            task["vendor_snippet"],
            merged,
            pre_len=int(task.get("pre_len") or 0),
            post_len=int(task.get("post_len") or 0),
            body_snippet=task.get("body_snippet") or "",
        )
        return merged, summary
    except RuntimeError as exc:
        if "```" in response and _UNCLOSED_MERGED_BLOCK_RE.search(response):
            raise RuntimeError(
                f"区域 {task['index']}: {exc}（LLM 输出可能被截断）"
            ) from exc
        raise RuntimeError(f"区域 {task['index']}: {exc}") from exc


_DIFF_BLOCK_RE = re.compile(
    r"```(?:diff|patch|fix)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_diff_from_llm_response(response: str) -> Tuple[str, str]:
    summary_m = _SUMMARY_RE.search(response)
    summary = summary_m.group(1).strip() if summary_m else "AI diff 合并"

    diff = ""
    block_m = _DIFF_BLOCK_RE.search(response)
    if block_m:
        diff = block_m.group(1).strip()
    elif _looks_like_unified_diff(response):
        diff = response.strip()
    else:
        merged_m = _MERGED_BLOCK_RE.search(response)
        if merged_m:
            raise RuntimeError("期望 unified diff，但 LLM 返回了代码块")
        raise RuntimeError("LLM 未返回有效的 unified diff")

    if not _looks_like_unified_diff(diff):
        raise RuntimeError("LLM diff 缺少 @@ hunk 头")
    return diff, summary


def _looks_like_unified_diff(text: str) -> bool:
    return bool(re.search(r"^@@ -\d+", text or "", re.MULTILINE))


def _resolve_conflict_region_via_llm_diff(
    *,
    source_path: str,
    file_content: str,
    task: Dict[str, Any],
    config: Dict[str, str],
) -> Tuple[str, str]:
    """Merge one region via LLM unified diff; return (new_file_content, summary)."""
    from web_app.build_fix_service import _apply_unified_diff

    hs = task["replace_start"] + 1
    he = task["replace_end"]
    body = (task.get("body_snippet") or "").strip()

    system = load_prompt("conflict_merge_diff")
    hint_block = user_hint_prompt_suffix("conflict")
    if hint_block:
        system = system.rstrip() + "\n\n" + hint_block

    user_parts = [
        f"文件路径: {source_path}",
        f"冲突区域 {task['index']}/{task['total']}（约第 {hs}-{he} 行）",
        f"冲突类型: {task.get('kind', 'unknown')}",
        "=== 当前 vendor 冲突主体 ===",
        body or task.get("vendor_snippet", ""),
    ]
    if task.get("incremental_only"):
        user_parts.append(
            "【强制】vendor 已有同名函数且实现与 GKI 旧代码不同。"
            "禁止贴入整个 GKI 函数或新增第二个同名定义；只把 .rej 的 +/- 合入现有函数。"
        )
    incoming_body = (task.get("incoming_body_snippet") or "").strip()
    if incoming_body and not task.get("incremental_only"):
        user_parts.append("=== GKI incoming 冲突主体 ===")
        user_parts.append(incoming_body)
    hunk_body = (task.get("hunk_body") or "").strip()
    if hunk_body:
        user_parts.append("=== .rej hunk（只把其中 +/- 合入 vendor）===")
        user_parts.append(hunk_body)
        user_parts.append(
            "【强制】每条 .rej 的 + 必须紧挨其前导 context 落地；"
            "禁止把 GKI 插入写进厂商独有块（如 CONTINUOUS_WR）。"
            "若 hunk 下一行是 }，合入后下一行仍须是该 }。"
        )
    _append_conflict_logic_hints(user_parts, task)
    old_fn = (task.get("gki_old_function") or "").strip()
    new_fn = (task.get("gki_new_function") or "").strip()
    if old_fn or new_fn:
        user_parts.append(
            "【函数实现对照】对照 GKI 旧/新函数的语义变更，合入 vendor；"
            "禁止用 GKI 新函数整体替换。"
        )
        if old_fn:
            user_parts.append("=== GKI 旧版函数实现 ===")
            user_parts.append(old_fn)
        if new_fn:
            user_parts.append("=== GKI 新版函数实现（对照用，禁止整段粘贴）===")
            user_parts.append(new_fn)
    preview = (task.get("function_merge_preview") or "").strip()
    if preview:
        user_parts.append(
            "=== 函数级三路合并预览（含冲突标记；在标记处解决并删掉标记）==="
        )
        user_parts.append(preview)
    user_parts.append("请输出 summary + ```diff unified diff ```")

    max_tokens = _estimate_region_merge_max_tokens(
        task.get("vendor_snippet", ""), body,
    )
    response, _usage = _call_llm(
        system, "\n\n".join(user_parts), config, timeout=300, max_tokens=max_tokens,
    )
    try:
        diff_text, summary = _extract_diff_from_llm_response(response)
        patched = _apply_unified_diff(file_content, diff_text)
        _validate_merged_source(patched, source_path=source_path)
        return patched, summary
    except (RuntimeError, ValueError) as exc:
        raise RuntimeError(f"区域 {task['index']} diff: {exc}") from exc


def resolve_merge_conflict_tasks_via_llm(
    *,
    source_path: str,
    original_content: str,
    tasks: List[Dict[str, Any]],
    config: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """Apply LLM (diff-first) to remaining conflict tasks."""
    from web_app.conflict_region_utils import (
        apply_hunk_merge_to_source,
        assert_micro_inserts_follow_context,
        extract_merged_hunk_body,
        validate_merged_hunk_middle,
        _vendor_body_lines,
    )

    if config is None:
        config = get_llm_config()
    if not config.get("api_key"):
        raise RuntimeError("LLM 未配置 API Key")

    merged = original_content
    summaries: List[str] = []
    for task in sorted(tasks, key=lambda t: t["replace_start"], reverse=True):
        hunk_body = (task.get("hunk_body") or "").strip()
        try:
            candidate, summary = _resolve_conflict_region_via_llm_diff(
                source_path=source_path,
                file_content=merged,
                task=task,
                config=config,
            )
            if hunk_body:
                assert_micro_inserts_follow_context(candidate, hunk_body)
            merged = candidate
            summaries.append(f"#{task['index']} diff: {summary}")
            continue
        except RuntimeError:
            pass

        region_merged, summary = _resolve_conflict_region_via_llm(
            source_path=source_path,
            task=task,
            config=config,
        )
        pre_len = int(task.get("pre_len") or 0)
        post_len = int(task.get("post_len") or 0)
        middle = extract_merged_hunk_body(
            task["vendor_snippet"], region_merged, pre_len, post_len,
        )
        validate_merged_hunk_middle(
            middle,
            _vendor_body_lines(task["vendor_snippet"], pre_len, post_len),
        )
        merged = apply_hunk_merge_to_source(
            merged, task["replace_start"], task["replace_end"], middle,
        )
        if hunk_body:
            assert_micro_inserts_follow_context(merged, hunk_body)
        summaries.append(f"#{task['index']} body: {summary}")

    return merged, "LLM " + "; ".join(summaries)


def resolve_merge_conflict_via_llm(
    *,
    source_path: str,
    original_content: str,
    rej_content: str = "",
    has_conflict_markers: bool = False,
    config: Optional[Dict[str, str]] = None,
    job: Optional[Dict[str, Any]] = None,
    job_id: str = "",
) -> Tuple[str, str]:
    """Return (merged_file_content, summary); prefers deterministic merge when job tags available."""
    if job and (job.get("from_tag") or job.get("to_tag")):
        from web_app.conflict_merge_service import resolve_conflict_file
        proposed, summary, _strategy = resolve_conflict_file(
            job,
            job_id=job_id,
            source_path=source_path,
            original_content=original_content,
            rej_content=rej_content,
            has_conflict_markers=has_conflict_markers,
        )
        return proposed, summary

    return _resolve_merge_conflict_llm_only(
        source_path=source_path,
        original_content=original_content,
        rej_content=rej_content,
        has_conflict_markers=has_conflict_markers,
        config=config,
    )


def _resolve_merge_conflict_llm_only(
    *,
    source_path: str,
    original_content: str,
    rej_content: str = "",
    has_conflict_markers: bool = False,
    config: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """LLM-only fallback when job has no tag metadata."""
    from web_app.conflict_region_utils import (
        apply_hunk_merge_to_source,
        assert_micro_inserts_follow_context,
        collect_conflict_merge_tasks,
        extract_merged_hunk_body,
        validate_merged_hunk_middle,
        _vendor_body_lines,
    )

    if config is None:
        config = get_llm_config()
    if not config.get("api_key"):
        raise RuntimeError("LLM 未配置 API Key")

    tasks = collect_conflict_merge_tasks(
        original_content=original_content,
        rej_content=rej_content,
        has_conflict_markers=has_conflict_markers,
    )
    if not tasks:
        raise RuntimeError(
            "无法解析冲突区域（无 .rej hunk 且无 conflict marker），请手动合入"
        )

    merged = original_content
    summaries: List[str] = []
    for task in sorted(tasks, key=lambda t: t["replace_start"], reverse=True):
        region_merged, summary = _resolve_conflict_region_via_llm(
            source_path=source_path,
            task=task,
            config=config,
        )
        pre_len = int(task.get("pre_len") or 0)
        post_len = int(task.get("post_len") or 0)
        try:
            middle = extract_merged_hunk_body(
                task["vendor_snippet"],
                region_merged,
                pre_len,
                post_len,
            )
            validate_merged_hunk_middle(
                middle,
                _vendor_body_lines(task["vendor_snippet"], pre_len, post_len),
            )
        except ValueError as exc:
            raise RuntimeError(f"区域 {task['index']}: {exc}") from exc
        merged = apply_hunk_merge_to_source(
            merged,
            task["replace_start"],
            task["replace_end"],
            middle,
        )
        summaries.append(f"#{task['index']}: {summary}")

    if rej_content.strip():
        assert_micro_inserts_follow_context(merged, rej_content)

    _validate_merged_source(merged, source_path=source_path)
    if "<<<<<<<" in merged or ">>>>>>>" in merged:
        raise RuntimeError("合并后仍含 git 冲突标记，请检查各冲突区域")

    orig_lines = (original_content or "").count("\n") + 1
    merg_lines = (merged or "").count("\n") + 1
    if orig_lines >= 80 and merg_lines < int(orig_lines * 0.95):
        raise RuntimeError(
            f"合并后文件行数异常减少：{merg_lines} 行（原 {orig_lines} 行），疑似区域替换错误"
        )

    combined = f"共 {len(tasks)} 个区域 — " + "; ".join(summaries)
    return merged, combined


_FIX_BLOCKS_RE = re.compile(
    r"```(?:fix|fixed|patch|merged)?\s*([^\n`]+)\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def _llm_output_truncated(response: str, usage: Optional[Dict[str, Any]], max_tokens: int) -> bool:
    """True when the model likely hit max_tokens before finishing the reply."""
    usage = usage or {}
    if str(usage.get("finish_reason") or "").lower() == "length":
        return True
    try:
        completion = int(usage.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        completion = 0
    if max_tokens > 0 and completion >= max(1, int(max_tokens * 0.95)):
        return True
    text = response or ""
    if text.count("```") % 2 == 1:
        return True
    return False


def _parse_build_fix_blocks(response: str) -> Tuple[List[Dict[str, str]], str]:
    """Parse summary + closed ```fix path blocks. Incomplete fences are ignored."""
    summary_m = _SUMMARY_RE.search(response or "")
    summary = summary_m.group(1).strip() if summary_m else "AI 编译修复完成"
    from web_app.build_fix_service import sanitize_llm_fix_path

    fixes: List[Dict[str, str]] = []
    for m in _FIX_BLOCKS_RE.finditer(response or ""):
        path = sanitize_llm_fix_path(m.group(1))
        content = m.group(2)
        if content.endswith("\n"):
            content = content.rstrip("\n") + "\n"
        if path and path != "unknown" and content.strip():
            fixes.append({"path": path, "content": content})
    if not fixes:
        block_m = _MERGED_BLOCK_RE.search(response or "")
        if block_m and (block_m.group(1) or "").strip():
            fixes.append({"path": "unknown", "content": block_m.group(1)})
    return fixes, summary

def _build_fix_reference_examples() -> str:
    """Real failure patterns as illustrations only — not prescriptive rules for specific errors."""
    return """=== 参考示例（真实踩坑对照，非强制剧本 — 须以当前诊断链/snippet 为准） ===
以下仅说明**通用规则**在过往任务中的典型失败形态；**不得**照搬路径、行号或符号名。

**示例 1 — 行号锚点错误，误删文件头 `/**`**
- 实际 diff：`@@ -1,…` 起笔，hunk 含 `-/**`；匹配到文件头章节说明而非厂商 `#define`
- 应吸取：`@@` 锚在厂商 `#define` 行；不要删除任何注释行；不要整文件重写

**示例 2 — 散落删除注释边界**
- 应吸取：不要删除任何注释行；宏重定义只删厂商重复 `#define`

**示例 3 — 给 GKI 头出 diff / 整文件重写导致截断**
- 应吸取：禁止 `include/linux/` fix 块；每个厂商文件只出很短的 unified diff"""


def _comment_block_integrity_guidance() -> str:
    """Rules: fix only erroring code; do not delete comment blocks unless repairing broken structure."""
    return """=== ⚠ 注释与最小改动（删改 .h/.c 时遵守） ===
**首要原则**：只修改与**当前编译报错**直接相关的代码行，**不要**为了「整洁」去删 kernel-doc / `/** … */` 注释块。

**宏重定义**：只删除厂商侧重复 `#define`（不要 `#ifndef`、不要改 GKI）。此处只强调：
- ❌ 不要删任何 `/**`、` *`、` */`、`/*` 注释行
- ❌ 不要把整个 .h/.c 写入 fix 块（diff 通常十几行）
- `@@` 锚在厂商侧 `#define` 行，禁止 `@@ -1,…`

**若必须动到注释（仅当报错本身与注释/守卫相关，或磁盘 snippet 标明结构已损坏）**：
- 不得**散落**删除：只删 `/**` 留 ` *`、只删 ` */` 留 ` *` 等
- 不得误删文件头 license / 与本次报错无关的章节说明块"""


def _macro_redefinition_guidance(errors: List[Dict[str, Any]]) -> str:
    """Inject when gcc reports macro redefined + previous-definition note (generic, not MIN-only)."""
    messages = " ".join((e.get("message") or "").lower() for e in errors)
    if "redefin" not in messages and "macro redefined" not in messages:
        return ""
    from web_app.build_fix_diagnostics import is_kernel_readonly_path

    def _is_redef_error(e: Dict[str, Any]) -> bool:
        if (e.get("kind") or "").lower() != "error":
            return False
        msg = (e.get("message") or "").lower()
        return "redefin" in msg or "macro redefined" in msg

    redef_errors = [e for e in errors if _is_redef_error(e)]
    prev_sites = [
        e for e in errors
        if (e.get("kind") or "").lower() == "note"
        or e.get("context_role") == "previous_definition"
        or "previous definition" in (e.get("message") or "").lower()
    ]
    if not prev_sites and not redef_errors:
        return ""

    err_vendor = [e for e in redef_errors if not is_kernel_readonly_path(e.get("file") or "")]
    err_kernel = [e for e in redef_errors if is_kernel_readonly_path(e.get("file") or "")]
    note_vendor = [e for e in prev_sites if not is_kernel_readonly_path(e.get("file") or "")]
    note_kernel = [e for e in prev_sites if is_kernel_readonly_path(e.get("file") or "")]
    case1 = bool(err_vendor and note_kernel)
    case2 = bool(err_kernel and note_vendor)
    if not case1 and not case2:
        # Fall back from roles when note/error pairing is incomplete.
        case1 = bool(err_vendor)
        case2 = bool(err_kernel)

    def _fmt(sites: List[Dict[str, Any]]) -> str:
        return ", ".join(
            f"{e.get('file', '?')}:{e.get('line', '?')}" for e in sites[:5]
        ) or "(见日志)"

    parts = [
        "=== ⚠ 本次为「宏重定义」类错误 — 只删厂商重复 #define（禁止改 GKI） ===",
        "判定：error = 后 include 的定义；note: previous definition = 先 include 的定义。",
        "**无论哪种 include 顺序，改法相同**：删除厂商代码里那份与内核同名的 `#define`。",
        "不要 `#ifndef` 包裹、不要改 `include/linux/`、不要整文件重写、不要删注释。",
        "**输出硬限制**：summary 一行 + 每个厂商文件一个很短的 unified diff（通常 <20 行）。",
    ]
    if case1:
        parts.append(
            f"**情形 1（本次命中）— GKI 头在前，厂商头在后**：\n"
            f"- error 在厂商: {_fmt(err_vendor)}\n"
            f"- previous definition 在 GKI（只读）: {_fmt(note_kernel)}\n"
            f"- **在厂商 error 落点删除** `#define`（内核已提供实现）。"
        )
    if case2:
        parts.append(
            f"**情形 2（本次命中）— 厂商头在前，GKI 头在后**：\n"
            f"- error 在 GKI（只读，禁止出 diff）: {_fmt(err_kernel)}\n"
            f"- previous definition 在厂商: {_fmt(note_vendor)}\n"
            f"- **在厂商 note 处删除** `#define`（不要给 GKI 出 diff）。"
        )
    parts.append(
        "**禁止**：修改 `include/linux/*.h`；`#ifndef` 包裹；diff 删除注释行；"
        "把整个 .h 写入 fix 块；删完 `#define` 后再追加 `#ifdef`/`#undef` 块。"
    )
    parts.append(
        "**diff 锚点**：`@@` 对齐厂商 `#define <宏名>` 行，禁止 `@@ -1,…`；每个冲突宏一个 hunk。"
    )
    return "\n".join(parts)


def _identifier_collision_guidance(chains: List[Dict[str, Any]]) -> str:
    """Generic guidance when vendor identifiers collide with kernel macros."""
    collision = [
        c for c in chains
        if c.get("chain_type") == "kernel_macro_collision"
    ]
    if not collision:
        return ""
    symbols = ", ".join(
        f"'{c.get('symbol')}'" for c in collision[:4] if c.get("symbol")
    )
    return f"""=== ⚠ 本次为「vendor 标识符 vs 内核宏」冲突 — 必读修复决策 ===
已识别 {len(collision)} 条诊断链，涉及符号: {symbols or '(见诊断链)'}。

**推理顺序（必须按此执行，再写 summary 与 diff）**：
1. primary error 在 vendor/ 可写源文件；readonly note 指向 `include/linux/` 等内核宏定义 — **内核头只读，勿改**
2. error 形态为 `too many arguments to function-like macro` / `expected ';' after` 时，通常表示 vendor 侧**函数名/宏名**与内核宏**同名**，预处理阶段被内核宏替换
3. **优先**在 vendor 侧消除同名冲突（例如 rename 局部 static 函数并同步改调用点；或 rename vendor 宏），使编译单元不再与内核宏同名
4. 同文件靠后的 `undeclared identifier` / `expected ';'` 常为**连带错误**（cascade），修 primary 后再验证，勿只对 cascade 打补丁
5. 禁止 `#undef` 内核宏、禁止修改 `include/linux/` 上游头、禁止用 `#ifndef` 包裹 vendor 侧仍会在当前内核版本下展开的 `#define`

**推荐修复（按优先级，选最小 diff）**：
A. 在 vendor 源文件 rename 与内核宏同名的局部符号，并更新本文件内全部引用
B. 若 vendor 头文件定义了与内核同名的宏/函数式宏，删除或 rename vendor 侧定义（参照宏重定义链路的处理方式）
C. 仅当确实无法 rename 且 diff 更小时，才考虑调整 include 顺序 — 通常不如 rename 可靠

**明确禁止**：
- ❌ 修改 note 指向的内核头文件
- ❌ `#undef` 内核宏名
- ❌ 对 cascade error 单独补 DEVICE_ATTR / sysfs 属性或前移声明；文件末尾往往已有 DEVICE_ATTR，修 primary 处 rename 即可
- ❌ 只 rename 函数定义而不同步改本文件内全部调用点（snippet 中 `collision_use` 锚点须一并修改）"""


def _is_llm_timeout_message(msg: str) -> bool:
    low = msg.lower()
    return "超时" in msg or "timed out" in low or "timeout" in low


def resolve_build_errors_via_llm(
    *,
    errors: List[Dict[str, Any]],
    log_excerpt: str = "",
    file_contexts: Optional[List[Dict[str, Any]]] = None,
    target_repo_dir: str = "",
    build_workdir: str = "",
    search_roots: Optional[List[Dict[str, str]]] = None,
    apply_feedback: Optional[List[str]] = None,
    focus_paths: Optional[List[str]] = None,
    diagnostic_chains: Optional[List[Dict[str, Any]]] = None,
    readonly_note_contexts: Optional[List[Dict[str, Any]]] = None,
    wait_log: Optional[Any] = None,
    config: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, str]], str]:
    """Return ([{path, content}, ...], summary) for build error fixes."""
    if config is None:
        config = get_llm_config()
    if not config.get("api_key"):
        raise RuntimeError("LLM 未配置 API Key")

    system = load_prompt("build_fix")
    hint_block = user_hint_prompt_suffix("build_fix")
    if hint_block:
        system = system.rstrip() + "\n\n" + hint_block

    llm_errors = list(errors or [])
    llm_chains = list(diagnostic_chains or [])
    llm_readonly = list(readonly_note_contexts or [])
    llm_excerpt = log_excerpt or ""

    if focus_paths and len(focus_paths) == 1:
        from web_app.build_fix_diagnostics import filter_diagnostics_for_focus
        llm_errors, llm_chains, llm_readonly = filter_diagnostics_for_focus(
            llm_errors, llm_chains, llm_readonly, focus_paths[0],
        )

    def _compose_user_msg(*, compact: bool) -> str:
        parts = [
            f"合入目标路径（⚠ 尽可能不要修改）: {target_repo_dir or '(未指定)'}",
            f"编译工作目录（Android 源码根或编译 cwd，优先在此树内找替代修复）: {build_workdir or '(未指定)'}",
        ]
        if search_roots and not compact and not focus_paths:
            parts.append("=== 文件搜索根目录（按优先级，合入目标路径最后） ===")
            for i, r in enumerate(search_roots, 1):
                mark = " ⚠ 合入目标，非必要勿改" if r.get("name") == "target_repo" else ""
                parts.append(f"{i}. [{r.get('name', '?')}] {r.get('path', '')}{mark}")
            parts.append(
                "fix 代码块路径请优先落在非 target_repo 的根下；"
                "仅当必须改合入树时在 summary 中说明理由。"
            )
        if llm_errors:
            parts.append("=== 结构化编译错误（含角色标注；同文件多条 error 均已保留） ===")
            role_hints = {
                "primary_error": "← 厂商侧 error，在此修复（勿改内核）",
                "previous_definition": "← 厂商先前定义，在此修复（勿改内核）",
                "related_error": "← 同文件关联 error",
                "cascade_error": "← 可能由前面错误引起，勿单独打补丁",
                "readonly_macro_definition": "← GKI 先前定义，只读勿改",
                "readonly_error_site": "← GKI error 落点，只读；改厂商文件",
                "error_site": "",
            }
            limit = 12 if compact else 20
            for i, err in enumerate(llm_errors[:limit], 1):
                role = err.get("context_role") or err.get("role") or ""
                hint = role_hints.get(role, "")
                kind = err.get("kind") or "error"
                parts.append(
                    f"{i}. [{kind}/{role}] {err.get('file', '?')}:{err.get('line', '?')}: "
                    f"{err.get('message', err.get('kind', 'error'))} {hint}".rstrip()
                )
        else:
            parts.append("未解析到标准 gcc error 行，请根据下方日志片段推断根因。")

        if llm_chains:
            from web_app.build_fix_diagnostics import format_diagnostic_chains_for_llm
            chain_text = format_diagnostic_chains_for_llm(llm_chains)
            if chain_text:
                parts.append(chain_text)

        macro_hint = _macro_redefinition_guidance(llm_errors)
        if macro_hint:
            parts.append(macro_hint)
        collision_hint = _identifier_collision_guidance(llm_chains)
        if collision_hint:
            parts.append(collision_hint)
        parts.append(_comment_block_integrity_guidance())
        parts.append(_build_fix_reference_examples())

        if llm_readonly:
            parts.append("=== 只读诊断来源：内核宏/note 片段（勿修改这些文件） ===")
            for note in llm_readonly[:3]:
                macro = note.get("macro") or "?"
                parts.append(
                    f"--- READONLY {note.get('fix_path') or note.get('path', '?')}"
                    f":{note.get('line', '?')} macro={macro} ---"
                )
                parts.append(note.get("snippet") or note.get("message") or "")

        if llm_excerpt and not compact:
            parts.append("=== 编译日志片段 ===")
            parts.append(llm_excerpt[:8000 if focus_paths else 18_000])
        elif llm_excerpt and compact:
            parts.append("=== 编译日志片段（精简） ===")
            parts.append(llm_excerpt[:5000])

        if focus_paths:
            parts.append("=== 本次仅修改以下路径（每个路径一个 fix 块，上下文须与该路径 snippet 逐字一致） ===")
            for fp in focus_paths:
                if "/include/linux/" in fp.replace("\\", "/"):
                    parts.append(
                        f"- {fp} （只读内核头，禁止修改；改 vendor note 处 previous definition）"
                    )
                else:
                    parts.append(f"- {fp}")

        if file_contexts:
            parts.append("=== 相关源文件上下文（当前磁盘内容；fix 块路径用 FIX_PATH，勿抄 [build_workdir] 前缀） ===")
            for ctx in file_contexts[:16]:
                loc_hint = ctx.get("abs_path") or ctx.get("path", "?")
                fix_path = ctx.get("fix_path") or ""
                target_tag = " [位于合入目标路径内，优先找外部替代修复]" if ctx.get("in_target_repo") else ""
                role_label = ctx.get("role_label") or ctx.get("role") or ""
                role_prefix = f"[{role_label}] " if role_label else ""
                header = f"--- {role_prefix}FIX_PATH: {fix_path or loc_hint}{target_tag} ---"
                parts.append(header)
                aliases = ctx.get("symlink_aliases") or []
                if aliases and not compact:
                    parts.append(
                        "（以下路径为软链接别名，与 FIX_PATH 同一文件，只需输出一个 fix 块）: "
                        + ", ".join(aliases[:6])
                    )
                anchor_lines = ctx.get("anchors") or []
                if anchor_lines and len(anchor_lines) > 1:
                    anchor_desc = ", ".join(
                        f"L{a.get('line')}({a.get('role', '?')})" for a in anchor_lines[:8]
                    )
                    parts.append(f"（多错误锚点: {anchor_desc}；snippet 中 >>> 标记各 error 行）")
                content = ctx.get("content") or ""
                use_snippet = (
                    compact
                    or bool(focus_paths)
                    or len(content) > 6000
                    or len(llm_errors) > 10
                )
                if content and not use_snippet and len(file_contexts or []) <= 2 and len(content) <= 12_000:
                    parts.append(content)
                else:
                    parts.append(ctx.get("snippet") or content[:6000])

        if apply_feedback:
            parts.append("=== 上次 diff 应用失败（必须据此修正，勿重复相同上下文） ===")
            for i, msg in enumerate(apply_feedback[:8 if compact else 12], 1):
                parts.append(f"{i}. {msg}")
            struct_markers = (
                "块注释", "孤立", "/**", "#ifndef", "头文件结构", "注释未闭合",
            )
            if any(any(m in fb for m in struct_markers) for fb in apply_feedback):
                parts.append(
                    "=== 上次写回因块注释结构被破坏而拒绝 ===\n"
                    "宏重定义修复：只删除厂商侧重复 `#define`，不要 `#ifndef`，不要改 GKI。"
                    "**不要**在 diff 中删除任何 `/**`/` *`/` */` 行，禁止整文件重写。\n"
                    "若拒绝信息含「孤立 kernel-doc」：说明此前 diff 误删了文件头注释 — "
                    "本次锚点设在厂商 `#define` 行，禁止 `@@ -1,…`。\n"
                    "若 snippet 显示磁盘已有孤立 ` *` 行（历史损坏）：须先补回 `/**` 或删除残缺注释块，再改宏定义。"
                )

        parts.append(
            "请输出 summary 行 + 一个或多个 ```fix 文件路径\\nunified diff ``` 代码块。"
            "禁止整文件重写；只提交最小 diff。路径必须与日志或上述搜索根目录一致。"
            "多个相似头文件须分别输出独立 fix 块，各自上下文对应该路径 snippet。"
            "修复策略须与当前诊断链一致；勿套用参考示例中的路径/行号/符号名。"
        )
        return "\n\n".join(parts)

    user_msg = _compose_user_msg(compact=False)
    max_out = BUILD_FIX_LLM_MAX_TOKENS
    llm_timeout = BUILD_FIX_LLM_TIMEOUT
    if wait_log:
        hint_parts = ["最小改动（只修报错代码）", "参考示例"]
        if _macro_redefinition_guidance(llm_errors):
            hint_parts.insert(0, "宏重定义决策")
        if _identifier_collision_guidance(llm_chains):
            hint_parts.append("标识符冲突")
        if apply_feedback:
            hint_parts.append("上次写回失败反馈")
        if hint_block:
            hint_parts.append("用户补充说明")
        wait_log(f"prompt 约束已注入: {', '.join(hint_parts)}")
        wait_log(
            f"LLM 请求约 {(len(system) + len(user_msg)) // 1000}k 字符，"
            f"{len(file_contexts or [])} 个文件上下文，"
            f"timeout={llm_timeout}s，max_tokens={max_out}"
        )

    def _do_call(
        user: str,
        *,
        timeout: int,
        tokens: int,
    ) -> Tuple[str, Dict[str, Any]]:
        return _call_llm(
            system,
            user,
            config,
            timeout=timeout,
            max_tokens=tokens,
            max_attempts=BUILD_FIX_LLM_MAX_ATTEMPTS,
        )

    try:
        response, usage = _do_call(user_msg, timeout=llm_timeout, tokens=max_out)
    except RuntimeError as exc:
        if not _is_llm_timeout_message(str(exc)):
            raise
        extended_timeout = min(600, max(llm_timeout + 120, int(llm_timeout * 1.5)))
        if wait_log:
            wait_log(
                f"请求超时，以完整 prompt / timeout={extended_timeout}s / max_tokens={max_out} 重试"
                "（保留全部修复约束，不精简）"
            )
        try:
            response, usage = _do_call(
                user_msg, timeout=extended_timeout, tokens=max_out,
            )
        except RuntimeError as exc2:
            if not (focus_paths and _is_llm_timeout_message(str(exc2))):
                raise
            compact_msg = _compose_user_msg(compact=True)
            compact_timeout = min(360, max(180, llm_timeout))
            compact_tokens = max(2048, max_out // 2)
            if wait_log:
                wait_log(
                    "仍超时，以精简日志片段 prompt（"
                    f"{len(compact_msg) // 1000}k 字符）/ max_tokens={compact_tokens} / "
                    f"timeout={compact_timeout}s 重试（宏重定义规则仍保留）"
                )
            response, usage = _do_call(
                compact_msg, timeout=compact_timeout, tokens=compact_tokens,
            )
    if wait_log and usage:
        wait_log(
            f"LLM 响应完成: prompt={usage.get('prompt_tokens', '?')} "
            f"completion={usage.get('completion_tokens', '?')} tokens"
            + (f" finish_reason={usage.get('finish_reason')}" if usage.get("finish_reason") else "")
        )

    truncated = _llm_output_truncated(response, usage, max_out)
    fixes, summary = _parse_build_fix_blocks(response)
    retry_cap = max(BUILD_FIX_LLM_RETRY_MAX_TOKENS, max_out)
    if truncated and not fixes and retry_cap > max_out:
        retry_tokens = retry_cap
        retry_timeout = min(600, max(llm_timeout + 60, int(llm_timeout * 1.25)))
        if wait_log:
            wait_log(
                f"输出疑似被 max_tokens={max_out} 截断"
                f"（completion={usage.get('completion_tokens', '?')}），"
                f"以 max_tokens={retry_tokens} 重试"
            )
        response, usage = _do_call(user_msg, timeout=retry_timeout, tokens=retry_tokens)
        if wait_log and usage:
            wait_log(
                f"截断重试完成: prompt={usage.get('prompt_tokens', '?')} "
                f"completion={usage.get('completion_tokens', '?')} tokens"
                + (f" finish_reason={usage.get('finish_reason')}" if usage.get("finish_reason") else "")
            )
        truncated = _llm_output_truncated(response, usage, retry_tokens)
        fixes, summary = _parse_build_fix_blocks(response)

    if not fixes:
        if focus_paths and re.search(
            r"无需|跳过|已无|无需修改|不必修改|已删除|已修复|无需再改", summary, re.I
        ):
            return [], summary
        if truncated:
            raise RuntimeError(
                "LLM 输出被 max_tokens 截断，未得到完整 fix 代码块"
                f"（completion={usage.get('completion_tokens', '?')}）。"
                "可提高 GKI_BUILD_FIX_LLM_MAX_TOKENS 后重试编译修复"
            )
        raise RuntimeError("LLM 未返回有效的 fix 代码块")
    if truncated and wait_log:
        wait_log(f"输出可能仍截断，已解析 {len(fixes)} 个完整 fix 块，其余留待下一轮")

    return fixes, summary


"""检查飞书 ModemEE 多维表格（换票 + 按 HASH 查询）

使用方式（在 modem-analysis-unified 根目录，或任意目录）：

    set FEISHU_DEBUG=1
    python analysis_skills/modem-l2-ee-analysis/scripts/check_feishu_record.py [ee_hash]

会加载 skill 根目录下的 .env（与 feishu_bitable_client 一致）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
# scripts → modem-l2-ee-analysis → analysis_skills → modem-analysis-unified
SKILL_ROOT = SCRIPT_DIR.parents[2]
SHARED_DIR = SKILL_ROOT / "scripts" / "_shared"

if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

try:
    from dotenv import load_dotenv

    env_path = SKILL_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from feishu_bitable_client import FeishuBitableClient, query_modemee_from_feishu

app_id = (os.getenv("FEISHU_APP_ID") or "").strip()
app_secret = (os.getenv("FEISHU_APP_SECRET") or "").strip()

if not app_id or not app_secret:
    print(
        "错误：请设置 FEISHU_APP_ID / FEISHU_APP_SECRET（可在 skill 根目录 .env）",
        file=sys.stderr,
    )
    sys.exit(1)

print(f"[check] SKILL_ROOT={SKILL_ROOT}", file=sys.stderr)
print(f"[check] dotenv_loaded={bool((SKILL_ROOT / '.env').exists())}", file=sys.stderr)

client = FeishuBitableClient(app_id=app_id, app_secret=app_secret)

ee_hash = sys.argv[1] if len(sys.argv) > 1 else "de4e6eb8f44e047693a1711c7ed4841b"
query_result = query_modemee_from_feishu(ee_hash, client)
print(query_result)

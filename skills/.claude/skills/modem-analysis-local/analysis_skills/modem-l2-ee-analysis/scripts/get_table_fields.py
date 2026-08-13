"""获取飞书多维表格字段信息

使用方式：
    python get_table_fields.py

环境变量：
    FEISHU_APP_ID - 飞书应用 ID
    FEISHU_APP_SECRET - 飞书应用 Secret
"""

import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "_shared"))
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

import requests

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
APP_TOKEN = "JzmgbczwraPHQ1s2Fz9cmHh7nov"
TABLE_ID = "tblANV8zkvN8llAf"


def get_tenant_access_token():
    if not APP_ID or not APP_SECRET:
        print("错误：请设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET", file=sys.stderr)
        sys.exit(1)
    url = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}
    response = requests.post(url, json=payload, timeout=30)
    data = response.json()
    return data.get("tenant_access_token")


def get_table_fields():
    token = get_tenant_access_token()
    url = f"{FEISHU_API_BASE}/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/fields"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, timeout=30)
    return response.json()


if __name__ == "__main__":
    result = get_table_fields()
    print(json.dumps(result, ensure_ascii=False, indent=2))

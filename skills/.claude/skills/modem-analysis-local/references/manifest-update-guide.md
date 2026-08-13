# Manifest 更新工具使用指南

## 核心原则

1. **逐层写回**：L0 完成 → 写 `l0_baseline`；L1 完成 → 写 `l1_business`；……禁止全部做完再一次性写入。
2. **首选 `str_replace`**：直接编辑 `job_manifest.json`，精确替换占位 `{}`。
3. **备选固定脚本**：仅使用仓库内 `scripts/update_manifest.py`，配合 `--data-file` 传入 JSON 数据文件。
4. **禁止临时 Python 脚本**：AI 不得生成 `_tmp_*.py` 等来写 manifest。

---

## 方法一：`str_replace` 直接编辑（首选）

**适用**：所有 L0/L1/L2/L3；Windows；含换行的 `final_report`；复杂嵌套。

**步骤**：

1. 定位 manifest 中的空占位，例如 `"l0_baseline": {}`
2. 用 `str_replace` 替换为完整 JSON 对象（注意逗号与缩进）
3. 更新 `"updated_at"`（`_meta` 节）

### L0 示例

```text
old: "l0_baseline": {}
new: "l0_baseline": { ...完整对象... }
```

### L3 示例

L3 需同时写两个字段，可两次 `str_replace`：

```text
old: "l3_conclusion": {},
     "final_report": ""
```

或先替换 `l3_conclusion`，再单独替换 `"final_report": ""`。

---

## 方法二：固定脚本 + 数据文件（备选）

**适用**：单阶段 JSON 体积大、不便放进 `str_replace` 参数时。

**步骤**：

1. 用 Write 工具写入纯 JSON 数据文件（不是 `.py`），例如  
   `{WORKSPACE_ROOT}/{issue_key}/.stage_l0.json`
2. 调用固定脚本：

```bash
# Windows / Linux 通用
PYTHONIOENCODING=utf-8 python scripts/update_manifest.py \
  --manifest Z:\skills\data_store_linux\OS162-37733\job_manifest.json \
  --stage l0 \
  --data-file Z:\skills\data_store_linux\OS162-37733\.stage_l0.json
```

L2 示例：

```bash
python scripts/update_manifest.py \
  --manifest <MANIFEST_PATH> \
  --stage l2 --domain call \
  --data-file <STAGE_JSON_PATH>
```

L3 的 JSON 结构示例（`final_report` 与 l3 字段同级放在同一文件）：

```json
{
  "conclusion_type": "valid",
  "issue_type": "call",
  "primary_root_cause": { "cause": "...", "confidence": "high", "evidence": [] },
  "recommendations": [],
  "status": "completed",
  "final_report": "## 分析结论\n\n..."
}
```

脚本会自动：写入 `l3_conclusion`、提取 `final_report`、刷新 `_meta.updated_at`。

### 脚本参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--manifest` | 推荐 | manifest 完整路径（优先） |
| `--issue-key` | 与 workspace 二选一 | 未给 `--manifest` 时使用 |
| `--workspace` | 否 | 默认读 `.env` 的 `WORKSPACE_ROOT` |
| `--stage` | 是 | `l0` / `l1` / `l2` / `l3` |
| `--domain` | L2 必填 | `call` / `data` / `sim` / `ee` |
| `--data-file` | 与 `--data` 二选一 | **Windows 推荐** |
| `--data` | 与 `--data-file` 二选一 | 短 JSON 字符串（Linux/Mac） |

---

## 禁止做法

| 做法 | 原因 |
|------|------|
| 创建 `_tmp_update_*.py` 临时脚本 | 不可复现、易留垃圾文件、与固定脚本职责重复 |
| `python -c "import json; ..."` | PowerShell 引号/转义失败率高 |
| Read 整 manifest + Write 整文件 | AI 易破坏 JSON 结构或漏字段 |
| 分析结束才一次性写 L0~L3 | 违反编排契约，中途失败无法恢复 |
| 直接改 NAS 上的 manifest | 必须写本地 `{WORKSPACE_ROOT}/{issue_key}/` |

---

## 常见问题

**Q: `final_report` 很长怎么办？**  
A: 用 `str_replace` 只替换 `"final_report": ""` 这一段；或 L3 走 `--data-file`。

**Q: 阶段 JSON 文件要提交 git 吗？**  
A: 否。`.stage_*.json` 为本地中间产物，写回 manifest 后可删；已在 `.gitignore` 时勿提交。

**Q: `--data` 和 `--data-file` 选哪个？**  
A: Windows 一律 `--data-file`；Linux 短数据可用 `--data`。

---

## 总结

- ✅ 每层完成 → 立即写回  
- ✅ 首选 `str_replace`  
- ✅ 备选 `scripts/update_manifest.py --manifest ... --data-file ...`  
- ❌ 禁止临时 Python 脚本、禁止 `python -c`、禁止整文件重写

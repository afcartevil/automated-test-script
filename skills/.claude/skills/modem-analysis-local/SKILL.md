---
name: modem-analysis-local
description: 给定 Jira 单号或已有 manifest，完成 modem 日志准备与 L0→L1→L2→L3 故障分析，产出可回写 Jira 的报告。
version: 1.0.0
---

# Modem 故障分析

本 skill 包含日志准备、分层分析与结论汇总：

- `log-pipeline/` — Jira 上下文、下载、解压、trace 导出、`job_manifest.json`
- `analysis_skills/` — L0 ~ L3 分析 playbook
- `scripts/` — manifest 写回、可选飞书看板更新

**`SKILL_ROOT`**：本文件所在目录。所有相对命令均以此为基准。

## 一、输入与模式

| 模式 | 用户说法示例 | 必填参数 |
|------|--------------|----------|
| **full** | 「分析 OS162-37733」 | `issue_key` |
| **prepare-only** | 「只下载处理 log」 | `issue_key` |
| **analyze-only** | 「log 已准备好，直接分析」 | `issue_key`（工作区已有 manifest） |
| **manifest** | 「分析这个 manifest」 | `manifest_path` |

## 二、首次使用（环境）

1. 在 skill 根目录执行：`pip install -r requirements.txt`（需要 Box 浏览器下载时再 `playwright install chromium`）
2. 复制 `copy .env.example .env`，填写至少 `WORKSPACE_ROOT`、`JIRA_*`
3. 将配置同步给日志准备模块（其读取 `log-pipeline/.env`）：
   ```powershell
   copy .env log-pipeline\.env
   ```
4. 外部工具（按需）：7-Zip、`ELT_HOME` / `NLT_HOME`、Wireshark、QCOM QUTS — 见 `references/setup.md`

## 三、执行步骤（严格顺序）

### Step 0 — 日志准备（full / prepare-only）

```powershell
set PYTHONIOENCODING=utf-8
python log-pipeline\run_pipeline.py --issue-key <issue_key>
```

- 成功后在 `{WORKSPACE_ROOT}/{issue_key}/job_manifest.json` 落盘
- 失败：终止流程，透传 pipeline 输出
- **analyze-only / manifest**：跳过本步

**已有 manifest**：确认 `job_manifest.json` 在工作区根或用户给定路径；若目录多包一层 `{issue_key}/`，上提后重跑或手动整理。

```text
MANIFEST_PATH = {WORKSPACE_ROOT}/{issue_key}/job_manifest.json
```

（manifest 模式使用用户提供的绝对路径。）

### Step 1 — L0 基础指标

读取并执行：`analysis_skills/modem-l0-baseline/SKILL.md`  
→ 写回 `manifest.analysis.l0_baseline`

### Step 2 — L1 业务判断

读取并执行：`analysis_skills/modem-l1-business-judge/SKILL.md`  
→ 写回 `manifest.analysis.l1_business`（`primary_domain ∈ { ee, call, data, sim, other }`）

### Step 3 — L2 域内分析

| primary_domain | SKILL.md |
|----------------|----------|
| `ee` | `analysis_skills/modem-l2-ee-analysis/SKILL.md` |
| `call` | `analysis_skills/modem-l2-call-analysis/SKILL.md`（+ `subskills/`） |
| `data` | `analysis_skills/modem-l2-data-analysis/SKILL.md`（+ `sub_skills/`） |
| `sim` | `analysis_skills/modem-l2-sim-analysis/SKILL.md` |
| `other` | 跳过，进入 Step 4 |

→ 写回 `manifest.analysis.l2_domains.<domain>`

### Step 4 — L3 最终结论

读取并执行：`analysis_skills/modem-l3-conclusion/SKILL.md`  
→ 写回 `manifest.analysis.l3_conclusion`、`manifest.analysis.final_report`

### Step 5 — 交付

**prepare-only**：结束，告知 `MANIFEST_PATH` 与 `WORKSPACE_ROOT`。

**full / analyze-only / manifest**：

1. 按固定格式交付 `final_report`（见下）
2. 仅当用户**明确要求更新飞书看板**时，可执行：

```powershell
set PYTHONIOENCODING=utf-8
python scripts\finalize_analysis.py --manifest <MANIFEST_PATH> --skip-upload --skip-delete
```

**交付格式（强约束）**：

```text
[FINAL_REPORT_BEGIN]
<manifest.analysis.final_report 原文>
[FINAL_REPORT_END]
```

禁止改写、压缩或翻译 `final_report`；补充说明放在 `附加说明` 小节。

---

⚠️ 各层 `SKILL.md` + `references/playbook.md` 要求 **AI 亲自分析**；不要直接调用各层 `scripts/run_*.py`（调试用）。

## 四、日志读取

```powershell
set PYTHONIOENCODING=utf-8
python analysis_skills\log-search-read\scripts\log_search_read.py --manifest <MANIFEST_PATH> list
python analysis_skills\log-search-read\scripts\log_search_read.py --manifest <MANIFEST_PATH> search --query "SIM_STATE"
```

## 五、manifest 写回

每完成一层**立即**写回。见 `references/manifest-update-guide.md`：

1. 首选 `str_replace` 精确改 JSON  
2. 备选 `python scripts/update_manifest.py --manifest <MANIFEST_PATH> --stage l0 --data-file <path>`

禁止：`python -c` 拼 JSON、整文件重写 manifest、临时 `_tmp_*.py` 批量写入。

## 六、典型对话

> 用户：分析 OS162-37733

1. 确认 `.env` 与 `log-pipeline\.env`  
2. `python log-pipeline\run_pipeline.py --issue-key OS162-37733`  
3. L0 → L1 → L2 → L3，逐步写回 manifest  
4. 输出 `[FINAL_REPORT_BEGIN]` … `[FINAL_REPORT_END]`

> 用户：manifest 在 D:\data\OS162-37733\job_manifest.json，直接分析

跳过 Step 0，从 Step 1 开始。

## 七、错误处理

### SKILL_FAILED

**唯一触发**：脚本 stdout 出现以 `SKILL_FAILED:` 开头的行 → 原样复制并终止。

日志证据不足、置信度低等**不**触发 SKILL_FAILED。

### 其他

| 情况 | 动作 |
|------|------|
| Step 0 失败 | 停止，汇报 pipeline 输出 |
| L0~L3 缺证据 | 各层降级，`gaps` + 降低 `confidence` |
| `final_report` 为空 | `FINAL_REPORT_MISSING: ...` |
| 飞书看板更新失败 | 不影响已产出结论 |

## 八、目录结构

```
modem-analysis-local/
├── SKILL.md
├── README.md
├── requirements.txt
├── .env.example
├── log-pipeline/
├── analysis_skills/
├── scripts/
├── schemas/
└── references/
```

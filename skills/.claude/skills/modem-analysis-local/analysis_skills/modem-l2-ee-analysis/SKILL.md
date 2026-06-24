---
name: modem-l2-ee-analysis
description: 对 ModemEE/Modem异常场景做 L2 故障分析，结合 `analysis.l0_baseline`、`analysis.l1_business`、Jira 上下文和打包日志，提取时间线、关键证据和候选根因，并写回 `analysis.l2_domains.ee`。同时查询飞书多维表格，若不存在则记录到表格。Use when L1 primary domain is `ee`.
---

# L2 ModemEE 分析

在 L1 已将问题判定为 `ee` 时使用这个 skill。

## 职责

- 围绕 ModemEE/Modem异常建立故障时间线。
- 识别关键失败节点、异常类型、触发原因和对比点。
- 查询飞书多维表格，判断该异常是否已知。
- 若表格中不存在该 ModemEE，则写入新记录。
- 输出 `analysis.l2_domains.ee`。

## 飞书多维表格

表格链接：https://transsioner.feishu.cn/base/JzmgbczwraPHQ1s2Fz9cmHh7nov?table=tblANV8zkvN8llAf&view=vewLvx6K3h

### 表格字段

| 字段名 | 说明 |
|--------|------|
| jira_key | Jira 单号 |
| ee_type | 异常类型（modem_ee/phonecrash/assert/watchdog） |
| err_code | 异常代码（如 0x0000004d） |
| exception_source | 异常源（文件:行号） |
| ee_hash | 唯一标识 Hash |
| platform | 平台代号（CN6/GEN99/GEN98） |
| chip_vendor | 芯片厂商（MTK/展锐/高通） |
| chip_model | 芯片型号 |
| sw_version | 软件版本 |
| title | 标题 |
| description | 描述 |
| call_stack | 调用栈/异常文件 |
| root_cause | 根因 |
| solution | 解决方案 |
| status | 状态（待分析/分析中/已解决） |
| first_occurrence | 首次发生时间 |
| occurrence_count | 发生次数 |

## Skip Rule (L0 Validity Gate)

If `analysis.l0_baseline.validity_gate.status == "invalid"` (or `analysis.l0_baseline.should_continue == false`), this skill MUST be skipped.

## 调用时机

本 skill 在以下情况被调用：

1. **Orchestrator Step 10**：当 L1 的 `primary_domain == "ee"` 时，orchestrator 调用 `$modem-l2-ee-analysis`
2. **触发条件**：L0 检测到 ModemEE（`modem_state.route_to_ee == true` 或 `validity_gate.is_modemee_issue == true`），L1 优先路由到 `ee`

## 飞书表格写入保证

**每次执行本 skill 都必须尝试查询飞书多维表格**，并按照以下规则操作：

- 查询到已存在记录 → 读取已知根因，不重复写入
- 查询不到记录 → **必须写入新记录**，确保每个 ModemEE 都被记录到飞书表格中
- 查询失败（网络/鉴权问题）→ 记录错误信息，继续本地分析，不阻塞流程

## 执行步骤

1. 读取 Jira 文本、`analysis.l0_baseline` 和 `analysis.l1_business`。
2. 从 Jira 文本和日志中提取 EE 详细信息：
   - 异常类型（ee_type）
   - 异常代码（err_code）
   - 异常源（exception_source）
   - 异常文件和行号
3. 提取平台信息：
   - 平台代号（platform）
   - 芯片厂商（chip_vendor）
   - 芯片型号（chip_model）
   - 软件版本（sw_version）
4. 生成 EE Hash（基于 ee_type + err_code + exception_source）。
5. **查询飞书多维表格**（使用 `feishu_bitable_client.py` 中的 `query_modemee_from_feishu` 函数）：
   - 若存在（hit）：返回已知根因和解决方案
   - 若不存在（miss）：**调用 `write_modemee_to_feishu` 写入新记录**，状态为"待分析"
6. 将证据整理为结构化对象，写回 `analysis.l2_domains.ee`。

### 飞书表格操作的具体时机

| 阶段 | 操作 | 调用的函数 |
|------|------|-----------|
| 提取 EE 信息后 | 生成 ee_hash，查询飞书表格 | `query_modemee_from_feishu(ee_hash, client)` |
| 查询结果不存在时 | 写入新记录到飞书表格 | `write_modemee_to_feishu(ee_data, client)` |
| 查询结果存在时 | 读取已知根因和解决方案 | 从返回的 `record` 中提取 `root_cause` 和 `solution` |

### 调用方式

飞书表格查询与写入已封装在 `run_l2_ee_analysis.py` 中，直接通过命令行调用：

```bash
# Linux/macOS/容器
PYTHONIOENCODING=utf-8 python analysis_skills/modem-l2-ee-analysis/scripts/run_l2_ee_analysis.py \
  --manifest <MANIFEST_PATH>

# Windows cmd
set PYTHONIOENCODING=utf-8 && python analysis_skills\modem-l2-ee-analysis\scripts\run_l2_ee_analysis.py ^
  --manifest <MANIFEST_PATH>
```

返回字段（stdout JSON）：
- `feishu_query.exists`：是否命中已知记录
- `feishu_query.record`：已知记录内容（含 `root_cause`、`solution`）
- `ee_hash`：本次异常的唯一标识
- `ee_details`：提取的异常详情
- `candidate_causes`：候选根因列表

失败处理：若输出包含 `SKILL_FAILED:`，复制该行，终止后续步骤。

## 边界

- 不改写 L1 业务判断。
- 不输出最终面向人的总结报告。
- 飞书表格查询仅用于辅助分析，不替代人工判断。

## 环境变量

需要配置以下环境变量：

```
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
```

## 资源

- `references/playbook.md`
- `references/output-schema.md`
---
name: jira-reader
description: >
  通过 MCP 读取 Jira 单信息，提取需求关键要素，并结合 carrier_keys_matrix.xlsx
  给出 CarrierConfig 修改建议。
  触发词："读Jira"、"解析Jira"、"看Jira"、"Jira需求"、"jira reader"、
  "分析Jira单"、"Jira XXX"、"以及用户提供 Jira ID 时自动触发。
---

# Jira Reader Skill

## 用途

通过 Jira MCP 接口读取指定 Jira 单的 ID、标题、描述等信息，解析需求内容，然后结合 `carrier_keys_matrix.xlsx` 矩阵表给出 CarrierConfig 修改建议。

---

## Workflow

### Step 1：通过 MCP 读取 Jira 信息

**输入**：用户提供 Jira ID（如 `AR-20250409-0421`）或 Jira 链接

**动作**：
1. 从用户输入中提取 Jira ID
2. 调用 `jira-mcp` MCP server 获取 Jira 单详情
   - 优先使用 `get_issue` 工具，传入 `issueKey` 参数
   - 若 `get_issue` 不可用，尝试 `search_issues` 或其他可用的 Jira 查询工具
3. 从返回结果中提取以下字段：

| 字段 | 来源 | 说明 |
|------|------|------|
| `jira_id` | Jira 编号 | 如 `AR-20250409-0421` |
| `summary` | Jira 标题 | 需求概述 |
| `description` | Jira 描述正文 | 详细需求说明 |
| `status` | Jira 状态 | 判断是否可执行 |
| `affect_versions` | 影响版本 | 提取项目名+安卓版本+市场 |
| `attachments` | 附件 | 检查是否有参考文档/截图/Log |

> **注意**：MCP 返回的字段名可能因实现不同而有差异，按实际返回适配。
> 若 MCP 连接失败或返回异常，提示用户检查网络/权限后重试。

### Step 2：解析需求内容

从 Jira 的 summary + description 中提取结构化信息：

#### 基础信息

| 字段 | 提取规则 |
|------|----------|
| `project_name` | 从"影响版本"中提取项目型号（如 `X6878`、`S667LN`） |
| `android_version` | 版本号映射：16→W, 15→V, 14→U, 13→T, 12→S |
| `market` | 版本后缀：`in`=印度, `op`=海外 |

版本解析示例：
- `X6878-16.1.0.160(IN001PF001AZ)FANS` → 项目=`X6878`, Android=`W`, 市场=`in`
- `S667LN-H6933BCEFGHIJK-T-OP-260112V1912` → 项目=`S667LN`, Android=`T`, 市场=`op`

#### 需求信息

| 字段 | 提取规则 |
|------|----------|
| `action_type` | 从描述动词判断：`新增` / `修改` / `删除` / `隐藏` |
| `target_carrier` | 运营商名称（如"伊拉克41820"、"孟加拉Robi"） |
| `mccmnc` | PLMN 值，拆分为 mcc(前3位)+mnc(剩余)，如 `41820` → mcc=`418`, mnc=`20` |
| `carrier_id` | 描述中明确提及的 carrier_id |
| `config_keys` | 涉及的 CarrierConfig key 名称 |
| `expected_values` | 期望的参数值 |
| `is_common` | 描述中是否明确提及"通用" |

#### Log 信息提取（如描述中包含）

| 字段 | 提取规则 |
|------|----------|
| `log_carrierId` | 搜索 `carrierId` 关键字 |
| `log_mccmnc` | 搜索 SIM 的 MCC-MNC 信息 |

### Step 3：查询 carrier_keys_matrix.xlsx

使用 xlsx skill 或 Python 脚本读取矩阵文件：
```
shared/data/carrier_keys_matrix.xlsx
```
（相对于 skills 根目录，与 jira-reader、carrier-lookup 等 skill 同级）

根据 Step 2 提取的信息，查询以下内容：

#### 3.1 查 Project 表

- 输入：`project_name`
- 输出：该项目的**芯片平台**（MTK / QCOM / SPRD）
- 规则：查不到项目时**不猜测**，标记为"待确认：需补 Project 表"

#### 3.2 查 CarrieId_Ims 表

- 输入：`mccmnc` 或 `carrier_name`
- 输出：`carrier_id`、`mccmnc`、`carrier_name`、IMS 参考能力
- 规则：以 `carrier_id + mccmnc` 双重确认运营商身份

#### 3.3 查 carrier_keys 表

- 输入：`config_keys`
- 输出：每个 key 的以下信息：

| 字段 | 说明 |
|------|------|
| `key_name` | key 全名 |
| `supported_platforms` | 支持的平台（MTK / QCOM / SPRD） |
| `default_value` | 系统默认值 |
| `recommend_target` | 建议落点（平台文件 or 通用文件） |

> **⚠️ 若 key 在 carrier_keys 表中不存在**：
> 1. 在分析报告的"待确认项"中标记该 key 为"矩阵表未收录"
> 2. 询问用户：该 key 是否正确？是否需要补录到矩阵表？
> 3. 若用户确认补录 → 调用 `matrix-update` skill 完成补录
> 4. `matrix-update` 完成后自动返回 key 信息，继续完成本步骤分析
> 5. 若用户说 key 名称有误 → 更正 key 名称后重新查询

#### 3.4 查 Carrier_Config 表

- 输入：`carrier_id` + `key_name`
- 输出：该运营商当前 key 的**已配置值**（用于判断是新增还是修改）

### Step 4：综合分析并给出修改建议

将前三步的结果汇总，输出完整的修改建议。

> **⚠️ 用户纠正分析结论时**（用户说"这个 key 不对"/"应该用 XXX"/"你分析错了"等）：
> 1. 记录用户提供的新 key 名称
> 2. 在 `carrier_keys` 表中重新搜索新 key
> 3. **若新 key 存在** → 以新 key 更新分析结论，重新输出修改建议
> 4. **若新 key 不存在** → 调用 `matrix-update` skill 补录后，继续更新分析结论



```
## Jira 需求分析报告

### 基本信息
| 字段 | 值 |
|------|-----|
| Jira ID | ... |
| 标题 | ... |
| 状态 | ... |
| 项目 | ... |
| Android版本 | ... |
| 市场 | ... |

### 运营商确认
| 字段 | 值 | 来源 |
|------|-----|------|
| 运营商名称 | ... | Jira / 矩阵表 |
| carrier_id | ... | Jira / 矩阵表 |
| mccmnc | ... | Jira / 矩阵表 |
| 平台 | ... | Project 表 |

### 修改建议
| Key | 当前值 | 期望值 | 建议落点文件 | 操作 |
|-----|--------|--------|-------------|------|
| key1 | (无) | true | carrier_config_mtk_all_project.xml | 新增 |
| key2 | false | true | carrier_config_mtk_all_project.xml | 修改 |

### 落点判定依据
- key 支持平台：MTK
- 项目平台：MTK
- 是否三平台通用：否
- 是否明确要求通用：否
- → 落点：平台文件 `carrier_config_mtk_all_project.xml`

### default_value 说明
- key1 默认值为 `false`，需求要求 `true`，需要显式配置覆盖
- key2 默认值为空，建议结合需求单确认

### 待确认项（如有）
- [ ] ...
```

---

## 输出规范

1. **必须输出完整的分析报告表格**（如上格式）
2. **缺失字段必须标记为"待确认"**，不猜测
3. **carrier_id 必须通过矩阵表确认**，不能仅凭 Jira 描述
4. **平台必须通过 Project 表确认**，不能凭经验判断
5. **default_value 为空时需提示风险**，建议用户确认后再配

---

## 限制

- 通过 MCP 访问 Jira，若 MCP 不可用则提示用户检查配置
- 读取 carrier_keys_matrix.xlsx 需要该文件存在且可访问
- 不执行任何文件修改操作，仅分析和建议
- 不自动判定最终的提交方案，修改确认由 `carrierconfig-edit` skill 负责

---

## 与其他 Skill 的衔接

本 Skill 完成后，输出直接供后续 skill 使用：

```
jira-reader (分析报告) → carrier-lookup (确认落点) → carrierconfig-edit (改代码) → carrierconfig-submit (提交)
```

若本 Skill 已给出明确的修改建议（落点文件+操作），可直接跳过 `carrier-lookup` 进入 `carrierconfig-edit`。

遇到矩阵表未收录的 key 或用户纠正结论时，内部调用 `matrix-update` 完成补录后继续：

```
jira-reader (发现未知 key 或用户纠正)
    └→ matrix-update (补录矩阵) → 返回 key 信息 → jira-reader 继续/重新输出分析
```

# TranCarrierConfig - CarrierConfig 开发 Skill 集合

> 传音 CarrierConfig/APN 开发的 AI 辅助工作流，覆盖从 Jira 需求到 Gerrit 提交的全流程。

---

## 目录

- [整体架构](#整体架构)
- [Skill 列表](#skill-列表)
- [完整流程示例](#完整流程示例)
- [辅助工具](#辅助工具)
- [数据文件说明](#数据文件说明)

---

## 整体架构

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌────────────────────┐
│ jira-reader │ ──→ │ carrier-lookup  │ ──→ │ carrierconfig-   │ ──→ │ carrierconfig-     │
│  读 Jira    │     │  查矩阵判落点   │     │     edit         │     │     submit         │
│  分析需求   │     │  确认身份       │     │  改 XML 配置     │     │  台账+提交+通知    │
└──────┬──────┘     └───────┬─────────┘     └──────────────────┘     └────────────────────┘
       │                   │
       │            ┌──────┴──────┐
       └──────────→ │ matrix-     │ ←── 用户手动触发
                    │  update     │
                    │  补录矩阵   │
                    └─────────────┘
```

**设计原则**：每个 Skill 单一职责，可独立使用，也可串联执行完整流程。

---

## Skill 列表

### 1. jira-reader — 读 Jira + 分析需求

| 项目 | 说明 |
|------|------|
| **路径** | `.agents/skills/jira-reader/` |
| **职责** | 通过 Jira MCP 读取工单信息，提取需求要素，结合矩阵表给出 CarrierConfig 修改建议 |
| **触发词** | `读Jira`、`解析Jira`、`分析Jira单`、`Jira需求`、以及提供 Jira ID/链接时自动触发 |
| **是否改文件** | ❌ 只读 |

**核心流程**：

| 步骤 | 内容 |
|------|------|
| Step 1 | 通过 MCP 调用 `get_issue` 读取 Jira 详情（ID、标题、描述、版本） |
| Step 2 | 解析需求：提取项目名、安卓版本、运营商、mccmnc、涉及的 key、期望值 |
| Step 3 | 查询矩阵表（Project → 平台，CarrieId_Ims → 运营商，carrier_keys → key 信息） |
| Step 4 | 综合分析，输出完整修改建议报告（平台、落点、当前值、期望值、操作类型） |

**输出示例**：

```
## Jira 需求分析报告
├── 基本信息（Jira ID / 项目 / Android版本 / 市场）
├── 运营商确认（carrier_id + mccmnc 双重验证）
├── 修改建议（key / 当前值 / 期望值 / 落点文件 / 操作）
├── 落点判定依据
└── 待确认项
```

---

### 2. carrier-lookup — 查矩阵 + 判落点

| 项目 | 说明 |
|------|------|
| **路径** | `.agents/skills/carrier-lookup/` |
| **职责** | 查询矩阵表确认项目平台、运营商身份、key 归属，判定改动应落平台文件还是通用文件 |
| **触发词** | `查平台`、`查运营商`、`确认落点`、`查矩阵`、`carrier_id查询`、`mccmnc查询`、`这个key放哪` |
| **是否改文件** | ❌ 只读 |

**核心流程**：

| 步骤 | 内容 |
|------|------|
| Step 1 | 查 `Project` 表：项目名 → 芯片平台（MTK / QCOM / SPRD） |
| Step 2 | 查 `CarrieId_Ims` 表：运营商名/mccmnc → carrier_id + mccmnc 双重确认 |
| Step 3 | 查 `Carrier_Config` 表：确认该运营商当前 key 的已配置值 |
| Step 4 | 查 `carrier_keys` 表：确认 key 归属和推荐落点 |

**落点判定规则**：

| 条件 | 落点文件 |
|------|---------|
| 单平台 key | `carrier_config_{platform}_all_project.xml` |
| 多平台 key | 各对应平台 `*_all_project.xml` |
| 三平台通用 key | `carrier_config_mccmnc_*.xml` 或 `carrier_config_carrierid_*.xml` |
| 需求明确说"通用" | 通用文件（不管 key 归属） |

---

### 3. carrierconfig-edit — 改 XML 配置

| 项目 | 说明 |
|------|------|
| **路径** | `.agents/skills/carrierconfig-edit/` |
| **职责** | 根据落点方案，在目标 XML 文件中执行精确的增删改操作 |
| **触发词** | `改 CarrierConfig`、`加参数`、`改配置`、`新增 key`、`删除 key`、`修改 key`、`隐藏参数` |
| **是否改文件** | ✅ 修改 XML |

**核心流程**：

| 步骤 | 内容 |
|------|------|
| Step 1 | 定位目标 `<carrier_config>` 块（按 cid 或 mcc+mnc） |
| Step 2 | 检查 key 是否已存在 |
| Step 3a | 修改已有 key → 替换 value + 添加修改注释 |
| Step 3b | 新增 key → 插入行 + 添加新增注释 |
| Step 3c | 删除 key → 删除整行 + 添加删除记录注释 |
| Step 3d | 新增整个 carrier_config 块（运营商不存在时） |
| Step 4 | 展示 diff 供用户确认 |

**注释格式**：

```xml
<!--TDD:add for [JiraID] by [用户名] [日期] start -->
<boolean name="carrier_volte_available_bool" value="true" />
<!--TDD:add for [JiraID] by [用户名] [日期] end -->
```

---

### 4. carrierconfig-submit — 台账 + 提交 + 通知

| 项目 | 说明 |
|------|------|
| **路径** | `.agents/skills/carrierconfig-submit/` |
| **职责** | 更新台账记录、执行 Git 提交推送到 Gerrit、发送飞书变更通知 |
| **触发词** | `提交 CarrierConfig`、`推送 gerrit`、`更新台账`、`git提交`、`push到gerrit`、`飞书通知` |
| **是否改文件** | ✅ 修改 Excel + Git |

**核心流程**：

| 步骤 | 内容 |
|------|------|
| Step 1 | 自动预填 `jira_issue_notes` 台账（从上下文提取字段） |
| Step 2 | 用户确认后写入矩阵表的 `jira_issue_notes` Sheet |
| Step 3 | 3项精简自检（台账已更新 / XML完整 / 注释格式正确） |
| Step 4 | Git commit（标准格式：ID / DESCRIPTION / TYPE / AFFECT_PROJECTS / TEST_SUGGESTIONS） |
| Step 5 | Push 到 Gerrit（MTK→`refs/for/master`，QCOM→`refs/for/com_master_qcomw`） |
| Step 6 | 飞书 Webhook 通知变更摘要 |

---

### 5. matrix-update — 补录矩阵表

| 项目 | 说明 |
|------|------|
| **路径** | `.agents/skills/matrix-update/` |
| **职责** | 当出现矩阵表中不存在的 CarrierConfig key 时，收集信息并补录到 `carrier_keys` Sheet |
| **触发词** | `矩阵补录`、`矩阵里没有这个`、`新增key到矩阵`、`update matrix` |
| **是否改文件** | ✅ 追加 Excel |
| **触发来源** | `jira-reader` / `carrier-lookup` 内部调用，或用户手动触发 |

**核心流程**：

| 步骤 | 内容 |
|------|------|
| Step 1 | 检查 key 是否已存在（防重复） |
| Step 2 | 收集补录信息（支持自动推断：`_bool`→boolean，三平台→通用） |
| Step 3 | 展示待写入内容，**必须用户确认** |
| Step 4 | 追加到 `carrier_keys` Sheet 末尾 |
| Step 5 | 返回补录结果给调用方，调用方继续执行（无需用户重新触发） |

---

## 完整流程示例

### 标准串联流程（Jira → 提交）

```
用户："Jira TOS170-619 立陶宛 RTT 设置不可用"

  ① jira-reader
     └→ 读取 Jira → 解析需求（立陶宛、RTT、X6887/MTK/A16）
     └→ 查矩阵（3家运营商 Telia/BITĖ/Tele2，key=rtt_supported_bool）
     └→ 输出修改建议报告

  ② carrier-lookup
     └→ 确认平台 MTK、运营商身份、落点 carrier_config_mtk_all_project.xml
     └→ 输出改动方案

  ③ carrierconfig-edit
     └→ 在 XML 中为 3 家运营商新增 rtt_supported_bool=true
     └→ 展示 diff → 用户确认

  ④ carrierconfig-submit
     └→ 更新 jira_issue_notes 台账
     └→ git commit → push to Gerrit
     └→ 飞书通知
```

### 单独使用场景

| 场景 | 只用哪个 Skill |
|------|---------------|
| "查一下孟加拉 Robi 的 carrier_id" | `carrier-lookup` |
| "X6887 是什么平台" | `carrier-lookup` |
| "帮我改一下这个 key 的值" | `carrierconfig-edit` |
| "矩阵里没有这个 key，帮我加上" | `matrix-update` |
| "看一下这个 Jira 单说什么" | `jira-reader` |

### 纠正流程（矩阵补录）

```
用户："AI 分析的 key 不对，应该用 carrier_hide_2g_bool"

  └→ jira-reader / carrier-lookup 识别纠正
  └→ 查矩阵发现 carrier_hide_2g_bool 不存在
  └→ 调用 matrix-update 补录
  └→ 返回 key 信息 → 继续分析/判定
```

---

## 辅助工具

| 工具 | 路径 | 用途 |
|------|------|------|
| `refresh_matrix.py` | `shared/scripts/` | 从源码自动提取 CarrierConfig key 信息，刷新矩阵数据（离线维护工具，不参与日常流程） |

运行方式（在 skills 根目录下）：

```bash
pip install -r shared/scripts/requirements.txt
python shared/scripts/refresh_matrix.py
```

> `refresh_matrix.py` 内的 `SOURCE_FILES` / `CONFIG_FILES` 指向本机 Android 源码树，换机器后需按实际路径修改；输出始终写入 `shared/data/carrier_keys_matrix.xlsx`。

---

## 数据文件说明

### carrier_keys_matrix.xlsx

路径：`shared/data/carrier_keys_matrix.xlsx`（相对于 skills 根目录）

| Sheet | 内容 | 查询入口 |
|-------|------|---------|
| `Project` | 项目名 → 芯片平台映射 | jira-reader / carrier-lookup |
| `CarrieId_Ims` | carrier_id / mccmnc / 运营商名称 / IMS 信息映射 | jira-reader / carrier-lookup |
| `Carrier_Config` | 各运营商当前已配置的参数现状 | carrier-lookup |
| `carrier_keys` | 所有已知 CarrierConfig key 的归属、平台、默认值 | jira-reader / carrier-lookup / matrix-update |
| `jira_issue_notes` | 改单台账记录 | carrierconfig-submit |

---

## Skill 速查表

| Skill | 触发关键词 | 改文件 | 可独立用 |
|-------|-----------|--------|---------|
| `jira-reader` | 读Jira、解析Jira、Jira ID | ❌ | ✅ |
| `carrier-lookup` | 查平台、查运营商、查矩阵、确认落点 | ❌ | ✅ |
| `carrierconfig-edit` | 改配置、加参数、新增/修改/删除 key | ✅ XML | ✅ |
| `carrierconfig-submit` | 提交、推送gerrit、更新台账、飞书通知 | ✅ Excel+Git | ✅ |
| `matrix-update` | 矩阵补录、新增key到矩阵 | ✅ Excel | ✅ |

---

## 目录结构

```
skills/                          ← 拷贝到其它主机时，整体复制此目录即可
├── README.md                    ← 本文件（skills 根目录）
├── shared/                      ← 共享资源（原 assert + tools）
│   ├── data/
│   │   └── carrier_keys_matrix.xlsx
│   └── scripts/
│       ├── refresh_matrix.py
│       └── requirements.txt
├── jira-reader/
│   └── SKILL.md
├── carrier-lookup/
│   └── SKILL.md
├── carrierconfig-edit/
│   └── SKILL.md
├── carrierconfig-submit/
│   └── SKILL.md
└── matrix-update/
    └── SKILL.md
```

## 部署到其它主机

1. 将整个 `skills/` 目录拷贝到目标主机的 agent skills 路径（如项目 `.agents/skills/` 或用户 `~/.agents/skills/`）
2. 确保 agent 能发现各子目录下的 `SKILL.md`（Cursor 会自动扫描 skills 目录）
3. 矩阵数据随目录一起带走，路径统一为 `shared/data/carrier_keys_matrix.xlsx`
4. 若需刷新矩阵，在目标主机安装依赖后运行 `shared/scripts/refresh_matrix.py`，并按本机源码路径修改脚本内 `SOURCE_FILES`

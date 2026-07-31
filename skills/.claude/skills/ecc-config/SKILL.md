---
name: ecc-config
version: 1.2.0
description: >-
  Configures ECC emergency numbers for MTK, Unisoc/展锐, or Qualcomm/高通
  repositories from user parameters or Jira issues (number, mccmnc, with/without
  SIM, category, names, blocking). Supports batch edits and multiple languages
  per number. Use when the user mentions MTK ECC, Unisoc/展锐 ECC, Qualcomm/高通
  ECC, EccList, tranecc, emergency number configuration, ecc_list_tran2, mccmnc,
  or asks to modify ECC based on a Jira ticket. Jira reads go through harness-jira.
---

# 通用 ECC 配置（MTK + 展锐 + 高通）

根据用户参数修改 ECC 配置，支持 MTK、展锐（Unisoc）、高通（Qualcomm）仓库。执行前读取本目录下的参考文件。

## 参考文件

| 文件 | 内容 |
|------|------|
| [parameters.md](parameters.md) | 输入参数定义、归一化 schema、校验规则 |
| [mapping.md](mapping.md) | MTK/Unisoc/Qualcomm 字段映射与状态决策 |
| [mcc-language.md](mcc-language.md) | MCC 官方语言网络查询规则 |
| [examples.md](examples.md) | 典型场景示例 |

## 外部依赖（Harness）

| 依赖 | 用途 |
|------|------|
| **harness-jira** | Jira 驱动模式下读取 issue（禁止改用 Jira MCP） |

执行约定：先遵循 `harness-jira` skill，再运行 `harness --json jira ...`；不要 `knowledge route/search`，也不要调用 Jira MCP。

## 平台检测

用户提供 ECC 仓库路径。按以下特征识别平台：

| 平台 | 识别条件 |
|------|----------|
| **MTK** | 存在 `xml/ecc_list_tran2.xml` |
| **Unisoc** | 存在 `assets/ecc_list.xml` 且存在 `res/values/ecc_config_list.xml` |
| **Qualcomm** | 存在 `assets/ecc_list.xml` 且存在 `res/values/config.xml`（名称映射），且无 `ecc_config_list.xml` |
| **冲突** | 同时满足多平台特征，或 `assets/ecc_list.xml` 下同时有 `config.xml` 与 `ecc_config_list.xml` → 要求用户明确指定平台 |

用户可显式指定：`platform: mtk | unisoc | qualcomm`。

## 平台级优先级（跨平台统一）

当需要在多个平台之间做“统一配置决策”（例如基于不同平台原配置生成同一目标语义）时，使用以下优先级：

`MTK > Unisoc(展锐) > Qualcomm(高通)`

规则：
- 若高优先级平台已有可用原配置，优先以其作为统一基线。
- 若高优先级平台无对应条目，再回退到次级平台。
- 若三平台都无可用原配置，则按用户输入与各平台默认规则生成。
- `simState` 仅 MTK 生效，不参与跨平台统一语义。

## 目标文件

### MTK

| 文件 | 用途 |
|------|------|
| `xml/ecc_list_tran2.xml` | 紧急号码配置（唯一有效） |
| `xml/ecc_block_list.xml` | 屏蔽非紧急号码（有条件） |
| `res/values/config.xml` | 号码→名称 key 映射（按 MCC） |
| `res/values/strings.xml` | 英文名称 |
| `res/values-*/strings.xml` | 多语言名称 |

### Unisoc（tranecc）

| 文件 | 用途 |
|------|------|
| `assets/ecc_list.xml` | ECC 主配置（无屏蔽文件） |
| `res/values/ecc_config_list.xml` | 号码→名称 key 映射（按 MCC） |
| `res/values/strings.xml` | 英文名称 |
| `res/values-*/strings.xml` | 多语言名称 |

### Qualcomm（高通）

| 文件 | 用途 |
|------|------|
| `assets/ecc_list.xml` | ECC 主配置（与展锐相同，无屏蔽文件） |
| `res/values/config.xml` | 号码→名称 key 映射（按 MCC，与 MTK 文件名相同） |
| `res/values/strings.xml` | 英文名称 |
| `res/values-*/strings.xml` | 多语言名称 |

**展锐与高通 ECC 主配置字段一致**（`Condition`、`CardFlag`、`EccType`、`Plmn`）；仅名称映射资源文件不同。

## 工作流

```
Task Progress:
- [ ] Step 1: 确认仓路径并识别平台
- [ ] Step 2: 解析并规范化输入
- [ ] Step 3: 校验参数（含平台差异）
- [ ] Step 4: 推导平台字段（Condition/CardFlag/BlockType/Plmn）
- [ ] Step 5: 解析当地语言（必要时网络查询）
- [ ] Step 6: 应用修改
- [ ] Step 7: 输出变更摘要
```

## Jira 驱动模式

当用户提供 Jira 单号 / URL（或明确要求“按 Jira 单处理 ECC”）时，按以下顺序执行：

1. **读取 Jira（必须走 harness-jira）**：
   - 先读取并遵循 **harness-jira** skill，再执行 CLI（优先 `--json`）。
   - 用户给 issue key：`harness --json jira get --issue <KEY>`
   - 用户给 URL：`harness --json jira get --url "<URL>"`；需要先提取 key 时用 `harness --json jira parse-key "<URL>"`
   - **禁止**使用 Jira MCP / 其他 Jira 客户端读取；凭据缺失或 CLI 认证失败时，按 harness-jira 指引处理（如 `config setup-jira`），不要回退到 MCP。
   - **不能只看标题**，必须结合返回的 description / comments 中下列字段综合判断需求：
     - **步骤**（操作步骤 / Steps）
     - **期望结果**（Expected Result）
     - **测试结果**（Actual / Test Result）
     - 以及验收条件、评论中的有效补充
2. 从上述内容（尤其是步骤、期望结果、测试结果的对照）提取结构化 ECC 意图（号码、mccmnc、有卡/无卡、是否要求非紧急、是否要求屏蔽、名称变更等）。
   - 标题仅作概览；**以描述里的期望结果与测试结果为准**界定目标行为。
   - 若期望结果与测试结果冲突或信息不完整，先整理疑问再询问用户，不盲改。
3. 读取仓内当前 ECC 配置，形成“当前状态 vs 目标状态”差异清单。
4. 先输出“整理后的目标 ECC 配置”给用户确认（若用户未要求跳过确认）；确认后再落库修改。
5. 若 Jira 目标与当前配置冲突，按 Jira 目标为准，并在摘要中记录冲突处理及依据字段（步骤/期望/测试结果）。

Jira 模式下，参数来源优先级：
`用户当前消息显式参数 > Jira 描述（步骤+期望结果+测试结果） > 标题概览 > 仓内现状推断默认值`

### Step 1 — 确认路径与平台

- 用户提供 ECC 仓库路径。
- 按“平台检测”规则识别 MTK/Unisoc/Qualcomm，并验证对应目标文件存在。

### Step 2 — 解析输入

支持自然语言或结构化 YAML，归一化为 `entries[]`（见 parameters.md）。一次可传入多个号码；一个号码可含多个 `localNames`。

### Step 3 — 校验

- 号码必填。
- 无卡不可为假紧急。
- 名称修改要求 mccmnc 非空（公共号码不可配名称）。
- MTK：`block: true` 仅当对应侧为非紧急且用户明确要求屏蔽。
- Unisoc / Qualcomm：忽略 `block` / `simState`（无屏蔽文件），并在摘要中提示。
- 非紧急规则按 mapping.md 执行（按平台分别处理）。
- 用户仅说明“有卡是紧急号码”（无卡未指定，且未区分真/假紧急）时：先查原配置；原配置有卡已紧急则不改；原配置有卡非紧急时，普通号码改为“有卡假紧急”，**112/911 等 3GPP 国际通用紧急号码**改为“有卡真紧急”（见 mapping.md）。
- Jira 若明确写“XXX 号码不应是紧急号码”，按 mapping.md 的 Jira 专项规则处理（先读现状，再决定删配置或加屏蔽）。

### Step 4 — 推导配置值（按平台）

按 [mapping.md](mapping.md) 推导：

- **MTK**：`Condition`、`Plmn`、`BlockType`、`SimState`
- **Unisoc / Qualcomm**：`Condition`、`CardFlag`、`Plmn`、`EccType=0`

`CardFlag` 在 Unisoc/Qualcomm 中优先级高于 `Condition`。
跨平台统一时，先按平台优先级 `MTK > Unisoc > Qualcomm` 选取基线语义，再映射到各平台字段。

### Step 5 — 解析当地语言

- 用户已指定 → 直接使用。
- 未指定且需改当地语言名 → 按 [mcc-language.md](mcc-language.md) 网络查询 MCC 官方语言，映射为 `values-{qualifier}` 并验证目录存在。

### Step 6 — 应用修改

**MTK (`xml/ecc_list_tran2.xml`)**：
- 查找/新增 `<EccEntry Ecc="..." Category="..." Condition="..." Plmn="..."/>`
- **指定 `mccmnc` 的条目覆盖公共条目**（`Plmn` 为空/省略）；用户传入 `mccmnc` 时新增/改 MCC 侧条目，不直接改公共条目
- 指定运营商条目排在同 MCC `FFF` 条目**之前**
- 非紧急：按 mapping.md「非紧急配置规则」处理

**MTK (`xml/ecc_block_list.xml`)**（仅 `block: true` 时）：
- 新增/修改 `<EccBlockNumber .../>`

**Unisoc / Qualcomm (`assets/ecc_list.xml`)**：
- 查找/新增 `<EccEntry Ecc="..." Category="..." Condition="..." Plmn="..." EccType="0" [CardFlag="..."]/>`
- 不处理屏蔽文件（不存在）

**名称**（mccmnc 非空时，按平台）：
- MTK / Qualcomm：在 `config.xml` 的 `ecc_config_{MCC}` 中定位 `string_key`
- Unisoc：在 `ecc_config_list.xml` 的 `ecc_config_{MCC}` 中定位 `string_key`
- 改英文名 → `values/strings.xml`；改当地语言名 → `values-{lang}/strings.xml`

### Step 7 — 变更摘要

```markdown
## ECC 配置变更摘要

**ECC 路径**: {path}

### 条目 {n}: 号码 {number}
- **平台**: {MTK|Unisoc|Qualcomm}
- **ecc 主配置**: {新增|修改|跳过} — Ecc={number}, Condition={v}, Plmn={p}, Category={c}, {CardFlag/EccType}
- **block list**: {新增|修改|跳过|不支持} — ...
- **名称**: {修改|跳过}
- **语言查询**: {查询词} → {结论}（若适用）
- **警告**: {如有}
```

## 关键规则速查

1. 同一套输入参数，按平台走不同字段映射。
2. MTK：指定 `mccmnc` 的配置覆盖公共配置；非紧急规则与 block/simState 按 mapping.md 执行。
3. Unisoc / Qualcomm：`EccType` 固定 `0`，`CardFlag` 优先级高于 `Condition`。
4. Unisoc / Qualcomm：无屏蔽文件，忽略 `block`/`simState` 并提示。
5. 跨平台统一决策优先级：`MTK > Unisoc > Qualcomm`（`simState` 不参与统一）。
6. 名称映射文件：MTK/高通=`config.xml`，展锐=`ecc_config_list.xml`。
7. 名称仅按 MCC 配置，公共号码和单运营商均不可配名称。
8. MCC 官方语言必须网络查询，不得硬编码。
9. Jira 驱动：经 **harness-jira**（`harness jira get/parse-key`）读取；**禁止 Jira MCP**；**不能只看标题**；须结合描述中的步骤、期望结果、测试结果整理目标配置。
10. 用户仅说明“有卡是紧急号码”且未区分真/假紧急时：原配置有卡非紧急 → 普通号码改有卡假紧急；**112/911 等 3GPP 国际通用紧急号码**改有卡真紧急。

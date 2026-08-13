---
name: matrix-update
description: >
  当用户提供新的 CarrierConfig key（矩阵表中不存在）时，验证并补录到
  carrier_keys_matrix.xlsx 中。
  触发词："矩阵补录"、"矩阵里没有这个"、"新增key到矩阵"、"update matrix"、
  "这个key矩阵没有"、"补录到矩阵"，以及被 jira-reader / carrier-lookup 内部调用。
---

# Matrix Update Skill

## 用途

当 AI 给出的 CarrierConfig 建议被用户纠正，或出现矩阵表中不存在的 key 时，
负责将新 key 补录到 `carrier_keys_matrix.xlsx` 的 `carrier_keys` Sheet 中，
保持矩阵表与实际使用保持同步。

---

## 触发条件

本 Skill 由以下场景触发：

| 触发来源 | 触发时机 |
|---------|---------|
| `jira-reader` | Jira 需求中涉及的 key 在矩阵里查不到时 |
| `carrier-lookup` | 查询 key 归属时发现 carrier_keys 表无此 key 时 |
| 用户手动 | 用户主动说"矩阵里没有这个 key，帮我加上" |

---

## 数据源

矩阵文件路径：`shared/data/carrier_keys_matrix.xlsx`（相对于 skills 根目录，即与本 README 同级）

目标 Sheet：**`carrier_keys`**

---

## 工作流

### Step 1：确认待补录的 key

1. 获取 key 名称（来自调用方传入或用户输入）
2. 在 `carrier_keys` Sheet 中搜索该 key_name
3. **若已存在**：输出现有信息，告知调用方/用户无需补录，直接返回现有数据
4. **若不存在**：进入 Step 2 收集信息

### Step 2：收集补录信息

向用户确认以下字段（尽可能从上下文自动推断，推断的字段需让用户确认）：

| 字段 | 是否必填 | 说明 | 自动推断来源 |
|------|---------|------|------------|
| `key_name` | ✅ 必填 | CarrierConfig key 全名，含类型后缀（如 `_bool`/`_int`/`_string`） | 用户提供 |
| `supported_platforms` | ✅ 必填 | 支持平台：`MTK` / `QCOM` / `SPRD`（多选，空格分隔） | 从源码/文档推断 |
| `default_value` | ✅ 必填 | 系统默认值（如 `false` / `0` / 空） | 从源码注释或文档推断 |
| `feature_desc` | ✅ 必填 | 功能描述，说明该 key 控制什么行为 | 从 Jira 需求/文档推断 |
| `recommend_target` | ✅ 必填 | 建议落点：`平台` 或 `通用` | 根据 supported_platforms 判断 |
| `value_type` | 可选 | 值类型：`boolean` / `int` / `string` / `string-array` | 从 key 名称后缀推断 |
| `notes` | 可选 | 备注（如适用 Android 版本范围、废弃信息等） | 用户补充 |

> **推断规则**：
> - key 以 `_bool` 结尾 → `value_type = boolean`
> - key 以 `_int` 结尾 → `value_type = int`
> - key 以 `_string` 结尾 → `value_type = string`
> - `supported_platforms` 三平台都有 → `recommend_target = 通用`，否则 → `recommend_target = 平台`

### Step 3：展示待写入内容

在执行写入前，展示即将写入的行内容让用户确认：

```
## 待写入矩阵表（carrier_keys Sheet）

| 字段 | 值 |
|------|-----|
| key_name | rtt_supported_bool |
| supported_platforms | MTK QCOM SPRD |
| default_value | false |
| feature_desc | 控制运营商是否支持 RTT over IMS，决定 RTT 设置是否可见 |
| recommend_target | 通用 |
| value_type | boolean |
| notes | Android T+ 引入 |

确认写入？(yes / 修改后重试)
```

### Step 4：写入矩阵表

用户确认后执行：

1. 读取 `carrier_keys_matrix.xlsx`
2. 定位 `carrier_keys` Sheet
3. 在最后一行追加新记录
4. 保存文件
5. 输出确认信息：

```
✅ 已补录到矩阵表
  key_name: rtt_supported_bool
  位置: carrier_keys Sheet，第 N 行
  文件: shared/data/carrier_keys_matrix.xlsx
```

### Step 5：返回给调用方

补录完成后，将该 key 的完整信息返回给调用方（jira-reader / carrier-lookup），
使其可以继续完成分析流程，**无需用户重新触发**。

---

## 禁止事项

1. **禁止未经用户确认直接写入** — Step 3 的确认步骤不可跳过
2. **禁止重复写入** — Step 1 必须先检查是否已存在
3. **禁止空字段写入** — 必填字段必须有值，不能留空
4. **禁止修改已有行** — 本 Skill 只追加，不修改现有数据（修改需用户手动操作）

---

## 与其他 Skill 的衔接

```
jira-reader（发现未知 key）
    └→ matrix-update（补录）→ 返回 key 信息 → jira-reader 继续分析

carrier-lookup（查询 key 归属时查不到）
    └→ matrix-update（补录）→ 返回 key 信息 → carrier-lookup 继续查询
```

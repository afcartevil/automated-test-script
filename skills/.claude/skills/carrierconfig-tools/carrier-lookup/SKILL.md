---
name: carrier-lookup
description: >
  根据项目、运营商、mccmnc 等信息查询矩阵表，确认芯片平台、carrier_id 映射、
  判定改动落点（平台文件 or 通用文件）。
  触发词："查平台"、"查运营商"、"确认落点"、"查矩阵"、"lookup carrier"、
  "carrier_id查询"、"mccmnc查询"、"这个key放哪"、"平台还是通用"、
  以及 jira-reader 完成后自动衔接调用。
---

# Carrier Lookup Skill

## 用途

查询 `carrier_keys_matrix.xlsx` 矩阵表，完成两件事：
1. **确认身份**：项目 → 平台，运营商 → carrier_id + mccmnc
2. **判定落点**：key 应该改平台文件还是通用文件

纯查询操作，**不修改任何文件**。

---

## 数据源

主文件：`shared/data/carrier_keys_matrix.xlsx`（相对于 skills 根目录）

| Sheet | 用途 | 查询方式 |
|-------|------|----------|
| `Project` | 项目名 → 芯片平台映射 | 按项目名搜索 `Project` 列，取 `Platform` 值 |
| `CarrieId_Ims` | carrier_id / mccmnc / 运营商映射 | 按 mccmnc 或 carrier_name 搜索 |
| `Carrier_Config` | 当前参数现状 | 按 mccmnc 或 carrier_id 搜索，查看 key 分列 |
| `carrier_keys` | key 归属与平台支持 | 按 key_name 搜索，查看 supported_platforms / recommend_target |

---

## 查询流程

### Step 1：确认平台

输入：项目名（来自 jira-reader 或用户直接提供）

1. 在 `Project` 表中搜索项目名
2. 读取 `Platform` 列 → 得出 `mtk` / `qcom` / `sprd`
3. **查不到项目时**：先补充项目到 Project 表，不允许猜平台

### Step 2：确认运营商

输入：运营商名称 / mccmnc / carrier_id（任意一个或多个）

1. 在 `CarrieId_Ims` 表中搜索：
   - 有 mccmnc → 按 mccmnc 搜索
   - 有 carrier_id → 按 carrier_id 搜索
   - 仅有名称 → 按 carrier_name 模糊搜索
2. 取出：`carrier_id`、`mccmnc`、`carrier_name`
3. **双重确认**：以 `carrier_id + mccmnc` 双重校验，防错运营商

### Step 3：确认参数现状

输入：carrier_id 或 mccmnc + key_name（如有）

1. 在 `Carrier_Config` 表中搜索对应运营商
2. 查看 target key 的**当前值**
3. 对比 Jira 需求中的期望值

### Step 4：判定 key 归属和落点

输入：key_name

1. 在 `carrier_keys` 表中搜索 key_name
2. **若 key 存在** → 读取 `supported_platforms` 和 `recommend_target`，进入落点判定
3. **若 key 不存在**：
   - 在输出结果中标记该 key 为"⚠️ 矩阵表未收录"
   - 询问用户：该 key 是否正确？是否需要补录到矩阵表？
   - 若用户确认补录 → 调用 `matrix-update` skill 完成补录
   - `matrix-update` 完成后自动返回 key 信息，继续执行落点判定
   - 若用户说 key 名称有误 → 更正后重新查询
4. 若用户纠正落点建议（如"应该是通用文件不是平台文件"）：
   - 重新查询 `carrier_keys` 表确认新 key 或重新判定
   - 若涉及新 key → 调用 `matrix-update` 补录后继续

判定规则：

| 条件 | 落点 |
|------|------|
| 单平台 key（如仅 MTK） | 对应平台 `carrier_config_{platform}_all_project.xml` |
| 多平台 key（如 MTK+QCOM） | 各对应平台 `*_all_project.xml` |
| 三平台通用 key（MTK+QCOM+SPRD） | 通用文件 `carrier_config_mccmnc_*.xml` 或 `carrier_config_carrierid_*.xml` |
| 需求明确说"通用" | 通用文件（不管 key 归属） |

### 落点文件映射

```
平台文件：
  MTK  → trancarrierconfig/carrier_config_mtk_all_project.xml
  QCOM → trancarrierconfig/carrier_config_qcom_all_project.xml
  SPRD → trancarrierconfig/carrier_config_sprd_all_project.xml

通用文件（按匹配方式）：
  mccmnc 匹配 → trancarrierconfig/carrier_config_mccmnc_{mcc}{mnc}.xml
  carrier_id 匹配 → trancarrierconfig/carrier_config_carrierid_{cid}.xml
```

---

## 输出格式

查询完成后，输出以下结构化表格：

```
## 查询结果

### 身份确认
| 字段 | 值 |
|------|-----|
| 项目 | X6878 |
| 平台 | MTK |
| 运营商 | 伊拉克 Zain |
| carrier_id | 1657 |
| mccmnc | 41820 |

### Key 信息
| Key | 当前值 | 期望值 | 归属平台 | 推荐落点 |
|-----|--------|--------|----------|----------|
| carrier_volte_available_bool | true | false | MTK QCOM SPRD | 通用文件 |

### 改动方案
| 项目 | 值 |
|------|-----|
| 改动类型 | 平台 |
| 目标文件 | trancarrierconfig/carrier_config_mtk_all_project.xml |
| 匹配方式 | cid="1657" |

### default_value 参考
| Key | default_value | 说明 |
|-----|---------------|------|
| carrier_volte_available_bool | true | 与默认值不同，需显式配置 |
```

---

## default_value 判断规则

- **非空**：通常表示系统默认行为；若运营商需求与默认一致，可不显式配置
- **需覆盖**：在对应 carrier_config 块显式写入
- **为空**：源码未直接给出默认值，建议结合 log / 需求单确认后再配

---

## 禁止事项

1. **禁止猜平台** — 查不到项目时先补项目
2. **禁止只看名称确认运营商** — 必须 carrier_id + mccmnc 双重确认
3. **禁止不查 key 归属就判落点** — 先查 supported_platforms
4. **不修改任何文件** — 本 skill 是只读的（矩阵补录交由 matrix-update 处理）

---

## 与其他 Skill 的衔接

```
jira-reader → 结构化需求 ──→ carrier-lookup（本 skill）→ 改动方案 ──→ carrierconfig-edit
```

也可以单独调用：
```
用户："查一下孟加拉 Robi (47002) 的 carrier_id"
→ 只执行 Step 2，输出运营商映射结果
```

遇到矩阵表未收录的 key 或用户纠正落点建议时，内部调用 `matrix-update`：

```
carrier-lookup（发现未知 key 或用户纠正）
    └→ matrix-update（补录矩阵）→ 返回 key 信息 → carrier-lookup 继续判定落点
```

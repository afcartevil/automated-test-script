---
name: carrierconfig-edit
description: >
  根据 carrier-lookup 的方案，执行 XML 配置的增删改操作。
  触发词："改 CarrierConfig"、"加参数"、"改配置"、"edit carrierconfig"、
  "新增 key"、"删除 key"、"修改 key"、"隐藏参数"、以及 carrier-lookup 完成后自动衔接。
---

# CarrierConfig Edit Skill

## 用途

根据 `carrier-lookup` 输出的改动方案，在目标 XML 文件中执行精确的增删改操作。

---

## 前置条件

必须已获得以下信息（来自 `carrier-lookup` 或用户直接提供）：

| 必需信息 | 说明 |
|----------|------|
| 目标文件 | `carrier_config_*_all_project.xml` 或通用文件 |
| 匹配方式 | `cid="XXX"` 或 `mcc="XXX" mnc="XX"` |
| 操作类型 | 新增 / 修改 / 删除 |
| key_name | 要改的 key 全名 |
| 新值 | 期望的 value |
| Jira ID | 用于生成注释 |
| 用户名 | 当前电脑用户名，用于注释 |

**缺少任何一项时，先询问用户补充，不猜测。**

---

## 操作流程

### Step 1：定位目标位置

- 用 `search_content` 在目标文件中搜索匹配条件（cid 或 mcc+mnc）
- 找到对应的 `<carrier_config ...>` 块
- 确认块的位置和范围

### Step 2：检查 key 是否已存在

在找到的 `<carrier_config>` 块内搜索 key_name：

- **已存在** → 进入 Step 3a（修改）
- **不存在** → 进入 Step 3b（新增）

### Step 3a：修改已有 key

1. 用 `replace_in_file` 精确替换 value 值
2. 在修改行前后添加注释标记：
```xml
<!--TDD:modify for [JiraID] by [用户名] [日期] start -->
<boolean name="carrier_volte_available_bool" value="false" />
<!--TDD:modify for [JiraID] by [用户名] [日期] end -->
```

### Step 3b：新增 key

1. 在 `<carrier_config>` 块内的末尾（`</carrier_config>` 前）插入新行
2. 用注释包裹：
```xml
<!--TDD:add for [JiraID] by [用户名] [日期] start -->
<boolean name="carrier_volte_available_bool" value="true" />
<!--TDD:add for [JiraID] by [用户名] [日期] end -->
```

### Step 3c：删除 key

1. 定位目标 key 行及其注释
2. 用 `replace_in_file` 删除整行（包括前导空格）
3. 在删除位置添加注释记录：
```xml
<!--TDD:delete for [JiraID] by [用户名] [日期] carrier_xxx=value -->
```

### Step 3d：隐藏参数

对于需要隐藏的参数（如 WAP APN）：
1. 在对应的 APN 条目上添加不可见属性
2. 用注释记录隐藏操作

### Step 4：新增整个 carrier_config 块（运营商不存在时）

当目标文件中没有该运营商的 `<carrier_config>` 块时：

```xml
<!--TDD:add for [JiraID] by [用户名] [日期] start -->
<carrier_config cid="1657">
    <boolean name="carrier_volte_available_bool" value="true" />
</carrier_config>
<!--TDD:add for [JiraID] by [用户名] [日期] end -->
```

新增位置规则：
- 优先找相同 mccmnc 的其他块附近插入
- 若无同类块，插入到文件末尾（`</carrier_config_list>` 前）

### Step 5：展示 diff 确认

修改完成后：
1. 重新读取修改区域，展示修改前后的对比
2. 输出结构化确认表格：

```
## 修改确认

| 项目 | 值 |
|------|-----|
| 文件 | trancarrierconfig/carrier_config_mtk_all_project.xml |
| 运营商 | 伊拉克 Zain (cid=1657) |
| 操作 | 修改 |
| Key | carrier_volte_available_bool |
| 原值 | true |
| 新值 | false |
| Jira | AR-20250409-0421 |

请确认修改是否正确。
```

---

## 注释格式规范

### 必须遵守

| 操作 | 注释关键字 | 示例 |
|------|-----------|------|
| 新增 | `TDD:add for` | `<!--TDD:add for AR-20250409-0421 by chunyan.tang 2025-05-14 start -->` |
| 修改 | `TDD:modify for` | `<!--TDD:modify for AR-20250409-0421 by chunyan.tang 2025-05-14 start -->` |
| 删除 | `TDD:delete for` | `<!--TDD:delete for AR-20250409-0421 by chunyan.tang 2025-05-14 key_name=value -->` |

### 格式要求

- `start` 和 `end` 必须成对
- 日期格式：`YYYY-MM-DD`
- 用户名：从环境变量获取或固定为当前执行用户

---

## XML 格式红线

1. **不破坏 XML 结构** — 标签必须正确闭合
2. **不多空行** — 新增后不产生多余空行
3. **删除要干净** — 删除整行代码和关联空格，不留孤行
4. **标签类型匹配** — 值的类型必须与标签匹配：
   - `<boolean>` → `true` / `false`
   - `<int>` → 整数
   - `<string>` → 文本
   - `<string-array>` → 多行 `<item>`

---

## 常用配置写法模板

### 按 carrier_id 匹配
```xml
<carrier_config cid="1657">
    <boolean name="carrier_wfc_ims_available_bool" value="true" />
</carrier_config>
```

### 按 mcc+mnc 匹配
```xml
<carrier_config mcc="414" mnc="06">
    <boolean name="key_disable_flash_message" value="false" />
</carrier_config>
```

---

## 禁止事项

1. **不修改非目标文件** — 只改 carrier-lookup 指定的文件
2. **不使用全文重写** — 用 replace_in_file 精确修改，不动无关行
3. **不猜测缺失信息** — 缺 key、缺值、缺匹配方式时先问
4. **不执行 git 操作** — 提交由 `carrierconfig-submit` 负责

---

## 与其他 Skill 的衔接

```
carrier-lookup → 改动方案 ──→ carrierconfig-edit（本 skill）→ diff 确认 ──→ carrierconfig-submit
```

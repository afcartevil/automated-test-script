---
name: tones-scmp
description: >-
  查询 TONES SCMP：属性申请/属性库、项目模糊搜索、分区策略列表、策略下属性配置值、
  SPD 产品配置清单与特性配置清单（可按特性编码/名称/owner/配置状态/与我相关筛选）。
  通过 scripts/run.py 调用 api-tones.transsion.com。支持按项目名查 KM9 等项目、查策略
  tr_product-tOS16.3.0-KM9-mp-00228、读策略 attributeInfo 中 attrCode 的配置值。
  当用户提到 SCMP、项目策略、partition strategy、attrCode 配置值、产品配置清单、特性清单、
  KM9、tones-build-platform、tones-spd 或 hk-intra-paas 时使用。Agent 必须先配置 token 再请求。
version: 0.4.1
---

# TONES SCMP 属性查询

通过本 skill 自带的 CLI（`scripts/run.py`）查询 SCMP 属性申请与属性信息。**禁止手写 curl/requests**，统一走 CLI 以保证 header 与 HAR 一致。

## 调用契约

本 skill 目录记为 `SKILL_ROOT`（即含 `SKILL.md` 的目录）。所有 CLI 调用使用：

```text
python "<SKILL_ROOT>/scripts/run.py" --json <子命令...>
```

**必须加 `--json`**，便于解析 `code` / `data` / `records`。

示例：

```text
python "D:/skills/tones-scmp/scripts/run.py" --json scmp apply list --page 1 --size 10
```

## 首次使用检查清单

Agent 在发起业务查询前，按顺序执行：

```
配置检查：
- [ ] 1. 依赖已安装（httpx, pyyaml）
- [ ] 2. config.yaml 存在且 token 非空
- [ ] 3. 探活请求成功（scmp apply count 返回 code=0000）
- [ ] 4. 再执行用户要求的查询
```

### 步骤 1：安装依赖（每个 Agent 环境一次）

```text
pip install -r "<SKILL_ROOT>/scripts/requirements.txt"
```

### 步骤 2：初始化配置

```text
python "<SKILL_ROOT>/scripts/run.py" config init
python "<SKILL_ROOT>/scripts/run.py" config path
python "<SKILL_ROOT>/scripts/run.py" config show
```

配置文件路径：`<SKILL_ROOT>/scripts/config.yaml`（由 `config init` 从 `config.example.yaml` 生成）。

也可用环境变量覆盖：`TONES_CLI_CONFIG=<绝对路径>`。

### 步骤 3：获取并写入 token（token 为空或探活失败时）

**不要猜测 token。** 按以下方式获取后写入配置：

1. 请用户在浏览器登录 [hk-intra-paas SCMP](https://hk-intra-paas.transsion.com/tones-scmp/)（或导出 HAR）。
2. 打开 DevTools → Network，刷新属性相关页面。
3. 找到发往 `api-tones.transsion.com` 的 XHR 请求，从 Request Headers 复制：

| Header | 写入 config 字段 |
|--------|------------------|
| `p-auth` | `auth_profiles.hk-intra-paas.p_auth` |
| `authorization`（若有） | `auth_profiles.hk-intra-paas.authorization` |
| `p-rtoken` | `auth_profiles.hk-intra-paas.p_rtoken` |
| `p-appid` | `auth_profiles.hk-intra-paas.p_appid`（通常 `220713001`） |

写入命令：

```text
python "<SKILL_ROOT>/scripts/run.py" config set auth_profiles.hk-intra-paas.p_auth "<p-auth值>"
python "<SKILL_ROOT>/scripts/run.py" config set auth_profiles.hk-intra-paas.authorization "<authorization值>"
python "<SKILL_ROOT>/scripts/run.py" config set auth_profiles.hk-intra-paas.p_rtoken "<p-rtoken值>"
python "<SKILL_ROOT>/scripts/run.py" config set auth_profiles.hk-intra-paas.p_appid "220713001"
```

`p_auth` 与 `authorization` 通常相同；若 HAR 只有 `p-auth`，两者可填同一值。

用户直接提供 token 时，用 `config set` 写入，**不要在对话中回显完整 token**。

### 步骤 4：探活

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply count
```

- `code` 为 `0000` → 配置有效，继续业务查询
- HTTP 401/403 或 API 非 `0000` → token 过期，回到步骤 3 请用户刷新 token

## 业务命令速查

### 属性申请清单

```text
# 分页列表（status 省略=全部；0待审批 1未通过 2已通过 3取消）
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply list --page 1 --size 10
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply list --status 0

# 各状态数量
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply count

# 负责人 / 申请人下拉
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply responsible-persons
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply persons

# 二/三级部门下拉
python "<SKILL_ROOT>/scripts/run.py" --json scmp department second
python "<SKILL_ROOT>/scripts/run.py" --json scmp department third
```

### 属性信息查询

```text
# 按 attrCode 查属性定义、默认值、负责人、部门、版本范围等
python "<SKILL_ROOT>/scripts/run.py" --json scmp info query --attr-code ro.tr_dynamicbar.resident_plane.support

# 属性版本详情 + 关联特性（attributeFeatures，含四级特性编码 fourthFeatureCode）
python "<SKILL_ROOT>/scripts/run.py" --json scmp info detail --attr-code ro.tr_telephony.sms_filter.support
python "<SKILL_ROOT>/scripts/run.py" --json scmp info detail --bid sid_1394974796370022400 --version 20251226.0001
python "<SKILL_ROOT>/scripts/run.py" --json scmp info detail --attr-code ro.tr_telephony.sms_filter.support --features-only

# 组合筛选（参数与 HAR 一致，按需叠加）
python "<SKILL_ROOT>/scripts/run.py" --json scmp info query --attr-code <code> --attr-type 2 --architecture-level system
python "<SKILL_ROOT>/scripts/run.py" --json scmp info query --second-department "SW_系统应用开发部" --third-department "SW_通信协议开发部"
```

`info query` 可选：`--page`、`--size`、`--attr-code`、`--attr-type`（1/2）、`--architecture-level`（system/vendor）、`--package-name`、`--attr-mode`、`--second-department`、`--third-department`、`--fourth-department`。

`info detail` 可选：`--bid` + `--version`（与 HAR 一致），或仅 `--attr-code`（自动解析 bid/version）；`--features-only` 仅返回 `attributeFeatures` 段。关联特性字段见 `data.attributeFeatures[]`：`fourthFeatureCode`、`fourthFeature`、`supportAttrValue`、`notSupportAttrValue` 等。

### 分区类型（必辨）

SCMP 项目/策略查询**必须指定 `--partition`**。用户未说明分区时，**先询问**，不要默认猜测。

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp partition list
```

| `--partition` | 含义 | partitionGroupBid | 项目搜索 API |
|---------------|------|-------------------|--------------|
| `tr_product` | 项目定制软件（公共分区） | `1234567892` | `queryProjectInfoByNameLike` 扁平列表 |
| `tr_region` | 区域定制软件 | `1234567894` | `queryProjectInfoTree` 树形（含市场子节点） |
| `tr_carrier` | 运营商定制软件（推导，无独立 HAR） | `1234567893` | 同 `tr_region` 树形 API |

策略列表 / 详情 API 三种分区相同，仅 `partitionGroupBid` 不同；`tr_region` / `tr_carrier` 策略记录可能带 `market` 字段（如 OP、TR、RU）。

### 项目 → 策略 → 策略内属性配置（三级串联）

**前置：确认 `--partition`。**

#### tr_product 示例（KM9）

```text
# 1. 模糊查项目（扁平列表，取 data[].name）
python "<SKILL_ROOT>/scripts/run.py" --json scmp project search --partition tr_product --name KM9

# 2. 查策略
python "<SKILL_ROOT>/scripts/run.py" --json scmp strategy list --partition tr_product \
  --project-name "KM9_H357(Android 16)" --strategy-code tr_product-tOS16.3.0-KM9-mp-00228

# 3. 读策略属性配置
python "<SKILL_ROOT>/scripts/run.py" --json scmp strategy detail --partition tr_product \
  --strategy-code tr_product-tOS16.3.0-KM9-mp-00228 \
  --project-name "KM9_H357(Android 16)" \
  --attr-code bluetooth.profile.ccp.server.enabled --attrs-only
```

#### tr_region 示例（X6886）

```text
# 1. 树形查项目（取父节点 name，非 projectName 简写）
python "<SKILL_ROOT>/scripts/run.py" --json scmp project search --partition tr_region --name X6886

# 可选：含市场子节点
python "<SKILL_ROOT>/scripts/run.py" --json scmp project search --partition tr_region --name X6886 --include-markets

# 2. 查策略（同一项目下按 market 区分多条策略）
python "<SKILL_ROOT>/scripts/run.py" --json scmp strategy list --partition tr_region \
  --project-name "X6886_H8921(Android 16)"

# 3. 读某条区域策略详情
python "<SKILL_ROOT>/scripts/run.py" --json scmp strategy detail --partition tr_region \
  --bid sid_2059534620843585536 --attrs-only
```

#### tr_carrier（推导）

命令与 `tr_region` 相同，仅将 `--partition tr_region` 换为 `--partition tr_carrier`。策略 code 通常以 `tr_carrier-` 开头。

辅助命令：

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp partition groups   # API 原始分区组列表
python "<SKILL_ROOT>/scripts/run.py" --json scmp partition list     # 内置三分区对照表
```

**字段映射要点：**

| 步骤 | tr_product | tr_region / tr_carrier |
|------|------------|-------------------------|
| project search 输出 | `data[].name` 作 `--project-name` | 树形 `_meta` 提示；父节点 `name` 作 `--project-name` |
| strategy list | `records[].strategyCode` 含 `tr_product-` | 含 `tr_region-` / `tr_carrier-`，且有 `market` |
| strategy detail | `attributeInfo[].attrValue` 为策略配置值 | 同左 |

`strategy detail` 完整响应还含 `appComponentInfo`、`machineResourceDetailInfo` 等；查属性值时加 `--attrs-only`。

### SPD 产品配置清单 / 特性配置清单

HAR：`scmp根据项目信息查询配置清单以及特性清单.har`。服务为 **`tones-spd`**（与 build-platform 共用 token）。

**典型流程：项目名 → projectBid + specBid → 产品配置 / 特性配置**

```text
# 0. 一键解析（推荐）：项目名 → projectBid + spec list bid (sid_...)
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd resolve --name KM9

# 1. 查产品规格清单版本（也可直接用 resolve 的 specBid）
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd spec list --name KM9 --tos-version 16.3.0

# 2. 产品配置清单（68 项字典类配置，含 code/name/configStatus）
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd config list --spec-bid sid_2062434858361171968

# 3. 特性配置清单（默认全量；可按特性编码/配置角色等筛选）
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd feature list \
  --spec-bid sid_2062434858361171968 \
  --feature-code SF-202507-001728
```

**用户示例：「KM9 项目中与我相关的特性配置，只看已完成的」**

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd resolve --name KM9
# 取 data.specBid，然后：
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd feature list \
  --spec-bid <specBid> --my-related true --config-status true
```

**用户示例：「按特性编码查配置角色（如 CMO）」**

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd feature list \
  --spec-bid sid_2062434858361171968 --feature-code SF-202507-001728
# data.records[0].configRole → CMO
```

`feature list` 筛选参数：

| 参数 | API 字段 | 说明 |
|------|----------|------|
| `--my-related false` | `myRelated` | **默认**。全量特性清单（与网页 SPD 特性配置清单一致）；按 `--feature-code` 查配置角色时必须用此模式 |
| `--my-related true` | `myRelated` | 仅返回与当前登录用户相关的特性（约数十条）；适合「我的待办特性」场景 |
| `--config-status true/false` | `configStatus` | true=已完成 false=未完成 |
| `--build-config-status true/false` | `buildConfigStatus` | 构建配置完成状态 |
| `--feature-code` | `lv4Code` | 特性编码，如 SF-202507-002778 |
| `--feature-name` | `lv4Name` | 特性名称（子串） |
| `--feature-owner` | `featureOwner` | 特性负责人 |
| `--feature-se` | `featureSe` | 特性 SE 工号 |
| `--config-owner` | `configOwner` | 配置负责人 |
| `--self-check-status` | `selfCheckStatus` | 如 Pass |
| `--page` / `--size` | `current` / `size` | 分页，默认 1/200 |

项目名解析规则：`tr_product` 下若多条匹配，优先 `projectName` 与关键词完全一致的项（如 KM9 选 `KM9` 而非 `KM9_SunMao`）。

辅助：`scmp spd project detail --bid <projectBid>` 查 SPD 项目详情。

## 响应解读

成功：`{"code":"0000","msg":"success","data":...}`

- **apply list**：`data.records[]` 含 `attrCode`、`applyCode`、`status`、`responsiblePerson`、`attrDefinition`、`approvalCenterUrl` 等
- **apply count**：`data[]` 含 `status`（中文标签）与 `statusTotal`
- **info query**：`data.records[]` 含 `attrCode`、`attrDefinition`、`attrDefaultValue`、`responsiblePerson`、`secondDepartment`、`version`、`applyTypeDesc` 等
- **info detail**：`data` 含完整属性版本详情；`data.attributeFeatures[]` 含 `fourthFeatureCode`（四级特性编码）、`fourthFeature`、`firstFeature`~`fourthFeature` 层级、`supportAttrValue` / `notSupportAttrValue`；`data.isConfigRefFlag` 表示是否已关联特性
- **project search**：`data[]` 含 `bid`、`name`（完整项目名）、`projectName`（机型简写）、`chip`
- **strategy list**：`data.records[]` 含 `bid`、`strategyCode`、`version`、`projectName`
- **strategy detail**：`data.attributeInfo[]` 含 `attrCode`、`attrValue`、`attrValueType`、`attrDefinition`（策略级配置值，非属性库默认值）
- **spd resolve**：`data.projectBid`、`data.specBid`、`data.tosVersion`、`data.marketList`
- **spd config list**：`data[]` 含 `code`、`name`、`configStatus`、`valueType` 等
- **spd feature list**：`data.records[]` 含 `lv4Code`、`lv4Name`、`featureOwner`、`configOwner`、`configRole`（配置角色，如 CMO/领域）、`configStatus`、`buildConfigStatus`、`attributeFeatureConfigInfoList`（绑定的 attrCode）

## Agent 行为约束

1. **先配置、后查询** — token 未配置或探活失败时，不要反复盲试 API
2. **先确认分区** — `project search` / `strategy list` / `strategy detail` 必须带 `--partition`；用户没说清时主动询问是 `tr_product` / `tr_region` / `tr_carrier`
3. **只用 CLI** — 不要绕过 `scripts/run.py` 直接请求
4. **只用 `--json`** — 解析结构化结果后向用户总结
5. **token 安全** — 不在回复中粘贴完整 token；`config show` 输出已脱敏
6. **skill 可移植** — 整个 `tones-scmp/` 目录拷贝到任意 Agent 的 skills 路径即可使用，无需 pip install 本包

## 目录结构

```
tones-scmp/
├── SKILL.md                 # 本文件
├── reference.md             # API 与配置字段详表
└── scripts/
    ├── run.py               # CLI 入口（Agent 只调用此文件）
    ├── requirements.txt
    ├── config.example.yaml
    ├── config.yaml          # 运行时生成，含 token，勿提交
    └── tones_cli/           # CLI 实现
```

更多 API 对照见 [reference.md](reference.md)。

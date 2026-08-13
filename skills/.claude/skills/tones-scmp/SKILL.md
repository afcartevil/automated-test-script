---
name: tones-scmp
description: >-
  查询 TONES SCMP：属性申请/属性库、项目模糊搜索、分区策略列表、策略下属性配置值、
  SPD 产品配置清单与特性配置清单（可按特性编码/名称/owner/配置状态/与我相关筛选）、
  SPD 项目候选匹配与按市场支持一键查询。内置 UAC 自动登录，无需手工配置 token。
  通过 scripts/run.py 调用 api-tones.transsion.com。支持按项目名查 KM9 等项目、查策略
  tr_product-tOS16.3.0-KM9-mp-00228、读策略 attributeInfo 中 attrCode 的配置值。
  当用户提到 SCMP、项目策略、partition strategy、attrCode 配置值、产品配置清单、特性清单、
  KM9、tones-build-platform、tones-spd、UAC 登录或 hk-intra-paas 时使用。
version: 0.5.0
---

# TONES SCMP 属性查询

通过本 skill 自带的 CLI（`scripts/run.py`）查询 SCMP / SPD。**禁止手写 curl/requests**，统一走 CLI。

## 调用契约

本 skill 目录记为 `SKILL_ROOT`（即含 `SKILL.md` 的目录）。所有 CLI 调用使用：

```text
python "<SKILL_ROOT>/scripts/run.py" --json <子命令...>
```

**必须加 `--json`**，便于解析 `code` / `data` / `records`。

## 首次使用检查清单

Agent 在业务查询前，按顺序执行：

```
启动检查：
- [ ] 1. 依赖已安装（httpx, cryptography）
- [ ] 2. 已执行 auth login（或任意 scmp 命令触发自动登录）
- [ ] 3. 探活成功（scmp apply count 返回 code=0000）
- [ ] 4. 再执行用户要求的查询
```

### 步骤 1：安装依赖（每个 Agent 环境一次）

```text
pip install -r "<SKILL_ROOT>/scripts/requirements.txt"
```

### 步骤 2：UAC 自动登录（强制）

账号密码已写死在 `tones_cli/uac_login.py`，**不要**向用户索取 token，**不要**要求浏览器 DevTools / HAR 手工填配置。

```text
# 显式登录（推荐会话开始时执行一次）
python "<SKILL_ROOT>/scripts/run.py" --json auth login

# 强制刷新 token
python "<SKILL_ROOT>/scripts/run.py" --json auth login --force

# 查看缓存状态（不含明文 token）
python "<SKILL_ROOT>/scripts/run.py" --json auth status
```

说明：

- 任一次 `scmp ...` 命令在入口也会自动 `ensure_auth()`（无缓存则登录）。
- Token 缓存到 `<SKILL_ROOT>/scripts/.token_cache.json`；HTTP 401/过期时客户端会自动再登录并重试一次。
- **不要在回复中回显完整 token。**

### 步骤 3：探活

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply count
```

- `code` 为 `0000` → 继续业务查询
- 仍失败 → `auth login --force` 后重试一次；勿反复盲试

## 业务命令速查

### 属性申请清单

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply list --page 1 --size 10
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply list --status 0
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply count
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply responsible-persons
python "<SKILL_ROOT>/scripts/run.py" --json scmp apply persons
python "<SKILL_ROOT>/scripts/run.py" --json scmp department second
python "<SKILL_ROOT>/scripts/run.py" --json scmp department third
```

### 属性信息查询

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp info query --attr-code ro.tr_dynamicbar.resident_plane.support
python "<SKILL_ROOT>/scripts/run.py" --json scmp info detail --attr-code ro.tr_telephony.sms_filter.support
python "<SKILL_ROOT>/scripts/run.py" --json scmp info detail --bid sid_1394974796370022400 --version 20251226.0001
python "<SKILL_ROOT>/scripts/run.py" --json scmp info detail --attr-code ro.tr_telephony.sms_filter.support --features-only
```

`info query` 可选：`--page`、`--size`、`--attr-code`、`--attr-type`（1/2）、`--architecture-level`（system/vendor）、`--package-name`、`--attr-mode`、`--second-department`、`--third-department`、`--fourth-department`。

### 分区类型（必辨）

SCMP 项目/策略查询**必须指定 `--partition`**。用户未说明分区时，**先询问**。

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp partition list
```

| `--partition` | 含义 | partitionGroupBid | 项目搜索 API |
|---------------|------|-------------------|--------------|
| `tr_product` | 项目定制软件（公共分区） | `1234567892` | `queryProjectInfoByNameLike` 扁平列表 |
| `tr_region` | 区域定制软件 | `1234567894` | `queryProjectInfoTree` 树形（含市场子节点） |
| `tr_carrier` | 运营商定制软件（推导） | `1234567893` | 同 `tr_region` 树形 API |

### 项目 → 策略 → 策略内属性配置（三级串联）

**前置：确认 `--partition`。**

#### tr_product 示例（KM9）

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp project search --partition tr_product --name KM9
python "<SKILL_ROOT>/scripts/run.py" --json scmp strategy list --partition tr_product \
  --project-name "KM9_H357(Android 16)" --strategy-code tr_product-tOS16.3.0-KM9-mp-00228
python "<SKILL_ROOT>/scripts/run.py" --json scmp strategy detail --partition tr_product \
  --strategy-code tr_product-tOS16.3.0-KM9-mp-00228 \
  --project-name "KM9_H357(Android 16)" \
  --attr-code bluetooth.profile.ccp.server.enabled --attrs-only
```

#### tr_region 示例（X6886）

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp project search --partition tr_region --name X6886
python "<SKILL_ROOT>/scripts/run.py" --json scmp project search --partition tr_region --name X6886 --include-markets
python "<SKILL_ROOT>/scripts/run.py" --json scmp strategy list --partition tr_region \
  --project-name "X6886_H8921(Android 16)"
python "<SKILL_ROOT>/scripts/run.py" --json scmp strategy detail --partition tr_region \
  --bid sid_2059534620843585536 --attrs-only
```

#### tr_carrier（推导）

命令与 `tr_region` 相同，仅将 `--partition tr_region` 换为 `--partition tr_carrier`。

辅助：

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp partition groups
python "<SKILL_ROOT>/scripts/run.py" --json scmp partition list
```

### SPD 产品配置 / 特性 / 市场支持

服务 **`tones-spd`**（与 build-platform 共用 UAC token）。

**典型流程 A（build-platform 解析项目名）：**

```text
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd resolve --name KM9
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd spec list --name KM9 --tos-version 16.3.0
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd config list --spec-bid sid_...
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd feature list --spec-bid sid_... --feature-code SF-202507-001728
```

**典型流程 B（sdd_test 对齐：按产品名 + TOS → 市场支持表）：**

```text
# 全量 SPD 项目列表
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd project list

# 按产品名匹配有序候选（精确 > 去括号 > 普通 > Android > SunMao）
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd candidates --name X6886

# 一键：候选遍历 + 规格匹配 + 普通特性/Google 合并 + 市场 0/1
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd one-step --name X6886 --tos-version 16.1.0

# 已知 specBid 时只解析市场支持
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd market-support --spec-bid sid_...

# Google Program 清单
python "<SKILL_ROOT>/scripts/run.py" --json scmp spd google list --spec-bid sid_...
```

`one-step` / `market-support` 的 `data` 形态：`{ "SF-xxx": { "OP": "1", "RU": "0", ... }, ... }`  
（文案含「不参加」/「不支持」→ `"0"`，否则 `"1"`）。

`feature list` 筛选参数：

| 参数 | API 字段 | 说明 |
|------|----------|------|
| `--my-related false` | `myRelated` | **默认**全量；按编码查配置角色用此模式 |
| `--my-related true` | `myRelated` | 仅与当前登录用户相关 |
| `--config-status true/false` | `configStatus` | 已完成/未完成 |
| `--build-config-status true/false` | `buildConfigStatus` | 构建配置状态 |
| `--feature-code` | `lv4Code` | 特性编码 |
| `--feature-name` | `lv4Name` | 特性名称 |
| `--feature-owner` / `--feature-se` / `--config-owner` | 对应字段 | 负责人筛选 |
| `--self-check-status` | `selfCheckStatus` | 如 Pass |
| `--page` / `--size` | `current` / `size` | 默认 1/200 |

辅助：`scmp spd project detail --bid <projectBid>`。

## 响应解读

成功：`{"code":"0000","msg":"success","data":...}`

- **auth login**：`data.logged_in` / `p_auth_present`（不回显 token）
- **spd candidates**：有序 `data[]`，含 `rank` / `name` / `bid`
- **spd one-step / market-support**：`data` 为特性→市场支持表；`_meta` 含选用项目与 `featureCount`
- **spd resolve**：`data.projectBid`、`data.specBid`、`data.tosVersion`、`data.marketList`
- **spd feature list**：`data.records[]` 含 `lv4Code`、`configRole`、`attributeFeatureConfigInfoList` 等
- 其余 apply / info / project / strategy 字段含义同前版

## Agent 行为约束

1. **先登录、后查询** — 会话开始执行 `auth login`；过期用 `--force`，不要向用户要 token
2. **先确认分区** — `project search` / `strategy list` / `strategy detail` 必须带 `--partition`
3. **只用 CLI** — 不要绕过 `scripts/run.py` 直接请求
4. **只用 `--json`** — 解析结构化结果后向用户总结
5. **token 安全** — 不粘贴完整 token；账号逻辑在脚本内，勿在对话中解码传出
6. **skill 可移植** — 拷贝整个 `tones-scmp/` 目录即可；`pip install -r scripts/requirements.txt`

## 目录结构

```
tones-scmp/
├── SKILL.md
├── reference.md
└── scripts/
    ├── run.py
    ├── requirements.txt
    ├── .token_cache.json   # 运行时生成，勿提交
    └── tones_cli/
        ├── uac_login.py    # 内置账密 + 自动登录
        ├── config.py       # 内置 service 端点
        └── ...
```

更多 API 对照见 [reference.md](reference.md)。

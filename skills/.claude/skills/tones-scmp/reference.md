# TONES SCMP CLI Reference

## 鉴权（UAC 自动登录）

不再使用 `config.yaml` / 浏览器手工 token。

| 项 | 说明 |
|----|------|
| 实现 | `tones_cli/uac_login.py`（账密 Base64 写死，同 sdd_test） |
| 网关 | `https://pfgatewaysz.transsion.com:9199` |
| 登录 | GET `.../crypto/rsaKeyPair` → RSA 加密密码 → POST `.../login/account` |
| 缓存 | `scripts/.token_cache.json`（`p_auth` / `authorization` / `p_rtoken` / `p_appid`） |
| CLI | `auth login` / `auth login --force` / `auth status` |
| 刷新 | 业务请求遇 401/token 过期时 HTTP 客户端自动 `force_refresh` 并重试 1 次 |

内置服务端点见 `tones_cli/config.py` 的 `SERVICES`（`tones-build-platform` / `tones-spd`）。

## 分区对照（内置）

| partition | label | bid | project API |
|-----------|-------|-----|-------------|
| `tr_product` | 项目定制软件 | 1234567892 | `queryProjectInfoByNameLike` |
| `tr_region` | 区域定制软件 | 1234567894 | `queryProjectInfoTree` |
| `tr_carrier` | 运营商定制软件 | 1234567893 | `queryProjectInfoTree`（推导） |

CLI：`scmp partition list` / `scmp partition groups`。

## API 对照表（build-platform / SCMP）

| CLI | Method | Path |
|-----|--------|------|
| `auth login` | POST (UAC gateway) | `/uac-auth-service/v2/api/uac-auth/login/account` |
| `scmp apply list` | POST | `/attributeApply/queryAttributeApplyByPage` |
| `scmp apply count` | POST | `/attributeApply/getAttributeApplyCountByStatus` |
| `scmp info query` | POST | `/attributeInfo/queryAttributeInfoByPage` |
| `scmp info detail` | POST | `/attributeInfo/getAttributeVersionDetail` |
| `scmp project search --partition tr_product` | POST | `/projectInfo/queryProjectInfoByNameLike` |
| `scmp project search --partition tr_region\|tr_carrier` | POST | `/projectInfo/queryProjectInfoTree` |
| `scmp strategy list` | POST | `/partitionStrategy/getPartitionStrategyByPage` |
| `scmp strategy detail` | GET | `/partitionStrategy/getPartitionStrategyDetail/{bid}` |
| `scmp partition groups` | POST | `/partitionInfo/queryPartitionGroupInfoList` |

## project search

| 参数 | 说明 |
|------|------|
| `--partition` | **必填** `tr_product` / `tr_region` / `tr_carrier` |
| `--name` | 模糊关键词 |
| `--include-markets` | 仅树形分区：输出含 type=1 市场子节点 |

## info detail / strategy

同此前 HAR 约定：`info detail` 可用 `--bid`+`--version` 或 `--attr-code`；`strategy list/detail` 必须 `--partition`。

## SPD 服务（tones-spd）

| CLI | Method | Path / 逻辑 |
|-----|--------|-------------|
| `scmp spd resolve` | 链式 | build-platform 项目搜索 + `getProjectInfoDetail` + `queryProductSpecificationList` |
| `scmp spd project list` | POST | `/spd-projectInfo/getProjectInfoList` |
| `scmp spd project detail` | POST | `/spd-projectInfo/getProjectInfoDetail` |
| `scmp spd candidates` | 客户端 | `getProjectInfoList` + 名称匹配排序（sdd_test） |
| `scmp spd spec list` | POST | `/productSpecificationList/queryProductSpecificationList` |
| `scmp spd config list` | POST | `/productSpecificationList/queryProductConfigList` |
| `scmp spd feature list` | POST | `/productSpecificationList/queryFeatureConfigList` |
| `scmp spd google list` | POST | `/productSpecificationList/queryGoogleProgramList` |
| `scmp spd market-support` | 链式 | feature(+google) → `{code:{market:"0"|"1"}}` |
| `scmp spd one-step` | 链式 | candidates → tos 规格 → 合并特性 → 市场支持表 |

### candidates / one-step 匹配优先级

1. 全名精确匹配  
2. 去掉括号后缀精确匹配  
3. base name + token 子集  
同名中：普通优先；含 `ANDROID` 次之；含 `SUNMAO` 最低。

### market 支持值规则

`marketInfoList[].value` 含「不参加」或「不支持」→ `"0"`，否则 → `"1"`。

### spd feature list 请求体

| CLI 参数 | JSON 字段 |
|----------|-----------|
| `--spec-bid` | `bid` |
| `--page` / `--size` | `current` / `size` |
| `--my-related true/false` | `myRelated` |
| `--config-status true/false` | `configStatus` |
| `--build-config-status true/false` | `buildConfigStatus` |
| `--feature-code` | `lv4Code` |
| `--feature-name` | `lv4Name` |
| `--feature-owner` / `--feature-se` / `--config-owner` | 对应字段 |
| `--self-check-status` | `selfCheckStatus` |

HAR：`scmp根据项目信息查询配置清单以及特性清单.har`

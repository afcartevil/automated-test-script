# TONES SCMP CLI Reference

## 配置字段（scripts/config.yaml）

见 `config.example.yaml`。Token 从浏览器 DevTools 获取。

## 分区对照（内置）

| partition | label | bid | project API | HAR |
|-----------|-------|-----|-------------|-----|
| `tr_product` | 项目定制软件 | 1234567892 | `queryProjectInfoByNameLike` | scmp根据项目名称模糊查询项目信息.har 等 |
| `tr_region` | 区域定制软件 | 1234567894 | `queryProjectInfoTree` | scmp根据区域分区中项目信息名称模糊查询项目信息.har 等 |
| `tr_carrier` | 运营商定制软件 | 1234567893 | `queryProjectInfoTree`（推导） | 无独立 HAR |

CLI：`scmp partition list` 输出上表；`scmp partition groups` 调 API 原始列表。

## API 对照表

| CLI | Method | Path |
|-----|--------|------|
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

树形分区返回扁平化 `data[]`，含 `isMarket`、`parentName`；`_meta.hint` 说明如何用 `name` 填 `--project-name`。

## info detail 请求体

| CLI 参数 | JSON 字段 | 说明 |
|----------|-----------|------|
| `--bid` | `bid` | 属性 bid；与 `--version` 同用 |
| `--version` | `version` | 属性版本，如 `20251226.0001` |
| `--attr-code` | — | 未提供 `--bid` 时，经 `info query` 解析 bid/version |
| `--features-only` | — | 客户端裁剪，仅输出 `attributeFeatures` 相关字段 |

HAR：`根据属性查询关联特性信息.har`

## strategy list 请求体

| CLI 参数 | JSON 字段 | 说明 |
|----------|-----------|------|
| `--partition` | → `partitionGroupBid` | 由内置 profile 映射 |
| `--project-name` | `projectName` | 必填 |
| `--page` / `--size` | `current` / `size` | 分页 |
| `--strategy-type` | `strategyType` | 默认 0 |
| `--status` | `status` | 默认 0 |
| `--market` | `market` | 区域/运营商可选；未指定时 tr_region/tr_carrier 传 `null` |
| `--strategy-code` | — | 客户端子串过滤 |

## strategy detail

| 参数 | 说明 |
|------|------|
| `--partition` | **必填** |
| `--bid` / `--strategy-code` | 二选一 |
| `--project-name` | 用 `--strategy-code` 解析 bid 时必填 |
| `--market` | 解析 bid 时可选 |
| `--attr-code` | 过滤 `attributeInfo` |
| `--attrs-only` | 仅返回属性段 |

## 串联示例

**tr_product / KM9：**

```text
scmp project search --partition tr_product --name KM9
scmp strategy list --partition tr_product --project-name "KM9_H357(Android 16)"
scmp strategy detail --partition tr_product --bid sid_... --attr-code <code> --attrs-only
```

**tr_region / X6886：**

```text
scmp project search --partition tr_region --name X6886
scmp strategy list --partition tr_region --project-name "X6886_H8921(Android 16)"
scmp strategy detail --partition tr_region --bid sid_2059534620843585536 --attrs-only
```

**tr_carrier：** 同上，换 `--partition tr_carrier`。

## SPD 服务（tones-spd）

配置 `services.tones-spd`：`base_url` + `path_prefix: /tones-spd`，`auth_profile` 与 build-platform 相同。

| CLI | Method | Path |
|-----|--------|------|
| `scmp spd resolve` | POST (链式) | build-platform `queryProjectInfoByNameLike` + spd `getProjectInfoDetail` + `queryProductSpecificationList` |
| `scmp spd project detail` | POST | `/spd-projectInfo/getProjectInfoDetail` |
| `scmp spd spec list` | POST | `/productSpecificationList/queryProductSpecificationList` |
| `scmp spd config list` | POST | `/productSpecificationList/queryProductConfigList` |
| `scmp spd feature list` | POST | `/productSpecificationList/queryFeatureConfigList` |

### spd spec list 请求体

| CLI 参数 | JSON 字段 |
|----------|-----------|
| `--project-bid` / `--name` | `projectBid`（name 经 build-platform 解析） |
| `--tos-version`（可重复） | `tosVersionList` |

### spd feature list 请求体

| CLI 参数 | JSON 字段 |
|----------|-----------|
| `--spec-bid` | `bid`（产品规格清单 sid） |
| `--page` / `--size` | `current` / `size` |
| `--my-related true/false` | `myRelated` | 默认 `false`（全量清单）；`true` 仅与我相关 |
| `--config-status true/false` | `configStatus` |
| `--build-config-status true/false` | `buildConfigStatus` |
| `--feature-code` | `lv4Code` |
| `--feature-name` | `lv4Name` |
| `--feature-owner` | `featureOwner` |
| `--feature-se` | `featureSe` |
| `--config-owner` | `configOwner` |
| `--self-check-status` | `selfCheckStatus` |

HAR：`scmp根据项目信息查询配置清单以及特性清单.har`

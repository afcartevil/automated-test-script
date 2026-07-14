# MCC 官方语言查询

**不维护静态 MCC→语言表**。当地语言未指定时，必须从网络实时查询。

## 平台资源差异

名称 key 的 MCC 路由文件按平台不同：

| 平台 | MCC 映射文件 | 说明 |
|------|--------------|------|
| MTK | `res/values/config.xml` | `string-array name="ecc_config_{MCC}"` |
| Unisoc（展锐） | `res/values/ecc_config_list.xml` | 同样使用 `ecc_config_{MCC}` |
| Qualcomm（高通） | `res/values/config.xml` | 与 MTK 同名文件，与展锐不同 |

语言查询与 `values-*` 目录验证流程三平台通用。

## 何时触发

- 用户提供了 `localNames` 但未指定 `language`
- 用户要求改当地语言名但未说明语言

用户已显式指定语言（如 `pl-rPL`、`zh-rCN`）时，跳过网络查询。

## 查询流程

1. 从 `mccmnc` 提取 MCC（前 3 位）。
2. 使用 **WebSearch** 查询，例如：
   - `MCC 260 country official language`
   - `MCC 460 国家 官方语言`
3. 从查询结果确定该国家/地区的**官方语言**。
4. 将语言映射为仓库中已有的 `res/values-{qualifier}/` 目录名。
5. **验证目录存在**：在 ECC 仓库 `res/` 下确认对应目录存在。
6. 按平台到 MCC 映射文件定位 `ecc_config_{MCC}`，再根据号码取 `string_key`。

## 语言 → values 目录映射

查询到官方语言后，映射为 Android qualifier。常见示例：

| 语言 | values 目录 |
|------|-------------|
| 波兰语 | `values-pl-rPL` |
| 简体中文 | `values-zh-rCN` |
| 繁体中文（台湾） | `values-zh-rTW` |
| 越南语 | `values-vi-rVN` |
| 法语 | `values-fr` 或 `values-fr-rFR` |
| 德语 | `values-de-rDE` |
| 西班牙语 | `values-es-rES` |
| 葡萄牙语 | `values-pt-rPT` |
| 俄语 | `values-ru` |
| 阿拉伯语 | `values-ar` |
| 印地语 | `values-hi` |
| 泰语 | `values-th-rTH` |
| 印尼语 | `values-in` |
| 土耳其语 | `values-tr` |

映射时优先匹配 ECC 仓库中**实际存在**的 `values-*` 目录（用 Glob 或列目录确认），而非假设目录名。

## 多官方语言国家

若一个国家有多种官方语言（如比利时、瑞士、印度）：

1. 结合 MCC 对应的具体国家/地区判断。
2. 优先选择与 EccList 已有 `values-*` 目录匹配的语言。
3. 仍无法判断时，列出候选语言并询问用户。

## 查询失败处理

以下情况询问用户指定语言：

- 网络查询无结果
- 无法确定官方语言
- 映射后的 `values-*` 目录在 EccList 中不存在

列出 ECC 仓库 `res/` 下可用的 `values-*` 目录供用户选择。

## 规则

- **不得**凭记忆硬编码 MCC→语言映射，必须通过网络查询。
- 变更摘要中注明查询来源（查询关键词 + 结论）。
- 用户显式指定语言时，跳过网络查询。

## 查询结果记录示例

```markdown
- **语言查询**: "MCC 260 Poland official language" → 波兰语 → values-pl-rPL（目录已验证存在）
```

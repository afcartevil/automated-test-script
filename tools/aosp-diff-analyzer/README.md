# AOSP Diff Analyzer
对比两个Android版本的framework diff，提取API/接口/行为变更清单。

## 输入
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source_version | string | 是 | 源版本 |
| target_version | string | 是 | 目标版本 |
| diff_content | string | 是 | git diff输出 |
| module_filter | string | 否 | 模块过滤 |

## 输出
deprecated_apis, removed_apis, added_apis, summary

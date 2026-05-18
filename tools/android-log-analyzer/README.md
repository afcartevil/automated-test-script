# Android Log Analyzer
解析logcat/ril/atcmd日志，提取关键事件和异常信息。

## 输入
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| log_content | string | 是 | 原始日志 |
| log_type | string | 否 | logcat/ril/atcmd/bugreport |
| filters | array | 否 | 过滤关键词 |

## 输出
events, errors, statistics

# L2 ModemEE 输出结构

```json
{
  "analysis": {
    "l2_domains": {
      "ee": {
        "status": "done|insufficient_evidence|skipped_invalid",
        "timeline": [],
        "evidence": [],
        "candidate_causes": [],
        "gaps": [],
        "ee_details": {
          "ee_type": "modem ee|phonecrash|assert|watchdog|...",
          "err_code": "0x...|...",
          "exception_source": "...",
          "first_occurrence": "2026-01-01T12:00:00"
        },
        "database_query": {
          "success": true,
          "status": "hit|miss|query_error|no_query_params",
          "exists": false,
          "record": {},
          "write_result": {
            "success": true,
            "status": "written",
            "action": "inserted|updated"
          }
        }
      }
    }
  }
}
```

## 字段说明

### status
- `done`: 分析完成，找到足够证据
- `insufficient_evidence`: 证据不足
- `skipped_invalid`: L0 已判定为无效问题，跳过分析

### ee_details
从日志中提取的 ModemEE 关键信息：
- `ee_type`: 异常类型（modem ee、phonecrash、assert、watchdog 等）
- `err_code`: 异常代码
- `exception_source`: 异常源
- `first_occurrence`: 首次发生时间

### database_query
数据库查询结果：
- `success`: 查询是否成功
- `status`: 查询状态
  - `hit`: 数据库中存在该 ModemEE
  - `miss`: 数据库中不存在
  - `query_error`: 查询出错
  - `no_query_params`: 缺少查询参数
- `exists`: 是否存在记录
- `record`: 已知记录详情
- `write_result`: 写入结果（仅在 miss 时尝试写入）
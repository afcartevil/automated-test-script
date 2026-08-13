# 常见问题与原因对照表

| 序号 | 问题现象 | 日志特征 | 根因说明 |
|---|---|---|---|
| 1 | 开机无触摸 | `[FTS_TS/I]fts_get_ic_information:fw is invalid, need read boot id` / `[FTS_TS/E]fts_read_bootid:read boot id fail,read:0x0000` / `[FTS_TS/E]fts_get_ic_information:read boot id fail` | TP IC 短路，导致初始化异常 |

## 详细说明

### 问题1：开机无触摸

**问题描述**：

- 开机触摸无响应

**日志特征**：

```text
[FTS_TS/I]fts_get_ic_information:fw is invalid, need read boot id
[FTS_TS/E]fts_read_bootid:read boot id fail,read:0x0000
[FTS_TS/E]fts_get_ic_information:read boot id fail
```

**根因分析**：

- 驱动无法通过常规寄存器识别 IC 型号。
- 读取 `boot id` 失败。
- SOP 对应根因：TP IC 短路，导致初始化异常。

**排查建议**：

- 检查 TP 供电是否正常。
- 检查复位引脚是否正常。

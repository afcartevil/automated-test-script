# 典型案例

## 案例1：海外反馈，KM7 Touch does not work at all.

### 现象

- 无触摸。

### 根因

- 触摸 IC 短路，导致初始化失败。

### 关键日志

```text
[FTS_TS/E]fts_read_bootid:read boot id fail,read:0x0000
[FTS_TS/E]fts_get_ic_information:read boot id fail
```

## 案例2：海外反馈，While on a WhatsApp video call, attempting to access the Notification Panel results in mis-touch behavior, causing inaccurate or unintended touch responses.

### 现象

- 在使用 WhatsApp 通话时，左上角下划失效。

### 根因

- 在使用 WhatsApp 通话时，下拉状态栏事件被胶囊电话拦截。

### 关键日志

```text
[FTS_TS/I]fts_input_report_b:[B][resolution_multiples:16] P0 (702,1519) touch down!
[FTS_TS/I]fts_input_report_b:[B][resolution_multiples:16] P0 (488,1590) touch up!
```

### 结论说明

- 该案例中底层已有触摸数据上报。
- SOP 结论是：Framework 层已收到数据上报，应交给上层同事继续排查分析。

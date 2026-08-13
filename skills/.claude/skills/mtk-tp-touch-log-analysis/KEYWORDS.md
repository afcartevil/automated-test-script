# 关键字与日志示例参考

## 关键词列表

用于日志搜索的关键词（竖线分隔，可直接用于 grep）：

```text
tran_touch|fts|nvt|omn|ilitek
```

## 关键日志示例与解读

以下按 SOP 展示顺序整理，保留页面代码块中原有的 `...` 省略写法。

### 系统启动并允许 TP 驱动加载

**日志示例**：

```text
[tran_touch-INFO]flod_main_device_init 942:bootmode 0 load ...
```

**解读**：

- 表示系统处于 `Normal` 或 `Factory` 模式，允许加载触摸驱动。

### 内核开始探测 TP 设备

**日志示例**：

```text
[tran_touch-INFO]tpd_probe 800:mian ctp probe start
```

**解读**：

- 表明内核已找到对应设备树节点，并开始执行 TP 核心探测流程。

### TP 芯片开始初始化

**日志示例**：

```text
[tran_touch-INFO]match_tp_controller 427:start load main controller ...
```

**解读**：

- 表明 TP 芯片初始化开始。
- 需要关注 `vendor` 与 `ic` 字段，例如 `vendor:focaltech ic:ft3683g`。

### TP 芯片初始化成功

**日志示例**：

```text
[tran_touch-INFO]match_tp_controller 441:load main controller ...
```

**解读**：

- 表明 TP 芯片初始化成功。
- 仍需继续核对 `vendor` 与 `ic` 是否与项目配置一致。

### 触摸数据 down/up 上报

**日志示例**：

```text
[FTS_TS/I]fts_input_report_b:[B][resolution_multiples:16] P0 (...) touch down!
[FTS_TS/I]fts_input_report_b:[B][resolution_multiples:16] P0 (...) touch up!
```

**解读**：

- 表示底层已有触摸数据上报。
- 一旦确认存在 `touch down` / `touch up`，应继续检查 framework 或上层链路，而不是继续停留在 TP 驱动加载结论。

## 字段关注点

- `bootmode`：确认当前是否允许加载 TP 驱动。
- `vendor`：确认匹配到的 TP 厂商。
- `ic`：确认匹配到的 TP 芯片型号。
- `resolution_multiples`：辅助确认触摸上报节点来自 TP 输入链路。

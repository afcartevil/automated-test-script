# SIM 卡状态流转分析

## 状态定义

| 状态 | 含义 |
|------|------|
| ABSENT | 卡不存在 |
| UNKNOWN | 初始化中或状态异常 |
| READY | SIM 卡通信就绪（未完成数据加载，不代表识卡成功） |
| LOADED | SIM 卡数据加载完成（真正识卡成功） |
| PIN_REQUIRED | PIN 锁等待输入 |
| PUK_REQUIRED | PIN 错误次数过多 |
| CARD_IO_ERROR | 硬件访问错误 |
| CARD_RESTRICTED | 卡被限制 |

## onSimStateChanged 状态码
- `1` = ABSENT
- `5` = LOADED
- 示例：`onSimStateChanged 5 -> 1` 表示 LOADED → ABSENT

## 正常流程
```
ABSENT → READY → LOADED          （正常识卡，LOADED 才算完成，< 3s）
LOADED → ABSENT → READY → LOADED （热插拔）
```

## 异常流程
```
ABSENT → CARD_IO_ERROR            （硬件问题）
ABSENT → UNKNOWN                  （状态异常）
READY → ABSENT                    （掉卡）
ABSENT → PIN_REQUIRED             （PIN 锁）
LOADED → ABSENT（无 +ESIMS:0,11） （接触不良掉卡）
```

## 救卡流程
```
LOADED → ABSENT (+ESIMS:0,13) → READY (+ESIMS:1,14) → LOADED
```

## 时间分析

| 转换 | 正常 | 异常 |
|------|------|------|
| ABSENT → READY | < 2s | > 5s 通信就绪延迟 |
| READY → LOADED | < 1s | > 3s 数据加载缓慢（停留在 READY 不代表识卡成功） |
| 完整流程 | < 3s | > 10s 严重延迟 |
| 救卡流程 | 1-3s | > 10s 救卡缓慢 |

## 与 AT+ESIMS 的关联

| ESIMS 事件 | 对应状态 |
|------------|---------|
| `+ESIMS:1,29` | → READY（通信就绪，但还需等 LOADED 才算识卡完成） |
| `+ESIMS:0,1` | → CARD_IO_ERROR |
| `+ESIMS:0,11` | → ABSENT（拔卡） |
| `+ESIMS:0,13` | → ABSENT（救卡开始） |
| `+ESIMS:1,14` | → READY（救卡成功，还需等 LOADED） |

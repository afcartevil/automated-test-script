---
name: mtk-battery-gauge-stack
description: "MTK电池-gauge: 分析power_supply注册与gauge调用链，覆盖battery manager到mt63xx-gauge实现 | battery/SOC/fgauge/power_supply/电量不准/电量跳变/充电百分比异常 | 当用户报告MTK设备SOC跳变、电量不准、fgauge数据异常、battery设备注册问题时使用。充电流程走transsion-charger-orchestrator"
---

# MTK 电量计与电池栈

## 适用范围

只分析 battery 设备注册与 gauge 数据路径。

包含：
- `drivers/power/supply/mtk-battery-manager.c`
- `drivers/power/supply/mtk_battery.c`
- `drivers/power/supply/*-gauge.c`（如 `mt6357-gauge.c`）

不包含：
- `transsion/tc_charger.c` 的充电策略投票与插拔控制
- PD 协议与 Type-C 状态机
- USB 角色切换与枚举

## 固定入口

优先从以下函数开始：
1. `mtk-battery-manager.c` 中 `bm_battery_service_init()`
2. battery 注册点（`psd.name = "battery"` + `power_supply_register`）
3. `mtk_battery.c` 中 gauge 消费调用：
   - `gauge_get_property()`
   - `gauge_get_property_control()`

再映射到具体 `*-gauge.c` 的 IC 实现函数。

## 分析步骤

```text
电量计排查清单
- [ ] 确认 battery psy 注册链路与回调
- [ ] 明确问题属性：SOC/电流/电压/温度/库仑值
- [ ] 跟踪 mtk_battery.c 到 gauge_get_property* 调用
- [ ] 定位对应 mt63xx-gauge.c 实现
- [ ] 区分“框架层问题”与“IC/寄存器问题”
```

## 输出模板

```markdown
## 触发点
- 输入触发：<关键词/日志/属性>
- 首个命中函数：<function>

## 电池路径
- 注册路径：<call chain>
- 运行时读数路径：<mtk_battery -> gauge function>

## 边界判断
- 是否在本 skill 范围：<yes/no + 原因>
- 是否需要转交：<目标 skill 或 none>

## 根因与下一步
- 最可能原因：<1-2 行>
- 下一步验证点：<文件/函数/日志>
```

## 约束

- `battery` 注册层与 `gauge` 芯片实现层必须分开分析
- 本 skill 不处理 charger vote，转交 charger skill
- 若属于 USB 角色/Type-C 附着问题，转交 extcon/PD skill
- 仅在根因明确（或用户明确确认某根因）时输出“改进措施”
- 若根因不确定，仅输出“可能根因”与证据，不输出改进措施

---
name: transsion-wireless-bypass-fan
description: "Transsion-无线旁路风扇: 分析无线旁路(磁吸风扇)路径，定位旁路电流目标与不掉电判据 | magnetism_fan/无线旁路/磁吸风扇/旁路电流 | 当用户报告无线旁路触发失败、触发后不生效、与有线快充冲突时使用"
---

# Transsion 无线旁路（磁吸风扇）分析

## 适用范围

只分析无线旁路特性链路及其在充电主控中的影响。

包含：
- `support_magnetism_fan_check`
- `support_magnetism_fan_bypass`
- `magnetism_fan_bypass_aicr`
- 无线旁路触发后电流目标与表现（约 300mA 入电池）

不包含：
- 有线全场景旁路/旁路2.0 主链（转交 `transsion-charger-orchestrator`）
- BC1.2 / DCP 类型识别（转交 `transsion-bc12-type-detect`）
- PD/Type-C 协商状态机（转交 PD/TCPC skill）

## 固定入口

优先从以下关键词和函数命中：
1. `support_magnetism_fan_check`
2. `support_magnetism_fan_bypass`
3. `magnetism_fan_bypass_aicr`
4. 与旁路状态联动的 vote 与 ichg 限制日志

## 分析步骤

```text
无线旁路排查清单
- [ ] 先判触发条件：是否命中 `support_magnetism_fan_check` 与设备侧识别条件
- [ ] 再判开关条件：`support_magnetism_fan_bypass` 是否开启，是否写入对应旁路控制
- [ ] 再判执行结果：`magnetism_fan_bypass_aicr` 是否把入电池目标拉到约 300mA
- [ ] 观察现象验收：
  - 旁路后是否退至约 5.5V
  - 入电池电流是否约 300mA
  - 系统是否保持不掉电
- [ ] 失败分层：
  - A 层（资格门控）：风扇/无线条件未满足
  - B 层（执行失败）：旁路控制未下发或被覆盖
  - C 层（验收失败）：命令下发后电压/电流表现不符合预期
```

## 边界与转交

- 若命中 `bypass_charger` / `BYPASS_CHG_VOTER` / `BYPASS_V20_ENABLE`，说明问题是有线旁路主链，转交 `transsion-charger-orchestrator`。
- 若无线旁路已触发，但争议点是 `running_algo` / `support_alg` 的竞选先后，转交 `transsion-dcp-fastcharge-probe`。
- 若无线功率链路本身异常（无线协议、发射端识别、风扇通信），本 skill 仅给出“旁路策略侧可见证据”，再转交相邻无线协议域分析。

## 输出模板

```markdown
## 触发判定
- 命中锚点：<support_magnetism_fan_check / support_magnetism_fan_bypass / magnetism_fan_bypass_aicr>
- 结论：<未触发 / 已触发>

## 失败分层
- A 资格门控：<通过/失败 + 证据>
- B 执行路径：<通过/失败 + 证据>
- C 验收路径：<通过/失败 + 证据>

## 现象验收
- 电压表现：<是否约 5.5V>
- 入电池电流：<是否约 300mA>
- 系统供电：<是否不掉电>

## 转交建议
- 主 skill：<本 skill 或 transsion-charger-orchestrator>
- 次 skill：<transsion-dcp-fastcharge-probe / 其他>
```

## 约束

- 先判定“是否无线旁路场景”，再看协议与算法，不得反过来。
- 不把“无线旁路未触发”误判为“快充协议失败”。
- 无法取得无线侧关键日志时，必须显式标注“证据不足”，禁止过度归因。

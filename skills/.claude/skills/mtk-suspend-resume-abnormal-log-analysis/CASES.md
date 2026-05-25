# 典型案例

## 案例1：按键亮屏无响应

- **现象**：按电源键后屏幕无任何反应
- **关键日志**：无 `PowerManagerService: Waking up` 打印
- **分析**：按键事件未触发PowerManagerService的唤醒流程，问题不在显示链路
- **根因**：按键事件未送达PowerManagerService（非显示问题，需转输入链路排查）

---

## 案例2：亮屏后黑屏

- **现象**：按键后上层显示已亮屏，但屏幕仍为黑
- **关键日志**：
  ```text
  PowerManagerService: Waking up from sleep (uid=1000, reason=WAKE_REASON_POWER_BUTTON)
  ```
  kernel_log中无 `[LCM] lcm_resume` 打印
- **分析**：上层已下发亮屏指令，但DRM/Panel层未执行亮屏流程，链路断在中间层
- **根因**：DRM/Panel层未执行亮屏流程

---

## 案例3：灭屏后背光仍亮

- **现象**：灭屏后屏幕内容消失但背光仍亮
- **关键日志**：
  ```text
  [    xxx] [LCM] lcm_suspend begin
  [    xxx] [LCM] lcm_suspend end
  ```
  kernel_log中无 `lcm_setbacklight_cmdq level = 0`
- **分析**：Panel下电流程正常执行，但灭屏流程未下发关背光指令，背光仍保持亮屏时的值
- **根因**：灭屏流程未下发关背光指令

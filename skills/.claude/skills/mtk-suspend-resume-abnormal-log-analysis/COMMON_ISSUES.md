# 常见问题与根因对照表

| 异常现象 | 关键日志特征 | 根本原因 |
|----------|--------------|----------|
| 按电源键亮屏无响应 | 无 `PowerManagerService: Waking up` 打印 | 按键事件未送达PowerManager，非显示问题 |
| 上层已下发亮屏但屏不亮 | 有 `Waking up`，无 `lcm_resume` | DRM/Panel层未执行亮屏流程 |
| 亮屏后无背光 | 有 `lcm_resume end`，无 `lcm_setbacklight_cmdq` 或 level=0 | 背光未随亮屏一起下发 |
| 灭屏后屏幕未熄灭 | 有 `Going to sleep`，无 `lcm_suspend` | Panel未执行灭屏流程 |
| 唤醒后花屏 | `lcm_resume` 正常，但伴随 `mtk-dsi` 错误 | DSI链路异常，Panel init code下发失败 |

# 常见问题与根因对照表

| 异常现象 | 关键日志特征 | 根本原因 |
|----------|--------------|----------|
| 开机黑屏，无任何显示 | LK日志打印 `islcmfound = 0` | 屏幕未加载，LK阶段屏幕识别失败 |
| 开机黑屏，无任何显示 | LK日志打印 `lcm_epc_read epc_strings = 000000000000000000000000000000000000` | 屏幕EPC读取失败，屏幕硬件未连接或上电异常 |
| 正常显示开机Logo，进内核后黑屏/卡Logo | 内核日志持续打印 `mtk-dsi xxx.dsi: Waiting for bridge or panel driver` | Panel驱动未正常加载，屏幕加载失败 |
| 正常显示开机Logo，进内核后黑屏/卡Logo | 内核日志仅有 `lcm_probe begin`，无对应的 `lcm_probe end` | Panel probe流程执行失败，屏幕加载未完成 |
| LK Logo正常显示，进内核后花屏 | 内核日志打印 `[DISP][E]Cannot find disp pinctrl!` | 屏幕GPIO引脚配置错误 |

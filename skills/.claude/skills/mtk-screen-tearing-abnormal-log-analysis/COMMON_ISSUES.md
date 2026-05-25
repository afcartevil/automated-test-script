# 常见问题与根因对照表

| 异常现象 | 关键日志特征 | 根本原因 |
|----------|--------------|----------|
| 全屏花屏/雪花 | `mtk-dsi ...: underrun` 或 `DSI error` | DSI链路异常，信号/时序错误 |
| 全屏花屏 | `[CMDQ][ERR] task timeout` | CMDQ任务超时，画面未刷新完整 |
| 画面撕裂 | `wait TE timeout` 或无周期TE打印 | TE同步信号异常，上下屏不同步 |
| 帧卡住/残影 | `frame_done timeout` | 一帧未按时完成上屏 |

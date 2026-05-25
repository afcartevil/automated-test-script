# 关键字速查

## SOP官方关键字（不区分大小写）

### 优先关键字

| 关键字 | 适用日志 | 说明 |
|--------|----------|------|
| `tearing` | kernel_log | 画面撕裂相关日志，含TE信号、撕裂检测打印 |
| `vsync` | main_log, kernel_log | VSync垂直同步信号，SurfaceFlinger按此周期提交帧 |
| `te` | kernel_log | TE（Tearing Effect）信号，Panel向DDIC发送的同步信号 |
| `frame_done` | kernel_log | 帧上屏完成信号，MTK DRM CRT回调，标识一帧已完成 |
| `cmdq` | kernel_log | CMDQ（Command Queue）硬件队列，负责任务调度和帧刷新 |

### 显示链路补充关键字

| 关键字 | 适用日志 | 说明 |
|--------|----------|------|
| `drm` | kernel_log | Direct Rendering Manager，显示驱动框架 |
| `dsi` | kernel_log | MIPI DSI接口，Panel与主控之间的显示串行接口 |
| `disp` | kernel_log | Display子系统，含错误日志标签 `[DISP][E]` |
| `lcm` | kernel_log | LCM（液晶模组）驱动 |
| `hwc` | main_log | Hardware Composer，图层合成 |
| `surfaceflinger` | main_log | SurfaceFlinger，Android显示合成服务 |

## 关键日志示例与解读

### 1. DSI 链路错误

```text
[    xxx] mtk-dsi 14014000.dsi: underrun
[    xxx] [DISP][E] DSI error irq status = 0xXXXX
```

**解读**：DSI信号异常、带宽不足或时序配置错误，导致数据未按时传输到Panel，表现为全屏花屏或雪花屏。`underrun`表示DSI FIFO下溢，`irq status`可定位具体错误类型。

### 2. CMDQ 超时

```text
[    xxx] [CMDQ][ERR] task timeout, thread=X
```

**解读**：CMDQ硬件队列中的显示任务未在预期时间内执行完成，画面未正确刷新。常见于CMDQ资源竞争或任务配置错误，表现为全屏花屏或画面卡死。

### 3. TE 信号异常

```text
[    xxx] [DISP][E] wait TE timeout
```

**解读**：驱动等待TE（Tearing Effect）信号超时。TE信号是Panel发给DDIC的同步信号，缺失或不稳定会导致上下屏刷新不同步，表现为画面撕裂。

### 4. Frame done 异常

```text
[    xxx] [DISP][E] frame_done timeout
```

**解读**：一帧未在预期时间内完成上屏（frame done回调超时）。DRM CRT等待该帧的完成信号超时，表现为画面卡顿或上一帧残留（残影）。

# 时序对照（轨名 · 口述 · 改哪里）

非测试清单；**不要求波形图**。

## 口述 → 改哪里

| 用户原话 | 理解 | 优先改 |
|----------|------|--------|
| 开机 **TP INT 半高** | INT 浮空/弱驱，上电未稳 | DWS 上下拉；`IOVDD→RST→delay→INT`；pinctrl sleep；脚位与 dtsi 一致 |
| 下电 **TP 复位晚于 AVDD/vtouch** | 应先拉低 RST 再掉电 | suspend：`reset-gpio` 先于 `regulator_disable`；对齐参考机；与 LCM 下电序 |
| 灭屏后 INT 半高 / 亮屏后才正常 | sleep 默认电平或 resume 延时 | pinctrl sleep；`msleep`、RST 时序 |
| 手势开误掉 VCI/供电；手势关漏电 | 手势/深睡分支混用 | `TRAN_GESTURE_SUSPEND_MODE` vs `TRAN_SUSPEND_MODE`；`fts_gesture_suspend` |

屏轨与 TP RST 同时出现时，先分清 **显示** 还是 **TP 驱动** 再改。

## 轨名索引

| 轨 | 关键字 | 控制层 |
|----|--------|--------|
| OLED DVDD/VCI/VDDIO | `dvdd` `vci` `vddio` | panel dtsi、LCM/LK 表 |
| LCD AVDD/AVEE | `avdd` `avee` | bias、panel/LK |
| TP 电/RST/INT | `vtouch` `reset-gpio` `interrupts` | `*_touch.dtsi`、DWS、vendor `power_*` |

## 其它常见描述

| 描述 | 改法要点 |
|------|----------|
| VCI 灭屏掉太早 | 下电反序；延后 `disable(vci)` |
| DVDD 亮屏晚于 RST | LK 上电表、加 `msleep` |
| TP 与 LCM_RST 打架 | notifier / `resume_by_ddi` 先后 |
| DTS/DWS 不一致 | 三份 DWS 与 dtsi 对齐 |

灭屏链：`DISP blank` → `state_change_machine` → `tran_ts_suspend` → vendor。显示轨多在 panel/LK。日志：`TRAN_GESTURE_SUSPEND_MODE`、`fts_gesture_suspend`、`regulator disable`。

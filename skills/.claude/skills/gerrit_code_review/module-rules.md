# 模块识别规则

`scripts/module_detector.py` 根据 Gerrit 提交的**文件路径**、**标题 (subject)**、**patch 文本**自动推断影响模块。

## 外设驱动模块

| 模块 | 典型关键词 / 路径特征 |
|------|----------------------|
| **LCM** | lcm, lcd, display, panel, mipi_dsi, drm, framebuffer, disp, ddp |
| **TP** | tp, touch, touchscreen, touchpanel, goodix, focaltech, gsl, ft5 |
| **Sensor** | sensor, accelerometer, gyro, als, proximity, magnetometer, hall |
| **Audio** | audio, sound, codec, speaker, mic, afe, asoc, snd |
| **Video** | video, camera, imgsensor, camsys, csi, isp, v4l2 |
| **Key** | gpio-keys, keypad, power_key, volume_key |
| **马达** | vibrator, haptic, motor, vib |
| **Charger** | charger, charging, battery, fuel_gauge, mtk_chg |
| **USB** | usb, typec, type-c, xhci, gadget, usb_phy |

多个外设模块同时命中时，按上表顺序用 `/` 连接，例如：`LCM/TP/Sensor`。

## 通信模块

电话、数据网络、SIM 卡等相关改动识别为 **通信**，典型关键词：

- telephony, phone, ril, modem, radio, sim
- cellular, connectivity, volte, vonr, ims, lte, nr, gsm, cdma
- network stack, netd, carrier, apn, subscription, ccci, mipc

通信模块排在外设模块之后，例如：`LCM/通信`。

## 输出格式

- `modules`: 数组，如 `["LCM", "TP", "通信"]`
- `modules_display`: 字符串，如 `LCM/TP/通信`
- 无匹配时：`modules` 为 `[]`，`modules_display` 为 `未识别`

## 使用位置

1. `review-bundle.json` 顶层及每个 change
2. HTML 报告 **基本信息 → 模块**
3. Terminal summary **Change/topic info → 模块**

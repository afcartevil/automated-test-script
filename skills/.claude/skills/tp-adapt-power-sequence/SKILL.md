---
name: tp-adapt-power-sequence
description: Adapts Transsion/MTK TP/LCM power timing in DTS, three DWS copies, panel/LK, and TP vendor drivers when the user reports a specific rail timing fault (OLED DVDD/VCI/VDDIO, LCD AVDD/AVEE, or TP vtouch/RST/INT). Use when a voltage is wrong order/too early/late on screen-off-on or gesture-on vs gesture-off, and config changes are needed—not for oscilloscope test procedures.
funcType: "AI自动化适配"
category: "驱动"
---

# TP / LCM 时序配置适配

用户已定位 **哪一路 / 哪段时序不对**。本 skill 只做 **配置溯源 → 参考机 diff → 改 DTS / 三处 DWS / LK / panel·TP 驱动**；**不做测试步骤**。

**输入**：**文字描述**即可（示波器结论口述，**不要求、不解析波形图**，勿催用户附图）。缺 **异常轨** 或 **路径（开机/灭屏/手势开/关）** 时只追问这两项。

| 要素 | 示例 |
|------|------|
| 异常轨 | OLED `DVDD/VCI/VDDIO`；LCD `AVDD/AVEE`；TP `vtouch/RST/IOVDD/INT` |
| 口述 | 开机 INT 半高；下电 RST 晚于 AVDD/vtouch；手势开误掉 VCI 等 → [timing-spec.md](timing-spec.md) |
| 参考 | 项目名、OLED/LCD |

## 配置层（按轨）

| 类型 | 轨 | 优先改 |
|------|-----|--------|
| OLED | DVDD/VCI/VDDIO | panel dtsi、LCM/LK 上电表、`msleep` |
| LCD | AVDD/AVEE | bias/panel/LK（≠ TP 节点 `avdd-gpio`） |
| TP | RST/vtouch/INT | `mediatek/tp/*_touch.dtsi`、三处 DWS、`transsion/vendor/*` suspend |

## 流程

1. **搜控制点**：DTS（tp/panel）→ 三处 DWS（与 `tp-adapt-dws-pin` 同步）→ LK `custom/<project>/` → 驱动（panel；TP：`transsion_mtk_platform.c`、`power_source_ctrl`、vendor suspend/resume）。记下 enable/disable 顺序、`msleep`、手势分支是否误关该轨。
2. **对参考机**：同平台量产项目 diff；目标顺序以用户口述或手册为准。
3. **最小改动**：只动异常轨；延时优先抄参考机。手势开勿完整掉电；手势关勿漏 `regulator_disable`；纯 LCM 轨问题改 panel/LK，勿只改 TP。
4. **输出**：异常轨、路径、根因层（DTS/DWS/LK/panel/TP/core）、修改表、一句「烧录后你方复测，无需附图」。

## 关联

- `tp-adapt-dws-pin` · `tp-adapt-gesture-driver` · 口述/轨名对照 [timing-spec.md](timing-spec.md)

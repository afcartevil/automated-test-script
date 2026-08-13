---
name: tp-adapt-super-resolution
description: Guides Transsion/MTK super touch / super-resolution (超级触控/超分效果) DTS debugging—supplier-resolution-X on &touch, display-coords alignment, and vendor driver resolution_multiples reporting. Use when porting 超分、超级触控、supplier-resolution、resolution_multiples、display-coords、触控精度不足、坐标范围异常，或超分效果不生效。
---

# 超级触控 / 超分效果 DTS 调试

核心配置：`&touch` 节点 `supplier-resolution-X = <N>`，经 core 解析为 `resolution_multiples`，vendor 驱动按倍数上报高精度坐标。OpenGrok / 源码细节见 [reference.md](reference.md)。

## 代码实现链路

```text
&touch DTS
  supplier-resolution-0 = <16>
  → tran_parse_dt()                    // transsion_core.c（main）
  → supplier_list.resolution_multiples
  → match_tp_controller()              // supplier 匹配后 controller->supplier 挂接
  → vendor 上报（如 focaltech fts_input_report_b / goodix goodix_ts_report_finger）
  → input 子系统 ABS_MT_POSITION_X/Y（高精度坐标）
```

**与 vendor 节点联动**

```text
focaltech,display-coords = <0 0 (panel_w*N-1) (panel_h*N-1)>
  → input_set_abs_params(ABS_MT_POSITION_*, max)
  → max 须与 supplier-resolution 倍数一致
```

| DTS 属性 | 影响 |
|----------|------|
| `supplier-resolution-X` | 超分倍数 N；缺省或解析失败 → 1（等同无超分） |
| `supplier-num` / `supplier-X` | 须与 vendor IC 匹配，否则 `resolution_multiples` 到不了驱动 |
| `focaltech,display-coords` 等 | ABS 坐标上限 = 面板分辨率 × N |

**上报策略（vendor 差异）**

- Focaltech：向 framework 上报 IC 原始高精度坐标；dmesg 日志里的 `(x,y)` 为 `raw / resolution_multiples`
- Goodix：正常模式同样上报高精度坐标；工模模式会先除 N 再上报

## 前置

- `fc-tp-driver` Pass
- 功能验证：`fc-tp-super-resolution`（`getevent -p` 核对 ABS 0035/0036 max）
- 参考机型：同 TP IC + 同分支 `tran_*_touch.dtsi`（查 OpenGrok `supplier-resolution` in `dts/mediatek/tp`）

## 改 DTS

**1. `&touch`（与 supplier 条目同 index）**

```dts
&touch {
    supplier-num = <1>;
    supplier-0 = "any, focaltech, ft3683g";
    supplier-vendor-0 = "TM";
    supplier-resolution-0 = <16>;   /* 常见 16；以参考机型/IC 规格为准 */
};
```

多 supplier 时按 index 递增：`supplier-resolution-1`、… 与 `supplier-1` 对应。

**2. Vendor IC 子节点 — 对齐 display-coords**

```dts
/* 例：面板 1080×2400，N=16 → max_x≈17279, max_y≈38975 */
focaltech,display-coords = <0 0 17279 38975>;
```

计算公式：`max_x = panel_width × N - 1`，`max_y = panel_height × N - 1`（以参考 dtsi 为准，勿手算硬套）。

## 验证

**1. DTS 解析（开机 dmesg）**

```bash
adb shell dmesg | grep -iE "supplier-resolution|resolution_multiples"
```

期望：`supplier-resolution-0: 16`（或目标值）；触摸时 vendor 日志含 `[resolution_multiples:16]` / `[res:16]`。

**2. 超分 ABS max（推荐脚本）**

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-super-resolution\scripts\check_tp_super_resolution.py" --panel-w 1080 --panel-h 2400 --multiplier 16
```

或手工：`adb shell getevent -p`，在 TP event 中查 `0035`/`0036` 的 max = `panel × N - 1`。

**3. 基础触摸**

- `fc-tp-touch` Pass；边缘/四角无越界、无漂移

## 故障分流

| 现象 | 排查 |
|------|------|
| 超分完全不生效 | `&touch` 缺 `supplier-resolution-X`（默认 1）；或 supplier 未匹配（查 `match supplier` / `no supplier matched`） |
| dmesg 倍数为 1 | DTS 未合入/属性名拼写错（`supplier-resolution-0` 非 `supplier-resolution`）；index 与 `supplier-0` 不对应 |
| 触摸偏移/边缘越界 | `display-coords` max 与 `supplier-resolution` 不一致；参考同分辨率机型 |
| 仅工模坐标错 | Goodix 工模会除 N 上报，核对 `TRAN_FACTORY_MODE` 分支；Focaltech 工模亦会除 N |
| 精度无感但范围对 | 上层游戏/系统是否消费高精度坐标；对比参考机 getevent 步进 |
| 驱动 probe 失败 | `tp-adapt-bringup` |

## 关联

`tp-adapt-bringup` · `tp-adapt-smart-sampling` · `tool-opengrok` · `fc-tp-super-resolution` · `fc-tp-touch`

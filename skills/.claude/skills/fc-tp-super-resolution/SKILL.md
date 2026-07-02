---
name: fc-tp-super-resolution
description: Func-check skill for TP super-resolution import via adb getevent -p—ABS 0035/0036 max must equal panel_resolution × N - 1. Use when func-check needs 超分导入验证、超级触控、supplier-resolution、getevent ABS max、0035 0036、display-coords 是否生效。
---

# FC: TP 超分效果导入检查

通过 `getevent -p` 找到 TP 的 input event，读取 **ABS 0035（X）/ 0036（Y）** 的 `max`。超分导入成功后：

```text
max_x = panel_width  × N - 1
max_y = panel_height × N - 1
```

例：1080×2400、N=16 → `max_x=17279`，`max_y=38399`。

## 前置条件

- 设备已通过 `adb devices` 连接
- `fc-tp-driver` Pass（TP 驱动已 probe）

## 检查步骤

### 方式 A：脚本（推荐）

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-super-resolution\scripts\check_tp_super_resolution.py"
```

严格核对（参考机型已知面板与倍数）：

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-super-resolution\scripts\check_tp_super_resolution.py" --panel-w 1080 --panel-h 2400 --multiplier 16
```

或直接写期望 max：

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-super-resolution\scripts\check_tp_super_resolution.py" --expect-max-x 17279 --expect-max-y 38399
```

退出码 `0` = Pass，`1` = Fail。

### 方式 B：手工 adb

```bash
adb shell getevent -p
```

在 TP 设备块（常见 `mtk-tpd` / `focaltech` / `goodix` 等 name）中查找：

```text
ABS (0003): ...
                0035  : value 0, min 0, max 17279, ...
                0036  : value 0, min 0, max 38399, ...
```

| 字段 | 含义 |
|------|------|
| `0035` | `ABS_MT_POSITION_X`，max = 超分后 X 上限 |
| `0036` | `ABS_MT_POSITION_Y`，max = 超分后 Y 上限 |

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass（严格） | 找到 TP event；`max_x`/`max_y` 与 `panel × N - 1` 或 `--expect-max-*` 一致 |
| Pass（快速，无 panel 参数） | 找到 TP event；`max_x > 1079` 且 `max_y > 2399`（明显高于 1× 1080p） |
| Fail | 找不到含 0035/0036 的 TP 节点；或 max 仍为 1× 屏分辨率量级（如 1079/2399）；或与期望值不符 |

**未导入超分（N=1）特征**：1080×2400 屏 max 约为 `1079` / `2399`，不会到 `17279` / `38399`。

## 输出格式

```
## 功能检查：TP 超分 ABS max

**skill**: fc-tp-super-resolution
**结果**: Pass / Fail

| 检查项 | 期望 | 实际 | Pass/Fail |
|--------|------|------|-----------|
| event 节点 | 含 0035/0036 | /dev/input/eventN | ... |
| ABS 0035 max | panel_w×N-1 | ... | ... |
| ABS 0036 max | panel_h×N-1 | ... | ... |

### 下一步
（Pass：结束；Fail：见 Fail 后续）
```

## Fail 后续

- `tp-adapt-super-resolution`：核对 `&touch` 的 `supplier-resolution-X`、`focaltech,display-coords`（或 vendor 等价属性）
- `fc-tp-driver`：驱动未加载时先排查 probe
- `fc-tp-touch`：max 正确但仍无坐标上报

## Harness 路由

- func-check：`func-check-registry.md` → `fc-tp-super-resolution`
- adaptation-debug：`routing-table.md` TP 区 → 先 `fc-tp-super-resolution`，Fail → `tp-adapt-super-resolution`

---
name: fc-tp-touch-master
description: Func-check skill for Transsion Touch Master (区域操作大师) import via adb getprop ro.tr_game.touch_master.model. Use when func-check needs 区域操作大师、touch_master.model 是否导入。
---

# FC: 区域操作大师导入检查

通过 `getprop` 核对 ODM 属性是否已导入。

## 前置条件

- 设备已通过 `adb devices` 连接

## 检查属性

| 属性 | 取值 | 含义 |
|------|------|------|
| `ro.tr_game.touch_master.model` | `0` | 不支持 / 未导入 |
| | `1` | 支持精简版全量区域操作大师 |
| | `2` | 支持全量版区域操作大师 |

**Pass**：取值为 `1` 或 `2`。  
**Fail**：为空、`0`、或非 `0/1/2` 的非法值。

## 检查步骤

### 方式 A：脚本（推荐）

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-touch-master\scripts\check_tp_touch_master.py"
```

严格核对指定版本：

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-touch-master\scripts\check_tp_touch_master.py" --expect-model 2
```

退出码 `0` = Pass，`1` = Fail。

### 方式 B：手工 adb

```bash
adb shell getprop ro.tr_game.touch_master.model
```

## Pass / Fail

| 结果 | 条件 |
|------|------|
| Pass | `model` 为 `1` 或 `2`（或与 `--expect-model` 一致） |
| Fail | `model` 为 `0`、空、或非法值 |

## 输出格式

```
## 功能检查：区域操作大师导入

**skill**: fc-tp-touch-master
**结果**: Pass / Fail
**model**: 0 / 1 / 2
**版本**: 未导入 / 精简版 / 全量版

| 检查项 | 期望 | 实际 | Pass/Fail |
|--------|------|------|-----------|
| ro.tr_game.touch_master.model | 1 或 2 | ... | ... |

### 下一步
（Pass：结束；Fail：见 Fail 后续）
```

## Fail 后续

- 核对 ODM `PRODUCT_*_PROPERTIES` / 参考机 `getprop` 是否打包 `ro.tr_game.touch_master.model`

## Harness 路由

- func-check：`func-check-registry.md` → `fc-tp-touch-master`
- adaptation-debug：`routing-table.md` TP 区 → 先 `fc-tp-touch-master`，Fail → ODM 属性打包核对

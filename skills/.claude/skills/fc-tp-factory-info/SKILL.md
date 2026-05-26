---
name: fc-tp-factory-info
description: Func-check skill for Transsion/MTK factory midtest TP IC name, module vendor string, and firmware/BV display via sysfs (tp_vendor, tp_firmware_version, tp_name). Use when func-check needs 工模 TP IC/固件信息是否正确、midtest 触摸信息页 UNKNOWN/空白/版本不符、或 port 后核对 supplier 与固件串。
funcType: "AI自动化适配"
category: "驱动"
---

# FC: 工模 TP IC / 固件信息显示检查

核对工厂测试（midtest / tranfacmode）信息页所依赖的 **sysfs 原文** 是否完整、格式合理，并与工单/BOM 期望（若提供）一致。只读检查，不改代码。

## 前置条件

- `adb devices` 已连接
- TP 驱动已加载（建议先过 `fc-tp-driver` 或确认 `lsmod | grep -i tran` 有模块）
- 折叠机需确认当前查看的是 **主屏还是副屏** 信息页

## 快速检查（推荐）

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-factory-info\scripts\check_tp_factory_info.py"
```

可选期望子串（大小写不敏感）：

```powershell
python "$env:USERPROFILE\.cursor\skills\func-check\fc-tp-factory-info\scripts\check_tp_factory_info.py" --expect-vendor TM_GOODIX_01 --expect-fw 0x
```

见 [../RUN.md](../RUN.md)。

## 手工步骤

### 1. 定位真实 sysfs 路径

勿只读 `mtk-tpd` symlink；用 find 找全部触摸信息节点：

```text
adb shell readlink -f /sys/devices/platform/mtk-tpd 2>/dev/null
adb shell cat /sys/devices/platform/mtk-tpd/tp_vendor
adb shell cat /sys/devices/platform/mtk-tpd/tp_firmware_version
# 若 mtk-tpd 为 symlink，以上路径会解析到真实 pdev（如 odm:touch）
adb shell 'find /sys/devices/platform /sys/bus/platform/devices -maxdepth 5 -name tp_vendor 2>/dev/null'
```

记录 **工厂 APK 实际使用的 pdev 路径**（常与 `readlink` 结果一致）。

### 2. 读取三字段原文

对步骤 1 中**每个**含 `tp_vendor` 的目录执行：

```text
adb shell cat <path>/tp_vendor
adb shell wc -c <path>/tp_firmware_version
adb shell cat <path>/tp_firmware_version
adb shell cat <path>/tp_name
```

`tp_name` 仅折叠等项目存在，无则 N/A。

### 3. 格式与内容判定

对照 [expected-format.md](expected-format.md)：

| 检查项 | Pass | Fail |
|--------|------|------|
| `tp_vendor` | 非空、非 `UNKNOWN`；形如 `模组厂_IC代号_序号`（含 `_`） | 空 / `UNKNOWN` / 仅乱码 |
| `tp_firmware_version` | `wc -c` > 0；含 `0x` 与 `bv:`（Goodix 可为 `0x*_0x*,bv:0x*_0x*`） | 长度为 0 / 全 `0x00` / 节点不存在 |
| 与 BOM 一致（用户提供时期望） | vendor 含期望 IC 串；fw 含期望版本或 BV 片段 | 模组名或 BV 与工单不符 |
| 主副屏（折叠） | 信息页所在屏与 `readlink`/`tp_name` 一致 | 外屏页读到主屏 sysfs |

**说明**：`TRAN_FACTORY_MODE` 下固件串可能 **不含** Algo/Func 行，与常温工程模式不同，属正常分支，不单独判 Fail。

### 4. 内核佐证（Fail 时）

```text
adb shell dmesg | grep -iE "tran_touch|match supplier|vendor_name|controller_init_state|fw:0x|bv:0x" | tail -40
```

关注：`main tp init failed`、`UNKNOWN` 前是否 `controller_init_state` 未就绪、`match supplier` 失败。

### 5. 工模 UI（可选）

进入 **工厂测试 → 触摸/TP 信息**（各项目菜单名可能不同），目视 IC 名、模组厂、固件/BV 是否与步骤 2  sysfs **一致**。UI 空白但 sysfs 正常 → 上层 APK/权限；sysfs 已 Fail → 先修内核/DTS。

## Pass / Fail

| 结果 | 条件 |
|------|------|
| **Pass** | 目标屏路径下 `tp_vendor` 合法且非 UNKNOWN；`tp_firmware_version` 非空且格式符合 expected-format；若提供 `--expect-*` 则匹配 |
| **Fail** | 任一必查项不满足，或 UI 与 sysfs 明显不一致且无合理解释 |

## 输出格式

```
## 功能检查：工模 TP IC / 固件信息

**skill**: fc-tp-factory-info
**结果**: Pass / Fail

| 路径 | tp_vendor | tp_firmware_version (字节数) | 判定 |
|------|-----------|------------------------------|------|
| ... | ... | ... | Pass/Fail |

### readlink / tp_name
...

### 与 BOM 对比（如有）
...

### 下一步
```

## Fail 后续

- `tp-adapt-factory-sysfs`（DTS supplier、ops 版本钩子、双 platform 冲突）
- `tp-adapt-engineering-sysfs`（节点未创建、init 时序、symlink 指错屏）
- `fc-tp-selinux`（`Permission denied`）
- `fc-tp-driver`（驱动未 probe）

## 与其它 skill 分工

| skill | 职责 |
|-------|------|
| **本 skill** | 工模信息 **是否正确显示**（func-check） |
| `fc-tp-sysfs` | 快速可读性检查，不校验 vendor 格式与 BOM |
| `fc-tp-factory` | 容值 `/proc/tp_panel_test` |
| `tp-adapt-factory-sysfs` | 源码侧修复与根因分析 |

## 附加资源

- 字段格式与 Goodix/折叠说明：[expected-format.md](expected-format.md)

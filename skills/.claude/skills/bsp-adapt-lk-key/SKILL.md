---
name: bsp-adapt-lk-key
description: >-
  Guides debugging Mediatek LK2 keypad paths so hardware combos map correctly to RECOVERY_BOOT (typically Power + Volume Up) and FACTORY_BOOT / shutdown factory mode (typically Power + Volume Down),
  including Tran macros TRAN_RECOVERY_KEY_CUSTOM and TRAN_FACTORY_KEY_CUSTOM, DTS mediatek,kp properties, and boot_mode_check ordering in mt_boot.
  Use when troubleshooting lk2 bootloader combo keys, recovery entry, factory/engineering mode keys, keypad DTS on MTK Tran branches, or macros in target/*/rules.mk versus project *.mk.
disable-model-invocation: true
funcType: "AI自动化适配"
category: "驱动"
---

# MTK LK2：组合键进入 Recovery / 关机工模（FACTORY）

面向仓库路径：`vendor/mediatek/proprietary/bootable/bootloader/lk2`，重点关注 `platform/mediatek/common/keypad` 与 `app/mt_boot`。

## 行为与术语（对齐代码）

- **RECOVERY_BOOT**：`recovery_check()` 中在 `WITH_PLATFORM_MEDIATEK_COMMON_KEYPAD` 下通过 `detect_key(RECOVERY_KEY)` 判断；另有 WDT / misc 等 recovery 路径。
- **FACTORY_BOOT（关机工模等）**：`factory_key_check()` 中通过 `detect_key(FACTORY_KEY)`，且受 `tran_is_factory_forbidden()` 等业务限制。
- **物理组合键**：产品侧常见为 **Power + VolUp → Recovery**、**Power + VolDown → Factory**。LK 层 `detect_key()` 多数实现为**单独检测某个“第二键”位**（VolUp/VolDown 在 KPD 矩阵或 PMIC 映射中的列），**是否在 PL 或其它阶段还要求按住 Power** 以具体平台与上层流程为准；调试时需同时核对 **Preloader/boot_mode** 与本文 LK 路径。

## 1. 先定位宏在哪个 makefile（target 还是 project）

不同分支习惯不同：

1. **优先查** `lk2/target/<TARGET_NAME>/rules.mk`（例如 `TRAN_FACTORY_KEY_CUSTOM := yes`、`TRAN_RECOVERY_KEY_CUSTOM := yes`）。
2. **再查** `lk2/project/<project>.mk` 是否重复或覆盖同一变量（当前树里也可能为空，以分支为准）。
3. ** keypad 编译开关**：`lk2/platform/mediatek/common/keypad/rules.mk`  
   - `TRAN_FACTORY_KEY_CUSTOM=yes` → `GLOBAL_CFLAGS += -DTRAN_FACTORY_KEY_CUSTOM`  
   - `TRAN_RECOVERY_KEY_CUSTOM=yes` → `GLOBAL_CFLAGS += -DTRAN_RECOVERY_KEY_CUSTOM`

若宏与 DTS / `detect_key` 分支不一致，会出现“只见电源键有效、音量组合无效”或读错矩阵位等现象。

## 2. DTS：`mediatek,kp` 与音量键映射

实现文件：`platform/mediatek/common/keypad/mtk_key.c`。

关键属性（节点 compatible：`mediatek,kp`）：

| 属性 | 作用 |
|------|------|
| `mediatek,hw-recovery-key` | KPD 硬件编号，映射到 `RECOVERY_KEY` / `BOOT_MENU_KEY` / `MENU_SELECT_KEY` |
| `mediatek,hw-factory-key` | KPD 硬件编号，映射到 `FACTORY_KEY` / `MENU_OK_KEY` |
| `mediatek,factory-key-type` | `KPD_IP_KEY`（读 `KP_MEM`）、`GPIO_KEY`、`PMIC_HOME2_KEY` 等 |
| `mediatek,gpio_index`（代码中为 `mediatek,gpio_key_index`） | GPIO 音量键时使用 |

默认 fallback（无 DTS）：recovery 倾向走 PMIC rst/home 语义；需以实际 DTS 为准。

## 3. `TRAN_*_KEY_CUSTOM` 对检测路径的影响（必查）

同一文件 `detect_key(enum key_index index)`：

- **`TRAN_FACTORY_KEY_CUSTOM`**：`FACTORY_KEY` **固定走** `is_pmic_key_pressed(HOME_KEY)`，**不再走** `factory-key-type` 的 KPD/GPIO 分支。若硬件上关机工模键是 **VolDown（矩阵键）**，打开此宏却未把 PMIC HOME 接到该键，会失败。
- **`TRAN_RECOVERY_KEY_CUSTOM`**：`RECOVERY_KEY` **固定走** KPD `KP_MEM1` 位扫描（与 `key_mapping[RECOVERY_KEY]` 中的 hw key 编号一致），与默认分支里按 `factory-key-type` 的路径分离。

调试时：**宏开关 + DTS hw key 编号 + factory-key-type** 三者必须自洽。

## 4. Boot 模式裁决顺序（为何“只会进 Recovery 不进工模”等）

文件：`app/mt_boot/boot_mode.c` → `boot_mode_check()`。

要点：

1. `pl_mode_check()`（来自 `platform_get_boot_mode()` / PL 侧模式）优先。
2. **`recovery_check()` 早于 `factory_key_check()`**。若两把键映射冲突或粘连，可能出现只看到一种模式。
3. **`bootmenu_check()`**：当前 Tran 改动中对 `detect_key(BOOT_MENU_KEY)` **直接返回 false**，等于禁用键盘进入 boot menu（避免误入 fastboot 等）；与 recovery/factory 并列时需知情。
4. **工厂禁用**：`factory_key_check()` 含 `!tran_is_factory_forbidden()`，业务禁止进工厂时会表现为组合键“无效”。
5. **Fastboot / PayJoy**：与 fastboot 相关的禁用逻辑在其它分支；若怀疑误入 fastboot，查 `boot_ui.c` / PayJoy 条件。

## 5. 日志与 Trace（推荐调试步骤）

1. **临时提高 trace**：`mtk_key.c`、`boot_mode.c` 中已有 `LOCAL_TRACE` / `LTRACEF`。编译带 UART log 的 lk，开机按住组合键，查看是否打印  
   `detect RECOVERY_KEY`、`boot_mode = …`、`key=%d index=%d`、`KP_STA` / `KP_MEM1` 等。
2. **对照打印**：确认 `init_key_mapping()` 之后 `key_mapping[RECOVERY_KEY]` 与 `key_mapping[FACTORY_KEY]` 是否为预期的矩阵索引。
3. **PMIC 路径**：若 factory 分支走 `HOME_KEY`，核对 PMIC key 驱动（如 `mt6363_keys.c` 等平台文件）是否上报按下。
4. **矩阵路径**：VolUp/VolDown 关注 `din = REG16(KP_MEM1 + ...)` 每一位是否为低有效（代码里 `!din` 表示按下）。

## 6. 常见根因清单

1. **`target/rules.mk` 未打开 `TRAN_*` 或与伙伴分支不一致**，导致 `detect_key` 路径与硬件不匹配。
2. **DTS `mediatek,hw-recovery-key` / `mediatek,hw-factory-key` 填错列**，VolUp/VolDown 对调或与参考机不一致。
3. **`TRAN_FACTORY_KEY_CUSTOM` 开启但 factory 实际为矩阵键**，PMIC HOME 无连接。
4. **`tran_is_factory_forbidden()` 为 true** 或其它安全策略禁止工厂模式。
5. **仅进 PL 阶段模式**：需同时查 Preloader / `platform_get_boot_mode()` 传入值，不单看 LK。

## 7. 涉及的主要源文件索引

| 路径 | 说明 |
|------|------|
| `platform/mediatek/common/keypad/mtk_key.c` | DTS 解析、`init_key_mapping`、`detect_key` |
| `platform/mediatek/common/keypad/rules.mk` | `TRAN_*` → `-D` |
| `platform/mediatek/common/keypad/include/mtk_key.h` | `enum key_index`、`factory_key_type` |
| `app/mt_boot/boot_mode.c` | `recovery_check`、`factory_key_check`、`boot_mode_check` 顺序 |
| `app/mt_boot/boot_ui.c` | Boot menu 音量选择、`MENU_OK_KEY` / `PMIC_RST_KEY` |
| `target/*/rules.mk` | 多数 Tran 项目宏定义入口 |

按上述顺序逐项核对，可系统化保障 **Power + VolUp / VolDown** 在 LK 侧映射到 **Recovery** 与 **关机工模（FACTORY）**。

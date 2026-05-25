# DRV_Audio_Adapt 使用手册

一句话：把这个 SKILL 当成一位「按你给的 SOP 帮你做 P1 移植，每完成一个 repo 就停下来跟你对账」的助理。

## 1. 什么时候用

适用：**MTK 平台** Audio P1 升级移植（bringup）。两种场景：

- `vnd12 非榫卯 → vnd16 榫卯`
- `vnd14 非榫卯 → vnd14 榫卯`

不适用：QCOM/Unisoc 平台；上线后业务 bug 诊断。

## 2. 怎么触发

直接在 Cursor 聊天里说一句包含触发词的话即可，例如：

- "帮我做 cm7w 项目的 audio bringup"
- "做 P1 移植，从 vnd14 非榫卯升到 vnd14 榫卯"
- "audio bringup：升级前 `Z:/xxx/base`、升级后 `Z:/xxx/base_sunmao`、`vnd14_to_vnd14`、编译选项 `cm7w_h616_64_bsp`、配置表见附图"

触发词命中后，SKILL 会先按 [SKILL.md](SKILL.md) 走，然后进入阶段 0。

## 3. 准备 5 项输入（缺啥 SKILL 会主动问你）

| 项 | 例子 |
| --- | --- |
| `base_code` 升级前 vnd 绝对路径 | `Z:/path/to/pre_upgrade` |
| `base_code_sunmao` 升级后 vnd 绝对路径 | `Z:/path/to/post_upgrade` |
| `scenario` 升级场景 | `vnd12_to_vnd16` 或 `vnd14_to_vnd14` |
| `project_compile_option` 升级前编译选项 | `cm7w_h616_64_bsp` 或截图 |
| `sw_config_table` 软件配置表 | 截图或文本，包含 PA 型号 / SPK 个数 / SPK PATH / MIC 个数 / `PHONE_MIC_MODE` / `HEADSET_MIC_MODE` / 是否 TypeC |

> 5 项不强制一次性给全，但 **越全 SKILL 越少打断你**。

## 4. 执行模式（默认是分阶段执行）

| 模式 | 行为 | 适用 |
| --- | --- | --- |
| `execute_phased`（默认） | 真改文件，每个阶段末停下来给摘要，你确认才继续 | 真的要做这次 P1 |
| `audit_only` | 完全不写文件，只产差异/缺口报告 | leader review、摸底、卡口检查 |

切换方式：直接说一句话 —— "先 audit 跑一遍" / "按 phased 执行"。

## 5. 6 个阶段一目了然

```
阶段 0: 输入采集 + 变量推导  →  给你一张「变量确认表」
阶段 1: projects repo        →  ProjectConfig.mk / PA / aurisys / audio_device.xml / audiotest
阶段 2: kernel DTS           →  PA 节点 / tran_audio_controller / typec switch
阶段 3: preloader DWS        →  GPIO 三件套
阶段 4: tools/dct DWS        →  同上
阶段 5: custom DWS + factory.ini
阶段 6: 验收交付             →  改动汇总 + 未决项清单 + 验证命令
```

每个阶段末尾都会给你 **三栏摘要**：

| 项 | 含义 |
| --- | --- |
| 本阶段改了什么 | 列文件 + 关键改动 |
| 还差什么 | 缺源文件 / 配置表未给的字段 / 待你拍板的歧义 |
| 是否继续 | 默认问你能否进下一阶段 |

## 6. 当 SKILL 问你问题时

SKILL 在这 5 类情况下 **一定** 会停下来问，请直接回答：

1. PA 文件的所有候选源都不存在。
2. 升级前 `ProjectConfig.mk` 没这个 macro，软件配置表也没给。
3. DTS 的 GPIO 与 DWS 互相缺失。
4. `audio_device.xml` diff 涉及节点删除/改名。
5. 软件配置表截图 OCR 不清楚。

回答方式越具体越好，例：

- "用升级前文件那个值"
- "配置表上 PA 型号是 AW87xxx，配 yes"
- "缺的文件让我从中央库去拿，先 skip"
- "节点改名不要动，跳出 SOP"

## 7. 红线提醒（你必须人工跟进的事）

- **vnd12 → vnd16 的 PA 算法 so 不能复制旧的**（ARSI API 1.6 → 1.9 不兼容）。SKILL 会在阶段 1 提醒你并在阶段 6 把它列为强制未决项，你需要：
  1. 找 FAE 索取升级后的 PA so。
  2. 通知 AFE：升级前/后 ARSI API 版本、PA 算法库版本、集成方式（AP / ADSP HIFI / ADSP RV55）、PA 参数能否复用。
- **aurisys xml 中的 `/vendor/etc/audio_param` 必须改成 `/odm/etc/vconfig/audio/audio_param`**（SKILL 会自动做并 Grep 校验）。
- **`audio_policy_configuration.xml` / `audio_effects.xml` 等 SKILL 不主动改动**。需要改时 SKILL 会告诉你，由你决定。
- **SKILL 不替你 `git commit` / `repo upload`**，只给"建议改动 + 验证命令"。

## 8. 常见对话示例

切模式：

> "切到 audit_only" / "切回 execute_phased"

跳过某个阶段：

> "阶段 3 我自己来，直接进阶段 4"（SKILL 会跳过 §3 但会提示你阶段 3 的预计改动清单）

回到某阶段重做：

> "阶段 1 的 §1.6 audio_device.xml 重做一遍，刚才 diff 漏了一个 mixPort"

确认继续：

> "继续" / "下一阶段" / "OK"

终止：

> "停一下" / "结束"

## 9. 验证（阶段 6 SKILL 会给你这套命令清单）

首次起机三连：

```bash
adb shell dumpsys media.audio_flinger | grep -E 'mixer|record'
adb shell dmesg -T | grep -iE 'tran_audio_controller|aw87|fsm|oca|hl1280|sliptswitch'
adb shell tinycap /sdcard/cap.wav -D 0 -d 0 -c 2 -r 48000 -t 5 && adb pull /sdcard/cap.wav
```

完整清单见 [references/verify-commands.md](references/verify-commands.md)。

## 10. 文件结构（碰到要排错时再看）

```
DRV_Audio_Adapt/
├── SKILL.md          模型入口（你一般不需要改）
├── USAGE.md          本文件
├── README.md         目录索引
├── workflows/        6 个阶段执行手册
└── references/       事实查找表（变量 / 宏控 / PA 文件矩阵 / DTS / DWS / factory.ini / 验证命令）
```
碰到 SKILL 行为不符合预期时，最常需要核对的是 `references/` 下对应表格 —— 那里写的是"事实"，SKILL 据此决策。


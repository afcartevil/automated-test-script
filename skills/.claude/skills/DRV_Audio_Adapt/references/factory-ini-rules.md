# 工模 `factory.ini` 配置规则

阶段 5 的一部分，目标文件：`{base_code_sunmao}/vendor/mediatek/proprietary/custom/{project_name_sunmao}/factory/factory.ini`。

## 1. MenuItem 注释规则

对下列五行，若 **没有** 行首注释符（ `//` ），把它们注释掉：

| 待注释行 | 含义 |
| --- | --- |
| `MenuItem=Loopback(A);` | 工模 Loopback 入口 |
| `MenuItem=Ringtone(A);` | 工模 Ringtone 入口 |
| `MenuItem=WavePlayback(A);` | 工模 WavePlayback 入口 |
| `MenuItem=Speaker Rdc Calibration(A);` | SPK Rdc 校准入口 |
| `MenuItem=Speaker OC Test(A);` | SPK 过流测试入口 |

操作细节：

- 必须先 Read 目标文件，确认上述行是否已有注释符；已注释则跳过。
- 注释采用"在行首加一个 `//`"的最小改动方式，保持后段不变。
- 不要删除这些行——只注释，便于将来开放工模。

## 2. `Audio.Mic.Sets`

| 麦克风个数 | 期望值 |
| --- | --- |
| 单麦 | `Audio.Mic.Sets=1` |
| 双麦（或更多） | `Audio.Mic.Sets=1,2` |

> 来源：软件配置表 / `MTK_AUDIO_NUMBER_OF_MIC`。两者冲突时以软件配置表为准并提示开发者。

## 3. `Audio.Input.TypecHeadset`

| 耳机接口 | 处理 |
| --- | --- |
| TypeC | `Audio.Input.TypecHeadset=1` 必须存在且未注释 |
| 3.5mm | `Audio.Input.TypecHeadset=1` 行必须存在但 **被注释**（或不存在） |

操作细节：

- TypeC：
  - 文件中无此行 → 在AUDIO部分代码处的合理位置追加 `Audio.Input.TypecHeadset=1`。
  - 文件中有此行但被注释 → 去掉行首注释符。
- 3.5mm：
  - 文件中有此行且未注释 → 在行首加注释符。
  - 文件中无此行 → 不补。

## 4. 自检（阶段 5 完成后）

- 5 个 MenuItem 行：全部已注释（或本身就是注释）。
- `Audio.Mic.Sets`：与 mic 个数一致。
- `Audio.Input.TypecHeadset`：与 [projectconfig-macros.md §1.6](projectconfig-macros.md) 中的 `TRAN_AUDIO_TYPEC_SUPPORT` 自洽。

## 5. 跳出条款

- 文件中存在 5 个 MenuItem 行的"变体"（如带额外参数、不同大小写、写法略不同）→ 不要自作主张匹配，问开发者哪几行需要处理。
- `Audio.Mic.Sets` 在文件中出现多次且取值不同 → 问开发者，不要随便选其一改。

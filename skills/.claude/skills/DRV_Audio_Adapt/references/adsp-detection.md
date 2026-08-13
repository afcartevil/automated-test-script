# ADSP 类型检测 & `aurisys_config_rv/hifi3.xml` 选型

## 1. 检测目标

判定平台 ADSP 三态：

- `no_adsp`：平台不含 ADSP
- `rv55`：平台含 ADSP，类型为 RV55
- `hifi`：平台含 ADSP，类型为 HIFI（默认非 RV55）

## 2. 检测数据源

**仅读取升级前平台 DTS**（变量 `pre_platform_dts_path`，按 [variables.md §5.3](variables.md) 在阶段 0 独立解析）。

- 与 **升级前项目 DTS**（`pre_project_dts_path`，§5.2）是**不同文件**——禁止用 `{project_name_sunmao}.dts` 做 ADSP 检测。
- 升级后平台 DTS（`post_platform_dts_path`）在本次 bringup 完成前不可信，**不作为** ADSP 检测源。

阶段 1 执行 ADSP 检测前，必须已持有阶段 0 确认的 `pre_platform_dts_path`；若未解析 → 先回到阶段 0 执行 §5.3，不得临时用项目 DTS 或升级后路径顶替。

> 平台 DTS 文件名必须为 `{platform_name}.dts`（如 `mt6878.dts`），比对时 **不区分大小写**。

## 3. 检测规则（按顺序）

1. 在平台 DTS 文件中 Grep `snd_audio_dsp:`：
  - **未命中** → `no_adsp`。本步骤直接结束，**不需要** 移植 `aurisys_config_rv.xml` / `aurisys_config_hifi3.xml`。
  - **命中** → 进入步骤 2。
2. 在同一文件中 Grep `mtk-dsp-type`：
  - 命中且值为 `RV55`→ `rv55`。
  - 其余情况（命中但值不是 `RV55`、或未命中）→ `hifi`。
3. `mtk-dsp-type` 命中但值 **既不是 `RV55` 也不是常见 HIFI 标识（`HIFI3` / 空）** → 跳出 SOP，问开发者。

## 4. 选型 → 文件


| 检测结果      | 需要移植的 xml                                                      |
| --------- | -------------------------------------------------------------- |
| `no_adsp` | 跳过 ADSP 相关 的`aurisys_config_rv.xml/aurisys_config_hifi3.xml`移植 |
| `rv55`    | 仅移植 `aurisys_config_rv.xml`                                    |
| `hifi`    | 仅移植 `aurisys_config_hifi3.xml`                                 |


## 4.1 移植前的清空（强制）

无论 §3 检测结果为 `no_adsp` / `rv55` / `hifi`，**移植开始前** 必须把升级后侧两份目标文件全部删除（任一存在则删）：

- `{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/audio/aurisys_config_rv.xml`
- `{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/audio/aurisys_config_hifi3.xml`

之后按 §3 检测结果决定是否注入新版本（`rv55` 注入 rv、`hifi` 注入 hifi3、`no_adsp` 都不注入）。这样可以避免"升级后侧从平台基线带来的旧模板"与本轮项目层版本共存的歧义。

## 5. 文件源 / 目 路径

### 5.1 `vnd14_to_vnd14`


| 文件                         | 升级前 候选源（取其一）                                                                                                                                                                                                                             | 升级后目标                                                                                               |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `aurisys_config_rv.xml`    | `{base_code}/device/transsion/{project_name_sunmao}/audio/aurisys_config_rv.xml` `{base_code}/device/mediatek/{platform_name}/aurisys_config_rv.xml`                                                                                     | `{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/audio/aurisys_config_rv.xml`    |
| `aurisys_config_hifi3.xml` | `{base_code}/device/transsion/{project_name_sunmao}/aurisys_config_hifi3.xml` `{base_code}/device/transsion/{project_name_sunmao}/audio/aurisys_config_hifi3.xml` `{base_code}/device/mediatek/{platform_name}/aurisys_config_hifi3.xml` | `{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/audio/aurisys_config_hifi3.xml` |


### 5.2 `vnd12_to_vnd16`

SOP 未提供 vnd12 侧的 rv / hifi3 xml 源路径；进入本场景时直接跳出 SOP：

- 必须告知开发者"vnd12 → vnd16 的 `aurisys_config_rv/hifi3.xml` SOP 未覆盖"。
- 建议询问 AFE 是否随 PA so 一并提供升级后版本，或参考 `examples/reference-submissions.md` 中相近平台的提交。

## 6. 移植后强制改写

无论 rv 还是 hifi3，移植到升级后目标路径后必须执行 [pa-file-matrix.md §6](pa-file-matrix.md) 的路径改写（与 PA 的 `aurisys_config.xml` **同一规则**）：

```
/vendor/etc/  →  /odm/etc/vconfig/audio/
```

例：`/vendor/etc/audio_param` → `/odm/etc/vconfig/audio/audio_param`。不得残留 `"/vendor/etc/`；不得修改 `/vendor/lib`、`/vendor/lib64`。

## 7. 同名冲突处理

若升级前两个候选源都存在且内容不同：

- 默认采用 **项目层**（`device/transsion/{project_name_sunmao}/...`）覆盖 **平台层**（`device/mediatek/{platform_name}/...`）的策略——项目层 win。
- 必须在阶段 1 摘要里显式提示开发者已发生项目/平台层冲突，附两份文件的相对路径。


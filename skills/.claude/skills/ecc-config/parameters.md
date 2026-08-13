# 通用输入参数（MTK + 展锐 + 高通）

## 用户原文说明

用户提供 ECC 仓库路径，并传入以下参数（三平台共用）：

- **号码**（必填）
- **mccmnc**：只有3位则表示不限定mnc，为空则表示公共紧急号码修改
- **有卡**：表示有卡情况下是真紧急、假紧急还是非紧急号码，不填则表示不更改
- **无卡**：表示无卡情况下是不是紧急号码（无卡不能配置假紧急，只能配置真紧急），不填则表示不更改
- **语音台（category）**：为空则表示不更改或配置成0（新增紧急号码的情况）
- **英文名**：不填则表示不更改
- **当地语言**：要修改的语言，没说明则需根据mcc自行查找国家官方语言
- **当地语言名**：要改成的名字
- 一次可同时传入多个号码进行修改
- 一个号码可同时修改多个语言名称（需指定语言）
- 可选提供 **Jira 单号 / URL**：经 **harness-jira**（`harness jira get`）读取单内容；根据**描述中的步骤、期望结果、测试结果**（不能只看标题）整理目标 ECC 配置，再执行修改。**禁止**使用 Jira MCP

补充参数：

- **屏蔽**：仅当有卡/无卡为非紧急且用户**明确说明需要屏蔽**时生效（仅 MTK 支持）
- **SimState**：可选，在此 SIM 卡状态时判断为非紧急号码（仅 MTK 支持）

## 参数表

| 参数 | 必填 | 空值含义 | 约束 |
|------|------|----------|------|
| 号码 | 是 | — | 每条记录至少一个 |
| mccmnc | 否 | 公共紧急号码（全运营商生效） | 仅 3 位 = 不限定 MNC |
| 有卡 | 否 | 不更改 | 真紧急 / 假紧急 / 非紧急 |
| 无卡 | 否 | 不更改 | 真紧急 / 非紧急；**不可**假紧急 |
| 语音台 category | 否 | 不更改；新增可为 0 | 语义按平台映射（Fire Brigade：MTK=4，展锐/高通=3） |
| 英文名 | 否 | 不更改 | — |
| 当地语言 | 条件 | 未指定则从网络查询 MCC 官方语言 | 见 mcc-language.md |
| 当地语言名 | 条件 | 提供语言条目时必填 | 同一号码可多条 |
| 屏蔽 | 否 | 不写入屏蔽配置 | MTK 支持；展锐/高通忽略并提示 |
| SimState | 否 | 省略 | MTK 支持；展锐/高通忽略并提示 |

## 平台差异说明

- **MTK**：可修改 `ecc_list_tran2.xml` 与 `ecc_block_list.xml`；名称映射 `res/values/config.xml`。**指定 `mccmnc` 的条目覆盖公共条目**（`mccmnc` 为空才改公共配置），见 mapping.md。
- **展锐（Unisoc）**：仅修改 `assets/ecc_list.xml`；无屏蔽文件；名称映射 `res/values/ecc_config_list.xml`。
- **高通（Qualcomm）**：ECC 主配置与展锐一致（`assets/ecc_list.xml`，`Condition`/`CardFlag`/`EccType`）；名称映射为 `res/values/config.xml`（与 MTK 同名，与展锐不同）。
- **Category 值差异**：同一语义在三平台值可能不同（Fire Brigade：MTK=4，展锐/高通=3）。

## 归一化 schema

```yaml
eccRepoPath: "/path/to/ecc-repo"
platform: "auto"            # auto|mtk|unisoc|qualcomm（内部识别结果）
jiraIssueKey: null          # 例如 "ECC-1234"，启用 Jira 驱动模式

entries:
  - number: "998"           # 必填
    mccmnc: "26003"         # ""=公共; "260"=MCC+FFF; "26003"=MCC+MNC
    withSim: "真紧急"        # 真紧急|假紧急|非紧急|null=不更改
    withoutSim: "非紧急"     # 真紧急|非紧急|null=不更改
    category: "0"           # null=不更改; 新增可为 "0"
    englishName: null       # null=不更改
    block: false            # true=写入 ecc_block_list（须非紧急+明确要求）
    simState: null          # 可选，整型 0-11
    localNames:
      - language: "pl-rPL"  # 可省略，由 MCC 网络查询推断
        name: "Numer alarmowy"

# 内部归一化（路由层，非用户必填）
normalized:
  - withSimState: "真紧急|假紧急|非紧急|null"
    withoutSimState: "真紧急|非紧急|null"
```

## 校验规则

1. `entries` 至少包含一条，`number` 不可为空。
2. `withoutSim` 不可为「假紧急」。
3. `block: true` 时，至少一侧（有卡或无卡）须为非紧急。
4. 平台=MTK 时，Condition=4 按 MTK 非紧急规则处理（见 mapping.md）。
5. 平台=Unisoc 或 Qualcomm 时，不写屏蔽文件；`block`/`simState` 仅提示忽略。
6. 修改名称时 `mccmnc` 不可为空（公共紧急号码不可配名称）。
7. 名称侧仅使用 MCC（前 3 位），不按 MNC 区分。
8. `localNames` 每项须有 `name`；`language` 未指定时触发网络查询。
9. 仅改一侧（有卡或无卡）时，按平台读取已有字段反推缺失侧；无法唯一确定时询问用户。
10. 当用户仅说明“有卡是紧急号码”且未指定无卡、也未区分真/假紧急时：先检查原配置；若原配置有卡已紧急则不改；若原配置有卡非紧急，则普通号码改为“有卡假紧急”，**112/911 等 3GPP 国际通用紧急号码**改为“有卡真紧急”（见 mapping.md）。
11. Jira 若声明“某号码不应是紧急号码”，须结合描述中的**步骤、期望结果、测试结果**判定（不能只看标题）；再读取当前配置：当前已非紧急→加屏蔽；当前是紧急→仅删除配置不屏蔽（MTK 公共条目命中也算有配置）。

## 自然语言解析提示

| 用户表述 | 归一化值 |
|----------|----------|
| 真紧急、紧急 | `真紧急` |
| 假紧急 | `假紧急` |
| 非紧急、不是紧急 | `非紧急` |
| 不更改、不改、保持 | `null` |
| 屏蔽、需要屏蔽 | `block: true` |
| PIN 锁定 | `simState: 2` |
| 展锐、Unisoc | `platform: unisoc`（若用户显式指定） |
| 高通、Qualcomm、QCOM | `platform: qualcomm`（若用户显式指定） |

# ECC 字段映射（MTK + 展锐 + 高通）

## 通用规则

### 平台级优先级（跨平台统一）

当不同平台原配置不一致，需要先形成“统一语义”再分别落各平台配置时，使用：

`MTK > Unisoc(展锐) > Qualcomm(高通)`

统一流程：
1. 读取三平台原配置（按用户指定平台集合）。
2. 按优先级选择基线平台语义（有卡/无卡、category、名称 key）。
3. 基于基线语义 + 用户输入，生成目标统一语义。
4. 将统一语义分别映射到各平台字段（MTK: Condition；展锐/高通: Condition+CardFlag）。

注意：
- `simState` 仅 MTK 生效，不参与跨平台统一语义。
- 若高优先级平台无条目，回退到次优平台；若都无条目，按用户输入与默认规则生成。

### Plmn 规则（三平台通用）

| mccmnc 输入 | Plmn 写法 | 示例 |
|-------------|-----------|------|
| 空 | 省略 `Plmn`（或 `Plmn=""`） | 公共紧急号码 |
| 3 位 MCC | `"{MCC} FFF"`（展锐常见也有 `"{MCC}"` 历史写法） | `260` → `260 FFF` |
| MCC+MNC（5~6 位） | `"{MCC} {MNC}"` | `26003` → `260 03` |

MNC 格式化：取 mccmnc 第 4 位起为 MNC，不足两位左补零（如 `2603` → `03`）。

### 名称映射文件

| 平台 | MCC 名称路由文件 |
|------|------------------|
| MTK | `res/values/config.xml` |
| 展锐（Unisoc） | `res/values/ecc_config_list.xml` |
| 高通（Qualcomm） | `res/values/config.xml` |

均使用 `ecc_config_{MCC}` + `item={号码},{string_key}`，再定位到 `res/values*/strings.xml`。

---

## MTK Mapping

### 文件与字段

- 主文件：`xml/ecc_list_tran2.xml`
- 屏蔽文件：`xml/ecc_block_list.xml`

`EccEntry` 字段：`Ecc`、`Category`、`Condition`、`Plmn`

紧急号码唯一配置文件。其他 `ecc_list_*.xml` 已弃用。

| 用户参数 | XML 属性 | 规则 |
|----------|----------|------|
| 号码 | `Ecc` | 直接对应 |
| 语音台 | `Category` | 3GPP TS24.008 服务类别位掩码 |
| 有卡 + 无卡 | `Condition` | 由组合推导；仅改一侧时合并已有配置 |
| mccmnc | `Plmn` | 见通用 Plmn 规则；**MTK 下指定 MCC 覆盖公共配置**（见下） |

### MCC 指定配置覆盖公共配置（MTK）

在 `ecc_list_tran2.xml` 中，同一 `Ecc` 可同时存在：

- **公共配置**：省略 `Plmn` 或 `Plmn=""`（全 MCC/运营商生效）
- **指定 MCC 配置**：`Plmn="{MCC} FFF"` 或 `Plmn="{MCC} {MNC}"`

**运行时规则**：在对应 MCC（及 MNC）下，**指定 MCC 的条目覆盖未指定 MCC 的公共条目**；公共条目仍对其他未单独配置的 MCC 生效。

**修改时的写法**：

| 用户 `mccmnc` | 应修改/新增的目标 | 是否改公共条目 |
|---------------|-------------------|----------------|
| 空 | 公共条目（无 `Plmn` / `Plmn=""`） | 是 |
| 已指定 MCC/MNC | 同 `Ecc` + 对应 `Plmn` 的条目 | **否**（保留公共条目，用 MCC 条目覆盖语义） |

示例：公共 `<EccEntry Ecc="999" Condition="1" Plmn="" />`；若要在 MCC 460 下设为非紧急，应**新增** `<EccEntry Ecc="999" Condition="4" Plmn="460 FFF" />`，而不是改公共条目。

读取原配置、推导 Condition、新增/修改条目时，凡用户传入 `mccmnc` 非空，均按「MCC 覆盖公共」理解：优先查/写该 `Plmn` 条目，公共条目仅作回退参考或跨 MCC 默认。

### Category 位定义（3GPP TS24.008）

| Bit | 值 | 含义 |
|-----|-----|------|
| 1 | 1 | Police |
| 2 | 2 | Ambulance |
| 3 | 4 | Fire Brigade |
| 4 | 8 | Marine Guard |
| 5 | 16 | Mountain Rescue |
| 6 | 32 | Manually initiated eCall |
| 7 | 64 | Automatically initiated eCall |
| 8 | 128 | spare，置 0 |

### Condition 含义

| 值 | 含义 |
|----|------|
| 0 | 无卡时是真紧急 |
| 1 | 有卡、无卡均为真紧急 |
| 2 | 有卡假紧急，无卡真紧急 |
| 3 | 有卡真紧急 |
| 4 | 不是紧急号码（见下方「非紧急配置规则」） |
| 10 | 有卡假紧急，无卡不是紧急号码 |

### 有卡 + 无卡 → Condition 推导表

两者均指定时：

| 有卡 | 无卡 | Condition |
|------|------|-----------|
| 真紧急 | 真紧急 | 1 |
| 真紧急 | 非紧急 | 3 |
| 假紧急 | 真紧急 | 2 |
| 假紧急 | 非紧急 | 10 |
| 非紧急 | 真紧急 | 0 |
| 非紧急 | 非紧急 | 4（见「非紧急配置规则」） |

### 仅指定“有卡=紧急”特殊规则（新增）

当用户**仅说明有卡是紧急号码**（未指定无卡，且未区分真紧急/假紧急）时：

1. 先读取原配置，判断“有卡侧”当前是否已为紧急。
2. 若原配置有卡已是紧急（真紧急或假紧急）→ **不修改**。
3. 若原配置有卡不是紧急 → 按下列优先级决定改为真紧急还是假紧急：
   - **3GPP 国际通用紧急号码**（见下节）→ 改为**真紧急**；
   - 其他号码 → 改为**假紧急**（MTK 对应 `Condition=2` 或 `10`，取决于无卡侧原状态）。

说明：非国际通用号码仍走“最小改动”策略，不主动升级为真紧急；112/911 等国际号码在有卡侧从非紧急恢复为紧急时，优先按真紧急处理。

#### 3GPP 国际通用紧急号码

指 3GPP 规范中的国际通用紧急号码，至少包括：

| 号码 | 说明 |
|------|------|
| `112` | 国际通用紧急号码 |
| `911` | 北美等地区通用紧急号码 |

同一规则适用于其他 3GPP 规定的国际通用紧急号码；若无法判断某号码是否属于该类，先询问用户。

**判定条件**（须同时满足）：
- 用户仅要求“有卡是紧急号码”，未指定真紧急/假紧急；
- 原配置有卡侧为**非紧急**；
- 目标号码属于上表国际通用紧急号码。

**MTK 落库**（保持无卡侧原语义，仅将有卡侧升级为真紧急）：

| 原 Condition | 原语义（有卡/无卡） | 更新后 Condition | 更新后语义 |
|--------------|---------------------|------------------|------------|
| 0 | 非紧急 / 真紧急 | 1 | 真紧急 / 真紧急 |
| 4 | 非紧急 / 非紧急 | 3 | 真紧急 / 非紧急 |
| 10 | 假紧急 / 非紧急 | 3 | 真紧急 / 非紧急 |

其他原 `Condition` 值：先反推有卡/无卡侧，将有卡侧改为真紧急后再查上表推导目标 `Condition`；无法唯一确定时询问用户。

**非国际号码**仍按原规则：有卡非紧急 → 改为有卡假紧急（`Condition=2` 或 `10`）。

### 非紧急配置规则（Condition=4）

配置为非紧急时，按 `mccmnc` 与 tran2 现有条目判断：

| 场景 | 行为 |
|------|------|
| `mccmnc` 指定，已有同 `Ecc` + `Plmn` 条目 | 改 `Condition` 为 4 |
| `mccmnc` 指定，无同 `Plmn` 条目，但存在**通用紧急号码**条目（`Plmn=""` 或省略 `Plmn`） | **新增**该 `Plmn` 的条目，`Condition=4`（覆盖通用配置） |
| `mccmnc` 指定，无任何相关条目（既无同 `Plmn` 也无通用条目） | **不新增** |
| `mccmnc` 为空，存在通用条目 | 改通用条目 `Condition` 为 4 |
| `mccmnc` 为空，无通用条目 | **不新增** |

通用紧急号码示例：`<EccEntry Ecc="999" Category="0" Condition="1" Plmn="" />` 表示 999 在公共配置中为紧急号码；若需将 MCC 460 下 999 设为非紧急，应新增 `<EccEntry Ecc="999" Category="0" Condition="4" Plmn="460 FFF" />`。

仅指定一侧时：读取 tran2 现有 `Condition`，反推缺失侧，再按上表更新；无法唯一确定时询问用户。

### Jira 专项：`XXX` 号码“不应是紧急号码”

当 Jira 明确要求某号码“不应是紧急号码”时（**须结合描述中的步骤、期望结果、测试结果判定，不能只看标题**），MTK 按以下分支处理：

1. 先按目标 `mccmnc` 读取当前生效配置，判断该号码当前是“紧急”还是“非紧急”。
2. 若读出当前已是**非紧急**（例如 `Condition=4`，或等价非紧急语义）：
   - 保留/补齐非紧急防护，**需要添加屏蔽**（`ecc_block_list.xml`）。
3. 若读出当前是**紧急**：
   - **仅删除对应紧急配置，不添加屏蔽**。

MTK 命中判定补充：
- 对 `mccmnc` 指定场景，若无同 `Plmn="{MCC} FFF/{MCC MNC}"` 条目，但存在公共条目（`Plmn=""` 或省略 `Plmn`），也视为“有配置命中”。
- 即：**MTK 中没有定义 mcc 的公共紧急号码，也算有配置**，不可当作“无配置”跳过。

**Condition 反推参考**（读取现有值时）：

| Condition | 有卡 | 无卡 |
|-----------|------|------|
| 0 | 非紧急 | 真紧急 |
| 1 | 真紧急 | 真紧急 |
| 2 | 假紧急 | 真紧急 |
| 3 | 真紧急 | 非紧急 |
| 4 | 非紧急 | 非紧急 |
| 10 | 假紧急 | 非紧急 |

### 条目排序

同一号码下，指定运营商（如 `260 03`）的 `<EccEntry>` 必须排在 `FFF`（如 `260 FFF`）**之前**。

### 定位条目

在 tran2 中按 `Ecc` + `Plmn` 匹配。修改时保持文件现有格式风格（空格、自闭合标签等）。

### 新增 vs 修改

| 场景 | 行为 |
|------|------|
| `mccmnc` 指定，紧急等行为变更，无同 `Plmn` 条目 | **新增**该 `Plmn` 的 `<EccEntry>`（覆盖公共语义，不改公共条目） |
| `mccmnc` 指定，已有同 `Ecc` + `Plmn` 条目 | 修改该条目 |
| `mccmnc` 为空，有/无公共条目 | 改或增公共条目 |
| 非紧急，`mccmnc` 指定，已有同 `Ecc` + `Plmn` 条目 | 改 `Condition` 为 4 |
| 非紧急，`mccmnc` 指定，无同 `Plmn` 但有通用条目（`Plmn=""`） | **新增**该 `Plmn` 条目，`Condition=4` |
| 非紧急，无任何相关条目 | **不新增** |
| 非紧急，`mccmnc` 为空，有通用条目 | 改通用条目 `Condition` 为 4 |
| 部分字段不更改 | 保留原属性值 |

---

## ecc_block_list.xml — EccBlockNumber

表示号码不是紧急号码，用于错位配置。**仅**在用户提交的配置中有卡或无卡为非紧急且**明确说明需要屏蔽**时才配置。

```xml
<EccBlockNumber Number="999" BlockType="2" Mcc="286" Mnc="01"/>
<EccBlockNumber Number="111" BlockType="0" Mcc="640" Mnc="FF" SimState="2"/>
```

| 用户参数 | XML 属性 | 规则 |
|----------|----------|------|
| 号码 | `Number` | 直接对应 |
| mccmnc | `Mcc` + `Mnc` | 3 位 MCC → `Mnc="FF"`；含 MNC → 拆分填入 |
| 屏蔽范围 | `BlockType` | 见下表 |
| SIM 状态 | `SimState` | 可选；在此 SIM 卡状态时判断为非紧急号码 |

### BlockType

| 值 | 含义 |
|----|------|
| 0 | 仅无卡时屏蔽 |
| 1 | 始终屏蔽 |
| 2 | 仅有卡时屏蔽 |

### BlockType 推导（`block: true` 时）

| 非紧急侧 | BlockType |
|----------|-----------|
| 仅无卡非紧急 | 0 |
| 仅有卡非紧急 | 2 |
| 有卡、无卡均非紧急 | 1 |

### SimState

在此 SIM 卡状态时判断为非紧急号码。用户未指定时可省略。

| 值 | 常量 | 含义 |
|----|------|------|
| 0 | `SIM_STATE_UNKNOWN` | 未知 |
| 1 | `SIM_STATE_ABSENT` | 无 SIM 卡 |
| 2 | `SIM_STATE_PIN_REQUIRED` | 锁定：需 PIN 解锁 |
| 3 | `SIM_STATE_PUK_REQUIRED` | 锁定：需 PUK 解锁 |
| 4 | `SIM_STATE_NETWORK_LOCKED` | 锁定：需网络 PIN 解锁 |
| 5 | `SIM_STATE_READY` | 就绪（有卡可用） |
| 6 | `SIM_STATE_NOT_READY` | SIM 未就绪 |
| 7 | `SIM_STATE_PERM_DISABLED` | SIM 永久禁用 |
| 8 | `SIM_STATE_CARD_IO_ERROR` | SIM 存在但故障 |
| 9 | `SIM_STATE_CARD_RESTRICTED` | SIM 受限 |
| 10 | `SIM_STATE_LOADED` | 已加载 |
| 11 | `SIM_STATE_PRESENT` | SIM 存在 |

自然语言映射示例：「PIN 锁定时屏蔽」→ `SimState="2"`。

`BlockType` 决定有卡/无卡侧是否屏蔽；`SimState` 进一步限定在特定 SIM 状态下生效。

---

## Unisoc / Qualcomm Mapping

展锐与高通 **ECC 主配置完全一致**（`assets/ecc_list.xml`），字段语义与决策表相同；**仅名称映射资源文件不同**（展锐=`ecc_config_list.xml`，高通=`config.xml`）。

### 文件与字段

- 主文件：`assets/ecc_list.xml`
- 无屏蔽配置文件（`block` / `simState` 需求忽略并提示）

`EccEntry` 字段：`Ecc`、`Category`、`Condition`、`Plmn`、`EccType`、`CardFlag`

固定规则：

- `EccType` 已弃用，统一写 `0`
- `CardFlag` 优先级高于 `Condition`
- `CardFlag` 缺省默认为 `0`

### 展锐/高通字段语义

#### Condition（仅表达有卡侧）

| 值 | 含义 |
|----|------|
| 1 | 有卡真紧急 |
| 2 | 有卡假紧急 |

#### CardFlag（优先级更高）

| 值 | 含义 |
|----|------|
| 0（缺省） | 有卡、无卡都紧急 |
| 1 | 有卡紧急、无卡非紧急 |
| 2 | 有卡非紧急、无卡紧急 |

### 输入状态 → Unisoc/Qualcomm 字段决策表

| 有卡 | 无卡 | Condition | CardFlag | 说明 |
|------|------|-----------|----------|------|
| 真紧急 | 真紧急 | 1 | 缺省/0 | 常规真紧急 |
| 假紧急 | 真紧急 | 2 | 0 或省略 | 与 MTK Condition=2 语义接近 |
| 真紧急 | 非紧急 | 1 | 1 | 通过 CardFlag 表达无卡非紧急 |
| 非紧急 | 真紧急 | 1 | 2 | 通过 CardFlag 表达有卡非紧急 |
| 假紧急 | 非紧急 | 2 | 1 | 有卡假紧急 + 无卡非紧急 |
| 非紧急 | 非紧急 | - | - | **不可直接表达**，需提示用户展锐/高通能力限制 |

### 仅指定“有卡=紧急”特殊规则（新增）

当用户仅说明“有卡是紧急号码”且未给无卡状态、也未区分真紧急/假紧急时（展锐/高通）：

1. 读取原配置并判断有卡侧当前是否紧急（由 `CardFlag` 优先，其次 `Condition`）。
2. 若原配置有卡已紧急（真或假）→ **不修改**。
3. 若原配置有卡非紧急 → 按下列优先级决定改为真紧急还是假紧急：
   - **3GPP 国际通用紧急号码**（见 MTK 节「3GPP 国际通用紧急号码」）→ 改为**真紧急**：
     - `Condition=1`
     - 按原无卡侧状态选择 `CardFlag`（无卡仍紧急 → 缺省/`0`；无卡非紧急 → `1`）
   - 其他号码 → 配置为**假紧急**：
     - `Condition=2`
     - 同时按原无卡侧状态选择 `CardFlag`（通常为 `0` 或 `1`，避免把无卡侧误改为紧急）。

补充：

- CardFlag 生效优先级高于 Condition。
- 对“有卡非紧急”场景，Condition 仍使用 `1` 或保留原值，实际由 `CardFlag=2` 控制。
- `Plmn` 仍按通用规则写入。

### Category 差异提示

`Category` 数值在三平台可能不同，必须按平台映射，不可直接复用。

示例：Fire Brigade

- **MTK**：4
- **展锐 / 高通**：3

### 高通与展锐的唯一差异（名称）

| 项目 | 展锐 | 高通 |
|------|------|------|
| ECC 主配置 | `assets/ecc_list.xml` | `assets/ecc_list.xml`（相同） |
| 名称 key 路由 | `res/values/ecc_config_list.xml` | `res/values/config.xml` |
| `strings.xml` 多语言 | 相同流程 | 相同流程 |

---

## 名称映射（三平台通用流程）

1. 从 `mccmnc` 提取 MCC（至少 3 位）。
2. 按平台在 `ecc_config_{MCC}` 中查找 `{号码},{string_key}`：
   - MTK / 高通：`res/values/config.xml`
   - 展锐：`res/values/ecc_config_list.xml`
3. 英文名 → `res/values/strings.xml` 对应 `string_key`。
4. 当地语言名 → `res/values-{language}/strings.xml` 对应 `string_key`。

限制：

- `mccmnc` 为空（公共号码）不改名称。
- 名称仅按 MCC 级别，不按 MNC 细分。

---

## 关键业务规则

1. 非紧急 + `mccmnc` 指定 + 无同 `Plmn` 条目 + 无通用条目 → 不新增 EccEntry。
2. 非紧急 + `mccmnc` 指定 + 无同 `Plmn` 条目 + **有通用条目**（`Plmn=""`）→ 新增该 `Plmn` 条目，`Condition=4`。
3. 非紧急 + 已有同 `Ecc` + `Plmn` 条目 → Condition 改为 4。
4. **MTK**：指定 `mccmnc` 的配置覆盖同号码公共配置；改 MCC 侧应新增/改 `Plmn` 条目，不直接改公共条目（`mccmnc` 为空时除外）。
5. Jira 指定“不应是紧急号码”时：若当前已非紧急 → 添加屏蔽；若当前是紧急 → 仅删紧急配置，不屏蔽。
6. MTK 读取命中时，`mccmnc` 指定场景下公共条目（`Plmn=""`/省略）也算“有配置”。
7. MTK 才支持 block/simState；展锐/高通忽略此需求并提示。
8. 展锐/高通写入 `assets/ecc_list.xml` 时 `EccType=0`。
9. 展锐/高通 `CardFlag` 优先级高于 `Condition`。
10. 跨平台统一语义时，平台优先级为 `MTK > Unisoc > Qualcomm`。
11. 名称仅 MCC 级别可配；高通用 `config.xml`，展锐用 `ecc_config_list.xml`。
12. 用户仅说明“有卡是紧急号码”且未区分真/假紧急时：原配置有卡非紧急 → 普通号码改为有卡假紧急；**112/911 等 3GPP 国际通用紧急号码**改为有卡真紧急（见「仅指定有卡=紧急」与「3GPP 国际通用紧急号码」）。

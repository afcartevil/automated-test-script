# 示例

## 1. 单号码 — Condition + Plmn

**用户输入**：
```
EccList 路径: vendor/.../EccList
号码: 998
mccmnc: 260
有卡: 真紧急
无卡: 非紧急
```

**归一化**：
```yaml
- number: "998"
  mccmnc: "260"
  withSim: "真紧急"
  withoutSim: "非紧急"
```

**结果**：
```xml
<EccEntry Ecc="998" Category="0" Condition="3" Plmn="260 FFF" />
```

---

## 2. 运营商条目排序

**用户输入**：MCC 260，运营商 03，号码 998，有卡假紧急，无卡非紧急。

**结果**（`260 03` 须在 `260 FFF` 前）：
```xml
<EccEntry Ecc="998" Category="0" Condition="10" Plmn="260 03" />
<EccEntry Ecc="998" Category="0" Condition="3" Plmn="260 FFF" />
```

---

## 3. 批量多号码

**用户输入**：
```
号码: 997, 998, 999
mccmnc: 260
有卡: 真紧急
无卡: 真紧急
```

**归一化**：3 条 `entries`，各推导 `Condition=1`，`Plmn="260 FFF"`。

---

## 4. 非紧急 — 无任何条目不新增

**用户输入**：号码 888，mccmnc 260，有卡非紧急，无卡非紧急。tran2 中无 888 相关条目（既无 `260 FFF` 也无通用 `Plmn=""`）。

**结果**：tran2 **不新增**条目。

---

## 4b. 非紧急 — 覆盖通用紧急号码（MTK MCC 覆盖公共）

**用户输入**：号码 999，mccmnc 460，有卡非紧急，无卡非紧急。tran2 存在通用条目：
```xml
<EccEntry Ecc="999" Category="0" Condition="1" Plmn="" />
```
但无 `Plmn="460 FFF"` 条目。

**结果**：**新增** MCC 460 覆盖条目（公共 `Plmn=""` 条目保留，由 `460 FFF` 条目在 MCC 460 下覆盖）：
```xml
<EccEntry Ecc="999" Category="0" Condition="4" Plmn="460 FFF" />
```

---

## 5. 非紧急 — 有原配置改 Condition=4

**用户输入**：号码 123，mccmnc 732101，有卡非紧急，无卡非紧急。tran2 已有：
```xml
<EccEntry Ecc="123" Category="0" Condition="2" Plmn="732 101"/>
```

**结果**：
```xml
<EccEntry Ecc="123" Category="0" Condition="4" Plmn="732 101"/>
```

---

## 6. 屏蔽 — 有卡非紧急

**用户输入**：号码 119，mccmnc 732，有卡非紧急，明确要求屏蔽。

**归一化**：
```yaml
- number: "119"
  mccmnc: "732"
  withSim: "非紧急"
  block: true
```

**结果**：
- tran2：若有条目则 `Condition=4`
- block list 新增：
```xml
<EccBlockNumber Number="119" BlockType="2" Mcc="732" Mnc="FF"/>
```

---

## 7. 屏蔽 + SimState

**用户输入**：号码 111，mccmnc 640，无卡非紧急，屏蔽，PIN 锁定时生效。

**结果**：
```xml
<EccBlockNumber Number="111" BlockType="0" Mcc="640" Mnc="FF" SimState="2"/>
```

---

## 8. 名称 — 改英文名

**用户输入**：号码 998，mccmnc 260，英文名改为 "Fire Brigade"。

**流程**：
1. `ecc_config_260` 中查 `998,fire_birgade_po`
2. 修改 `res/values/strings.xml`：
```xml
<string name="fire_birgade_po">Fire Brigade</string>
```

---

## 9. 名称 — 改当地语言（指定语言）

**用户输入**：号码 998，mccmnc 260，当地语言 pl-rPL，当地语言名 "Straż pożarna"。

**结果**：修改 `res/values-pl-rPL/strings.xml` 中 `fire_birgade_po`。

---

## 10. 名称 — 当地语言网络查询

**用户输入**：号码 998，mccmnc 260，当地语言名 "Straż pożarna"（未指定语言）。

**流程**：
1. WebSearch: `MCC 260 Poland official language` → 波兰语
2. 映射 `values-pl-rPL`，验证目录存在
3. 修改 `res/values-pl-rPL/strings.xml`

**摘要记录**：
```
语言查询: "MCC 260 Poland official language" → 波兰语 → values-pl-rPL
```

---

## 11. 名称不可配 — 公共号码

**用户输入**：号码 112，mccmnc 空，英文名 "Emergency"。

**结果**：跳过名称修改，提示「公共紧急号码无法配置名称」。

---

## 12. 单号码多语言

**用户输入**：
```
号码: 998
mccmnc: 260
当地语言名:
  - 语言: pl-rPL, 名称: Straż pożarna
  - 语言: de-rDE, 名称: Feuerwehr
```

**归一化**：
```yaml
localNames:
  - language: "pl-rPL"
    name: "Straż pożarna"
  - language: "de-rDE"
    name: "Feuerwehr"
```

**结果**：分别修改 `values-pl-rPL/strings.xml` 和 `values-de-rDE/strings.xml` 中的 `fire_birgade_po`。

---

## 13. 公共紧急号码

**用户输入**：号码 112，mccmnc 空，有卡真紧急，无卡真紧急。

**结果**：
```xml
<EccEntry Ecc="112" Category="0" Condition="1" />
```
（省略 `Plmn`）

---

## 14. 仅改一侧 — 合并现有配置

**用户输入**：号码 999，mccmnc 260，仅改有卡为假紧急（无卡不更改）。tran2 现有 `Condition="1"`（有卡真紧急、无卡真紧急）。

**推导**：有卡改为假紧急 + 无卡保持真紧急 → `Condition=2`。

**结果**：
```xml
<EccEntry Ecc="999" Category="0" Condition="2" Plmn="260 FFF" />
```

---

## 14b. 仅说明“有卡是紧急号码”（普通号码）

**用户输入**：号码 999，mccmnc 260，仅说明“有卡是紧急号码”，未指定无卡。

**处理规则**（非 112/911 等国际通用紧急号码）：
1. 读取原配置判断有卡侧是否已紧急；
2. 若已紧急（真或假）→ 不修改；
3. 若有卡非紧急 → 改为有卡假紧急（保持无卡侧原语义）。

**示例（MTK）**：原配置 `Condition="0"`（有卡非紧急、无卡真紧急）  
→ 更新为 `Condition="2"`（有卡假紧急、无卡真紧急）。

---

## 14c. 仅说明“有卡是紧急号码” — 3GPP 国际通用号码

**用户输入**：号码 112，mccmnc 460，仅说明“有卡是紧急号码”，未指定无卡，也未区分真/假紧急。

**处理规则**（112/911 等国际通用紧急号码）：
1. 读取原配置判断有卡侧是否已紧急；
2. 若已紧急 → 不修改；
3. 若有卡非紧急 → 改为有卡**真紧急**（保持无卡侧原语义）。

**示例（MTK）**：原配置 `Condition="4"`（有卡非紧急、无卡非紧急）  
→ 更新为 `Condition="3"`（有卡真紧急、无卡非紧急）。

**对比**：若号码为 999 等非国际通用号码，同场景下应更新为 `Condition="10"`（有卡假紧急、无卡非紧急）。

---

## Unisoc 示例（tranecc）

## 15. 指定展锐仓路径

**用户输入**：
```
ECC 仓路径: e:/code/ecc/tranecc
号码: 112
mccmnc: 460
有卡: 真紧急
无卡: 真紧急
```

**结果**：修改 `assets/ecc_list.xml`，不触碰 MTK 文件。

---

## 16. Category 差异（Fire Brigade）

**用户输入**：号码 117，mccmnc 460，语音台=火警，有卡真紧急，无卡真紧急。

**结果**：
- MTK 映射为 `Category=4`
- 展锐 / 高通 映射为 `Category=3`

展锐/高通写入示例：
```xml
<EccEntry Ecc="117" Category="3" Condition="1" Plmn="460 FFF" EccType="0"/>
```

---

## 17. Condition + CardFlag 联合

**用户输入**：号码 999，mccmnc 460，有卡非紧急，无卡真紧急。

**展锐映射**：
- `CardFlag=2`（有卡非紧急，无卡紧急）
- `Condition` 仅作为有卡紧急语义辅助，写 `1`
- `EccType=0`

```xml
<EccEntry Ecc="999" Category="0" Condition="1" Plmn="460 FFF" EccType="0" CardFlag="2"/>
```

---

## 18. 展锐固定 EccType

**用户输入**：任意号码更新（未提供 EccType）。

**结果**：展锐一律写 `EccType="0"`。

---

## 19. 展锐忽略 simState / block

**用户输入**：号码 111，mccmnc 640，有卡非紧急，要求屏蔽，simState=2。

**结果**：
- 修改 `assets/ecc_list.xml`（按 CardFlag/Condition 规则）
- 不写任何 block 文件（展锐无该文件）
- 摘要提示：`block` 与 `simState` 在展锐平台被忽略

---

## 20. 展锐名称修改（ecc_config_list.xml）

**用户输入**：号码 117，mccmnc 460，当地语言 `zh-rCN`，当地语言名“火警”。

**流程**：
1. 在 `res/values/ecc_config_list.xml` 的 `ecc_config_460` 查找 `117,{key}`
2. 修改 `res/values-zh-rCN/strings.xml` 中 `<string name="{key}">火警</string>`

---

## 21. 展锐无卡非紧急（CardFlag=1）

**用户输入**：号码 118，mccmnc 646，有卡真紧急，无卡非紧急。

**结果**：
```xml
<EccEntry Ecc="118" Category="0" Condition="1" Plmn="646" EccType="0" CardFlag="1"/>
```

---

## 22. 展锐不可表达场景告警

**用户输入**：号码 777，有卡非紧急，无卡非紧急。

**结果**：
- 给出告警：展锐 `Condition + CardFlag` 无法直接表达“有卡/无卡都非紧急”
- 不盲目写入冲突配置，要求用户确认替代策略

---

## Qualcomm 示例（高通）

## 23. 平台识别（高通 vs 展锐）

**路径特征**：
- `assets/ecc_list.xml` 存在
- `res/values/config.xml` 存在（含 `ecc_config_{MCC}`）
- **无** `res/values/ecc_config_list.xml` → 识别为高通

若同时存在 `config.xml` 与 `ecc_config_list.xml`，要求用户显式指定 `platform: qualcomm` 或 `platform: unisoc`。

---

## 24. 高通 ECC 主配置（与展锐相同）

**用户输入**：
```
ECC 仓路径: /path/to/qcom-ecc
号码: 112
mccmnc: 460
有卡: 真紧急
无卡: 真紧急
```

**结果**：修改 `assets/ecc_list.xml`：
```xml
<EccEntry Ecc="112" Category="0" Condition="1" Plmn="460 FFF" EccType="0"/>
```

---

## 25. 高通名称修改（config.xml）

**用户输入**：号码 117，mccmnc 460，当地语言 `zh-rCN`，当地语言名“火警”。

**流程**（与 MTK 名称路由相同，与展锐不同）：
1. 在 `res/values/config.xml` 的 `ecc_config_460` 查找 `117,{key}`
2. 修改 `res/values-zh-rCN/strings.xml` 中对应 `string_key`

---

## 26. 高通 Category（Fire Brigade = 3）

**用户输入**：号码 117，语音台=火警。

**映射**：
- MTK → `Category=4`
- 高通 / 展锐 → `Category=3`

---

## 27. 高通忽略 block / simState

与展锐示例 19 相同：修改 `assets/ecc_list.xml`，不写屏蔽文件，摘要中提示忽略。

---

## 28. 跨平台原配置不一致时的统一

**场景**：同一号码在三平台原配置不一致，需要统一后再分别写入（`simState` 除外）。

**优先级**：`MTK > 展锐 > 高通`

**示例**：号码 999，mccmnc 460  
- MTK 原配置推断有卡=真紧急  
- 展锐原配置推断有卡=非紧急  
- 高通原配置推断有卡=假紧急  

**统一决策**：
1. 先取 MTK 语义作为基线（最高优先级）；  
2. 结合用户输入生成目标统一语义；  
3. 再映射到各平台字段：  
   - MTK → `Condition`  
   - 展锐/高通 → `Condition + CardFlag`（`CardFlag` 优先）

**结果要求**：三平台最终语义一致（除 MTK 专属 `simState` 外）。

---

## 29. Jira 驱动 — 先整理目标配置再改文件

**用户输入**：`按 JIRA-12345 处理 ECC`

**处理流程**：
1. 读取 Jira（**harness-jira**，禁止 Jira MCP）：
   - `harness --json jira get --issue JIRA-12345`
   - 若给的是 URL：`harness --json jira get --url "..."` 或先 `parse-key`
2. **不能只看标题**；必须结合描述中的**步骤、期望结果、测试结果**提取号码、mccmnc、目标状态。
3. 对照期望结果与测试结果界定目标行为（如“期望非紧急、实测仍紧急”→ 改为非紧急）。
4. 读取仓内当前配置，生成“目标 ECC 配置清单”。
5. 先输出清单供用户确认，再执行文件修改。

**目标配置清单示例**：
```yaml
- number: "999"
  mccmnc: "460"
  withSim: "非紧急"
  withoutSim: "非紧急"
  action: "remove-or-block-by-current-state"
  jiraEvidence:
    steps: "插卡拨打 999"
    expected: "不应识别为紧急号码"
    actual: "仍按紧急号码拨出"
```

---

## 30. Jira 指定“不应是紧急号码” — 当前已非紧急则加屏蔽

**Jira 需求**：999 在 MCC 460 不应是紧急号码。  
**当前配置读取结果**：`<EccEntry Ecc="999" Condition="4" Plmn="460 FFF" />`（已非紧急）。

**结果**：
- 保持/修正非紧急主配置
- 新增屏蔽：
```xml
<EccBlockNumber Number="999" BlockType="1" Mcc="460" Mnc="FF"/>
```

---

## 31. Jira 指定“不应是紧急号码” — 当前是紧急则仅删配置不屏蔽

**Jira 需求**：999 在 MCC 460 不应是紧急号码。  
**当前配置读取结果**：仅命中公共条目（无 `460 FFF`）：
```xml
<EccEntry Ecc="999" Category="0" Condition="1" Plmn="" />
```

> 在 MTK 中，这种“公共条目命中”也算“有配置”。

**结果**：
- 删除对应紧急配置（按命中策略删除 MCC 侧或公共侧）
- **不新增** `ecc_block_list.xml` 屏蔽条目

# MTK SPN 分析参考

## 强特征

`MtkRIL`、`MtkNetworkResponse`、`MtkServiceStateTracker`、`MtkSpnOverride`、`MtkSIMRecords`、`MtkUiccProfile`、`mediatek-telephony-common`。

## 关键链路

状态栏/锁屏：

```text
MtkSIMRecords / MtkSpnOverride
→ CarrierDisplayNameResolver
→ MtkServiceStateTracker.extendSpnDisplayNameData
→ SERVICE_PROVIDERS_UPDATED
→ SystemUI
```

手动搜网：

```text
MtkNetworkResponse.getAvailableNetworksResponse
→ MtkRIL.lookupOperatorNameForPlmnList
→ lookupOperatorNameMVNO2 / SPN / EONS / NITZ
→ OperatorInfo alphaLong/alphaShort
```

displayName：

```text
MtkUiccProfile / ServiceStateTracker
→ SubscriptionManagerService.setDisplayNameUsingSrc
→ siminfo.display_name + name_source
```

云网：

```text
SpnCloudConfigController
→ TranRadioConfigManagerPluginImpl
→ TranTelephonyManagerEx.mergeCloudSpn
→ MtkSpnOverride 内存表
```

## 核心文件

- `vendor/mediatek/proprietary/frameworks/opt/telephony/.../MtkRIL.java`
- `vendor/mediatek/proprietary/frameworks/opt/telephony/.../MtkNetworkResponse.java`
- `vendor/mediatek/proprietary/frameworks/opt/telephony/.../MtkServiceStateTracker.java`
- `vendor/mediatek/proprietary/frameworks/opt/telephony/.../uicc/MtkSpnOverride.java`
- `vendor/mediatek/proprietary/frameworks/opt/telephony/.../uicc/MtkSIMRecords.java`
- `vendor/mediatek/proprietary/frameworks/opt/telephony/.../uicc/MtkUiccProfile.java`
- `frameworks/opt/telephony/.../ServiceStateTracker.java`
- `frameworks/opt/telephony/.../UiccProfile.java`
- `packages/apps/Apn/spn-conf.xml`
- `packages/apps/Apn/plmn-conf.xml`

设备配置通常位于：

- `/system_ext/etc/vconfig/spn-conf.xml`
- `/system_ext/etc/vconfig/plmn-conf.xml`
- `/vendor/etc/virtual-spn-conf-by-*.xml`

## 决策树

### 状态栏或锁屏名称错误

1. 对齐 SIM state、subId、EF_SPN 和注册 PLMN 时间线。
2. 检查 `SERVICE_PROVIDERS_UPDATED` 中 `showSpn/spn/dataSpn/showPlmn/plmn`。
3. 广播已错误：修 Telephony；广播正确而 UI 错：再查 SystemUI。
4. SIM 未 LOADED 时先发网络 PLMN、LOADED 后变正确：属于初始化时序/来源选择。
5. `tran_tsd_operator_spn_support=true` 时检查驻网 PLMN 写 displayName 的路径和 nameSource 优先级。

### 手动搜网显示 MCCMNC

1. 是否进入 `MtkNetworkResponse`。
2. `lookupOperatorNameForPlmnList` 的 numeric 和 display rule 是否正确。
3. `lookupOperatorName2` 是否命中 vconfig。
4. 是否被 `MTK_KEY_TRAN_TDD_LOOKUP_OPERATOR_NAME2_SKIP` 清空。
5. 全部未命中才考虑补配置表。

### MVNO/子品牌错误

检查 `getSpnByPattern` 及：

- `virtual-spn-conf-by-efspn.xml`
- `virtual-spn-conf-by-imsi.xml`
- `virtual-spn-conf-by-efpnn.xml`
- `virtual-spn-conf-by-efgid1.xml`

### 注入异常

确认：

- `telephony_injection.xml` 注入 `ServiceStateTracker` 和 `UiccProfile`；
- `MtkTelephonyComponentFactory.makeRIL()` 创建 `MtkRIL`；
- `/system_ext/framework/mediatek-telephony-common.jar` 存在。

## 常见根因

- SIM records 未完成时过早使用注册 PLMN；
- vconfig 条目缺失或打包路径错误；
- CarrierConfig 改变 SPN/PLMN 优先级；
- `name_source` 高优先级旧值阻止更新；
- A17 移植遗漏 MtkServiceStateTracker/MtkRIL hook；
- 云 SPN Plugin 到 Framework merge 链路断开。

## 修改注意

- 同 MCC 的 SIM/驻网 PLMN 选择要处理 SIM numeric 尚未加载的窗口。
- 不用单一运营商硬编码替代通用 SIM-loaded gate。
- defer 逻辑不能跳过后续 pollState。
- displayName 修复必须同时检查 `NAME_SOURCE_*` 优先级。

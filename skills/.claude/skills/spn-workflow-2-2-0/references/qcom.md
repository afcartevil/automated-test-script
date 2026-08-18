# QCOM SPN 分析参考

## 强特征

`QTIRILJ`、`QtiRIL`、`QtiNetworkResponse`、`QtiServiceStateTracker`、`QcomSpnOverride`、`QtiSIMRecords`、`QtiUiccProfile`、`qti-telephony-common`。

## 关键链路

状态栏/锁屏：

```text
QtiSIMRecords / QcomSpnOverride
→ CarrierDisplayNameResolver
→ QtiServiceStateTracker
→ SERVICE_PROVIDERS_UPDATED
→ SystemUI
```

手动搜网：

```text
QtiNetworkResponse.getAvailableNetworksResponse
→ QtiRIL.lookupOperatorNameForPlmnList
→ TS25 / SPN / EONS / NITZ / MVNO
→ OperatorInfo alphaLong/alphaShort
```

displayName：

```text
QtiUiccProfile / ServiceStateTracker
→ SubscriptionManagerService.setDisplayNameUsingSrc
→ siminfo.display_name + name_source
```

云网：

```text
SpnCloudConfigController
→ TeleService Plugin
→ TranTelephonyManagerEx.mergeCloudSpn
→ QcomSpnOverride
```

## 核心文件

- `vendor/qcom/proprietary/commonsys/telephony-fwk/opt/telephony/.../QtiRIL.java`
- `vendor/qcom/proprietary/commonsys/telephony-fwk/opt/telephony/.../QtiNetworkResponse.java`
- `vendor/qcom/proprietary/commonsys/telephony-fwk/opt/telephony/.../QtiServiceStateTracker.java`
- `vendor/qcom/proprietary/commonsys/telephony-fwk/opt/telephony/.../uicc/QcomSpnOverride.java`
- `vendor/qcom/proprietary/commonsys/telephony-fwk/opt/telephony/.../uicc/QtiSIMRecords.java`
- `vendor/qcom/proprietary/commonsys/resource-overlay/.../telephony_injection.xml`
- `frameworks/opt/telephony/.../ServiceStateTracker.java`
- `frameworks/opt/telephony/.../UiccProfile.java`
- `build/soong/scripts/check_boot_jars/package_allowed_list.txt`

设备配置通常位于：

- `/product/etc/spn-conf.xml`
- `/system_ext/etc/spn-conf.xml`
- `etc/plmn-conf.xml`
- `etc/virtual-spn-conf-by-*.xml`

## 决策树

### 状态栏或锁屏名称错误

1. 对齐 SIM state、subId、EF_SPN、注册 PLMN 与广播。
2. 检查 `SERVICE_PROVIDERS_UPDATED` 的 SPN/PLMN 字段。
3. `Load EF_SPN` 为空时区分 SIM 数据缺失和读卡时序。
4. `lookupOperatorSPN` 只对当前驻网 PLMN 生效；非当前 PLMN 应走 TS25/EONS/NITZ。
5. 广播错误修 QTI Telephony；广播正确才查 SystemUI。

### 手动搜网显示 MCCMNC

1. 确认 `QtiNetworkResponse.getAvailableNetworksResponse` 被调用。
2. 确认工厂实际创建 `QtiRIL` 和 QTI network response。
3. 检查 `lookupOperatorNameForPlmnList` 的 numeric、display rule 和 result。
4. 检查 `spn-conf/plmn-conf` 是否含目标 MCCMNC。
5. 全部 lookup 返回空时再补配置或移植逻辑。

### MVNO/子品牌错误

检查 QcomSpnOverride：

- `virtual-spn-conf-by-efspn.xml`
- `virtual-spn-conf-by-imsi.xml`
- `virtual-spn-conf-by-efpnn.xml`
- `virtual-spn-conf-by-efgid1.xml`

### 注入或启动异常

确认：

- `telephony_injection.xml` 包含 RIL、UiccProfile、ServiceStateTracker 等目标组件；
- `QtiTelephonyComponentFactory.makeRIL()` 返回 `QtiRIL`；
- `qti-telephony-common.jar` 已打包；
- boot jar 检查需要的 QTI package allowlist 已合入。

### 云 SPN 不刷新

检查：

- Plugin 是否调用 `mergeCloudSpn`；
- TeleService 与 telephony-common 是否存在 ClassLoader 影子单例；
- Framework 侧 QcomSpnOverride 是否收到内存表更新；
- 更新后是否触发 subscription/SPN refresh。

## 常见根因

- QtiRIL/QtiNetworkResponse 移植遗漏；
- injection 或 jar 未生效；
- SPN/PLMN 配置表缺项；
- EF_SPN 尚未完成时提前发布网络名称；
- EONS/NITZ/TS25 优先级不符合项目 CarrierConfig；
- TeleService 与 Framework 使用不同 QcomSpnOverride 实例；
- nameSource 高优先级值阻止 displayName 更新。

## 修改注意

- 先证明 QTI 子类在运行，再改 lookup 逻辑。
- 手动搜网问题优先落在 QtiNetworkResponse/QtiRIL，不误改状态栏链路。
- 云 SPN 问题需要验证 ClassLoader 和 refresh，不只验证 merge 返回成功。
- 不为单个 MCCMNC 复制一套已有 TS25 查找逻辑。

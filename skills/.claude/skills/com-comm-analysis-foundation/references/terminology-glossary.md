# Terminology Glossary

## 1. 基础通信术语

- **APN (Access Point Name)**：数据接入点配置，决定终端如何接入运营商数据网络。
- **PLMN (Public Land Mobile Network)**：公网移动通信网络标识，通常对应 MCC + MNC。
- **SPN (Service Provider Name)**：服务提供商名称，常用于状态栏或设置中的运营商显示。
- **RAT (Radio Access Technology)**：无线接入制式，如 2G / 3G / 4G / 5G。
- **IMS (IP Multimedia Subsystem)**：承载 VoLTE / VoNR / VoWiFi 等业务的核心 IP 多媒体子系统。
- **VoWiFi / WFC**：通过 Wi‑Fi 承载语音业务的能力与相关开关状态。
- **CS domain**：传统电路域语音/补充业务路径。
- **IMS domain**：基于 IMS 的语音与补充业务路径。

## 2. SIM / UICC 术语

- **UICC**：通用集成电路卡，SIM / USIM 等应用的宿主卡体。
- **IMSI**：国际移动用户识别码，SIM 的关键身份信息。
- **ICCID**：SIM 卡卡号标识。
- **ATR (Answer To Reset)**：SIM 卡在复位后返回的应答信息，是底层物理通信是否正常的重要判断点。
- **PIN / PUK**：SIM 安全码与解锁码。
- **READY**：SIM 已完成基本初始化，可被系统识别。
- **LOADED**：SIM 文件已加载完成，上层可读取记录信息。
- **CARD_IO_ERROR**：SIM 读写 I/O 异常，常见于卡损坏或通信异常。
- **CARD_RESTRICTED**：SIM 卡受限状态，常与运营商限制相关。
- **SIMRecords**：Android 上层负责读取 EF 文件并构建 SIM 记录的模块。
- **UiccController**：Android 上层管理卡状态、广播 READY / LOADED 的核心模块。

## 3. 网络 / 显示相关术语

- **OPERATOR**：网络侧返回的运营商长名 / 短名信息。
- **rawSpn / rawPlmn**：配置层或网络层取到的原始显示名称。
- **newSpn**：客制化后用于显示的 SPN 名称。
- **showSpn / showPlmn**：最终显示策略，决定界面显示 SPN 还是 PLMN。
- **CURRENT / AVAILABLE / FORBIDDEN**：手动搜网列表中的网络接入状态，分别表示当前驻留、可接入、受限。
- **NetworkScanHelper**：Android 侧处理手动搜网结果的常见关键日志入口。
- **ServiceStateTracker / SST**：管理注册状态、制式、运营商名称与图标显示的核心模块。

## 4. Call / Telephony 术语

- **MO (Mobile Originated)**：主叫、拨出呼叫。
- **MT (Mobile Terminated)**：被叫、来电呼叫。
- **Telecom**：Android 通话编排框架层。
- **Telephony**：Android 电话业务与底层通信管理层。
- **InCall**：来去电界面与通话交互相关模块。
- **DisconnectCause / TelephonyCause / ImsReasonInfo**：挂断原因、错误码与 IMS 侧原因信息。
- **Supplementary Service**：补充业务，如 CLIR、Call Waiting、Call Forwarding、Call Barring。
- **XCAP / Ut**：IMS 补充业务常见的 HTTP / XML 配置访问路径。

## 5. Modem / Stability 术语

- **Baseband**：调制解调器软件版本标识；显示 `Unknown` 往往是重大异常信号。
- **Modem EE**：Modem Exception，指 Modem 子系统异常崩溃或致命错误。
- **ASSERT / [Fatal error]**：底层关键报错形式，通常附带文件路径、行号和参数。
- **P1 / P2 / P3**：ASSERT 附带的关键参数，用于进一步定位根因。
- **_EE_INVALID**：Modem EE 自动打包出的关键 dump 目录。
- **__exp_main.txt**：AEE / EE 相关的重要摘要文件。
- **taglog**：粉丝日志等场景下的辅助关键日志。
- **minidump**：大数据或 crash 场景下的精简 dump 文件。
- **ccci_mdinit**：Modem 初始化相关关键字，常用于 EE 问题初筛。
- **DbgInfo**：与对应版本匹配的调试信息文件集合，平台侧解析闭源问题必需。
- **ELF / AXF**：与 Modem 版本匹配的符号文件或可执行映像，用于 dump / ASSERT 解析。

## 6. 分析动作术语

- **DUT**：待测设备。
- **REF**：参考设备 / 对比机。
- **断点（Breakpoint）**：正常流程停止、被拒绝或回滚的位置，是归因的第一抓手。
- **已知问题**：已有相同根因 CR / patch 可复用的问题。
- **未知问题**：现有资料无法闭环，需要附带完整材料升级平台进一步分析的问题。

## 7. 使用建议

如果回答对象是海外同事，可以直接在输出中保留英文缩写，并在第一次出现时带一句简短解释；
如果回答对象是内部新人，建议用“英文缩写 + 中文含义 + 在排查中的用途”三件套，理解速度会快很多。 

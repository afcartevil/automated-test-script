# Page 1
⽹络问题分析SOP
🐵本⽂档为⽹络问题分析标准操作流程（SOP），聚焦M TK 、展锐两⼤芯⽚平台，涵盖⽹络状
态流程梳理、⽇志抓取规范、⽇志分析⽅法三⼤核⼼板块，为⼯程师提供⽹络问题定位与
排查的标准化指引，适⽤于SPN显⽰、APN配置、RAT/IM S图标、搜⽹失败等多类⽹络问题
场景
⼀、⽹络状态流程
⼆、⽇志抓取
 《⼯具安装与环境配置指南》
三、⽇志分析
⼀、SPN（状态栏等各位置运营商名称显⽰）
spn类问题主要检查的log是ServiceStateTracker
⼀、M TK关键log
代码块
// ⽹络返回的运营商⻓名和短名
03-18 08:56:21.182527  2541  2758 D RILJ    : [0668]< OPERATOR 
{MD8475B_SmartStudio, MD8475B, 65010} [PHONE0]
// 更新运营商名称显⽰
01-27 09:28:47.343190  2830  2830 D MTKSST  : [GsmSST1] 
updateCarrierDisplayName: satellitePlmn=null
1
2
3
4
5

# Page 2
01-27 09:28:47.343317  2830  2830 D MTKSST  : [GsmSST1] 
updateCarrierDisplayName: rawSpn = Airtel ZM
01-27 09:28:47.343406  2830  2830 D MTKSST  : [GsmSST1] updateSpnDisplay: rule 
= 3
01-27 09:28:47.345866  2830  2830 D MTKSST  : [GsmSST1] TDD updateSpnDisplay 
mSS.getOperatorNumeric() = null
01-27 09:28:47.345987  2830  2830 D MTKSST  : [GsmSST1] TDD getNumeric 
simNumeric = 64501, operatorNumeric = null
01-27 09:28:47.346024  2830  2830 D MTKSST  : [GsmSST1] TDD 
currentMccEqualsSimMcc simNumeric = 64501, operatorNumeric = null
01-27 09:28:47.346511  2830  2830 D MTKSST  : [GsmSST1] 
notifyCarrierDisplayNameDataChanged: changed sending intent, rule=3, 
CarrierDisplayNameData={ spn = null, dataSpn = Airtel ZM, showSpn = false, 
plmn = No service, showPlmn = true, subId=1
M TK平台关键⽇志解读
• 核⼼⽇志⽂件：ServiceStateTracker
• 关键字段：
◦ OPERATOR ：返回当前⽹络⻓名/短名，PHONE0 代表SIM 卡1
◦ rawspn ：⼚商配置名称，plmn ：⽹络下发名称
◦ notifyCarrierDisplayNameDataChanged ：最终显⽰结果汇总
• 关键标识：
◦ MTKSST 、updateCarrierDisplayName 为核⼼关键字
◦ [GsmSST0] 对应SIM 卡1，[GsmSST1] 对应SIM 卡2
• 异常判断：若配置显⽰PLM N但实际显⽰SPN，或反之，可直接定位为显⽰逻辑异常
⼆、展锐关键log
代码块
07-25 10:53:50.877  1570  1570 D SST     : [0] updateSpnDisplayLegacy+
07-25 10:53:50.879  1570  1570 D SST     : [0] TDD updateSpnDisplay 
mSS.getOperatorNumeric() = 42402
07-25 10:53:50.879  1570  1570 D SST     : [0] updateSpnDisplay: rawPlmn = 
Etisalat e&
07-25 10:53:50.879  1570  1570 D SST     : [0] updateSpnDisplay: newSpn = null 
, rawSpn = 
07-25 10:53:50.879  1570  1570 D SST     : [0] updateSpnDisplay: rawSpn = 
07-25 10:53:50.879  1570  1570 D SST     : [0] TDD getNumeric simNumeric = 
42402, operatorNumeric = 42402
6
7
8
9
10
11
1
2
3
4
5
6

# Page 3
07-25 10:53:50.879  1570  1570 D SST     : [0] TDD currentMccEqualsSimMcc 
simNumeric = 42402, operatorNumeric = 42402
07-25 10:53:50.884  1570  1570 D SST     : [0] updateSpnDisplay: spnName = e& ,
 mNumeric = 42402
07-25 10:53:50.885  1570  1570 D SST     : [0] updateSpnDisplay: 
updateSpnDisplay: changed sending intent, rule=2, showPlmn='true', plmn='e&', 
showSpn='false', spn='e&', dataSpn='', subId='26'
07-25 10:53:50.888  1570  1570 D SST     : [0] updateSpnDisplayLegacy-
• 核⼼⽇志⽂件：ServiceStateTracker
• 关键字段：
◦ newSpn ：客制化显⽰名称，rawSpn ：第三⽅获取名称
◦ updateSpnDisplay: changed sending intent ：最终显⽰策略汇总
• 关键标识：
◦ SST 、updateSpnDisplayLegacy 为核⼼关键字
◦ [0] 对应SIM 卡1，[1] 对应SIM 卡2
• 异常判断：与M TK 平台逻辑⼀致，对⽐配置值与实际显⽰结果即可定位问题
三、⾼通关键log
代码块
⽹络返回运营商名称：
09-29 13:57:20.674417 radio  4263  4321 D RILJ    : [9500]< OPERATOR {CMCC, 
CMCC, 46000} [PHONE0]
09-29 13:57:20.674663 radio  4263  5755 D RILJ    : [9505]< OPERATOR {CMCC, 
CMCC, 46000} [PHONE0]
09-29 13:57:20.675245 radio  4263  5755 D RILJ    : [9511]< OPERATOR {CMCC, 
CMCC, 46000} [PHONE0]
更新运营商名称显⽰：
09-29 13:57:20.686370 radio  4263  4263 D SST     : [0] 
getCarrierDisplayNameLegacy+
09-29 13:57:20.691339 radio  4263  4263 D SST     : [0] 
updateCarrierDisplayName: satellitePlmn=null
09-29 13:57:20.691536 radio  4263  4263 D SST     : [0] 
updateCarrierDisplayName: rawPlmn = CMCC
09-29 13:57:20.691563 radio  4263  4263 D SST     : [0] 
updateCarrierDisplayName: rawSpn = CMCC
09-29 13:57:20.691613 radio  4263  4263 D SST     : [0] 
getCarrierDisplayNameLegacy-
7
8
9
10
1
2
3
4
5
6
7
8
9
10
11

# Page 4
09-29 13:57:20.691668 radio  4263  4263 D SST     : [0] updateSpnDisplay: 
origin = Spn=CMCC, DataSpn=CMCC, ShowSpn=true, Plmn=CMCC, ShowPlmn=false
09-29 13:57:20.691706 radio  4263  4263 D SST     : [0] updateSpnDisplay: rule 
= 1
09-29 13:57:20.694175 radio  4263  4263 D SST     : [0] TDD updateSpnDisplay 
mSS.getOperatorNumeric() = 46000
09-29 13:57:20.694248 radio  4263  4263 D SST     : [0] QTI getNumeric 
simNumeric = 46002, operatorNumeric = 46000
09-29 13:57:20.694290 radio  4263  4263 D SST     : [0] QTI 
currentMccEqualsSimMcc simNumeric = 46002, operatorNumeric = 46000
09-29 13:57:20.694395 radio  4263  4263 D SST     : [0] updateSpnDisplay: 
spnName = CMCC , mNumeric = 46002
• 核⼼⽇志⽂件：QtiServiceStateTracker.java
• 关键标识：
◦ SST 、updateSpnDisplay 为核⼼关键字
◦ [0] 对应SIM 卡1，[1] 对应SIM 卡2
• 异常判断：与M TK 平台逻辑⼀致，对⽐配置值与实际显⽰结果即可定位问题
三、⽰例问题
⽰例⼀：http://jira.transsion.com /browse/S685LNOS15-299通过⽇志发现PLM N下发值为空导致显
⽰异常
 0-android.log
⽰例⼆：http://jira.transsion.com /browse/TOS1510-45066客制化SPN配置未覆盖多语⾔场景
⼆、APN错误
APN问题⼀般是测试指出APN与对⽐机不符，需要研发验证需求来源，是否需要修改
代码块
// 当前运营商已配置的 APN
03-19 12:03:46.369427  2549  2549 D DPM-0   : Added [DataProfile=[ApnSetting] 
CSL Data, 2649, 45400, hkcsl, 192.168.59.51, http://192.168.58.171:8002, 
192.168.59.51, 8080, 8080, 0, mms | supl | hipri | default, IP, IP, true, 0, 
false, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 
961, false, UNEDITED, TrafficDescriptor={mDnn=hkcsl, null}, preferred=false]
03-19 12:03:46.369716  2549  2549 D DPM-0   : Added [DataProfile=[ApnSetting] 
IMS, 2650, 45400, ims, , null, , null, null, 0, ims, IPV6, IPV6, true, 0, 
false, 0, 0, 0, 0, 0, null, , false, GPRS|EDGE|UMTS|CDMA|CDMA - EvDo rev. 
0|CDMA - EvDo rev. A|CDMA - 1xRTT|HSDPA|HSUPA|HSPA|CDMA - EvDo rev. B|LTE|CDMA 
12
13
14
15
16
17
1
2
3

# Page 5
- eHRPD|HSPA+|GSM|TD_SCDMA|IWLAN|LTE_CA|NR, UNKNOWN, 0, -1, -1, false, 3, 961, 
false, UNEDITED, TrafficDescriptor={mDnn=ims, null}, preferred=false]
03-19 12:03:46.369845  2549  2549 D DPM-0   : Added [DataProfile=[ApnSetting] 
HOS, 2651, 45400, HOS, , null, , null, null, 0, xcap, IP, IP, true, 0, false, 
0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 961, 
false, UNEDITED, TrafficDescriptor={mDnn=HOS, null}, preferred=false]
• 问题特征：测试反馈APN配置与对⽐机不符
• 处理流程：
a.验证需求来源，优先确认是否有运营商官⽅⽂档⽀撑
b.对⽐同平台基线版本APN配置差异
c.仅在需求明确且有官⽅依据时，执⾏APN修改操作
• 典型案例：
http://jira.transsion.com /browse/TOS1610-74748：因未同步运营商最新APN参数导致⽹络连接
失败
三、RAT和IM S图标显⽰问题
代码块
// 调制器返回当前时间⽹络注册情况
01-27 09:24:25.787161  2830  3275 D RILJ    : [8825]< DATA_REGISTRATION_STATE 
RegStateResult{regState: REG_HOME, rat: LTE_CA, reasonForDenial: NONE, 
cellIdentity: CellIdentity.lte(CellIdentityLte{mcc: 645, mnc: 02, ci: 
20567583, pci: 2147483647, tac: 11103, earfcn: 2147483647, operatorNames: 
OperatorInfo{alphaLong: 64502, alphaShort: 64502, operatorNumeric: , status: 
0}, bandwidth: 20000, additionalPlmns: [], csgInfo: null, bands: [BAND_1]}), 
registeredPlmn: 64502, accessTechnologySpecificInfo: 
AccessTechnologySpecificInfo.eutranInfo(EutranRegistrationInfo{lteVopsInfo: 
LteVopsInfo{isVopsSupported: true, isEmcBearerSupported: false}, nrIndicators: 
NrIndicators{isEndcAvailable: false, isDcNrRestricted: false, isNrAvailable: 
false}, lteAttachResultType: 2, extraInfo: 0})} [PHONE0]
//vowifi 注册状态
01-27 09:30:51.104218  2830  2830 D ImsPhoneCallTracker: [0] Do not switch WFC 
mode, isWfcEnabled:false, isEmergencyNumber:true, 
mCarrierSwitchWfcModeRequired:false
4
5
1
2
3
4
5
6

# Page 6
• ⽇志解读：
a.⾸条⽇志包含漫游状态、注册制式等核⼼信息，TOS16.2版本需同时具备数据能⼒才显⽰制式
图标
b.第⼆条⽇志打印VoW iFi等增值服务状态，可⽤于排查图标不显⽰问题
• 典型案例：
http://jira.transsion.com /browse/X6873OS162-302：因⽹络未返回可⽤DNS地址导致数据能⼒
异常
三、搜⽹问题
代码块
// ⼿动搜⽹返回的列表（ raido log ）
02-18 12:38:38.722099  2630  2958 D RILJ    : [5145]< MTK: 
QUERY_AVAILABLE_NETWORKS_WITH_ACT [OperatorInfo Jio True5G/Jio 
True5G/405858/CURRENT/0, OperatorInfo Jio True5G 4G/Jio True5G 
4G/405858/AVAILABLE/0, OperatorInfo Vi India 4G/Vi India 4G/40401/FORBIDDEN/0, 
OperatorInfo Airtel 4G/Airtel 4G/40496/FORBIDDEN/0, OperatorInfo BSNL MOBILE 
4G/BSNL MOBILE 4G/40451/FORBIDDEN/0, OperatorInfo BSNL MOBILE 4G/BSNL MOBILE 
4G/40434/FORBIDDEN/0, OperatorInfo BSNL MOBILE 3G/BSNL MOBILE 
3G/40434/FORBIDDEN/0, OperatorInfo BSNL MOBILE 2G/BSNL MOBILE 
2G/40434/FORBIDDEN/0, OperatorInfo Vi India 2G/Vi India 2G/40401/FORBIDDEN/0, 
OperatorInfo BSNL MOBILE 2G/BSNL MOBILE 2G/40451/FORBIDDEN/0, OperatorInfo 
Airtel 2G/Airtel 2G/40496/FORBIDDEN/0, OperatorInfo Airtel 5G/Airtel 
5G/40496/FORBIDDEN/0, OperatorInfo Vi India 4G/Vi India 4G/40482/FORBIDDEN/0, 
OperatorInfo Airtel 2G/Airtel 2G/40403/FORBIDDEN/0, OperatorInfo Vi India 
2G/Vi India 2G/40414/FORBIDDEN/0] [PHONE0]
// ⼿动搜⽹返回的结果（ main log ）
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: Sync network scan 
completed, cellInfos = {CellType = CellInfoGsm, isRegistered = true, mcc = 
405, mnc = 858, alphaL = Jio True5G, alphaS = Jio True5G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 405, mnc = 858, alphaL = Jio True5G 
4G, alphaS = Jio True5G 4G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 96, alphaL = Airtel 4G, 
alphaS = Airtel 4G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 34, alphaL = BSNL MOBILE 
4G, alphaS = BSNL MOBILE 4G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 01, alphaL = Vi India 4G, 
1
2
3
4
5
6
7
8
9

# Page 7
alphaS = Vi India 4G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 51, alphaL = BSNL MOBILE 
4G, alphaS = BSNL MOBILE 4G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 34, alphaL = BSNL MOBILE 
3G, alphaS = BSNL MOBILE 3G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 51, alphaL = BSNL MOBILE 
2G, alphaS = BSNL MOBILE 2G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 01, alphaL = Vi India 2G, 
alphaS = Vi India 2G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 96, alphaL = Airtel 2G, 
alphaS = Airtel 2G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 34, alphaL = BSNL MOBILE 
2G, alphaS = BSNL MOBILE 2G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 96, alphaL = Airtel 5G, 
alphaS = Airtel 5G}
02-18 12:38:06.720572 18973  3619 D NetworkScanHelper: {CellType = 
CellInfoGsm, isRegistered = false, mcc = 404, mnc = 03, alphaL = Airtel 2G, 
alphaS = Airtel 2G}
log解读：
• ⽇志解读：
a.⼿动搜⽹出现重复运营商名称时，需核查plmn 值是否⼀致，不同PLM N属于正常⽹络配置
b.CURRENT 标记当前驻留⽹络，AVAILABLE 为可接⼊⽹络，FORBIDDEN 为受限⽹络
• 典型案例：
http://jira.transsion.com /browse/X6873H972-4253：经⽇志核查为不同PLM N的同品牌运营商⽹
络
10
11
12
13
14
15
16
17
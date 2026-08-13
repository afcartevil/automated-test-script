# Page 1
框架侧Call问题分析sop
1.⽂档概述
1.1 ⽂档⽬的
本⽂档旨在帮助阅读者快速上⼿框架侧Call问题分析
1.2 适⽤范围
本⽂档适⽤通话相关问题框架部分分析，如⽆法呼出，⽆法收到来电，以及通话中出现的异常。
1.3阅读建议
2-3章为介绍call流程，可阅读学习。
4章为通话完整流程的关键⽇志，遇到问题时可以参考对⽐。
5章为Call问题分析流程
2.涉及模块

# Page 2
Applications
各种应⽤（⽐如Dialer，蓝⽛，⻋机）通过bindincallservice的⽅式从telecom获取call相关信息和下
达call相关指令。
Telecom 
1.Telecom为上层各个app提供统⼀的接⼝，提供状态等call相关信息，定义上层每个app⽀持的功
能。
2.Telecom控制call的⽣命周期。
3.Telecom负责通话过程中的⾳频策略控制。
4.Telecom管理多路通话。
Telephony
1.Telephony负责将通⽤的通话请求转化为具体的⽹络协议指令。

# Page 3
2.Telephony直接与RIL对话，下发相关指令和监听来⾃M odem的信号，实时维护着通话的物理状
态。
3.Telephony负责确定当前通话能够⽀持哪些媒体特性。
4.Telephony管理设备上的不同插槽（Slot）和订阅信息（subId），确保通话被分配到正确的SIM 
卡上。
TranRadioNet
公司客制化功能实现的地⽅，能对call做出管理，能为Applications提供各种客制化功能⽀持情况
RIL（涉及较少）
1.不同平台的项⽬M odem指令不同，但Telephony下发的指令基本相同，因此需要RIL作为中间层转
换指令。
2.M odem会主动上报⼀些状态变化，如新来电、信号强度变化、⽹络制式切换等，RIL将其转换并上
报给Telephony。
3.RIL将来⾃Telephony的指令转化为M odem能够理解的具体指令。
4.RIL负责管理所有下发指令的⽣命周期，确保每⼀个请求都能收到对应的响应或超时处理。
5.RIL允许不同平台各⾃的客制化功能。
M odem 
M odem处理RIL的指令，和基站进⾏交互。
3.Call模块知识⽂档
 Call业务拨号流程分享
 来电铃声渐响业务分享
 IM S来电流程分享
 会议电话业务流程分享
 紧急号码配置与问题分析
4.通话整体流程关键⽇志
4.1 拨打电话
关键词：
CallIntentProcessor
Telecom.*Event.*CREATED

# Page 4
AttemptingtobindtoInCall
Telecom.*ConnectionServiceWrapper.*creat
Telecom.*InCallController.*onConnected
Telephony.*onCreateOutgoingConnection
Telecom.*notifyCreateConnectionComplete
GsmCdmaPhone.*dial
handleDialResult
ImsPhoneCallTracker.*processCallStateChange.*ImsCall
Telecom.*setCallState
Telecom.*CONNECTION_EVENT.*EVENT_CALL_ALERTING_NOTIFICATION
Telecom.*SET_DISCONNECTED
pass例⼦：
代码块
//Telecom 收到拨号请求
09-24 14:53:19.123925  1550  2740 I Telecom-UserCallIntentProcessor: 
sendIntentToDestination: send intent to Telecom directly.: TSI.pC(cssc)@Rrk 
//Telecom 创建 Call, 编号为 TC@15
09-24 14:53:19.129573  1550  2740 I Telecom : Event: RecordEntry TC@15: 
CREATED, com.sh.smart.caller;requestedAcct:none, selfMgd:false: 
TSI.pC(cssc)@Rrk 🔒  
//Telecom 尝试绑定 InCallService
09-24 14:53:19.192971  1550  1550 I Telecom-
InCallController$EmergencyInCallServiceConnection: Attempting to bind to 
InCall 
[ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl} 
supportsExternal? true supportsSelfMg?false], with Intent { 
act=android.telecom.InCallService 
cmp=com.sh.smart.caller/com.android.incallui.InCallServiceImpl (has extras) }: 
TSI.pC->CILH.sL->CILH.oQC->CM.sOCPA->CM.dSMCP->CM.dSPA(cssc)@Rrk 
//Telecom 绑定 InCallService 成功，使 dialer 启动 InCall 界⾯
09-24 14:53:19.241742  1550  1550 I Telecom-InCallController: onConnected to 
ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl}: 
ICSBC.oSC(cssc)@Rrs 
//Telecom 尝试创建 TelephonyConnectionService
09-24 14:53:25.101784  1550  2901 I Telecom-ConnectionServiceWrapper: 
createConnection([Call id=TC@15, state=CONNECTING, 
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, 
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
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

# Page 5
nnectionService}, 2, UserHandle{0}, handle=tel:*********82, vidst=A, 
childs(0), has_parent(false), mtkcap=[], mtkprop=[], cap=[], prop=[]], 
voip=false) via 
ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnect
ionService}.: TSI.pC->CIP.sNOCI->CSFM.rF(cssc)@Rrk 
//TelephonyConnectionService 创建
09-24 14:53:25.132517  2673  2673 I Telephony: onCreateOutgoingConnection, 
request: ConnectionRequest xxxxxxxxxxxxxxx 
Bundle[android.telecom.extra.START_CALL_WITH_VIDEO_STATE=0, 
android.telecom.extra.CALL_CREATED_TIME_MILLIS=97933471, 
android.telecom.extra.CALL_TELECOM_ROUTING_START_TIME_MILLIS=97939432, 
com.android.dialer.callintent.CALL_SPECIFIC_APP_DATA=[B@2c72f13, ] 
isAdhocConf: N 
// 流程⾛到 GsmCdmaPhone 拨号
09-24 14:53:25.143023  2673  2673 I GsmCdmaPhone: [1] dial; isEmergency=false 
(based on all phones) 
//GsmCdmaPhone 根据 useImsForCall 判断是否是 IMS call
09-24 14:53:25.151334  2673  2673 I GsmCdmaPhone: [1] useImsForCall=true, 
useOnlyDialedSimEccList=false, isEmergency=false, useImsForEmergency=false, 
useImsForUt=true, isUt=false, isSuppServiceCode=false, 
isPotentialUssdCode=false, isWpsCall=false, allowWpsOverIms=true, 
imsPhone=Handler (com.mediatek.internal.telephony.imsphone.MtkImsPhone) 
{e6eb154}, imsPhone.isVoiceOverCellularImsEnabled()=true, 
imsPhone.isVowifiEnabled()=false, imsPhone.isVideoEnabled()=true, 
imsPhone.getServiceState().getState()=0 
// 仅 IMS call 会打印，底层拨打成功
09-24 14:53:25.224672  2692  2692 D ImsCallSessionProxy: [callId = null] 
handleDialResult() success 
//Telecom 进⼊ dialing 状态
09-24 14:53:25.328646  1550  4067 I Telecom-CallsManager: setCallState 
CONNECTING -> DIALING, call: [Call id=TC@15, state=CONNECTING, 
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, 
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, handle=tel:*********82, vidst=A, 
childs(0), has_parent(false), mtkcap=[ sup_hld mut !v2a], mtkprop=[ m_volte], 
cap=[ sup_hld mut !v2a], prop=[]], voip=false: (...->CS.crCo->H.CS.crCo-
>H.CS.crCo.pICR)->CSW.hCCC(cap/cast)@E-E-RtU 
//TelephonyConnectionService 创建完成
09-24 14:53:25.468164  2673  2673 I TelecomFramework: 
TelephonyConnectionService: notifyCreateConnectionComplete TC@15_1: (...-
>CSW.hCCC)->CS.crCoC->H.CS.crCoC(cap/cast)@E-E-E-RtU 
// 仅 IMS call 会打印，收到底层呼通消息，代表对端收到来电， telephony 的 call 状态切成
ALERTING
09-24 14:53:27.393822  2673  2673 D ImsPhoneCallTracker: [1] 
processCallStateChange [ImsCall objId:46059387 onHold:N mute:N mCallProfile:{ 
serviceType=1, callType=2, restrictCause=0, mediaProfile={ audioQuality=0, 
11
12
13
14
15
16
17
18
19
20
21
22
23
24

# Page 6
audioDirection=1, audioCodecAttribute=null, videoQuality=0, videoDirection=-1, 
rttMode=0, hasRttAudioSpeech=false }, emergencyServiceCategories=0, 
emergencyUrns=[], emergencyCallRouting=0, emergencyCallTesting=false, 
hasKnownUserIntentEmergency=false, mRestrictCause=0, mCallerNumberVerstat= 0, 
mAcceptedRtpHeaderExtensions= [] } networkType:13 updateRequest:NONE merging:N 
merge action pending:N merged:N multiParty:N confHost:N buried term:N isVideo: 
N wasVideo: N isWifi: N session:[ImsCallSession objId:68709130 callId:
[UNINITIALIZED]] transientSession:null] state=ALERTING cause=0
//telecom 收到 telephony alerting 消息
09-24 14:53:27.455055  1550  3025 I Telecom : Event: RecordEntry TC@15: 
CONNECTION_EVENT, mediatek.telecom.event.EVENT_CALL_ALERTING_NOTIFICATION: 
CSW.oCE(cap)@RwE 🔒  //telecom 收到 telephony alerting 消息
// 仅 IMS call 会打印，收到底层接通消息，代表对端接听来电， telephony 的 call 状态切成 ACTIVE
09-24 14:53:34.771358  2673  2673 D ImsPhoneCallTracker: [1] 
processCallStateChange [ImsCall objId:46059387 onHold:N mute:N mCallProfile:{ 
serviceType=1, callType=2, restrictCause=0, mediaProfile={ audioQuality=0, 
audioDirection=3, audioCodecAttribute=null, videoQuality=0, videoDirection=-1, 
rttMode=0, hasRttAudioSpeech=false }, emergencyServiceCategories=0, 
emergencyUrns=[], emergencyCallRouting=0, emergencyCallTesting=false, 
hasKnownUserIntentEmergency=false, mRestrictCause=0, mCallerNumberVerstat= 0, 
mAcceptedRtpHeaderExtensions= [] } networkType:13 updateRequest:NONE merging:N 
merge action pending:N merged:N multiParty:N confHost:N buried term:N isVideo: 
N wasVideo: N isWifi: N session:[ImsCallSession objId:68709130 callId:1] 
transientSession:null] state=ACTIVE cause=0
//telecom 进⼊ ACTIVE 状态
09-24 14:53:34.791967  1550  4067 I Telecom-CallsManager: setCallState DIALING 
-> ACTIVE, call: [Call id=TC@15, state=DIALING, 
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, 
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, handle=tel:*********82, vidst=A, 
childs(0), has_parent(false), mtkcap=[ sup_hld mut], mtkprop=[ HD m_volte], 
cap=[ sup_hld mut], prop=[ HD]], voip=false: CSW.sA(cap)@RxI 
// 通话结束，打印挂断原因
09-24 14:53:42.256144  1550  4083 I Telecom : Event: RecordEntry TC@15: 
SET_DISCONNECTED, disconnected set explicitly> DisconnectCause [ Code: (LOCAL) 
Label: () Description: () Reason: (LOCAL) Tone: (27)  TelephonyCause: 3/-1 
ImsReasonInfo: ImsReasonInfo :: {504 : CODE_USER_DECLINE, 0, null}]: 
CSW.sDc(cap)@Ryg 🔒  
4.2 来电接听
关键词：
EVENT_CALL_RING
notifyNewRingingConnection
25
26
27
28
29
30
31
32

# Page 7
Telecom.*Event.*CREATED
Telecom.*ConnectionServiceWrapper.*creat
Telephony.*onCreateIncomingConnection
Telecom.*notifyCreateConnectionComplete
IncomingCallFilterGraph.*result
Telecom.*setCallState
isNeedDisturb
AttemptingtobindtoInCall
Telecom.*InCallController.*onConnected
DialerCall.*answer
Telecom.*AnswerRinging
Telecom.*SET_DISCONNECTED
pass例⼦：
代码块
//Telephony 收到来电请求
09-24 14:53:58.257287  2673  2673 D Phone-1 : Event EVENT_CALL_RING Received 
state=IDLE
//Telephony 发送来电请求通知
09-24 14:53:58.299244  2673  2673 I Phone-1 : notifyNewRingingConnection: 
phoneId=[1], connection=[[ImsPhoneConnection objId: 167206028 telecomCallID: 
null address: [BFlYyvCUId8-5BXPkqC93V8lOG0] isAdhocConf: N ImsCall: [ImsCall 
objId:103787967 onHold:N mute:N mCallProfile:{ serviceType=1, callType=2, 
restrictCause=0, mediaProfile={ audioQuality=0, audioDirection=3, 
audioCodecAttribute=null, videoQuality=0, videoDirection=-1, rttMode=0, 
hasRttAudioSpeech=false }, emergencyServiceCategories=0, emergencyUrns=[], 
emergencyCallRouting=0, emergencyCallTesting=false, 
hasKnownUserIntentEmergency=false, mRestrictCause=0, mCallerNumberVerstat= 0, 
mAcceptedRtpHeaderExtensions= [] } networkType:13 updateRequest:NONE merging:N 
merge action pending:N merged:N multiParty:N confHost:N buried term:N isVideo: 
N wasVideo: N isWifi: N session:[ImsCallSession objId:46958558 callId:1] 
transientSession:null]] state:INCOMING mParent:Ringing Call], registrants=
[com.android.internal.telephony.Registrant@a03b578, 
com.android.internal.telephony.Registrant@7af0451] 
//Telecom 创建 Call, 编号为 TC@16
09-24 14:53:58.336347  1550  4088 I Telecom : Event: RecordEntry TC@16: 
CREATED, null;null: TSI.aNIC(cap)@R0I 🔒  
//Telecom 尝试创建 TelephonyConnectionService
09-24 14:53:58.345822  1550  4088 I Telecom-ConnectionServiceWrapper: 
createConnection([Call id=TC@16, state=NEW, 
1
2
3
4
5
6
7
8

# Page 8
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, 
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, handle=tel:*********73, vidst=A, 
childs(0), has_parent(false), mtkcap=[], mtkprop=[], cap=[], prop=[]], 
voip=false) via 
ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnect
ionService}.: TSI.aNIC(cap)@R0I 
//TelephonyConnectionService 创建
09-24 14:53:58.420918  2673  2673 I Telephony: onCreateIncomingConnection, 
request: ConnectionRequest xxxxxxxxxxxxxxx 
Bundle[android.telecom.extra.INCOMING_CALL_ADDRESS=***, 
android.telecom.extra.CALL_SUBJECT=, 
mediatek.telecom.extra.EXTRA_INCOMING_GWSD=false, 
android.telecom.extra.LOCATION=null, android.telecom.extra.PRIORITY=-1, 
android.telecom.extra.CALL_CREATED_TIME_MILLIS=97972674, 
android.telecom.extra.CALL_TELECOM_ROUTING_START_TIME_MILLIS=97972690, ] 
isAdhocConf: N 
//TelephonyConnectionService 创建完成
09-24 14:53:58.492788  2673  2673 I TelecomFramework: 
TelephonyConnectionService: notifyCreateConnectionComplete TC@16_1: (...-
>CSW.hCCC)->CS.crCoC->H.CS.crCoC(cap/cast)@E-E-E-R0Q 
// 骚扰拦截检查允许来电
09-24 14:53:58.576701  1550 31466 I Telecom : IncomingCallFilterGraph: Filter 
com.android.server.telecom.callfiltering.CallFilter@ed85b16 done, result: 
[Allow, logged, notified]. 
//Telecom 切换到 RINGING 状态
09-24 14:53:58.578045  1550 31466 I Telecom-CallsManager: setCallState NEW -> 
RINGING, call: [Call id=TC@16, state=NEW, 
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, 
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, handle=tel:*********73, vidst=A, 
childs(0), has_parent(false), mtkcap=[ sup_hld mut spd_aud], mtkprop=[ 
m_volte], cap=[ sup_hld mut spd_aud], prop=[]], voip=false 
//isNeedDisturb( 勿扰模式 ) 未打开
09-24 14:53:58.579089  1550 31466 I Telecom : TranCallState: 
isNeedDisturbfalse 
//Telecom 尝试绑定 InCallService
09-24 14:53:58.623873  1550 31466 I Telecom-
InCallController$EmergencyInCallServiceConnection: Attempting to bind to 
InCall 
[ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl} 
supportsExternal? true supportsSelfMg?false], with Intent { 
act=android.telecom.InCallService 
cmp=com.sh.smart.caller/com.android.incallui.InCallServiceImpl } 
//Telecom 绑定 InCallService 成功，使 dialer 启动 InCall 界⾯
9
10
11
12
13
14
15
16
17
18
19
20
21

# Page 9
09-24 14:53:58.703295  1550  1550 I Telecom-InCallController: onConnected to 
ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl}: 
ICSBC.oSC(cssc)@R0Y 
// ⽤⼾点击接听
09-24 14:54:04.114520  4302  4302 I Dialer  : DialerCall.answer - videoState: 
0 
//Telecom 收到接听命令
09-24 14:54:04.116688  1550  2346 I Telecom-CallsManager: 
holdActiveAndAnswerRinging, newCall: [Call id=TC@16, state=RINGING, 
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, 
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, handle=tel:*********73, vidst=A, 
childs(0), has_parent(false), mtkcap=[ sup_hld mut spd_aud], mtkprop=[ 
m_volte], cap=[ sup_hld mut spd_aud], prop=[]], voip=false, activeCall: null: 
ICA.aC(cssc)@R14 
//Telecom 切到 ANSWERED 状态
09-24 14:54:04.130427  1550  2901 I Telecom-CallsManager: setCallState RINGING 
-> ANSWERED, call: [Call id=TC@16, state=RINGING, 
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, 
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, handle=tel:*********73, vidst=A, 
childs(0), has_parent(false), mtkcap=[ sup_hld mut spd_aud], mtkprop=[ 
m_volte], cap=[ sup_hld mut spd_aud], prop=[]], voip=false: ICA.aC-
>CSFM.rF(cssc)@R14 
// 通话接通， Telecom 切到 ANSWERED 状态
09-24 14:54:04.234185  1550  3022 I Telecom-CallsManager: setCallState 
ANSWERED -> ACTIVE, call: [Call id=TC@16, state=ANSWERED, 
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, 
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyCo
nnectionService}, 2, UserHandle{0}, handle=tel:*********73, vidst=A, 
childs(0), has_parent(false), mtkcap=[ sup_hld mut VTlrx VTltx VTlbi VTrrx 
VTrtx VTrbi spd_aud paus_VT], mtkprop=[ m_volte], cap=[ sup_hld mut VTlrx 
VTltx VTlbi VTrrx VTrtx VTrbi spd_aud paus_VT], prop=[]], voip=false: 
CSW.sA(cap)@R2M 
// 通话结束，打印挂断原因
09-24 14:54:11.582772  1550  4082 I Telecom : Event: RecordEntry TC@16: 
SET_DISCONNECTED, disconnected set explicitly> DisconnectCause [ Code: 
(REMOTE) Label: () Description: () Reason: (NORMAL) Tone: (27)  
TelephonyCause: 2/-1 ImsReasonInfo: ImsReasonInfo :: {510 : 
CODE_USER_TERMINATED_BY_REMOTE, 0, null}]: CSW.sDc(cap)@R4I 🔒  
5.问题分析流程
22
23
24
25
26
27
28
29
30
31
32

# Page 10
5.1 排除⼿机外部因素
需要其他⼿机按照以下步骤对⽐测试。测试机（DUT）和对⽐机（REF）如果现象⼀致，则⾮⼿机问
题。现象⼀致，则为有效问题，需进⼀步分析。
1.DUT与REF确保在相同位置，且设置的功能开关保持⼀致。尤其注意sim卡与⽹络，骚扰拦截和勿
扰模式的设置。
2.DUT测试后⽴刻将SIM 卡插⼊REF，进⾏相同操作。或DUT与REF插⼊相同运营商的卡同时操作，然
后换卡再同时操作。
5.2 ⽇志确认
1.⽇志抓取⽅法
参考 《⼯具安装与环境配置指南》
2.会使⽤到的log⽂件
M TK:
M obilelog/APLog*
展锐：ylog/ap/*

# Page 11
展锐android.log为main、radio和sys的整合，可以直接看，展锐没有crashlog。
主要使⽤main_log、radio_log和sys_log，crash_log和events_log只在提到的时候进去搜。
3.根据视频确认对应时间的log是否有抓到。
4.推荐使⽤Notepad++打开log，使⽤正则表达式搜索log。
5.3基础⽇志分析流程
Outgoingcall:

# Page 12

# Page 13
Incomingcall:
5.3.1 Telecom .*Event.*CREATED

# Page 14
在sys_log中搜索Telecom.*Event.*CREATED，此log表⽰Telecom建⽴通话的时间点，⾥⾯能知道
CallId（TC@15）这个重要信息，如果是拨号，则此log还会包含⽤⼾是⽤的拨号应⽤
（com.sh.smart.caller），以及⽤⼾指定的拨号sim卡。
例⼦：
09-2414:53:19.12957315502740ITelecom:Event:RecordEntryTC@15:CREATED,
com.sh.smart.caller;requestedAcct:none,selfM gd:false:TSI.pC(cssc)@Rrk 🔒 
5.3.2 setCallState
sys_log⾥搜索setCallState，找出对应CallId的所有log。这些log会记录此通电话的完整周期的状态切
换，以及call所拥有的能⼒，此处重点关注call的状态切换。
例⼦：
03-0615:14:27.26198117871949ITelecom-CallsM anager:setCallStateCONNECTING->
DIALING,call:[Callid=TC@33,state=CONNECTING,
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectio
nService},3,UserHandle{0},
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnecti
onService},3,UserHandle{0},handle=tel:***********,vidst=A,childs(0),has_parent(false),
mtkcap=[sup_hldmut!v2a],mtkprop=[m_volte],cap=[sup_hldmut!v2a],prop=[]],voip=false:
(...->CS.crCo->H.CS.crCo->H.CS.crCo.pICR)->CSW.hCCC(cap/cast)@E-E-FK8
03-0615:14:33.15187617872508ITelecom-CallsM anager:setCallStateDISCONNECTING->
DISCONNECTED,call:[Callid=TC@33,state=DISCONNECTING,
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectio
nService},3,UserHandle{0},
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnecti
onService},3,UserHandle{0},handle=tel:***********,vidst=A,childs(0),has_parent(false),
mtkcap=[sup_hldmut],mtkprop=[HDm_volte],cap=[sup_hldmut],prop=[HD]],voip=false:
CSW.sDc(cap)@FOo
🎼Call的所有状态有，常⻅的⽤红⾊标记
/**
*Indicatesthatacallisnewandnotconnected.Thisisusedasthedefaultstate
internally
*withinTelecomandshouldnotbeusedbetweenTelecomandcallservices.Call
servicesare
*notexpectedtoeverinteractwithNEWcalls,but{@link
android.telecom.InCallService}swill

# Page 15
*seecallsinthisstate.
*/
publicstaticfinalintNEW=TelecomProtoEnums.NEW;//=0
/**
*Theinitialstateofanoutgoing{@codeCall}.
*Commontransitionsareto{@link#DIALING}stateforasuccessfulcallor
*{@link#DISCONNECTED}ifitfailed.
*/
publicstaticfinalintCONNECTING=TelecomProtoEnums.CONNECTING;//=1
/**
*Thestateofanoutgoing{@codeCall}whenwaitingonusertoselecta
*{@linkandroid.telecom.PhoneAccount}throughwhichtoplacethecall.
*/
publicstaticfinalintSELECT_PHONE_ACCOUNT=
TelecomProtoEnums.SELECT_PHONE_ACCOUNT;//=2
/**
*Indicatesthatacallisoutgoingandinthedialingstate.Acalltransitionstothis
state
*onceanoutgoingcallhasbegun(e.g.,userpressesthedialbuttoninDialer).Calls
inthis
*stateusuallytransitionto{@link#ACTIVE}ifthecallwasansweredor{@link
#DISCONNECTED}
*ifthecallwasdisconnectedsomehow(e.g.,failureorcancellationofthecallbythe
user).
*/
publicstaticfinalintDIALING=TelecomProtoEnums.DIALING;//=3
/**

# Page 16
*Indicatesthatacallisincomingandtheuserstillhastheoptionofanswering,
rejecting,
*ordoingnothingwiththecall.Thisstateisusuallyassociatedwithsometypeof
audible
*ringtone.Normaltransitionsareto{@link#ACTIVE}ifansweredor{@link
#DISCONNECTED}
*otherwise.
*/
publicstaticfinalintRINGING=TelecomProtoEnums.RINGING;//=4
/**
*Indicatesthatacalliscurrentlyconnectedtoanotherpartyandacommunication
channelis
*openbetweenthem.Thenormaltransitiontothisstateisbytheuseransweringa
*{@link#DIALING}callora{@link#RINGING}callbeingansweredbytheotherparty.
*/
publicstaticfinalintACTIVE=TelecomProtoEnums.ACTIVE;//=5
/**
*Indicatesthatthecalliscurrentlyonhold.Inthisstate,thecallisnotterminated
*butnocommunicationisalloweduntilthecallisnolongeronhold.Thetypical
transition
*tothisstateisbytheuserputtingan{@link#ACTIVE}callonholdbyexplicitly
performing
*anaction,suchasclickingtheholdbutton.
*/
publicstaticfinalintON_HOLD=TelecomProtoEnums.ON_HOLD;//=6
/**
*Indicatesthatacalliscurrentlydisconnected.Allstatescantransitiontothisstate
*bythecallservicegivingnoticethattheconnectionhasbeensevered.Whenthe
user

# Page 17
*explicitlyendsacall,itwillnottransitiontothisstateuntilthecallserviceconfirms
*thedisconnectionorcommunicationwaslosttothecallservicecurrently
responsiblefor
*thiscall(e.g.,callservicecrashes).
*/
publicstaticfinalintDISCONNECTED=TelecomProtoEnums.DISCONNECTED;//=7
/**
*Indicatesthatthecallwasattempted(mostlyinthecontextofoutgoing,atleastat
the
*timeofwriting)butcancelledbeforeitwassuccessfullyconnected.
*/
publicstaticfinalintABORTED=TelecomProtoEnums.ABORTED;//=8
/**
*Indicatesthatthecallisintheprocessofbeingdisconnectedandwilltransition
next
*toa{@link#DISCONNECTED}state.
*<p>
*ThisstateisnotexpectedtobecommunicatedfromtheTelephonylayer,butwillbe
reported
*totheInCallUIforcallswheredisconnectionhasbeeninitiatedbytheuserbutthe
*ConnectionServicehasconfirmedthecallasdisconnected.
*/
publicstaticfinalintDISCONNECTING=TelecomProtoEnums.DISCONNECTING;//=9
/**
*Indicatesthatthecallisintheprocessofbeingpulledtothelocaldevice.
*<p>
*Thisstateshouldonlybesetonacallwith
*{@linkandroid.telecom.Connection#PROPERTY_IS_EXTERNAL_CALL}and
*{@linkandroid.telecom.Connection#CAPABILITY_CAN_PULL_CALL}.

# Page 18
*/
publicstaticfinalintPULLING=TelecomProtoEnums.PULLING;//=10
/**
*Indicatesthatanincomingcallhasbeenansweredbythein-callUI,butTelephony
hasn'tyet
*setthecalltoactive.
*/
publicstaticfinalintANSWERED=TelecomProtoEnums.ANSWERED;//=11
/**
*Indicatesthatthecallisundergoingaudioprocessingbyadifferentappinthe
background.
*@seeandroid.telecom.Call#STATE_AUDIO_PROCESSING
*/
publicstaticfinalintAUDIO_PROCESSING=
TelecomProtoEnums.AUDIO_PROCESSING;//=12
/**
*Indicatesthatthecallisinafakeringingstate.
*@seeandroid.telecom.Call#STATE_SIM ULATED_RINGING
*/
publicstaticfinalintSIM ULATED_RINGING=
TelecomProtoEnums.SIM ULATED_RINGING;//=13
5.3.3Telecom .*notifyCreateConnectionCom plete
sys_log中搜索Telecom.*notifyCreateConnectionComplete，找的对应CallId的log，此log表⽰
telecom与telephony之间已建⽴连接
例⼦：
09-2414:53:25.46816426732673ITelecomFramework:TelephonyConnectionService:
notifyCreateConnectionCompleteTC@15_1:(...->CSW.hCCC)->CS.crCoC-
>H.CS.crCoC(cap/cast)@E-E-E-RtU

# Page 19
🌟注意
部分通话会有重新建⽴的功能，这⾥的CallId⽐之前多了"_"后的⼀部分，这⼀部分表⽰建⽴
次数，如1表⽰第⼀次建⽴。
5.3.4 notifyNewRingingConnection
radio_log中搜notifyNewRingingConnection，此log表⽰底层上报来电通知
例⼦：
09-2414:53:58.29924426732673IPhone-1:notifyNewRingingConnection:phoneId=[1],
connection=[[ImsPhoneConnectionobjId:167206028telecomCallID:nulladdress:[BFlYyvCUId8-
5BXPkqC93V8lOG0]isAdhocConf:NImsCall:[ImsCallobjId:103787967onHold:Nmute:N
mCallProfile:{serviceType=1,callType=2,restrictCause=0,mediaProfile={audioQuality=0,
audioDirection=3,audioCodecAttribute=null,videoQuality=0,videoDirection=-1,rttM ode=0,
hasRttAudioSpeech=false},emergencyServiceCategories=0,emergencyUrns=[],
emergencyCallRouting=0,emergencyCallTesting=false,hasKnownUserIntentEmergency=false,
mRestrictCause=0,mCallerNumberVerstat=0,mAcceptedRtpHeaderExtensions=[]}
networkType:13updateRequest:NONEmerging:Nmergeactionpending:Nmerged:N
multiParty:NconfHost:Nburiedterm:NisVideo:NwasVideo:NisWifi:Nsession:[ImsCallSession
objId:46958558callId:1]transientSession:null]]state:INCOM INGmParent:RingingCall],
registrants=[com.android.internal.telephony.Registrant@a03b578,
com.android.internal.telephony.Registrant@7af0451]
🎨按照正常流程，此时为底层上报来电通知，telecom还未收通知到并作处理，因此CallId还未
创建，所以此log需根据问题时间点匹配
5.4根据问题场景进⼀步确认log
📚可以将搜索出来的log按时间顺序整理，然后给到AI，告诉AI需要分析的问题以及对应call的
Callid
5.4.1 Telecom Anom aly
关键词：CallsM anager
此情况⼀般为telecom阻⽌了通话，在sys_log中搜索CallsM anager寻找中断的原因。
找出原因后需要对⽐代码检查问题。建议提交CR咨询。
✏案例：

# Page 20
TC@5这通电话create后⽆后续流程，搜索log后得知原因是noavailableaccounts
03-0509:52:45.84798219172914ITelecom:Event:RecordEntryTC@5:CREATED,
com.sh.smart.caller;requestedAcct:ComponentInfo{com.android.phone/com.android.s
ervices.telephony.TelephonyConnectionService},1,UserHandle{0},selfM gd:false:
TSI.pC(cssc)@Al8
03-0509:52:45.86727319171917ITelecom-CallsM anager:Abortingcallsincethereare
noavailableaccounts.:TSI.pC->CM .fOCP->CM .sOCPA->CM .dSM CP->CM .mROC-
>CM .dSPA(cssc)@Al8
5.4.2 TelephonyAnom aly
关键词：com.android.phone
此情况⼀般为Telephonycrash导致，crash_log、events_log或main_log中搜索
com.android.phone，检查问题时间附近是否有进程崩溃
例⼦：
代码块
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: FATAL EXCEPTION: main
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: Process: 
com.android.phone, PID: 8540
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: 
android.os.BadParcelableException: ClassNotFoundException when unmarshalling: 
com.transsion.widgetslib.preference.OSDialogPreference$SavedState
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
android.os.Parcel.readParcelableCreatorInternal(Parcel.java:5356)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
android.os.Parcel.readParcelableInternal(Parcel.java:5205)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
android.os.Parcel.readParcelable(Parcel.java:5176)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
android.view.AbsSavedState.<init>(AbsSavedState.java:67)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
android.view.AbsSavedState.<init>(AbsSavedState.java:56)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
android.preference.Preference$BaseSavedState.<init>(Preference.java:2104)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
com.transsion.widgetslib.preference.OSEditTextPreference$SavedState.<init>
(OSEditTextPreference.java:205)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
com.transsion.widgetslib.preference.OSEditTextPreference$SavedState$1.createFro
mParcel(OSEditTextPreference.java:222)
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

# Page 21
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
com.transsion.widgetslib.preference.OSEditTextPreference$SavedState$1.createFro
mParcel(OSEditTextPreference.java:220)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
android.os.Parcel.readParcelableInternal(Parcel.java:5214)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
android.os.Parcel.readValue(Parcel.java:4965)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
android.os.Parcel.readValue(Parcel.java:4701)
02-07 05:41:44.091218 radio 8540 8540 E AndroidRuntime: at 
android.os.Parcel.-$$Nest$mreadValue(Unknown Source:0)
5.4.3拨号⽆法呼通
1.5.4.1以及5.4.2的情况均会导致此问题，请先确认5.4.1和5.4.2
2.若确认⽆5.4.1和5.4.2的问题，说明拨号流程已⾛完，在等待modem反馈呼通。此类问题⼀般为
modem⻓时间未反馈呼通导致。
关键词：Telecom.*SET_DISCONNECTED
在sys_log中搜索Telecom.*SET_DISCONNECTED，确认挂断原因。将挂断原因给到Modem继续分析
🎁案例
⽆法呼通，M odem反馈error，由M odem继续分析
01-2919:52:32.4690431000310510387ITelecom:Event:RecordEntryTC@5:
SET_DISCONNECTED,disconnectedsetexplicitly>DisconnectCause[Code:(ERROR)
Label:()Description:()Reason:(ERROR_UNSPECIFIED)Tone:(27)TelephonyCause:
36/-1ImsReasonInfo:ImsReasonInfo::{0:CODE_UNSPECIFIED,0,null}]:
CSW.sDc(cap)@BL8
5.4.4 ⽆法收到来电
1.此问题需要先确认骚扰拦截和勿扰模式情况
2.5.4.1以及5.4.2的情况均会导致此问题，请先确认5.4.1和5.4.2
3.确认⽆上述问题，则来电流程已⾛完，需确认视频，如没有来电界⾯显⽰，参考5.4.6
4.如果为没有来电铃声
关键词：
CallAudio
sys_log中搜索CallAudio，确认响铃情况
例⼦
12
13
14
15
16

# Page 22
03-0414:58:47.62161320468378ITelecom-CallAudioM anager:onCallEnteringRinging:
mFeatureFlags.separatelyBindToBtIncallService()?true:NCSSF.aC->ICFG.sF->ICFG.sF-
>ICFG.sF@AT4
03-0414:58:47.69602120463127ITelecom-CallAudioM odeStateM achine:M essagereceived:
NEW_RINGING_CALL.:NCSSF.aC->ICFG.sF->ICFG.sF->ICFG.sF->CAM .oCER-
>CAM SM .pM _2002@AT4
03-0414:58:47.69626820463127ITelecom-CallAudioM odeStateM achine:Audiofocusentering
RINGINGstate:NCSSF.aC->ICFG.sF->ICFG.sF->ICFG.sF->CAM .oCER->CAM SM .pM _2002@AT4
03-0414:58:47.71571420463127ITelecom-CallAudioM odeStateM achine$RingingFocusState:
tryStartRinging:AudioM anager#requestAudioFocus(RING):NCSSF.aC->ICFG.sF->ICFG.sF-
>ICFG.sF->CAM .oCER->CAM SM .pM _2002@AT4
03-0414:58:47.71988820463127ITelecom-CallAudioM odeStateM achine$RingingFocusState:
enter:AudioM anager#setM ode(M ODE_RINGTONE):NCSSF.aC->ICFG.sF->ICFG.sF->ICFG.sF-
>CAM .oCER->CAM SM .pM _2002@AT4
5.4.5 通话期间异常挂断
关键词：Telecom.*SET_DISCONNECTED
在sys_log中搜索Telecom.*SET_DISCONNECTED，确认挂断原因。
1.若挂断原因为remote，则为对端挂断，⾮异常。
2.若挂断原因为error，则需M odem确认
3.若挂断原因为local，则需继续确认
关键词:
hangup
hangup
在sys_log,main_log和radio_log中搜索，定位挂断地⽅，定位后需要代码确认，可咨询中国同事
🎉案例
vowifi环境变化，为保证active通话正常，系统⾃动挂断响ringing和hold的通话。
02-2211:02:37.74116728043147ITranVoWifiDualCallController:
hangupHoldOrRingingCall:reason:8216
02-2211:02:38.03623519502486ITelecom-CallsM anager:setCallState
DISCONNECTING->DISCONNECTED,call:[Callid=TC@417,state=DISCONNECTING,
tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyC
onnectionService},8,UserHandle{0},
cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.Telephony

# Page 23
ConnectionService},8,UserHandle{0},handle=tel:**********,vidst=A,childs(0),
has_parent(false),mtkcap=[sup_hldmut],mtkprop=[wifim_volte],cap=[sup_hld
mut],prop=[wifi]],voip=false:CSW.sDc(cap)@1oU
02-2211:02:38.03646119502486ITelecom:Event:RecordEntryTC@417:
SET_DISCONNECTED,disconnectedsetexplicitly>DisconnectCause[Code:(LOCAL)
Label:()Description:()Reason:(LOCAL)Tone:(27)TelephonyCause:3/-1
ImsReasonInfo:ImsReasonInfo::{504:CODE_USER_DECLINE,0,null}]:
CSW.sDc(cap)@1oU
5.4.6 ⽆通话界⾯问题
关键词：
AttemptingtobindtoInCall
Telecom.*InCallController.*onConnected
在sys_log中搜索，此log代表telecom与dialer连接，onConnected表⽰成功。
例⼦：
09-2414:53:58.623873155031466ITelecom-
InCallController$EmergencyInCallServiceConnection:AttemptingtobindtoInCall
[ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl}
supportsExternal?truesupportsSelfM g?false],withIntent{act=android.telecom.InCallService
cmp=com.sh.smart.caller/com.android.incallui.InCallServiceImpl}
09-2414:53:58.70329515501550ITelecom-InCallController:onConnectedto
ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl}:
ICSBC.oSC(cssc)@R0Y
1.若仅有AttemptingtobindtoInCall的log，则bind失败，⼀般为系统阻塞，可以提cr咨询
2.连接成功，则需要dialermodel确认此问题
5.4.7 免提听筒切换异常
关键词：
Dialer.*setAudioRoute
CallAudioRouteStateM achine
此类问题需要与⾳频模块⼀起确认。
main_log中搜Dialer.*setAudioRoute，可以得知⽤⼾点击切换的事件
sys_log中搜CallAudioRouteStateM achine，⾥⾯可以得知当前通话模式，以及⽀持的模式。

# Page 24
🐵案例：
⽤⼾多次切换免提与听筒，Telecom收到的⼴播消息延迟，导致状态混乱。
03-2118:46:49.6272701021610216IDialer:CallButtonPresenter.setAudioRoute-
sendingnewaudioroute:SPEAKER
03-2118:46:50.16563016544569ITelecom-CallAudioRouteStateM achine:
setSystemAudioState:changingfrom[AudioStateisM uted:false,route:EARPIECE,
supportedRouteM ask:EARPIECE,SPEAKER,activeBluetoothDevice:[],
supportedBluetoothDevices:[]]to[AudioStateisM uted:false,route:SPEAKER,
supportedRouteM ask:EARPIECE,SPEAKER,activeBluetoothDevice:[],
supportedBluetoothDevices:[]]:ICA.sAR-
>CARSM .pM _USER_SWITCH_SPEAKER(cssc)@Bms
//此处多了⼀次setSystemAudioState
03-2118:46:51.48879316544569ITelecom-CallAudioRouteStateM achine:
setSystemAudioState:changingfrom[AudioStateisM uted:false,route:SPEAKER,
supportedRouteM ask:EARPIECE,SPEAKER,activeBluetoothDevice:[],
supportedBluetoothDevices:[]]to[AudioStateisM uted:false,route:EARPIECE,
supportedRouteM ask:EARPIECE,SPEAKER,activeBluetoothDevice:[],
supportedBluetoothDevices:[]]:CARSM .mSPCR->CARSM .pM _SPEAKER_OFF-
>CARSM .pM _SWITCH_BASELINE_ROUTE->CARSM .pM _SWITCH_EARPIECE@Bmw
18:46:54.1934621021610216IDialer:CallButtonPresenter.setAudioRoute-sending
newaudioroute:SPEAKER
03-2118:46:54.20461916544569ITelecom-CallAudioRouteStateM achine:
setSystemAudioState:changingfrom[AudioStateisM uted:false,route:EARPIECE,
supportedRouteM ask:EARPIECE,SPEAKER,activeBluetoothDevice:[],
supportedBluetoothDevices:[]]to[AudioStateisM uted:false,route:SPEAKER,
supportedRouteM ask:EARPIECE,SPEAKER,activeBluetoothDevice:[],
supportedBluetoothDevices:[]]:ICA.sAR-
>CARSM .pM _USER_SWITCH_SPEAKER(cssc)@BtA
03-0414:58:15.12379520463111ITelecom:CallAudioRouteController:updateCallAudioState:
updatingcallaudiostateto[AudioStateisM uted:false,route:EARPIECE,supportedRouteM ask:
EARPIECE,SPEAKER,activeBluetoothDevice:[null],supportedBluetoothDevices:[]]:TSI.pC-
>CM .fOCP->CM .sOCPA->CM .dSM CP->CM .mROC->CM .dSPA->CM .pASP-
>CARC.pM _UPDATE_SYSTEM _AUDIO_ROUTE(cssc)@AHk
5.4.8 拨号扬声器默认开启

# Page 25
正常情况下，拨打电话是听筒模式。在开启⼾外模式的时候，拨打电话会开启扬声器。可以在sys_log
中搜索outdoorOpen关键字
代码块
03-20 09:22:54.595065  1000  3394  5450 I TranPMSCoreImpl: 
updateOutDoorModeOpen displayOn=true, outdoorOpen=true, 
isKeyguardShowing=false, noStayAwake=true
03-20 09:36:21.658906  1000  3394 26207 I Telecom : CallsManager: setCallState 
NEW -> RINGING, call: [Call id=TC@15, 
03-20 09:36:21.705608  1000  3394 26207 I TranPMSCoreImpl: 
updateOutDoorModeOpen displayOn=true, outdoorOpen=false, 
isKeyguardShowing=false, noStayAwake=false
03-20 09:36:39.095064  1000  3394  6055 I Telecom : CallsManager: setCallState 
RINGING -> ANSWERED, call: [Call id=TC@15,
03-20 09:36:39.185854  1000  3394  7032 I Telecom : CallsManager: setCallState 
ANSWERED -> ACTIVE, call: [Call id=TC@15,
03-20 09:36:39.226536  1000  3394  4972 I TranPMSCoreImpl: 
updateOutDoorModeOpen displayOn=true, outdoorOpen=true, 
isKeyguardShowing=false, noStayAwake=true
03-20 09:36:39.265513  1000  3394  6004 I Telecom : CallAudioRouteController: 
Message received: USER_SWITCH_SPEAKER=1104, arg1=0: ICA.sAR-
>CARC.pM_USER_SWITCH_SPEAKER(cssc)@KpA
5.5视频通话
5.5.1⽤⼾⼿动触发升降级：
降级：Dialer:CallButtonPresenter.changeToAudioClicked-enter
Telecom-VideoProviderProxy:VP->IC(callId=TC@13):sendSessionM odifyRequest:from=
[VideoProfilevideoState=AudioTxRxvideoQuality=4]to=[VideoProfilevideoState=Audio
OnlyvideoQuality=0]
升级：Dialer:CallButtonPresenter.changeToVideoClicked-enter
Telecom-VideoProviderProxy:IC->VP(callId=TC@13):sendSessionM odifyRequest:from=
[VideoProfilevideoState=AudioOnlyvideoQuality=0]to=[VideoProfilevideoState=AudioTx
RxvideoQuality=4]
5.5.2降级失败
从log可以看出是⽹络拒绝(Rejectbyremote)，可以转modem进⼀步确认
代码块
1
2
3
4
5
6
7

# Page 26
10-23 20:11:43.597133  8693  8693 I Dialer  : 
CallButtonPresenter.changeToAudioClicked - enter
10-23 20:11:43.598814  1945  1945 I Telecom : Event: RecordEntry TC@22: 
SEND_VIDEO_REQUEST, Audio Only
10-23 20:11:43.661993  1428  1643 W VT      : [SRV] [OPERATION][ID=1] 
vt_callback (spVp_confirm->getResult() : Fail : Reject by remote)
10-23 20:11:43.664671  1945  4295 I Telecom-VideoProviderProxy: VP->IC 
(callId=TC@22): receiveSessionModifyResponse: status=5 requestProfile=
[VideoProfile videoState = Audio Only videoQuality = 4] responseProfile=
[VideoProfile videoState = Audio Tx Rx videoQuality = 0]
10-23 20:11:43.665545  1945  4295 I Telecom : Event: RecordEntry TC@22: 
RECEIVE_VIDEO_RESPONSE, Status Code : 5 Video State: 3
5.5.3视频拨号没有弹出选卡界⾯
拨号卡设置为“每次询问”，拨打视频电话没有弹出选卡界⾯，需要检查双卡是否⽀持视频通话，如
果不⽀持，则不会弹框。可以在radio_log搜isVideoCallEnabled关键字，在main_log搜
showPhoneAccountSelectionDialog关键字，结合拨号的时间查看分析。
代码块
12-17 13:34:33.326297 radio 4312 4312 D ImsPhoneCallTracker: [1] 
handleFeatureCapabilityChanged: isVolteEnabled=false, isVideoCallEnabled=true, 
isVowifiEnabled=true, isUtEnabled=true
12-17 13:34:33.517509 radio 4312 4312 D ImsPhoneCallTracker: [0] 
handleFeatureCapabilityChanged: isVolteEnabled=false, 
isVideoCallEnabled=false, isVowifiEnabled=true, isUtEnabled=false
12-17 13:34:45.113048 10154 11750 11750 I Dialer : 
InCallActivity.showPhoneAccountSelectionDialog - waitingForAccountCall:null
12-17 13:34:45.113071 10154 11750 11750 I Dialer : 
InCallActivity.showPhoneAccountSelectionDialog - did not show select phone 
account
1
2
3
4
5
1
2
3
4
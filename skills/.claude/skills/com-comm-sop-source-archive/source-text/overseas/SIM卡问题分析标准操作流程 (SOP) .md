# Page 1
SIM卡问题分析标准操作流程(SOP)
1.⽂档概述
1.1⽂档⽬的
本⽂档旨在为Android开发者和测试⼯程师提供⼀个标准化的操作流程（SOP），⽤于分析和解决SIM
卡相关的常⻅问题，包括但不限于SIM 卡⽆法识别、状态异常、PIN/PUK锁问题以及信息读取失败等，
从⽽提⾼问题定位效率和解决质量。
1.2适⽤范围
• 问题现象:
◦ ⼿机⽆法检测到SIM 卡（不识卡）。
◦ SIM 卡状态显⽰异常（如：ABSENT,NOT_READY,CARD_IO_ERROR）。
◦ PIN码或PUK码锁定相关问题。
◦ ⽆法读取SIM 卡基础信息（如IM SI,ICCID）。
◦ ⽹络注册失败（作为SIM 初始化后的延伸问题）。
• 芯⽚平台:
◦ M TK
◦ SPRD(展讯)
2.问题分析地图
2.1核⼼问题分类
SIM 卡问题通常可以根据其在初始化流程中的表现，分为以下⼏类：
• 硬件/驱动层问题:M odem未能检测到SIM 卡的物理插⼊或拔出。
• PIN/PUK锁定问题:SIM 卡处于PIN或PUK码锁定状态，等待⽤⼾输⼊。
• 卡初始化问题:SIM 卡已被识别，但在读取卡信息或鉴权过程中失败（如I/O错误、卡⽚受限）。
• 应⽤层/框架层问题:SIM 卡已就绪（LOADED），但上层应⽤（如设置、拨号）未能正确获取或展
⽰SIM 卡状态和信息。
2.2分析流程概览

# Page 2
下表提供了⼀个从“问题现象”到“初步结论”的快速分析指南。
问题现象 关键分析步骤(⽇志关键词) 初步结论
⼿机不识卡 1.确认M odem是否有插拔卡上报：
• M TK:+ESIM S:1,12
• SPRD:+ECIND:3,100
2.检查UiccController是否收到
EVENT_ICC_STATUS_CHANGED
1.M odem⽆上报：很可能是SIM 卡槽、
SIM 卡接触不良等硬件问题，或M odem
固件异常。
2.RIL/Uicc框架层问题，未能正确处理
M odem上报的事件。
需要输⼊
PIN/PUK
1.检查M odem对PIN状态的查询响应：
AT+CPIN?->+CPIN:SIM PIN或SIM PUK。
2.确认PIN/PUK剩余尝试次数：
• M TK:AT+EPINC
• SPRD:AT+XX
SIM 卡开启了密码保护，属于正常流程。若
⽤⼾⽆法解锁，则需获取PUK码。
卡状态⾮
Ready
1.跟踪UiccController的
onGetIccCardStatusDone流程。
2.检查IccCardStatus的具体状态，如
CARD_IO_ERROR或CARD_RESTRICTED。
3.确认系统是否⼴播
ACTION_SIM _STATE_CHANGED为READY
。
卡初始化流程中断。可能原因包括：
• CARD_IO_ERROR:SIM 卡物理损坏或I/O
读写错误。
• CARD_RESTRICTED:运营商限制.
SIM 信息为
空
1.确认UiccController是否⼴播
ACTION_SIM _STATE_CHANGED为
LOADED。
2.检查SIM Records的fetchSimRecords流程
⽇志。
3.搜索readingEF_IM SI,readingEF_ICCID等
关键字。
4.确认onAllRecordsLoaded是否被成功调
⽤。
SIM 卡⽂件读取失败。可能是SIM 卡物理损坏
导致特定⽂件⽆法读取，或I/O错误。
详细SIM 卡流程等可⻅⽂档： SIM 卡流程SOP
2.3⽇志流程
M TK
代码块

# Page 3
// ==================== 阶段 1: SIM 卡插⼊检测  ==================== 
11-06 19:17:28.078688  1672  1694 I AT      : [0] AT< +ESIMS: 1,12 
(RIL_URC_READER, tid:492594703536) //MTK Modem 上报 SIM 卡插⼊事件 (1: 已插⼊ ,12: 插⼊原
因 ) 
11-12 16:05:20.479098  1183  1675 I AT      : RECV MSGID=4505 
[SIM_STATUS_CHANGE_WITH_CAUSE_IND], TXID=ffff, 
DUMP=841954240000000001000545FFFF10000001010000000000010101000B000000 //MIPC 收到
SIM 状态变更消息 
11-12 16:05:20.479832  1183  1686 I RmmSimCommUrc: [0] handleSimStateChanged, 
+ESIMS:1,12 //RIL 处理 SIM 卡插⼊事件 
// ==================== 阶段 2: 查询 PIN 码状态  ==================== 
11-06 19:17:29.565090  1672  1706 I AT      : [0] AT> AT+CPIN? 
(RIL_CMD_READER_3, tid:492579609776) //RIL 查询 SIM 卡 PIN 码状态 
11-06 19:17:29.572395  1672  1705 I AT      : [0] AT< +CPIN: SIM PIN 
(RIL_CMD_READER_3, tid:492580674736) //Modem 返回需要 PIN 码验证 
11-06 19:17:30.205229  1672  1706 I AT      : [0] AT> AT+CPIN=*** 
(RIL_CMD_READER_3, tid:492579609776) //RIL 发送 PIN 码进⾏ SIM 卡解锁 
// ==================== 阶段 3: 查询密码尝试次数  ==================== 
11-06 19:17:07.013180  1672  1706 I AT      : [0] AT> AT+EPINC 
(RIL_CMD_READER_3, tid:492579609776) //MTK 扩展命令查询密码剩余尝试次数 
11-06 19:17:07.019545  1672  1705 I AT      : [0] AT< +EPINC: 3, 3, 10, 10 
(RIL_CMD_READER_3, tid:492580674736) // 返回 PIN1=3 次 ,PIN2=3 次 ,PUK1=10 次 ,PUK2=10 次 
// ==================== 阶段 4: SIM 卡启⽤确认  ==================== 
11-06 19:17:28.745828  1672  1696 I AT      : [1] AT< +ESIMS: 1,29 
(RIL_URC2_READER, tid:492590492848) //MTK Modem 上报 SIM 卡启⽤状态 (29:ENABLE) 
11-12 16:05:50.920604  1183  1686 I RmmSimCommUrc: [0] handleSimStateChanged, 
+ESIMS:1,29 //RIL 处理 SIM 卡启⽤事件 
// ==================== 阶段 5: 上层状态更新  ==================== 
11-06 19:17:29.670660  2611  2611 D UiccController: onGetIccCardStatusDone: 
phoneId-0 IccCardStatus: IccCardState 
{CARDSTATE_PRESENT,PINSTATE_ENABLED_NOT_VERIFIED,num_apps=1,gsm_id=0{APPTYPE_US
IM,APPSTATE_PIN,pin1=PINSTATE_ENABLED_NOT_VERIFIED,pin2=PINSTATE_UNKNOWN}} 
//UiccController 获取 SIM 卡状态完成 
11-06 19:17:45.283975  2611  2611 D UiccController: Broadcasting intent 
ACTION_SIM_STATE_CHANGED READY reason null for phone: 0 // 系统⼴播 SIM 卡 READY 状态 
11-06 19:17:50.495336  2611  2611 D UiccController: Broadcasting intent 
ACTION_SIM_STATE_CHANGED LOADED reason null for phone: 0 // 系统⼴播 SIM 卡 LOADED 状
态 ( ⽂件加载完成 ) 
// ==================== 阶段 6: SIM 卡⽂件加载  ==================== 
11-06 19:17:50.500000  2611  2650 D SIMRecords: [0] fetchSimRecords: reading 
EF_IMSI // 开始读取 IMSI ⽂件 
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
25

# Page 4
11-06 19:17:50.501000  2611  2650 D SIMRecords: [0] fetchSimRecords: reading 
EF_ICCID // 开始读取 ICCID ⽂件 
11-06 19:17:50.502000  2611  2650 D SIMRecords: [0] fetchSimRecords: reading 
EF_AD // 开始读取 AD ⽂件 
11-06 19:17:50.510000  2611  2650 D IccFileHandler: [0] 
EVENT_GET_RECORD_SIZE_DONE: fileid=0x6F07 // 获取⽂件记录⼤⼩完成 
11-06 19:17:50.511000  2611  2650 D IccFileHandler: [0] EVENT_READ_RECORD_DONE:
 fileid=0x6F07 // 读取⽂件记录完成 
11-06 19:17:50.520000  2611  2650 D SIMRecords: [0] onAllRecordsLoaded: record 
load complete // 所有 SIM 卡记录加载完成 
SPRD
代码块
// ==================== 阶段 1: SIM 卡插⼊检测  ==================== 
11-14 10:09:03.607   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,100 
(RIL_URC_READER, tid:492594703536) //SPRD Modem 上报 SIM 卡插⼊事件 (3:SIM 类
型 ,100:SIM 热插拔插⼊ ) 
// ==================== 阶段 2: SIM 卡初始化中  ==================== 
   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,2 (RIL_URC_READER, 
tid:492594703536) //SPRD Modem 上报 SIM 卡初始化中 (2: 正在初始化或验证 ) 
// ==================== 阶段 3: 查询 SIM 卡类型  ==================== 
11-14 10:09:03.609   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,6,255,3 
(RIL_URC_READER, tid:492594703536) //SPRD Modem 上报 SIM 卡类型信息 (6:SIM 类型 ,255: 未
知 ,3: 具体类型参数 ) 
// ==================== 阶段 4: 查询 PIN 码剩余尝试次数  ==================== 
11-14 10:07:03.345   818   855 D RIL-AT  : Channel2: AT> AT+XX=0 
(RIL_CMD_READER, tid:492579609776) //SPRD 平台查询 PIN1 剩余尝试次数的 AT 命令 (0:PIN1) 
11-14 10:07:03.346   818  1137 D RIL-AT  : Channel2: AT< +XX: 3 
(RIL_CMD_READER, tid:492580674736) //Modem 返回 PIN1 剩余 3 次尝试机会 
// 如需查询其他密码状态，继续发送对应命令 
11-14 10:07:03.350   818   855 D RIL-AT  : Channel2: AT> AT+XX=2 
(RIL_CMD_READER, tid:492579609776) // 查询 PUK1 剩余尝试次数 (2:PUK1) 
11-14 10:07:03.351   818  1137 D RIL-AT  : Channel2: AT< +XX: 10 
(RIL_CMD_READER, tid:492580674736) //Modem 返回 PUK1 剩余 10 次尝试机会 
// ==================== 阶段 5: SIM 卡锁定状态检查  ==================== 
11-14 10:09:03.610   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,4,0 
(RIL_URC_READER, tid:492594703536) //SPRD Modem 上报 SIM 卡锁定状态 (4: 锁定状态 ,0: 未锁
定 ) 
26
27
28
29
30
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
12
13
14
15
16
17
18
19
20

# Page 5
// ==================== 阶段 6: SIM 卡准备就绪  ==================== 
11-14 10:09:03.611   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,2,1 
(RIL_URC_READER, tid:492594703536) //SPRD Modem 上报 SIM 卡初始化完成 (2: 初始化完成 ) 
11-14 10:09:03.612   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,0 
(RIL_URC_READER, tid:492594703536) //SPRD Modem 上报 SIM 卡就绪 (0:SIM ready) 
11-14 10:09:03.613   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,5 
(RIL_URC_READER, tid:492594703536) //SPRD Modem 再次确认 SIM 卡就绪 (5: 指⽰ SIM ready) 
// ==================== 阶段 7: 上层状态更新和⼴播  ==================== 
11-14 10:09:03.614   818   856 D RILJ    : [0] 
UNSOL_RESPONSE_SIM_STATUS_CHANGED //RIL Java 层收到 SIM 状态变更通知 
11-14 10:09:03.615  2611  2611 D UiccController: [0] updateSimState: READY 
//Uicc 控制器更新 SIM 卡状态为 READY 
11-14 10:09:03.616  2611  2611 D UiccController: Broadcasting intent 
ACTION_SIM_STATE_CHANGED READY reason null for phone: 0 // 系统⼴播 SIM 卡 READY 状态 
11-14 10:09:05.617  2611  2611 D UiccController: Broadcasting intent 
ACTION_SIM_STATE_CHANGED LOADED reason null for phone: 0 // 系统⼴播 SIM 卡 LOADED 状
态 ( ⽂件加载完成 ) 
11-14 10:09:05.618  2611  2611 D UiccController: Broadcasting intent 
ACTION_SIM_APPLICATION_STATE_CHANGED LOADED for phone: 0 slot: 0 port: 0 // 系统
⼴播 SIM 卡应⽤状态变更 
// ==================== 阶段 8: ⽹络注册准备完成  ==================== 
11-14 10:09:05.619  2611  2611 D TelephonyRegistry: [0] notifySimStateChange: 
READY->LOADED // 电话注册表通知 SIM 状态变化 
3.前置准备与⼯具
3.1环境配置
• 硬件:
◦ 待测⼿机
◦ 性能稳定的PC（Windows/Linux/M ac）
◦ USB数据线
• 软件:
◦ AndroidSDKPlatform-Tools(包含ADB)
◦ 对应⼿机型号的USB驱动程序
◦ ⽇志分析⼯具（⻅下⽂）
3.2⼯具安装与使⽤
21
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
33
34

# Page 6
• logExportTool:
◦ 使⽤:打开⼯具，连接⼿机，选择对应设备即可开始抓取。其强⼤的过滤和⾼亮功能是分析⽇志
的关键。例如，可以设置对应模块抓取相应⽇志。
4.标准操作流程(SOP)
4.1问题确认与复现
1.交叉验证:
◦ 将问题SIM 卡放⼊⼀台确认正常的⼿机中，观察问题是否复现。若复现，则⼤概率是SIM 卡问
题。
◦ 将⼀张确认正常的SIM 卡放⼊问题⼿机中，观察问题是否消失。若消失，则⼤概率是原SIM 卡问
题；若问题依旧，则⼤概率是⼿机硬件或软件问题。
2.记录复现步骤:清晰、准确地记录下复现问题的每⼀步操作，为后续分析提供稳定场景。
4.2⽇志抓取
1.连接设备:adbdevices确认⼿机与PC连接正常。
2.开启⽇志:在拨号盘输⼊特定指令（如*#*#9646633#*#*进⼊M TK⼯程模式），开启ModemLog
和telephonylog。
3.复现问题:执⾏问题复现步骤。
4.导出⽇志:
◦ AndroidLog:adblogcat-bmain-bradio-bsystem-vtime>android_log.txt
◦ M odemLog:通常保存在⼿机内置存储的特定⽬录（如/sdcard/debuglogger/），需将其导出
到PC。
4.3⽇志分析步骤
• 关键⽇志⽂件:
◦ android_log.txt(main/radio/systemlog):包含从Android框架层到RIL层的绝⼤部分逻辑。
◦ M odemLog:M odem侧的底层通信⽇志，是分析射频、⽹络协议问题的核⼼。
• 核⼼关键词:
◦ 通⽤:UiccController,IccCardStatus,SIM Records,onAllRecordsLoaded,
ACTION_SIM _STATE_CHANGED
◦ M TKAT:+ESIM S,+CPIN,+EPINC
◦ SPRDAT:+ECIND,+XX

# Page 7
◦ 状态:UNKNOWN,ABSENT,PIN_REQUIRED,PUK_REQUIRED,READY,LOADED,
CARD_IO_ERROR
• 分析要点:
a.从下⾄上分析:先从M odem的AT指令交互开始，确认最底层的硬件状态和SIM 卡响应是否正
常。
b.跟踪状态变化:以UiccController为核⼼，跟踪ACTION_SIM _STATE_CHANGED⼴播的整个
过程，从NOT_READY->READY->LOADED。
c.定位中断点:如果流程中断，查看中断前的最后⼀条关键⽇志，分析其上下⽂，确定失败原因。
例如，如果停在READY但未进⼊LOADED，则重点排查SIM Records的⽂件读取过程。
5.典型案例分析
以下案例基于⽂档提供的正常流程⽇志，可作为分析异常问题时的“⻩⾦标准”进⾏⽐对。
案例⼀:MTK平台SIM卡正常初始化流程分析
• 问题现象:⼿机开机后，正常识别SIM 卡并显⽰运营商。
• 分析过程:
a.插卡检测:M odem通过+ESIM S:1,12主动上报SIM 卡插⼊事件。RIL层RmmSimCommUrc处
理该事件。
b.PIN码处理(如有):RIL发送AT+CPIN?查询，M odem返回+CPIN:SIM PIN。上层输⼊密码后，
RIL发送AT+CPIN=***进⾏解锁。
c.SIM 卡启⽤:M odem上报+ESIM S:1,29，表⽰SIM 卡已启⽤。
d.上层状态更新:UiccController获取到卡状态后，更新内部状态，并向系统⼴播
ACTION_SIM _STATE_CHANGED，状态依次为READY。
e.SIM ⽂件加载:SIM Records开始执⾏fetchSimRecords，读取EF_IM SI,EF_ICCID等关键⽂
件。
f.加载完成:所有⽂件读取完毕后，SIM Records调⽤onAllRecordsLoaded，并最终由
UiccController⼴播LOADED状态。
• 结论与建议:整个流程清晰完整，从底层M odem上报到上层框架处理，再到SIM ⽂件加载，环环相
扣。分析SIM 卡问题时，可将异常⽇志与此流程对⽐，快速定位差异点。
案例⼆:SPRD平台SIM卡正常初始化流程分析
• 问题现象:⼿机开机后，正常识别SIM 卡并显⽰运营商。
• 分析过程:

# Page 8
a.插卡检测:M odem通过+ECIND:3,100上报SIM 卡热插拔插⼊事件。
b.初始化状态:M odem陆续上报+ECIND:3,2（初始化中）、+ECIND:3,4,0（未锁定）、
+ECIND:3,0（SIM ready）。
c.上层状态更新:RILJ收到UNSOL_RESPONSE_SIM _STATUS_CHANGED通知，
UiccController将状态更新为READY并⼴播。
d.加载完成:后续流程与M TK平台类似，SIM Records加载⽂件，最终⼴播LOADED状态。
• 结论与建议:SPRD平台的AT指令与M TK有所不同，但核⼼的初始化状态机（Ready->Loaded）在
Android框架层是⼀致的。分析时需注意区分不同平台的AT指令关键字。
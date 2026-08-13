# Page 1
StandardOperatingProcedure(SOP)for
SIM CardProblem Analysis
1.Docum entOverview
1.1PurposeoftheDocum ent
ThisdocumentaimstoprovideAndroiddevelopersandtestengineerswithastandardized
operatingprocedure(SOP)foranalyzingandresolvingcommonSIM card-relatedissues,
includingbutnotlimitedtoSIM cardunrecognized,abnormalstatus,PIN/PUKlockissues,and
informationreadingfailures,therebyimprovingtheefficiencyofproblemlocationandthe
qualityofproblemresolution.
1.2ScopeofApplication
• ProblemPhenomenon:
◦ ThephonecannotdetecttheSIM card(SIM cardnotrecognized).
◦ SIM cardstatusshowsananomaly(e.g.,ABSENT,NOT_READY,CARD_IO_ERROR).
◦ IssuesrelatedtoPINorPUKcodelock.
◦ UnabletoreadbasicSIM cardinformation(suchasIM SI,ICCID).
◦ Networkregistrationfailed(asanextendedissueafterSIM initialization).
• ChipPlatform:
◦ M TK
◦ SPRD(Spreadtrum)
◦ Qcom
2.Problem AnalysisM ap
2.1ClassificationofCoreIssues
SIM cardissuescangenerallybeclassifiedintothefollowingcategoriesbasedontheir
performanceduringtheinitializationprocess:
• Hardware/DriverLayerIssue:M odemfailstodetectthephysicalinsertionorremovalofthe
SIM card.

# Page 2
• PIN/PUKLockIssue:TheSIM cardisinaPINorPUKcodelockedstate,waitingforuserinput.
• CardInitializationIssue:TheSIM cardhasbeenrecognized,butfailsduringtheprocessof
readingcardinformationorauthentication(e.g.,I/Oerror,cardrestricted).
• ApplicationLayer/FrameworkLayerIssue:TheSIM cardisready(LOADED),butupper-layer
applications(suchasSettings,Dialer)failtocorrectlyobtainordisplaytheSIM cardstatus
andinformation.
2.2OverviewoftheAnalysisProcess
Thefollowingtableprovidesaquickanalysisguidefrom"problemphenomenon"to
"preliminaryconclusion".
Problem
Phenomen
on
Keyanalysissteps(logkeywords) PreliminaryConclusion
Phonefails
to
recognize
thecard
1.ConfirmwhethertheM odemreportscard
insertionorremoval:
• M TK:+ESIM S:1,12
• SPRD:+ECIND:3,100
2.CheckifUiccControllerhasreceived
EVENT_ICC_STATUS_CHANGED
1.M odemfailstoreport:M ostlikelydue
tohardwareissuessuchaspoor
contactintheSIM cardslotorSIM 
card,orabnormalM odemfirmware.
2.RIL/Uiccframeworklayerissue,failed
tocorrectlyhandletheevents
reportedbytheM odem.
PIN/PUK
input
required
1.ChecktheM odem'squeryresponsetothe
PINstatus:AT+CPIN?->+CPIN:SIM PINor
SIM PUK.
2.Confirmtheremainingnumberof
PIN/PUKattempts:
• M TK:AT+EPINC
• SPRD:AT+XX
TheSIM cardhaspasswordprotection
enabled,whichisanormalprocess.Ifthe
usercannotunlockit,theyneedtoobtain
thePUKcode.
Card
statusis
notReady
1.TracktheonGetIccCardStatusDone
processofUiccController.
2.CheckthespecificstatusofIccCardStatus,
suchasCARD_IO_ERRORor
CARD_RESTRICTED.
3.Confirmwhetherthesystembroadcasts
ACTION_SIM _STATE_CHANGEDasREADY.
Cardinitializationprocessinterrupted.
Possiblecausesinclude:
• CARD_IO_ERROR:SIM cardis
physicallydamagedorthereisanI/O
read/writeerror.
• CARD_RESTRICTED:Operator
restriction.

# Page 3
SIM 
informatio
nisempty
1.VerifywhetherUiccControllerbroadcasts
ACTION_SIM _STATE_CHANGEDas
LOADED.
2.ChecktheprocesslogoffetchSimRecords
forSIM Records.
3.Searchforkeywordssuchasreading
EF_IM SI,readingEF_ICCID,etc.
4.VerifywhetheronAllRecordsLoadedis
successfullycalled.
FailedtoreadSIM cardfile.Itmaybedue
tophysicaldamagetotheSIM card
causingaspecificfiletobeunreadable,
oranI/Oerror.
DetailedSIM cardproceduresandotherscanbefoundinthedocument: SIM 卡流程SOP
2.3LogProcess
M TK
代码块
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

# Page 4
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
17
18
19
20
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
1
2
3
4
5
6
7
8

# Page 5
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
3.PreparatoryW orkandTools
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
3.1Environm entConfiguration
• Hardware:
◦ M obilephonetobetested
◦ PCwithstableperformance(Windows/Linux/M ac)
◦ USBdatacable
• Software:
◦ AndroidSDKPlatform-Tools(包含ADB)
◦ USBdriverforthecorrespondingphonemodel
◦ Loganalysistool(seebelow)
3.2ToolInstallationandU sage
• logExportTool:
◦ Usage:Openthetool,connectyourphone,selectthecorrespondingdevice,andyoucan
startcapturing.Itspowerfulfilteringandhighlightingfunctionsarethekeytoanalyzing
logs.Forexample,youcansetthecorrespondingmoduletocapturetherelevantlogs.
4.StandardOperatingProcedure(SOP)
4.1Problem Confirm ationandReproduction
1.Cross-validation:
◦ InserttheproblematicSIM cardintoaconfirmednormalmobilephoneandobserve
whethertheproblemrecurs.Ifitdoes,itishighlylikelyaSIM cardissue.
◦ InsertaconfirmednormalSIM cardintotheproblematicphoneandobservewhetherthe
problemdisappears.Ifitdoes,itismostlikelyanissuewiththeoriginalSIM card;ifthe
problempersists,itismostlikelyahardwareorsoftwareissuewiththephone.
2.Recordthereproductionsteps:Clearlyandaccuratelydocumenteachstepoftheoperation
toreproducetheproblem,providingastablescenarioforsubsequentanalysis.
4.2LogCapture
1.Connectthedevice:Use"adbdevices"toconfirmthatthephoneisproperlyconnectedto
thePC.
2.EnableLogging:Enterspecificcommands(e.g.,*#*#9646633#*#*toenterM TKEngineering
M ode)onthedialertoenableM odemLogandtelephonylog.
3.Reproducetheissue:Executethestepstoreproducetheissue.

# Page 7
4.ExportLog:
◦ AndroidLog:adblogcat-bmain-bradio-bsystem-vtime>android_log.txt
◦ M odemLog:Usuallystoredinaspecificdirectory(suchas/sdcard/debuglogger/)ofthe
phone'sinternalstorage,itneedstobeexportedtoaPC.
4.3LogAnalysisSteps
• Keylogfile:
◦ android_log.txt(main/radio/systemlog):ContainsmostofthelogicfromtheAndroid
frameworklayertotheRILlayer.
◦ M odemLog:TheunderlyingcommunicationlogontheM odemside,whichisthecorefor
analyzingradiofrequencyandnetworkprotocolissues.
• CoreKeywords:
◦ 通⽤:UiccController,IccCardStatus,SIM Records,onAllRecordsLoaded,
ACTION_SIM _STATE_CHANGED
◦ M TKAT:+ESIM S,+CPIN,+EPINC
◦ SPRDAT:+ECIND,+XX
◦ 状态:UNKNOWN,ABSENT,PIN_REQUIRED,PUK_REQUIRED,READY,LOADED,
CARD_IO_ERROR
• AnalysisKeyPoints:
a.Analysisfrombottomtotop:StartwiththeATcommandinteractionoftheM odemto
confirmwhetherthestateofthebottom-levelhardwareandtheresponseoftheSIM card
arenormal.
b.Trackingstatechanges:CenteredaroundUiccController,tracktheentireprocessofthe
ACTION_SIM _STATE_CHANGEDbroadcast,fromNOT_READY->READY->LOADED.
c.Locatingthebreakpoint:Iftheprocessisinterrupted,checkthelastkeylogbeforethe
interruption,analyzeitscontext,anddeterminethecauseofthefailure.Forexample,ifit
stopsatREADYbutfailstoenterLOADED,focusontroubleshootingthefilereading
processofSIM Records.
5.AnalysisofTypicalCases
Thefollowingcasesarebasedonthenormalprocesslogsprovidedinthedocumentandcanbe
usedasthe"goldstandard"forcomparisonwhenanalyzingabnormalissues.

# Page 8
Case1:AnalysisoftheNorm alInitializationProcessofSIM Cardson
theM TKPlatform 
• Problemphenomenon:Afterthephoneisturnedon,itnormallyrecognizestheSIM cardand
displaysthecarrier.
• Analysisprocess:
a.SIM CardInsertionDetection:M odemactivelyreportstheSIM cardinsertioneventvia
+ESIM S:1,12.TheRILlayerRmmSimCommUrcprocessesthisevent.
b.PINcodehandling(ifany):RILsendsAT+CPIN?query,M odemreturns+CPIN:SIM PIN.
Aftertheupperlayerentersthepassword,RILsendsAT+CPIN=***tounlock.
c.SIM CardActivation:M odemreports+ESIM S:1,29,indicatingthattheSIM cardhasbeen
activated.
d.Upperlayerstateupdate:AfterUiccControllerobtainsthecardstate,itupdatesits
internalstateandbroadcastsACTION_SIM _STATE_CHANGEDtothesystem,withthestate
beingREADYinsequence.
e.SIM fileloading:SIM RecordsstartsexecutingfetchSimRecordstoreadkeyfilessuchas
EF_IM SIandEF_ICCID.
f.Loadingcompleted:Afterallfileshavebeenread,SIM RecordscallsonAllRecordsLoaded,
andfinallyUiccControllerbroadcaststheLOADEDstate.
• ConclusionsandRecommendations:Theentireprocessisclearandcomplete,fromthe
underlyingM odemreportingtotheupper-layerframeworkprocessing,andthentotheSIM 
fileloading,allstepsarecloselylinked.WhenanalyzingSIM cardissues,theabnormallogs
canbecomparedwiththisprocesstoquicklyidentifythepointsofdifference.
Case2:AnalysisoftheNorm alInitializationProcessoftheSIM Card
ontheSPRDPlatform 
• Problemphenomenon:Afterthephoneisturnedon,itnormallyrecognizestheSIM cardand
displaysthecarrier.
• Analysisprocess:
a.SIM CardInsertionDetection:TheM odemreportstheSIM cardhot-pluginsertionevent
via+ECIND:3,100.
b.Initializationstate:M odemsuccessivelyreports+ECIND:3,2(initializing),+ECIND:3,4,0
(unlocked),+ECIND:3,0(SIM ready).
c.Upperlayerstateupdate:RILJreceivestheUNSOL_RESPONSE_SIM _STATUS_CHANGED
notification,andUiccControllerupdatesthestatetoREADYandbroadcastsit.

# Page 9
d.Loadingcompleted:ThesubsequentprocessissimilartothatoftheM TKplatform,where
SIM RecordsloadsfilesandfinallybroadcaststheLOADEDstate.
• ConclusionsandRecommendations:TheATcommandsoftheSPRDplatformdifferfrom
thoseofM TK,butthecoreinitializationfinite-statemachine(Ready->Loaded)isconsistent
attheAndroidframeworklayer.Whenanalyzing,itisnecessarytopayattentionto
distinguishingtheATcommandkeywordsofdifferentplatforms.
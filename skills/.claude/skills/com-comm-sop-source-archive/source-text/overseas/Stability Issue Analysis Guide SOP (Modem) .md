# Page 1
StabilityIssueAnalysisG uideSOP(M odem )
1.Docum entOverview
1.1PurposeoftheDocum ent
Thisdocumentaimstoaddressvariousissuescausedbyabnormalcrashesofthemobilephone
M odemsubsystem(M odemEE),includingbutnotlimitedtoscenariossuchascellulardata
disconnection,SIM cardrecognitionfailure,IM EIloss/abnormaldisplay,andsignal
automaticallyrecoveringafterashortdisappearance,andprovidesstandardizedprocessesfor
problemlocation,analysis,andhandling.
1.2ScopeofApplication
• Applicableproblemphenomena:networkdisconnection,SIM cardrecognitionfailure,
abnormalIM EIdisplay,basebandversionshowingasUnknown,signaldisappearingfor
about10secondsandthenautomaticallyrecovering,andpoppingupamodemcrashprompt
• Applicablechipplatforms:M TK,Spreadtrum(SPRD),andallQualcommmobilephone
platforms
• Applicablescenarios:projecttestingissues,Bigdatamonitoringanomalies,marketcustomer
complaintsrelatedtoM odem
2.Problem AnalysisM ap
2.1ClassificationofCoreIssues

# Page 2
M odemEEissuescanbefurtherdividedinto5specificsub-scenarios:
1.Basebandversionnumberunknown/UnrecognizedcardtypeEE
2.Recoveryaftersignalloss/pop-upofmodemcrashinterfaceclassEE
3.FANSAEE/M onkeyAEETestTriggerClassEE
4.BigdataUSICmonitoringcaptureclassEE
5.UnconventionalEE(causedbyspecialscenariossuchasexcessiveIOload,interruptedOTA
upgrade,etc.)
2.2OverviewoftheAnalysisProcess
3.StandardOperatingProcedure(SOP)
3.1Problem Confirm ationandReproduction
1.Externalfactortroubleshooting:ReplacetheSIM card,changethenetworkenvironmentfor
testing,confirmwhethertheproblemstillrecurs,andruleoutexternalcausessuchascarrier
networkissuesandSIM carddamage
2.Reproductionpathconfirmation:Recordtheoperationstepsthattriggertheproblem,
confirmthattheproblemcanbereproducedstably,tofacilitatesubsequentretestingand
verification
3.2LogCapture
Forthecompletecapturesteps,refertotheofficialguidance:M odemEEIssueLogCaptureSOP,
andthecorestepsareasfollows:

# Page 3
1.ExecutetheADBcommandtoenablefulllogprinting,andthenrestartthephone
2.TriggerM odemEEbyperformingoperationsaccordingtothereproductionpath
3.Usethelogexporttooltoexportalllogs,andconfirmthatthelogs
include_EE_INVALIDdumpdirectory,main_log,modemlog,__exp_main.txtand
othercorefiles
3.3LogAnalysisSteps
• Keylogfiles:main_log,modemdumplog,__exp_main.txt,SYS_KERNEL_LOG,taglog
(fanlogscenario),minidump(Bigdatascenario)
• Corekeywords:ccci_mdinit,Modem exception,[ASSERT],[Fatal error
• AnalysisKeyPoints:
a.CheckthefilepathofASSERTerrorsfirst:Errors under the rf check 
directory are mostly due to RF configuration errors,whileerrorsunder
themml1/directoryaremostlyrelatedtoRFissues
b.Extractthefilename,linenumber,andP1/P2/P3parametersoftheerror-reporting,and
searchoninternalJiraandM TKonlineplatformstocheckifitisaknownissue
c.Forunknownissues,thecorrespondingversionoftheM odemELFfileandthefullDbgInfo
fileneedtobeextractedandsubmittedtothechipplatformforanalysis
Probl
em 
Locat
ion
Key
Featur
es
Core
Focus
Possible
causes
AnalysisSteps logfile keywor
d
Case
Reference
M OD
EM 
EE
Baseba
nd
version
number

unkno
wn/Unr
ecogniz
edSIM 
card
M odem
startup
process
img
loading
NV
Verificati
on
M odem
Status
Check
1.
Configuration
error
2.patch
dependency
missingmerge
3.Introduction
ofPlatform
M odifications
4.Standalone
hardware
issues
1.Checkifthe
aplogrecords
theEEprintout
2.EEhangs
beforelog
printing,and
thedump
modecanbe
manually
triggeredto
capturethe
dumpfor
confirmingthe
EEpoint
1.main_log
2.dumplog
1.ccci_
mdinit
2.M ode
m
exceptio
n
3.
[ASSERT
]
4.[Fatal
error
http://jira.t
ranssion.c
om/brows
e/CL8TOS1
501-1943

# Page 4
Toroughly
locatethe
specificerror
module,refer
totheerror-
reportingC
file;for
example,most
errorsunder
therfcheck
directoryare
RF
configuration
errors,and
thoseunder
themml1/
directoryare
roughly
relatedto
radio
frequency.
Recove
ryafter
signal
loss/m
odem
crash
interfac
e
EE
Printing
1.[ASSE
RT]
file:X
XXXX
X
P1:XXX
P2:XXX
P3:XXX
For
example:

[ASSERT
]
file:m cu/
l1/m m l1
/m m l1_r
f/src/m
m rf/gen
99/m m l1
Sameasabove 1.Findmodem
exceptionin
mainlog
2.Findthe
specificerror
message
printedby
assert,ina
certain
file/line,para
0~2
3.Checklocal
filesandreport
whetherthe
pathcanbe
accessed
3.Ifunableto
access,search
fortheerror
fileon
JIRA/onlineto
1.mainlog
2.modem
log
1.M ode
m
exceptio
n
2.
[ASSERT
]
3.[Fatal
error

LI6_v/LI7_
vOTA升级
后不识卡，
IM EI消失问
题复盘报
告

# Page 5
_rf_erro
r_check.
c
line:156
p1:0x00
000003

p2:0x00
00000b
p3:0x00
000007
seeifitisa
knownissue
4.SubmitaCR
forplatform
analysis,and
theversion
corresponding
symboltable
needstobe
provided.
FANSAE
E/
M onkey
AEE
Exceptio
nClass:
External
(EE)
Sameasabove 1.Confirmthe
EEpointin
__exp_main.txt
2.Retrievethe
corresponding
taglogfrom
thefanlog
system
3.Ifthereisno
corresponding
taglog,a
collection
application
needstobe
initiated
1.__exp_ma
in.txt
2.SYS_KERN
EL_LOG
3.taglog
1.M ode
m
exceptio
n
2.
[ASSERT
]
3.[Fatal
error
Big
data
USIC
Exceptio
nClass:
External
(EE)
Sameasabove 1.TNEParsing
ToolParses
Logs
2.Ifadumpis
required,the
modemdump
needstobe
retrieved
basedonBig
data.
1.mainlog
2.minidump
1.M ode
m
exceptio
n
2.
[ASSERT
]
3.[Fatal
error
Unconv
entiona
lEE
1.[ASSE
RT]
file:X
XXXX
X
1.IOloading
causes
modemEE
1.Findmodem
exceptionin
mainlog
1.mainlog
2.modem
log
1.M ode
m
exceptio
n

IO_LOADI
NG 负载导
致M odem
EE

# Page 6
P1:XXX
P2:XXX
P3:XXX
For
example:

[ASSERT
]
file:m cu/
l1/m m l1
/m m l1_r
f/src/m
m rf/gen
99/m m l1
_rf_erro
r_check.
c
line:156
p1:0x00
000003

p2:0x00
00000b
p3:0x00
000007
2.Forced
interruptio
nduring
theOTA
process
2.Findthe
specificerror
message
printoutof
assert,suchas
acertainfile/a
certainline,
para0~2
3.Checklocal
filesandreport
whetherthe
pathcanbe
accessed
3.Ifunableto
access,search
fortheerror
fileon
JIRA/onlineto
seeifitisa
knownissue
4.SubmitaCR
forplatform
analysis,and
theversion
corresponding
symboltable
needstobe
provided.
2.
[ASSERT
]
3.[Fatal
error
4.Problem handlingsteps
M odemEEProblemHandlingProcess

# Page 7
4.1EECauseAcquisition
M odem LogDum pAcquisition:
Undernormalcircumstances,modemEEwillautomaticallytriggerlogpackaging,andthere
willbea_EE_INVALIDdirectoryinthemodemlog,whichrecordsthelogsduringmodemEE
Retrievalofm ainlogfrom APlog:
Searchforexceptionorassert

# Page 8
aee_expObtainsEEInform ation:
Thedirectorywillbepresentinthelogsexportedusingthelogexporttool.TheEEfile
automaticallysubmittedforfanlogsisalsothisdbfile.Forthetoolandpathtoopenthedbg
file,pleasereferto:http://10.150.98.130/pages/viewpage.action?pageId=24691819
4.2Prelim inaryAnalysisoftheProblem 
TakingthisEEasanexample,youcansearchforerrc_chm_main.conM TKonline,andthen
confirmwhetheritisaknownissuebasedonthecorrespondingline(hereitis9158).Youcan
alsocheckthecodeaccordingtothecorrespondingfilepath.M TKonlineURL:
https://online.mediatek.com/_layouts/15/mol/ui/ext/home.aspx
4.3Problem Handling
4.3.1KnownIssues
●M TKonlineconfirmsthesamerootcauseCR->ConfirmsthepatchIDbasedontheCR->M TK
eserviceconfirmsthepatchapplicationstatus.

# Page 9
●Ifnotapplied,youneedtoapplyforthepatchofthecorrespondingprojectonM TKeservice.
Ifthepatchinformationcannotbefound,youneedtosubmitaCRtorequestM TKtoreleasethe
patchbasedontheprojectinformation.
●Arrangepatchintegrationandbasicfunctionself-check
4.3.2UnknownNewIssue
●M TKonlineconfirmedthesamerootcauseCR->noidenticalerrorCR.
●NeedtosubmitaCRbyoneselfandcommunicateandfollowupwithM TK.Theattachments
providedwiththeCRshallinclude
1)M DlogandM Ddumpbinatthetimepointoftheissue;
2)APLogatthetimepointoftheissue;
3)ELFfile(XXX.elf)generatedbycompilationontheM odemside;
4)AllDbgInfo_XXXfiles;AllfilesstartingwithDbgInfo(DbgInfo_XXX)underthe
correspondingfilepathneedtobeuploaded;
●CRfollow-uptoobtainthedebugpatch.
●Debugpatchretestpassed,applyingforreleaseoftheofficialpatch.
●Formalpatcharchiving&merging.M TKeservicelink:
https://eservice.mediatek.com/eservice-portal/dashboardM TKuploadlogandattachmentlink:
https://transfer.mediatek.com/
ELFFileAcquisition:Confirmtheproblemversion->TrackFiles->vnd_track->vendor->
mediatek->proprietary->modem->(projectname),allcontentsinside.Toviewthemodem
log,anEDBfileisrequired.Ifthefanlogcannotbeparsed,thisfileneedstobeplacedinthelog.
RetrievingallDbgInfo_XXXfiles:Confirmtheproblemversion->Confirmtheversiontimeand
baselineinformation->CorrespondingAPcode->M odemrepositoryCheckthecodemerge

# Page 10
timeinthemodemrepository'sgitlog,resettothemodemversioncommitatthetimeof
compilation,andthenuploadtheDbgfilestoM TK
5.TypicalCaseAnalysis
Case1:Problem ofcardnotbeingrecognizedandIM EIdisappearingafter
OTAupgrade
• Problem Phenom enon:AfterOTAupgradeofLI6_v/LI7_vversion,cardrecognitionfailure,
IM EIlossoccur,andthebasebandversionisdisplayedasUnknown
• Analysisprocess:
a.Checkthebasebandversionstatus,initiallydeterminedtobeM odemEE
b.Searchforthekeywordmain_logModem exception,andlocatetheASSERTerrorto
theNVverification-relatedmodule
c.ConfirmedthattherootcauseisthattheOTAupgradeprocesswasinterrupted,resulting
indatacorruptionintheNVpartition,andtheM odemstartupverificationfailuretriggered
EE

# Page 11
• ConclusionandSuggestions:IncorporateNVverificationcompatibilitypatches,add
integrityverificationtoOTAupgradepackages,andavoiddatacorruptioncausedby
abnormalinterruptionduringtheupgradeprocess.ReferenceDocument:LI6_v/LI7_vPost-
OTAUpgradeCardRecognitionFailureandIM EIDisappearanceProblemReviewReport
Case2:OccasionalM odem EECausedbyExcessiveIOLoad
• Problem Phenom enon:Thesignaloccasionallydropsforabout10secondswhenthe
machineisidle,andthenautomaticallyrecovers
• Analysisprocess:
a.CheckthemodemdumplogandlocatetheASSERTerrorintheIOread/writerelated
module
b.Checkedthesystemloadatthetimetheproblemoccurred,andconfirmedthatmultiple
backgroundprocessesweresimultaneouslyperformingIOreadandwriteoperations,
competingfortheschedulingresourcesoftheM odemsubsystem,whichtriggeredEEdue
totimeout
• ConclusionsandRecom m endations:OptimizethesystemIOschedulingstrategy,limitthe
IOpriorityofbackgroundprocesses,andavoidpreemptingresourcesoftheM odem
subsystem.Referencedocument:IO_LOADINGloadcausesM odemEE
6.FrequentlyAskedQuestions(FAQ)
Q:WhatshouldIdoifthecapturedM odemlogcannotbeparsed?
A:ConfirmwhethertheELFandDbgInfofilesforthecorrespondingversionhavebeenobtained.
Afterplacingthefilesinthelogdirectory,simplyopenthemusingtheparsingtool.
Q:IsaM odemEEissuenecessarilyasoftwareproblem?
A:Notnecessarily.M ostM odemEEissuesinmarketcustomercomplaintsarecausedby
hardwareproblemsthatleadtoM odemloadingfailures,soitisnecessarytofirstcheckwhether
thehardwareisnormal.
Q:WhatattachmentsarerequiredforsubmittingaproblemCRontheM TKplatform?
A:ItisnecessarytoprovidetheM DlogandM Ddumpbin,APLog,M odem-sideELFfile,andthe
correspondingversion'sfullDbgInfofileatthetimepointoftheissue.
7.Platform Expansion
TheabovemainlyexplainstheM TKplatform.Below,wewillexpandontheM odemEEissuesof
theUnisocplatform,mainlyinthreesteps:dumpcapture,dumpanalysis,andpreliminary
analysis.

# Page 12
7.1dum pcapture
SpecialattentionisrequiredfortheUserversion:
*#9646633#-->Debug&LOG-->YLog-->Settings-->LogSetting-->M odemlogSetting--
>M odemReset关闭
*#9646633#-->Debug&LOG-->YLog-->Settings-->LogSetting-->M odemlogSetting--
>M odemSaveDump打开

# Page 13
Thenstartcapturingthelog,reproducetheissue,andexportthelogaftercompletion.Aslongas
amodemcrashoccurs,bydefault,adumpfilewiththe.dmpsuffixwillbegeneratedinthe
/data/ylog/modem/directory
M ethodformanuallytriggeringamodemcrash:Entertheylogapplication,clickDebugsetting&
tools,clickmodemassertmanually,andthenamodemcrashwillbemanuallytriggered
7.2Dum pAnalysis
InthecapturedM odemlog,therewillbelogsintheformofminidumpand.dmp
Dumpfileswiththe.dmpsuffixneedtobeplacedinthelogeltoolforparsing:openthelogel
tool,simplydragthedmpfileintoit,andthetoolwilldisplaytheAssertInformationparsing
interface.Theparsingiscompletedwhen"finish"appears,andafterparsing,.assand.memfiles
willbegeneratedinthefolderunderthecorrespondingdirectory
7.3Prelim inaryAnalysis
①SearchingforkeywordssuchasM ODEM _CTRL,assert,andcrashinandroid.logcanrevealthe
sourcefileandcauseofM odemCrash(the.cfileisnotopensourcetousandrequiresthe
platformprovidertoquery)

# Page 14
The.assfilegeneratedafterparsingthe②.dmpfile,whenopenedintextformat,allowsyouto
viewthespecificversionandthecauseofthecrash
③OpentheminidumpfiletoviewthecauseoftheCrash
Sincesomecontentisnotopensource,afterlocalpreliminaryanalysis,submitaCQtothe
platformforfurtheranalysis,andthefollowingmaterialsneedtobeprovided:
A.Dumplog(logcontainingdmpandminidumpfiles)
B.Versioninformationwheretheissueoccurred(M odemversionnumber,etc.)

# Page 15
C.M odemversioncorrespondingsymboltable(.axffile)
D.Preliminaryanalysisconclusion
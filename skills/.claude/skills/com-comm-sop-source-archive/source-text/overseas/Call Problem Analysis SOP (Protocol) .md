# Page 1
CallProblem AnalysisSOP(Protocol)
ApplicableObjectsandScenarios
• ApplicableObjects:Testers,developers,andrelevanttechnicalsupportpersonnelrelatedto
theprotocol.
• ApplicableScenarios:M ainlyapplicabletohandlingthreem ajorcategoriesofissues,
nam elyvoice(Call)services,IM Sservices,andsupplem entaryservices.
• ApplicablePlatform:M TK 
Preparation
FortoolsusedinreadingthisSOP,pleasereferto 《⼯具安装与环境配置指南》
1.Voice(Call)Service
Voice(Call)servicesm ainlyinvolvecom m onissuessuchasoutgoingcalls(M O,callingparty),
incom ingcalls(M T,calledparty),calldrops,silentcalls,etc.Basedonthecurrentnetworkm ode
them obilephoneiscam pedon,callprocessesarem ainlydividedintotraditionalCS(Circuit
Switching)callsandIP-basedIM Scalls
Com pleteCallProcess
W henanalyzingaproblem ,itisfirstnecessarytorefertothecom pleteprocessandconfirm 
whichspecificstephasfailed.ThefollowingtakestheM obileOriginated(M O)processasan
exam ple:
1.CS(CircuitSwitching)CallingCallSignalingProcess
Intraditional2G /3G networks,voicecallsarem ainlycontrolledbytheM SC(M obileSwitching
Center).ThefollowingisthetypicalM obileOriginated(M O)process:

# Page 2
1.RRCConnectionSetup(U E↔RAN):Them obilephoneestablishesaRadioResourceControl
connectionwiththebasestation.
2.CM ServiceRequest(U E ➔ M SC):Them obilephonesendsaconnectionm anagem ent
servicerequesttothecorenetwork,requestingvoiceservice.
3.Authentication&Security(M SC↔HLR/AuC↔U E):Thecorenetworkperform s
authenticationandencryptionprocessesonusers.
4.Setup(U E ➔ M SC):Them obilephonesendsaSetupm essage,containinginform ationsuch
asthecallednum ber.
5.CallProceeding(M SC ➔ U E):TheM SCreceivestherequestandreplieswithCallProceeding,
indicatingthatitisprocessingthecall.
6.RABAssignment(M SC↔RAN↔U E):AllocateRadioAccessBearer(RAB)andestablisha
voicechannel.
7.Alerting(M SC ➔ U E):Thecalledendstartsringing,andtheM SCsendsanAlertingm essage
tothecallingend(thecallingendhearsthe"beep"sound).
8.Connect(M SC ➔ U E):Thecalledpartyanswersthecall,andtheM SCsendsaConnect
m essagetothecallingparty.

# Page 3
9.ConnectACK (U E ➔ M SC):Thecallingpartyreplieswithconfirm ation,atthistim ethetwo-
wayvoicecall(VoiceM edia)isofficiallyestablished.
ThefollowingprocessisthestandardprocessforestablishingaCSCall(CSFB)whenfallingback
from a4G networktoa3G network.IftheU Eisoriginallyina2G /3G network,therewillbeno
ESR( Extended_Service_Request )process:
2.IM S(IPM ultim ediaSubsystem )CallingCallSignalingProcess
In4G /5G networks(suchasVoLTE/VoNR),voiceistransm ittedasIPpackets,andsignalingis
basedonSIP(SessionInitiationProtocol).ThefollowingisatypicalIM Scallingprocess:

# Page 4
1.SIPINVITE(U E ➔ P-CSCF ➔ S-CSCF):Thecallingm obilephoneinitiatesaSIPINVITErequest,
whichincludesm edianegotiationinform ation(SDPOffer).
2.SIP100Trying(Network ➔ U E):Thenetworksidereplieswith100Trying,indicatingthatthe
requesthasbeenreceivedandisbeingprocessed.
3.SIP183SessionProgress(Network ➔ U E):Thenetworksidereturnsa183m essage
containingthecalledparty'sm edianegotiationinform ation(SDPAnswer).
4.PRACK&200OK (U E↔Network):ThecallersendsPRACK toconfirm the183m essage,and
thenetworkreplieswith200OK .
5.DedicatedBearerSetup(EPC/5G C↔RAN↔U E):Thecorenetworktriggersthe
establishm entofadedicatedQCI=1voicebearer(toensurevoicequality).
• Note:Thebitrateallocatedbythenetworkm ustbegreaterthanthem ediainform ation
negotiatedinM essage183(Algorithm :AS+RR/1000+RS/1000).
6.UPDATE&200OK (U E↔Network):Afterthededicatedbearerisestablished,thecalling
partysendsanU PDATEm essagetonotifythenetworkthattheresourcesareready,andthe
networkrespondswith200OK .
7.SIP180Ringing(Network ➔ U E):Thecalledsidestartsringing,andthenetworksendsa180
Ringingm essagetothecallingside.

# Page 5
8.SIP200OK(INVITE)(Network ➔ U E):Thecalledpartyanswersthecall,andthenetwork
sends200OK tothecallingparty.
9.SIPACK (U E ➔ Network):ThecallerreplieswithanACK confirm ation.
10.RTPM ediaFlow(U E↔CalledParty):Two-wayRTPvoicemediaflowisofficially
established.
Com paredwithtraditionalCScalls,IM Scallshavebandwidthrequirem entsforthededicated
voicebearer(Step5):thebitrateallocatedbythenetworkneedstobegreaterthanthem edia
inform ationnegotiatedinthe183SPm essage.Thespecificalgorithm isAS+RR/1000+RS/1000.
Forexam ple,inthefollowinglog,ASis38,andbothRRandRSare0,sotheQCI1bitrate
allocatedbythenetworkneedstobeatleast38,andtheallocationof40herem eetsthe
requirem ent:

# Page 6
Problem troubleshootingpoints
1.Confirmthenetworkmodeduringthecall(CSorIM S?)
◦ TroubleshootingM ethod:
▪ Checkthe4G /5G /HDiconsinthestatusbarviathetestvideo
▪ 在radiolog中搜索VOICE_REG /DATA_REG 
▪ ChecktheOTAm essagefrequencypoints(5G :NR-ARFCN,4G :EARFCN,3G :U ARFCN,
2G :ARFCN)forthecorrespondingtim eperiodintheM odem log
Thisdeterm ineswhichsetofsignalingproceduresyouneedtolookat.
2.Checkthenetworksignalqualityduringacall(isitaweaknetwork?)
◦ TroubleshootingM ethod:
▪ Checkthenum berofsignalbarswhilewatchingthevideo;
▪ (M TK Platform )ViewEM inform ationinM odem log:EM ->EM M A->4/5G ->Load->
M easurem ent
▪ SearchinRadiologforRSRP /RSRQ andotherkeywords
▪ CheckintheM odem logMeasurementReport ,focusingonRSRP (signalstrength)
andRSRQ (signalquality).W henRSRPisbelow-120dBm ,callfailureordroppedcalls
arehighlylikelytooccur.

# Page 7
3.Checkifthesignalingprocessiscompleteandifthereareanynetworkerrorreports?
◦ TroubleshootingM ethod:
▪ Com parewiththeabovestandardprocesstoseeatwhichstepthesignalingis
interrupted.PayspecialattentiontotheCANCEL ,RELEASE ,DISCONNECT 
m essagessentbythenetwork,andchecktheCause /Reason fieldstheycarry
(suchasM ediaBearerLost,Norm alClearing,etc.).
4.Cross-validation(checkREFbehavior)
◦ TroubleshootingM ethod:
▪ Confirm whetherthecom parisondevice(REF)atthesam elocationandwiththesam e
operatorhasthesam eproblem todistinguishwhetheritisaterm inalissueora
network-sidefault.
ActualProblem Cases
Case1:IM Scannotreceiveincom ingcalls(processinterruptedafter183SP)
• PhenomenonDescription:Testfeedbackindicatesthatthem obilephone(K M 9)cannot
answerincom ingcallsinaspecificenvironm ent,andthecom parisondevicealsoexhibitsa
sim ilarphenom enon.
• TroubleshootingProcess:
a.Confirmnetworkandsignal:ThephoneisregisteredonVoLTE(4G ),belongingtoIM S
Call.CheckMeasurementReport ,wheretheRSRPisaround-117dBm ,indicatinga
poorsignalbutstillatanacceptableconnectionlevel.

# Page 8
b.Checkthesignalingprocess:Them obilephonereceivedtheINVITE incom ingcall
requestfrom thenetworkandnorm allyrepliedwith100 Trying andm ultiple183 
Session Progress .
c.LocatingBreakpointsandErrorReporting:Afterthephonesent183 SP ,itdidnot
receivethePRACK from thenetworkforalongtim e.Subsequently,thenetworkdirectly
sentaCANCEL m essagetoendthecall.
d.Analyzethecauseoftheerror:ChecktheReasoncarriedinthe CANCEL m essage,
whichshows Media Bearer Lost (M ediabearerlost).Atthesam etim e,checkthe
underlyingOTAm essageandfindthatthenetworkindeeddidnotestablishadedicated
bearerwithQCI=1forthiscall.
• Conclusion:Networksideanom aly.Thenetworkfailedtosuccessfullyestablishadedicated
voicebearer,resultinginnoresponsetoPRACK andactivelyCANCEL thecall.Considering
thatthecom parisondevicealsohasthisissue,itisconfirm edtobeanetworkfault.
2.IM S
TheIM Sservicem odulem ainlyfocusesontheregistrationofVoLTE/VoW iFi,aswellasthe
handoverbetweenthetwo.OnlywhenIM Sregistrationissuccessfulcanthem obilephoneuse
high-definitionvoicecallsandrelatedsupplem entaryservices.
Com pleteIM SRegistrationProcess

# Page 9
IM Sregistrationm ainlyconsistsoftwophases:theestablishm entoftheunderlyingdata
channel(PDN)andtheinteractionoftheupper-layerSIPprotocol.
1.EstablishIM SPDN:Them obilephonerequeststhenetworktoestablishadedicatedIM S
datachannel(usuallyassignsadefaultbearerwithQCI=5).ForVoW iFi,anePDG tunnelalso
needstobeestablished.
2.InitiateaREGISTERrequest:Them obilephonesendsaSIP REGISTER m essage.
◦ Note:BycheckingtheP-Access-Network-Info (PANI)headerparam eters,itis
possibletodistinguishwhetherthecurrentregistrationisVoLTE,VoNR,orVoW iFi.
3.NetworkAuthentication(401&SecondREGISTER):Thenetworkusuallyfirstresponds
with401 Unauthorized toinitiateanauthenticationchallenge.Aftercalculation,the
m obilephoneinitiatesasecondREGISTER withauthenticationinform ation.
4.Registrationsuccessful(200OK):Networkauthenticationpassed,returning200 OK .

# Page 10
5.SubscriptionStatus(SUBSCRIBE&NOTIFY):Them obilephonesendsSUBSCRIBE (Event:
reg)tosubscribetotheregistrationstatus,andthenetworksendsNOTIFY m essages.At
thistim e,thestatefieldintheXM Lshouldbe"active" (ifitis"terminated" ,itm eans
beingderegisteredbythenetwork).
Thecom pletelogprocessisasfollows:
1.W henregisteringwithIM S,itisnecessarytoprioritizetherequestforIM SPDN,andthe
networkwillestablishaQCI5bearer
2.U EinitiatesaREG ISTERrequest.PayattentiontothePANI(P-Access-Network-Info)
param eter,whichcandistinguishbetweenVoLTE/VoNR/VoW iFi;payattentiontotheExpires
param eter,whichcandistinguishbetweenregistrationandderegistration
3.AfterreceivingREG 200OK ,theU EinitiatesaSU BSCRIBE,payingattentiontotheEvent
param eter,whichisusedtosubscribetotheregevent;andpayingattentiontotheExpires
param eter,whichisusedtodistinguishbetweenregistrationandderegistration
4.W henthenetworksendsaNOTIFYm essage,theIM Sstatusshouldbeactive(ifderegistered,
thestatusshouldbeterm inated)
VoW iFiIK Ev2AuthenticationCom pleteProcess

# Page 11
IK Ev2ism ainlyusedtoestablishsecureIPsectunnels,includingtwophases:IK E_SA_INITand
IK E_AU TH.Forthedetailedprocess,pleaserefertothefollowingdocum ent
 Vowifi介绍
Problem troubleshootingpoints
1.CheckiftheIM S/VoWiFiswitchisturnedon?
◦ TroubleshootingM ethod:CheckU Iscreenrecording;searchforthekeywordEIMSCFG 
inAP/M odem logtoconfirm theswitchstatus.
2.ConfirmwhetherthenetworksupportsIM S(VoPS)?
◦ TroubleshootingM ethod:
▪ CheckintheM odem logforTAU_Accept orAttach_Accept m essagestoseeif
theIMS voice over PS session param eterissupported

# Page 12
▪ SearchinM odem logforMSG_ID_ATP_IMC_IMSVOPS_NOTIFICATION_REQ to
viewims_vops flagbit.
3.CheckiftheunderlyingIM Cmodulemeetstheregistrationrequirements?
◦ TroubleshootingM ethod:(ForM TK platform )SearchforthekeywordNormal REG 
condition check result intheM odem logandcheckiftheoutputisOK .
4.CheckifIM SPDNestablishmentisnormal?
◦ TroubleshootingM ethod:Filterkeywords DATA_CALL_REQ | DATA_CALL_CNF ,
checkthedialingresultoftheIM SAPN,andconfirm whetheravalidIPaddresshasbeen
obtained.ForVoW iFi,itisalsonecessarytoconfirm whethertheIM SAPNconfiguration
contains bitmask 18 .
6.CheckiftheSIPregistrationprocessiscomplete?
◦ TroubleshootingM ethod:IntheSIPM essagesview,checkifthereisasentREGISTER ,
whetherthenetworkreplieswitherrorcodessuchas403 ,503 ,etc.,orifarejectis
directlyissuedinNOTIFY .
ActualProblem Case
Case1:VoW iFiregistrationfailed(IM SAPNconfigurationisabnorm al)
PhenomenonDescription:TheuserturnedontheVoW iFiswitch(W iFiCallingPreferred),but
theVoW iFiicondidnotappearinthestatusbar,andthefunctioncouldnotbeused.
TroubleshootingProcess:
1.Checktheswitchandprecondition:Confirm thattheVoW iFiswitchisturnedon.Searching
thelogrevealsthattheIM Cm oduleoutputsOK ,m eetingtheconditionsforinitiating
registration.

# Page 13
2.CheckIM SPDNStatus:CheckedtheIM SAPNdial-uprequestandfoundthatIM SPDN
establishm entfailed.Thelogprintedget NULL WLAN apn info ,returninganem ptyIP
address.
3.Analysisofthecause:EstablishingtheunderlyingVoW iFichannelm ustuseanIM SAPNthat
includesbitmask 18 .SincethephonefailedtoobtainthecorrectW LANAPNinform ation,
thedatachannelestablishm entfailed,andtheupper-layerSIPREGISTER wasnotsentat
all.
Conclusion:Term inal-sideconfigurationissue.TheU EsidedidnotcorrectlyconfiguretheIM S
APNwithbitm ask18,resultinginVoW iFibeingunabletoregister.
Case2:VoW iFiRegistrationFailed(RejectedduetoInternalNetwork
Abnorm ality)
Phenomenondescription:VoW iFicannotregister,andthecom parisondevicecannotregister
eitherunderthesam eW iFinetwork.
TroubleshootingProcess:
1.Checkswitchandprecondition:EIMSCFG showstheswitchison,IM Cconditioncheck
OK .
2.CheckIM SPDNStatus:DATA_CALL_CNF indicatesthatavalidIPv4addresshasbeen
successfullyobtained,indicatingthattheIM SPDNhasbeenestablishednorm ally.
3.CheckSIPsignaling:Them obilephonesuccessfullysentREGISTER ,andtheprocess
reachedthelaststepofNOTIFY .However,byparsingtheNOTIFY m essagesentbythe
network,itwasfoundthatIMS status isterminated ,andthecorrespondingevent 
isreject .
Conclusion:Networksideanom aly.Boththeconfigurationandprocessontheterm inalsideare
norm al,butthecorenetworkactivelyrejectedourregistrationrequest.Basedonthe
phenom enonofthecom parisondevice,itisconfirm edtobeanetwork-sideissue.

# Page 14
Case3:VoW iFi<->VoNRHandoverFailure(IM SPDNreject)
PhenomenonDescription:Duringacall,IM SPDNHandoverfailureleadstocalldrop.
TroubleshootingProcess:
1.Checktheswitchandprecondition:Norm alswitchfrom VoNRtoVoW iFibeforethe
problem occurred,indicatingthattheswitchstatusisnorm al
2.CheckIM SPDNStatus:There is no IP Address in DATA_CALL_CNF ,and
errcause_present isTrue,indicatingthatIM SPDNestablishm entfailed.
3.Analysisofthecause:From theOTAm essage,itcanbeseenthatthephonenorm ally
initiatedPDU_SESSION_ESTABLISHMENT_REQUEST ,andRequest Type isExisting 
PDU session ,indicatingthatweexpectedtoswitchIMS PDN to5G SA network,butthe
networkrepliedwithPDU_SESSION_ESTABLISHMENT_REJECT ,carryingthe
reasonunknown .
Conclusion:Networksideanom aly.Term inalsideconfigurationandprocessesareallnorm al,
butthecorenetworkactivelyrejectedourIM SPDNHandoverrequest.
3.Supplem entaryBusiness

# Page 15
Supplem entaryservicesm ainlyfocusonCLIR(CallingLineIdentificationRestriction),Call
Forwarding,CallBarring,andCallW aiting.Theoperationsofthispartoftheservicesareusually
dividedintotwocategories:Interrogation/CheckandActivation/Registration.Atthe
protocollevel,thesignalinginteractionsofsupplem entaryservicesdifferbetweenCSnetworks
andIM Snetworks.
Supplem entthecom pleteprocessofthebusiness
Duetonetworkevolution,theim plem entationm ethodsofsupplem entaryservicesarem ainly
dividedintotraditionalCSsignaling(SSviaCS)andIM S-basedXM Ldocum entm anagem ent
(XCAP/U tinterface).
1.CSNetworkSupplem entaryServiceSignalingProcedure(SSviaCS)
In2G /3G orCSFB(CSFallback)scenarios,supplem entaryservicesarem ainlyexchanged
betweenthem obilephone(U E)andthecorenetwork(M SC/HLR)throughREGISTER and
FACILITY m essages.
• InitiateRequest(UE ➔ NW):Them obilephonesendsREGISTER m essage,whichincludes
specificsupplem entaryservicecodes(SSCode,suchasCallForwarding,CallW aiting)and
operationtypes(Operation:suchasRegister,Activate,Deactivate,Interrogate).
• NetworkResponse(NW ➔ UE):Afternetworkprocessing,theresult(ReturnResult)orerror
(ReturnError/Reject)isreturnedviaRELEASE COMPLETE orFACILITY m essage.
Example:CSNetworkQueryCallForwardingInterrogation
TypeM oduleM essageCom m ent
OTACC[M S->NW ]CC__REG ISTERFacility:InterrogateSS(SS-Code:CallForwarding)
OTACC[NW ->M S]CC__RELEASE_COM PLETEFacility:ReturnResult(Status:
Active/Inactive,ForwardedToNum ber)
2.IM SNetworkSupplem entaryServiceSignalingProcedure(U tInterface/
XCAP)
InVoLTE/VoW iFinetworks,supplem entaryservicesusuallydonotuseSIPsignaling,butinstead
gothroughtheUtinterface.M obilephonesinteractwiththenetwork'sserviceapplication
server(TAS)throughtheHTTP/XCAPprotocol(XM LConfigurationAccessProtocol).
Toensuresecurity,m anyoperatorsrequirethatbeforeaccessingTAS,two-wayauthentication
m ustfirstbeperform edwithGBA(GenericBootstrappingArchitecture)processandBSF

# Page 16
(BootstrappingServerFunction)servertoobtainthesecuritykey(K s_NAF),andthenusethis
keytoperform HTTPDigestauthenticationwithTAS.
Acom pleteU tinterfaceinteractionisusuallydividedintotwophases:Phase1(BSF
authentication)andPhase2(XCAPserviceinteraction).
Phase1:BSFAuthentication(G BAProcess)
Ifthereisnovalidsecuritykeylocallyonthephone,orifTASreturns 401 Unauthorized 
challenge,thephonewillinitiateauthenticationwithBSF.
1.InitialRequest(UE ➔ BSF):Them obilephonesendsaHTTP GET requesttotheBSF
server,usuallywithoutauthenticationinform ation.
2.BSFChallenge(BSF ➔ UE):BSFreturns HTTP 401 Unauthorized ,andincludesa
random num ber(RAND)andnetworkauthenticationtoken(AU TN)inthe WWW-
Authenticate header,requiringthem obilephonetoperform AK A(Authenticationand
K eyAgreem ent)authentication.
3.M obilePhoneComputationandResponse(UE ➔ BSF):Them obilephonepassesRAND
andAU TNtotheU SIM cardforcom putation,resultingintheresponsevalue(RES)andthe
underlyingkey.Them obilephonethensendsanotherHTTP GET ,thistim eincludingthe
com putedRESintheAuthorization header.
4.BSFauthenticationsuccessful(BSF ➔ UE):AftertheBSFverifiesthattheRESiscorrect,it
returns HTTP 200 OK ,andincludesatransactionidentifier(B-TID,Bootstrapping
TransactionIdentifier)andthevalidityperiodofthekeyintheresponse.Atthispoint,both
them obilephoneandthenetworkhavegeneratedasharedkey(K s_NAF)forsubsequent
com m unication.
Phase2:XCAPServiceInteraction(withTAS/AS)
AfterobtainingtheB-TIDandkey,them obilephonebeginstotrulysetorquerysupplem entary
services.
1.ServiceRequest(UE ➔ TAS):Them obilephonesendstotheTASHTTP GET (query)or
HTTP PUT (setting)request,withtheU RLpointingtoaspecificsupplem entaryserviceXM L
node(suchassimservs.xml ).Atthistim e,them obilephonewillcarrytheB-TID
obtainedfrom theBSFintherequestheader.
2.TASAuthenticationandResponse(TAS ➔ UE):Afterreceivingtherequest,TASobtainsthe
correspondingkey(K s_NAF)from BSFbasedonB-TIDtoverifytheidentityofthem obile
phone.Aftertheverificationissuccessful,TASperform sthecorrespondingbusiness
operationandreturnsHTTP 200 OK (includingXM Lstatusdata)orthecorresponding
operationresult.

# Page 17
Example:CompletesignalingforcallforwardingqueryincludingBSFauthentication
TypeM oduleM essageCom m ent
---Phase1:G BAAuthentication(withBSF)---
HTTPU t[M S->NW ]G ET/bsf(InitiateinitialrequesttoBSF)
HTTPU t[NW ->M S]HTTP/1.1401U nauthorized(BSF下发AK A挑战，包含RAND/AU TN)
HTTPU t[M S->NW ]G ET/bsf(carryingRESresponsecalculatedbyU SIM )
HTTPU t[NW ->M S]HTTP/1.1200OK (Authenticationsuccessful,returningB-TIDand
validityperiod)
---Phase2:XCAPServiceInteraction(withTAS)---
HTTPU t[M S->NW ]G ET/.../sim servs.xm l(Querycallforwardingstatusfrom TAS,
carryingB-TID)
HTTPU t[NW ->M S]HTTP/1.1200OK (TASreturns200OK ,withthecallforwarding
statusinXM Lform atincludedintheBody)
(Note:Som eIM Snetworksalsosupportcarryingsupplem entaryserviceinform ationthrough
specificheadersinSIPINVITE,suchasCLIRim plem entedthroughPrivacy: id field)
Problem troubleshootingpoints
1.Whatisthecurrentnetworkdomain?(CSvsIM S)
◦ Confirm whetherthem obilephoneiscurrentlycam pedontheCSnetwork(2G /3G )orthe
IM Snetwork(VoLTE/VoW iFi).Thisdeterm ineswhetherthesupplem entaryserviceuses
thetraditionalCSREGISTER signalingortheIM SHTTP/XCAP process.
◦ TroubleshootingM ethod:
▪ Checkthestatusbaricon
▪ Checkthecurrentregistrationdom ain(VOICE_REG /DATA_REG )intheRadiolog.
2.IsthesupplementaryservicepermissionenabledfortheSIM card?
◦ M anysupplem entaryservices(especiallycallforwardingandcallbarring)require
perm issiontobeenabledonthecarrierside.Ifnotenabled,thenetworkwilldirectly
rejecttherequest.
◦ TroubleshootingM ethod:

# Page 18
▪ CheckinCSsignalingRELEASE COMPLETE forwhetheritcarriesReturn Error: 
SystemFailure orIllegalSS-Operation ;
▪ CheckinIM SwhethertheHTTPresponseis 403 Forbidden or 404 Not 
Found .Itisrecom m endedtousethesam ecardcom parisonm achineforcross-
verification.
3.IstheUtinterface(IM S)configuredcorrectlyandestablishedsuccessfully?
◦ Forsupplem entaryservicesunderVoLTE,adedicatedXCAPPDN(usuallyreusedwithIM S
orInternetPDN,dependingontheoperator)needstobeestablished,andthecorrect
XCAPserveraddress(XCAPRootU RI)isrequired.
◦ TroubleshootingM ethod:
▪ CheckiftheAPNandIPAddressofXCAPweresuccessfullyobtainedfrom theM odem 
log.
▪ CheckwhethertheXCAPU RLiscorrectlyconcatenatedintheAPlog(suchas
RIL/Telephonylog),andwhethertheauthentication(AK A)issuccessful.
4.Isthesignalinginteractioncomplete,andwhaterrorcodedidthenetworkreturn?
◦ CSDom ain:FocusoncheckingwhetherthenetworkrespondsaftertheREGISTER 
m essageissent,aswellasthespecificCauseValueorErrorCodeinRELEASE 
COMPLETE .
◦ IM SDom ain:Focusoncheckingwhether200 OK isreceivedaftertheHTTP GET/PUT 
requestissent.Ifitisa4xx/5xx error,thedetailederrordescriptionintheHTTPBody
needstobeanalyzed.
ActualProblem Case
Case1:CallforwardingsetupfailedunderVoLTE(U tinterfaceexception)
PhenomenonDescription:W henauserenables"U nconditionalCallForwarding"throughthe
m obilephonesettingsinterfaceundertheVoLTEnetwork,aprom pt"NetworkorSIM carderror"
appears.TroubleshootingProcess:
1.Confirm thenetworkdom ain:Atthistim e,them obilephoneisregisteredonVoLTE,and
thereisnofallbacktoCSduringthequeryprocess.Supplem entaryservicesshouldusethe
U tinterface(HTTPXCAP).

# Page 19
2.ViewNetLog:ByfilteringHTTP/XCAP-relatedkeywords,itwasfoundthatthephonesenta
HTTP PUT requesttom odifythecommunication-diversion (callforwarding)XM L
configuration.
3.Checknetworkresponse:Thenetworkdidnotreturn200 OK ,butinsteadreturnedHTTP 
403 Forbidden .
4.Furtheranalysis:Expand the response body of 403 Forbidden ,anditisfound
thatthenetworkprom ptis"U sernotauthorizedforthisservice".
Conclusion:ThisSIM carddoesnothavetheperm issiontom odifytheU tinterfaceforcall
forwardingonthecarrierside(TASserver).Itisalim itationissuerelatedtothecard
package/networkside.Itisrecom m endedthattheusercontactthecarriertoenableit.
Case2:CSDom ainCallWaitingQueryFailed(SignalingRejected)
PhenomenonDescription:W henauserdials*#43# toquerythecallwaitingstatusundera
3G network,theinterfaceprom pts"QueryFailed".TroubleshootingProcess:
1.Confirm thenetworkdom ain:Them obilephonecam pson3G (W CDM A)andfollowsthe
traditionalCSsupplem entaryservicesignalingprocess.
2.ViewM odem Log:FilterCC (CallControl)m odulem essages,find[MS->NW] 
CC__REGISTER ,andconfirm thatthephoneinitiatedaInterrogateSS (SS-Code:
CallW aiting)request.
3.Checknetworkresponse:Thenetworkrepliedwith[NW->MS] CC__RELEASE_COMPLETE .
4.Analysisoftheerrorcause:W henparsingtheRELEASE COMPLETE m essage,itwasfound
thatitcarriedReturn Error: FacilityNotSupported .
Conclusion:ThecurrentlyresidentM SC(M obileSwitchingCenter)doesnotsupportthequery
ofthissupplem entaryservice,orthereisanabnorm alconfigurationonthenetworkside.Itisa
network-sidecom patibility/configurationissue.
Case3:CallRestrictionQueryFailedunderVoLTE(DNSResolutionFailed
duetoIncorrectXCAPServerConfiguration)
PhenomenonDescription:W henausertriestoquerythe"CallRestriction"statusinthe
settingsundertheVoLTEnetwork,theinterfacespinsforalongtim eandthenprom pts
"Networkconnectionerror".
TroubleshootingProcess:

# Page 20
1.Confirm thenetworkdom ainandservicetype:TheuserisinaVoLTEenvironm ent,andthere
isnofallbacktoCSduringthequeryprocess.QueryingcallrestrictionsshouldfollowtheU t
interface(HTTPXCAPprocess).
2.CheckHTTP/XCAPsignaling:SearchinM odem logandAPlog(suchasTelephony/RIL)for
HTTP GET orXCAP relatedkeywords,andfindthatnoHTTPrequestsweresentatall.
3.Troubleshoottheunderlyingnetworkconnection:Bytracingthelogbackward,itwasfound
thatbeforethephonewasabouttoinitiateanHTTPrequest,itattem ptedtoperform DNS
resolutiononthedom ainnam eoftheXCAPserver(suchas
xcap.ims.mncXXX.mccYYY.pub.3gppnetwork.org).
4.ReasonsforDNSLocationFailure:
◦ Filteringbythekeyworddns intheNetlogshowsthattheDNSserverreturned
NXDOMAIN (dom ainnam edoesnotexist)ortheresolutiontim edout.
◦ FurtherinspectionoftheCarrierConfigreadlocallyonthephoneorthepre-configured
XCAPRootU RIintheSIM cardrevealsthatthedom ainnam eaddressintheconfiguration
containsaspellingerror(e.g.,mcc ism isspelledasmmc ,oranexpiredtestdom ain
nam eisused),causingDNStofailtoresolveittoarealIPAddress.
Conclusion:DuetotheincorrectconfigurationoftheXCAPserverdom ainnam ereadonthe
m obiledevice,DNSresolutionfailed,whichinturnpreventedtheestablishm entofaTCP
connectionwiththeTASserver,andtheHTTPrequestwasnotsentatall.Thisisanerrorinthe
operatorparam eterconfiguration(SSDS/M BN/CarrierConfig)ontheterm inalside,andthe
correspondingconfigurationfileneedstobem odified.
Appendix:G lossary
1.BasicBusinessConcepts
• M O(M obileOriginated):Caller,i.e.,them obilephoneinitiatesacallactively.
• M T(M obileTerminated):Called,i.e.,them obilephonereceivesanincom ingcall.
• CS(CircuitSwitched):CircuitSwitching,atraditional2G /3G voicecallnetworktechnology
thatoccupiesanexclusivecom m unicationchannel.
• IM S(IPM ultimediaSubsystem):IPM ultim ediaSubsystem ,anIP-basedvoiceand
m ultim ediaservicearchitecturein4G /5G networks,uponwhichVoLTE,VoNR,andVoW iFiare
allbased.

# Page 21
• CSFB(CSFallback):CircuitSwitchedFallback,atechnologywherewhenthe4G network
doesnotsupportVoLTE,thenetworkinstructsthem obilephonetofallbacktothe2G /3G CS
networkforcallswhenm akingorreceivingacall.
• SS(SupplementaryServices):Supplem entaryservices,suchasCallForwarding,Call
Barring,CallW aiting,CallingLineIdentificationRestriction(CLIR),etc.
2.ProtocolandSignaling
• RRC(RadioResourceControl):RadioResourceControl,thecontrolplaneprotocolbetween
them obilephoneandthebasestation,responsiblefortheestablishm ent,m aintenance,and
releaseoftheairinterfaceconnection.
• SIP(SessionInitiationProtocol):ThecorecontrollayerprotocolintheIM Snetworkusedto
establish,m odify,andterm inatem ultim ediasessions(suchasvoicecalls).
• SDP(SessionDescriptionProtocol):SessionDescriptionProtocol,usuallyincludedinthe
BodyofSIPm essages(suchasINVITE,183),isusedbyboththecallingandcalledpartiesto
negotiatem ediaparam eters(suchasaudioencodingform at,PortNum ber,bandwidth,etc.).
• PRACK(ProvisionalResponseAcknowledgement):ProvisionalResponse
Acknowledgem ent,am essageintheSIPprotocolusedforreliableacknowledgem entof1xx
provisionalresponses(e.g.,183SessionProgress).
• RTP(Real-timeTransportProtocol):TheReal-tim eTransportProtocol,whichisusedto
actuallytransm itvoicem ediadatastream sinabidirectionalchannelafteracallis
established.
• XCAP(XM LConfigurationAccessProtocol):XM LConfigurationAccessProtocol,basedon
HTTP.InVoLTE/VoW iFi,m obilephonesreadorm odifysupplem entaryserviceconfigurations
onthenetworksidethroughthisprotocol(U tinterface).
• GBA(GenericBootstrappingArchitecture):G enericBootstrappingArchitecture,an
authenticationm echanism .InIM Ssupplem entaryservices,itisusedfortheauthentication
processtogenerateasharedkeybefoream obilephoneestablishessecurecom m unication
withaserviceserver.
3.NetworkNodesandArchitecture
• M SC(M obileSwitchingCenter):M obileSwitchingCenter,thecorecontrolnodeofthe
2G /3G CSnetwork,responsiblefortheroutingandcontrolofvoicecalls.
• TAS(TelephonyApplicationServer):TelephonyApplicationServer,aservicelogicnodein
theIM Snetwork,responsibleforprocessingandstoringusers'supplem entaryservice
configurations(suchascallforwardingsettings).

# Page 22
• BSF(BootstrappingServerFunction):BootstrappingServerFunction,thecore
authenticationserverintheG BAarchitecture,responsibleforperform ingm utual
authenticationwiththem obilephoneandissuingthekey(K s_NAF).
4.K eyParam etersandIndicators
• QCI(QoSClassIdentifier):QualityofServiceClassIdentifier,usedtodefinethepriorityof
databearers.InIM S,QCI=5istypicallyusedforthedefaultbearerofSIPsignaling,QCI=1is
usedforthededicatedbearerofvoicem edia(RTP).
• PANI(P-Access-Network-Info):ASIPheaderparam eterusedtoindicatetothenetworkthe
typeofnetworkthem obilephoneiscurrentlyconnectedto(suchas4G E-U TRAN,5G NR,or
W iFi),andisanim portantindicatorfordistinguishingVoLTE,VoNR,andVoW iFiduring
troubleshooting.
• RSRP(ReferenceSignalReceivedPower):ReferenceSignalReceivedPower,akeyindicator
form easuringthesignalstrengthofacell.Thesm allerthevalue,theweakerthesignal(e.g.,
below-120dBm indicatesextrem elyweaknetworkandispronetocalldrops).
• RSRQ(ReferenceSignalReceivedQuality):ReferenceSignalReceivedQuality,anindicator
thatm easuresthecellsignalqualityandnetworkinterferencelevel.
• B-TID(BootstrappingTransactionIdentifier):BootstrappingTransactionIdentifier.Itis
assignedbytheBSFaftersuccessfulG BAauthentication,andthem obilephoneneedsto
carrythisidentifiertoproveitsidentitywhensubsequentlyaccessingtheTASserver.
Qcom Platform Voice&SSrefertothefollowing
docum ents:
 Qcom Voice&IM S架构
 ⾼通补充业务分析.pptx
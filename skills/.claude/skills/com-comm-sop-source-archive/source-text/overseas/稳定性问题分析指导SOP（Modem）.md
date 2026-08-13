# Page 1
稳定性问题分析指导SOP（Modem ）
1.⽂档概述
1.1⽂档⽬的
本⽂档旨在解决⼿机M odem⼦系统异常崩溃（M odemEE）引发的各类问题，包括但不限于蜂窝数据
掉⽹、SIM 卡不识卡、IM EI丢失/显⽰异常、信号短时间消失后⾃动恢复等场景，提供标准化的问题定
位、分析和处理流程。
1.2适⽤范围
• 适⽤问题现象：掉⽹、不识卡、IM EI显⽰异常、基带版本显⽰为Unknown、信号消失10s左右⾃动
恢复、弹出modemcrash提⽰
• 适⽤芯⽚平台：M TK 、展锐（SPRD）、⾼通全系列⼿机平台
• 适⽤场景：项⽬测试问题、⼤数据监控异常、市场客诉M odem相关问题
2.问题分析地图
2.1核⼼问题分类
M odemEE问题可细分为5类具体⼦场景：
1.基带版本号未知/不识卡类EE
2.信号消失后恢复/弹出modemcrash界⾯类EE
3.FANSAEE/M onkeyAEE测试触发类EE

# Page 2
4.⼤数据USIC监控捕获类EE
5.⾮常规EE（IO负载过⾼、OTA升级被打断等特殊场景导致）
2.2分析流程概览
3.标准操作流程(SOP)
3.1问题确认与复现
1.外部因素排查：更换SIM 卡、更换⽹络环境测试，确认问题是否仍然复现，排除运营商⽹络、SIM
卡损坏等外部原因
2.复现路径确认：记录问题触发的操作步骤，确认可稳定复现问题，便于后续复测验证
3.2⽇志抓取
完整抓取步骤参考官⽅指引：M odemEE问题log抓取SOP，核⼼步骤如下：
1.执⾏ADB命令开启⽇志全量打印，重启⼿机
2.按照复现路径执⾏操作触发M odemEE
3.使⽤⽇志导出⼯具导出全量⽇志，确认⽇志包含_EE_INVALIDdump⽬录、main_log、
modemlog、__exp_main.txt 等核⼼⽂件
3.3⽇志分析步骤
• 关键⽇志⽂件：main_log、modemdumplog、__exp_main.txt 、SYS_KERNEL_LOG 、
taglog（粉丝⽇志场景）、minidump（⼤数据场景）
• 核⼼关键词：ccci_mdinit 、Modem exception 、[ASSERT] 、[Fatal error
• 分析要点：
a.优先查看ASSERT报错的⽂件路径：rf check ⽬录下报错多为RF配置错误，mml1/ ⽬录下
报错多为射频相关问题

# Page 3
b.提取报错的⽂件名、⾏号以及P1/P2/P3参数，在内部Jira、M TKonline平台搜索是否为已知问
题
c.未知问题需提取对应版本的M odemELF⽂件、DbgInfo全量⽂件，提交给芯⽚平台分析
问题
定位
关键特
征
核⼼关注
点
可能原因 分析步骤 log⽂件 keywor
d
案例参考
M OD
EM 
EE
基带版
本号未
知/不识
卡
M odem
启动进程
img加载
NV校验
M odem
状态检查
1.配置错误
2.patch依赖漏
合
3.平台修改引⼊
4.单机硬件问题
具体错误模块⼤
致定位看报错c
⽂件；例如：rf
check⽬录下这
类⼤多是RF配
置错误；mml1/
⽬录下的⼤致定
位射频相关
1.检查aplog是
否记录到EE打印
2.EE挂死在log
打印前，可⼿动
触发dump模式
抓取dump确认
EE点
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
信号消
失后恢
复/mod
em
crash界
⾯
EE打印
1.[ASSE
RT]
file:X
XXXX
X
P1:XXX
P2:XXX
P3:XXX
例如：
[ASSERT
]
file:m cu/
l1/m m l1
/m m l1_r
f/src/m
m rf/gen
99/m m l1
_rf_erro
同上 1.mainlog中查
找modem
exception
2.找到assert具
体报错打印，某
某⽂件/某某⾏
，para0~2
3.查看本地⽂
件，报错路径能
否访问
3.不能访问就到
JIRA/onlie上搜
索报错⽂件，看
看是否已知问题
4.提交CR，给平
台分析，需要提
供版本对应符号
表
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

# Page 4
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
FANSAE
E/
M onkey
AEE
Exceptio
nClass:
External
(EE)
同上 1.__exp_main.t
xt中确认EE点
2.粉丝⽇志系统
中捞取对应的
taglog
3.若⽆对应
taglog，需发起
采集申请
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
⼤数据
USIC
Exceptio
nClass:
External
(EE)
同上 1.TNE解析⼯具
解析⽇志
2.如需dump，
需根据⼤数据捞
取modem
dump
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
⾮常规
EE
1.[ASSE
RT]
file:X
XXXX
X
P1:XXX
P2:XXX
P3:XXX
例如：
[ASSERT
]
1.IOloading
负载导致
modemEE
2.OTA过程中
强⾏打断
1.mainlog中查
找modem
exception
2.找到assert具
体报错打印，某
某⽂件/某某⾏
，para0~2
3.查看本地⽂
件，报错路径能
否访问
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
IO_LOADI
NG 负载导
致M odem
EE

# Page 5
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
3.不能访问就到
JIRA/onlie上搜
索报错⽂件，看
看是否已知问题
4.提交CR，给平
台分析，需要提
供版本对应符号
表
4.问题处理步骤
M odemEE问题处理流程
4.1EE原因获取
m odem logdum p获取：
⼀般情况，modemEE会⾃动触发⽇志打包，modemlog⾥会有_EE_INVALID的⽬录，⾥⾯记录了
modemEE时的⽇志

# Page 6
APlog中m ainlog获取：
可搜索exception或assert
aee_exp获取EE信息：
在使⽤logexporttool导出的⽇志会有该⽬录。粉丝⽇志⾃动提报的EE⽂件也是这个db⽂件。打开
dbg⽂件⼯具及路径可参考：http://10.150.98.130/pages/viewpage.action?pageId=24691819

# Page 7
4.2问题初步分析
以此EE为例，可在M TKonline搜索errc_chm_main.c，再根据对应line（此处是9158）确认是否
是已知问题。也可以根据对应⽂件路径去代码查看。M TKonline⽹址：
https://online.mediatek.com/_layouts/15/mol/ui/ext/home.aspx
4.3问题处理
4.3.1已知问题
●M TKonline确认相同根因CR->根据CR确认patchID->M TKeservice确认patch申请情况。
●未申请则需要在M TKeservice申请对应项⽬的patch，若查不到该patch信息则需要提CR请MTK 基
于该项⽬信息释放patch。
●安排patch合⼊及基本功能⾃检
4.3.2未知新问题
●M TKonline确认相同根因CR->没有相同报错CR。
●需要⾃⼰提CR，并与M TK 沟通跟进。CR提供附件需包括
1)问题时间点的M Dlog和M Ddumpbin;
2)问题时间点的APLog;
3)M odem端编译⽣成的ELF⽂件(XXX.elf)；
4)DbgInfo_XXXallfiles；对应filepath下的DbgInfo打头的所有file(DbgInfo_XXX)都要上传;
●CR跟进，获取debugpatch。
●debugpatch复测pass，申请释放正式patch。
●正式patch归档&合⼊。M TKeservice链接：https://eservice.mediatek.com/eservice-
portal/dashboardM TK上传⽇志及附件链接：https://transfer.mediatek.com/
ELF⽂件获取：确认问题版本->TrackFiles->vnd_track->vendor->mediatek->proprietary->modem-
>(项⽬名)⾥⾯所有东西。查看modemlog需要EDB⽂件，粉丝log⽆法解析需要将此⽂件放⼊log

# Page 8
⾥。
DbgInfo_XXXallfiles⽂件获取：确认问题版本->确认版本时间及基线信息->对应AP代码->modem
仓在modem仓gitlog查看代码合⼊时间，reset到编译版本时的modem版本提交去，然后将Dbg⽂件
上传给M TK
5.典型案例分析
案例1：OTA升级后不识卡、IMEI消失问题

# Page 9
• 问题现象：LI6_v/LI7_v版本OTA升级后，出现不识卡、IM EI丢失，基带版本显⽰为Unknown
• 分析过程：
a.检查基带版本状态，初步判定为M odemEE
b.搜索main_log关键字Modem exception ，定位到ASSERT报错为NV校验相关模块
c.确认根因为OTA升级过程中被打断，导致NV分区数据损坏，M odem启动校验失败触发EE
• 结论与建议：合⼊NV校验兼容补丁，OTA升级包增加完整性校验，避免升级过程异常打断导致数据
损坏。参考⽂档：LI6_v/LI7_vOTA升级后不识卡，IM EI消失问题复盘报告
案例2：IO负载过⾼导致偶现Modem EE
• 问题现象：机器⽆操作情况下偶现10s左右掉信号，之后⾃动恢复
• 分析过程：
a.查看modemdump⽇志，定位到ASSERT报错在IO读写相关模块
b.排查问题发⽣时的系统负载，确认后台多个进程同时进⾏IO读写，抢占M odem⼦系统调度资
源，导致超时触发EE
• 结论与建议：优化系统IO调度策略，限制后台进程IO优先级，避免抢占M odem⼦系统资源。参考
⽂档：IO_LOADING 负载导致M odemEE
6.常⻅问题(FAQ)
Q：抓取到的M odem⽇志⽆法解析怎么办？
A：确认是否获取了对应版本的ELF和DbgInfo⽂件，将⽂件放⼊⽇志⽬录后再使⽤解析⼯具打开即
可。
Q：M odemEE问题⼀定是软件问题吗？
A：不⼀定，市场客诉类M odemEE⼤多为硬件问题导致M odem加载失败，需要先排查硬件是否正
常。
Q：M TK 平台提交问题CR需要哪些附件？
A：需要提供问题时间点的M Dlog和M Ddumpbin、APLog、M odem端ELF⽂件、对应版本全量
DbgInfo⽂件。
7.平台拓展
上⾯主要讲解的M TK 平台，下⾯对展锐平台M odemEE问题进⾏拓展，主要分三步：dump抓取，
dump解析，初步分析
7.1dum p抓取
User版本需要特别关注：

# Page 10
*#9646633#-->Debug&LOG-->YLog-->Settings-->LogSetting-->M odemlogSetting--
>M odemReset关闭
*#9646633#-->Debug&LOG-->YLog-->Settings-->LogSetting-->M odemlogSetting--
>M odemSaveDump打开
然后开始抓取log，进⾏问题复现，完成后导出log即可，只要发⽣modemcrash,默认
在/data/ylog/modem/⽬录下,会⽣成.dmp后缀的dump⽂件

# Page 11
⼿动触发modemCrash⽅法：进⼊ylog应⽤,点击Debugsetting&tools,点击modemassert
manually,就会⼿动触发modemcrash
7.2dum p解析
在抓取的M odemlog中，会有minidump和.dmp形式的log
.dmp后缀的dump⽂件需要放到logel⼯具中进⾏解析：打开logel⼯具，直接将dmp⽂件拖进去
即可，⼯具会出现AssertInformation解析界⾯，直到出现finish为解析完成，解析后会在对应⽬录
下的⽂件夹⽣成.ass和.mem⽂件
7.3初步分析
①ap-->android.log中搜索M ODEM _CTRL,assert,crash等关键字可看出M odemCrash的源⽂件以
及原因(.c⽂件对我们不开源，需要平台⽅查询)

# Page 12
②.dmp⽂件解析后的.ass⽂件，⽂本形式打开，可查看到具体版本及Crash原因
③minidump⽂件打开，可查看Crash原因
由于部分内容不开源，本地初步分析后，提交CQ给到平台⽅进⼀步分析，需要提供以下资料：
A.Dumplog(包含dmp和minidump⽂件的log)
B.问题出现版本信息(M odem版本号等)
C.M odem版本对应符号表(.axf⽂件)
D.初步分析结论

# Page 13
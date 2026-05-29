---
tahp_adapt_skill: true
name: kb-skill-telephony-bug-analysis-mpp8j0io
domain_label: "telephony — bug_analysis"
domain_id: "kb-skill-telephony-bug-analysis-mpp8j0io"
module: telephony
func_type: bug_analysis
status: "deprecated"
generated_from_knowledge: true
created_at: "2026-05-28T08:56:45.374Z"
source: knowledge_base
---

# Telephony Bug 分析 Skill

## 适用场景
- 适用模块：telephony
- 适用业务类型：bug_analysis
- [请基于知识条目补充具体触发条件]

## ⚠️ 不适用情况（请人工补充）
- [待人工确认 1]
- [待人工确认 2]

## 核心处理方法
[基于以下 6 条知识条目，请整理核心处理步骤]

### 参考条目 1
file:mcu/
l1/mml1
/mml1_r
f/src/m
mrf/gen
99/mml1
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
索报错文件，看
看是否已知问题
4.提交CR，给平
台分析，需要提
供版本对应符号
表
4.问题处理步骤
ModemEE问题处理流程
4.1EE原因获取
modemlogdump获取：
一般情况，modemEE会自动触发日志打包，modemlog里会有_EE_INVALID的目录，里面记录了
modemEE时的日志

### 参考条目 2
稳定性问题分析指导SOP（Modem）
1.文档概述
1.1文档目的
本文档旨在解决手机Modem子系统异常崩溃（ModemEE）引发的各类问题，包括但不限于蜂窝数据
掉网、SIM卡不识卡、IMEI丢失/显示异常、信号短时间消失后自动恢复等场景，提供标准化的问题定
位、分析和处理流程。
1.2适用范围
•
适用问题现象：掉网、不识卡、IMEI显示异常、基带版本显示为Unknown、信号消失10s左右自动
恢复、弹出modemcrash提示
•
适用芯片平台：MTK、展锐（SPRD）、高通全系列手机平台
•
适用场景：项目测试问题、大数据监控异常、市场客诉Modem相关问题
2.问题分析地图
2.1核心问题分类
ModemEE问题可细分为5类具体子场景：
1.基带版本号未知/不识卡类EE
2.信号消失后恢复/弹出modemcrash界面类EE
3.FAN

### 参考条目 3
b.提取报错的文件名、行号以及P1/P2/P3参数，在内部Jira、MTKonline平台搜索是否为已知问
题
c.未知问题需提取对应版本的ModemELF文件、DbgInfo全量文件，提交给芯片平台分析
问题
定位
关键特
征
核心关注
点
可能原因分析步骤log文件keywor
d
案例参考
MOD
EM
EE
基带版
本号未
知/不识
卡
Modem
启动进程
img加载
NV校验
Modem
状态检查
1.配置错误
2.patch依赖漏
合
3.平台修改引入
4.单机硬件问题
具体错误模块大
致定位看报错c
文件；例如：rf
check目录下这
类大多是RF配
置错误；mml1/
目录下的大致定
位射频相关
1.检查aplog是
否记录到EE打印
2.EE挂死在log
打印前，可手动
触发dump模式
抓取dump确认
EE

### 参考条目 4
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
Monkey
AEE
Exceptio
nClass:
External
(EE)
同上1.__exp_main.t
xt中确认EE点
2.粉丝日志系统
中捞取对应的
taglog
3.若无对应
taglog，需发起
采集申请
1.__exp_ma
in.txt
2.SYS_KERN
EL_LOG
3.taglog
1.Mode
m
exceptio
n
2.
[ASSERT
]
3.[Fatal
error
大数据
USIC
Exceptio
nClass:
External
(EE)
同上1.TNE解析工具
解析日志
2.如需dump，
需根据大数据捞
取modem
dum

### 参考条目 5
*#9646633#-->Debug&LOG-->YLog-->Settings-->LogSetting-->ModemlogSetting--
>ModemReset关闭
*#9646633#-->Debug&LOG-->YLog-->Settings-->LogSetting-->ModemlogSetting--
>ModemSaveDump打开
然后开始抓取log，进行问题复现，完成后导出log即可，只要发生modemcrash,默认
在/data/ylog/modem/目录下,会生成.dmp后缀的dump文件

## 示例

### 正例
[请人工补充典型正例]

### ⚠️ 反例（待补充）
[待人工补充]

## ⚠️ 版本与平台约束（待确认）
- Android 版本范围：[待确认]
- 芯片平台：[待确认]

## 注意事项
[请基于知识条目补充注意事项]

## 维护信息
- 维护人：[待指定]
- 生成来源：知识库 6 条条目
- 模板版本：v1.0

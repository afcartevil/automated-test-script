:: Bitflip Analysis tools, Created by mtk71029 <yanghui.li@medaitek.com> v4.5.5
::	-s serialname    the serialname of phone for mulit-phones test
::	-o true/false    need force the screen on? default is false
::	-i seconds       the min time of phone reboot, default is 30
::	-r count         the repeat test times in traverse condition, default is 5 
::	-f true/false    using fast test mode? default is false
::	-m true/false    enable mrdump or not? default is false
::	-c true/false    clean test log? default is false
::	-a true/false    run second-stage to analysis root cause? default is true
::	-d true/false    save dram k log to dram_para partition, default is false
::	-k true/false    clean dram_para partition and dram full k ? default is true
::	-mt platform     force select platform scripts, such as mt6893
::	-cf file         select condition setting file in platform directory
::	-tf file         select test case file in TestCase directory
::	-ig true/false   ignore root cause check, force test all cases
::	-ib true/false   ignore battery level check, NOT care battery level in EVB, default is false
::	-p path          save log to path.
java -jar BitflipAnalysisTool.jar -o true -i 30 -ig true
pause
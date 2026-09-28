:: Bitflip Analysis tools, Created by mtk71029 <yanghui.li@medaitek.com> v5.4.0
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
::	-t temp          if it is higher than this temperature, it needs to be cooled down, default is 52'c
::	-mt platform     force select platform scripts, such as mt6893
::	-cf file         select condition setting file in platform directory
::	-tf file         select test case file in TestCase directory
::	-ig true/false   ignore root cause check, force test all cases
::	-ib true/false   ignore battery level check, NOT care battery level in EVB, default is false
::  -rp file         the test result files of previously reproducible fail
::	-p path          save log to path.

:: 1) Please open the result excel file of your last failed test such as BAT-Data_2025-06-05_23-06-02/alps-k6991v1_64-0123456789ABCDEF--BST.xlsx
:: 2) Delete all PASS items, keep the header row, and the actual failed items (if they are due to adb exceptions, remove them as well).
:: 3) You can also delete PASS stress cases and only keep the test fail cases to simplify the test process.
:: 4) Move the updated result file to Bitflip tool directory, and update the file name as 'retest-setting.xlsx' 
:: -rp connects to your updated fail result excel file.
:: -r how many rounds of testing should be repeated for each single item.

java -jar BitflipAnalysisTool.jar -o true -i 30 -r 20 -rp retest-setting.xlsx
pause
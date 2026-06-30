import pytest
from src.utils.adb.adb_utils import adb_shell
def test_add_counter_option(device_serial):
    '''
    ID:TOS163-26143
    DESCRIPTION: 【CTS】 CtsSimpleperfTestCases模块存在record_cmd#add_counter_option测试fail
    '''
    cmd = "simpleperf record -e cpu-cycles:u --add-counter instructions:u --no-inherit -o /data/local/tmp/test.data sleep 1"
    adb_shell(device_serial, cmd)
    # 检查是否生成sample数据
    check_cmd = "simpleperf dump --dump-record /data/local/tmp/test.data | grep PERF_RECORD_SAMPLE"
    output = adb_shell(device_serial, check_cmd)
    # 判断结果
    if not output:
        reason = "simpleperf --add-counter 未生成sample样本，CTS测试失败"
        pytest.fail(reason)
    adb_shell(device_serial, "rm -f /data/local/tmp/test.data")
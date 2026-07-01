import argparse
import pytest

from powertrde.env import add_path_to_python_env

if __name__ == "__main__":
    add_path_to_python_env()

    # 创建ArgumentParser对象
    parser = argparse.ArgumentParser(description='Run specific pytest test case.')
    parser.add_argument('--count', type=str, help='测试轮次')
    parser.add_argument('--reruns', type=str, help='fail重跑次数')
    parser.add_argument('--test_case', type=str, help='Path to the test file and test case.')
    parser.add_argument('--device_id', type=str, help='device_id')
    parser.add_argument('--c_device_id', type=str, help='copilot device_id')
    # parser.add_argument('--trde_board_index', type=str, help='trde control board charge index')
    parser.add_argument('--res_time', type=str, help='res_time')
    args = parser.parse_args()
    # 参数可以传入："tests/ppt/perf/platform_performance_layer/test_power_platform_performance.py::TestPowerPlatformPerformance::test_ppt_perf_dperf_0047"
    # print(args.count, args.reruns, args.test_case)
    # pytest.main([f'--count={args.count}', f'--reruns={args.reruns}', f'--device_id={args.device_id}', f'--c_device_id={args.c_device_id}', f'--res_time={args.res_time}', f'--trde_board_index={args.trde_board_index}', args.test_case])
    pytest.main([f'--count={args.count}', f'--reruns={args.reruns}', f'--device_id={args.device_id}', f'--c_device_id={args.c_device_id}', f'--res_time={args.res_time}', args.test_case])

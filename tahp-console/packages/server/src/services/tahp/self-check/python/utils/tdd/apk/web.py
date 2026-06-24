import subprocess

from utils.tdd.apk.get_result import wait_test_result

PACKAGE = "com.android.transsion.tdd.autotest"
WEB_ACTIVITY = f"{PACKAGE}/.web.WebActivity"

BAIDU_URL = "https://www.baidu.com"
DOUYIN_URL = "https://www.douyin.com"
IPV6_TEST_URL = "https://test-ipv6.com/"


def _run_adb(device_id: str, args: list[str], timeout: int = 30):
    cmd = ["adb", "-s", device_id, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def start_web_test(
    device_id: str,
    url: str,
    *,
    force_refresh: bool = True,
    timeout_seconds: int = 60,
) -> bool:
    """
    调起 WebActivity 加载指定网页。

    返回:
        界面拉起成功为 True，否则 False。
    """
    if not device_id or not str(url or "").strip():
        return False

    args = [
        "shell",
        "am",
        "start",
        "-n",
        WEB_ACTIVITY,
        "--es",
        "url",
        str(url).strip(),
        "--ez",
        "force_refresh",
        "true" if force_refresh else "false",
        "--ei",
        "timeout_seconds",
        str(timeout_seconds),
    ]
    result = _run_adb(device_id, args, timeout=max(30, timeout_seconds + 15))
    output = f"{result.stdout or ''}\n{result.stderr or ''}"
    if result.returncode != 0 or "Error" in output or "Exception" in output:
        return False
    return True


def run_web_test(
    device_id: str,
    url: str,
    *,
    force_refresh: bool = True,
    timeout_seconds: int = 60,
) -> bool:
    """
    打开网页并轮询 Pass/Fail 结果页。

    返回:
        PassActivity 为 True；FailActivity、拉起失败或超时为 False。
    """
    if not start_web_test(
        device_id,
        url,
        force_refresh=force_refresh,
        timeout_seconds=timeout_seconds,
    ):
        return False
    return wait_test_result(device_id)


def run_baidu_test(device_id: str, *, timeout_seconds: int = 60) -> bool:
    """访问百度并等待 Pass/Fail 结果页。"""
    return run_web_test(
        device_id,
        BAIDU_URL,
        force_refresh=True,
        timeout_seconds=timeout_seconds,
    )


def run_douyin_test(device_id: str, *, timeout_seconds: int = 60) -> bool:
    """访问抖音首页并等待 Pass/Fail 结果页。"""
    return run_web_test(
        device_id,
        DOUYIN_URL,
        force_refresh=True,
        timeout_seconds=timeout_seconds,
    )

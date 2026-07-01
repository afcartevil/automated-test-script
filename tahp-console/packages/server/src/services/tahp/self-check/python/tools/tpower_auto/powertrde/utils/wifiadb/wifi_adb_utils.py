import platform
import subprocess
import time
from typing import Dict, Optional

from powertrde.env import ADB_EXE
from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils

DEFAULT_WIFI_PASSWORD = '147258369'


def check_device_to_link_pc_current_wifi(u2d, wifi_password_if_needed: str = DEFAULT_WIFI_PASSWORD, check_wifi_internet: bool = False):
    pc_current_wifi_ssid, pc_current_wifi_password = get_pc_first_linked_wifi_info()
    if not pc_current_wifi_ssid:
        raise Exception('The PC is not connected to any Wi-Fi.')
    if not pc_current_wifi_password:
        pc_current_wifi_password = wifi_password_if_needed
    t_log.info(f'The PC Wi-Fi is {pc_current_wifi_ssid}')
    check_device_to_link_wifi(u2d, pc_current_wifi_ssid, pc_current_wifi_password, check_wifi_internet)


def check_device_to_link_wifi(u2d, ssid: str, password: str = DEFAULT_WIFI_PASSWORD, check_wifi_internet: bool = False):
    def _check_internet():
        if check_wifi_internet:
            for _ in range(3):
                if adb.is_network_valid(usb_device_sn):
                    #t_log.info("The device's Internet connection check pass.")
                    break
                time.sleep(2)
            else:
                raise Exception('After the device is connected to wifi, it cannot access the Internet!')

    usb_device_sn = u2d.serial
    if not is_wifi_on(usb_device_sn):
        #t_log.info(f'Device {usb_device_sn} Wi-Fi is off, will on it')
        set_wlan_on_off(usb_device_sn, True)
        time.sleep(6)
    device_current_wifi_ssid = get_linked_wifi_ssid(usb_device_sn)
    if ssid == device_current_wifi_ssid:
        _check_internet()
        return
    link_wifi_via_u2(u2d, ssid, password)
    device_current_wifi_ssid = get_linked_wifi_ssid(usb_device_sn)
    if device_current_wifi_ssid != device_current_wifi_ssid:
        raise Exception(
            f'After some connection operations on the device {usb_device_sn}, the current Wi-Fi ID of the device is {device_current_wifi_ssid}, which is not the same as the {ssid} of you specified, and the connection failed!')
    _check_internet()
    #t_log.info(f'Device {usb_device_sn} successfully connected to Wi-Fi {ssid}')


def set_wlan_on_off(sn: str, is_on: bool):
    adb.open_close_wifi(sn, is_on)


def is_wifi_on(sn: str):
    try:
        # 执行ADB命令
        result = subprocess.run(
            [ADB_EXE, "-s", sn, "shell", "settings", "get", "global", "wifi_on"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            # 获取命令返回值
            wifi_status = result.stdout.strip()
            return wifi_status == "1"  # Wi-Fi开启返回True
        else:
            raise RuntimeError("Failed to execute ADB command.")
    except Exception as e:
        raise RuntimeError(f"An error occurred: {e}")


def get_linked_wifi_ssid(sn: str):
    """
    检查当前ADB设备连接的Wi-Fi的SSID。

    :param sn: 设备序列号。
    :return: SSID（字符串）或 None（未连接Wi-Fi）
    """
    try:
        # adb shell命令查询连接的Wi-Fi信息
        command = f'{ADB_EXE} -s {sn} shell "dumpsys wifi | grep \'mWifiInfo SSID\'"'

        # 执行命令
        result = subprocess.run(command, capture_output=True, text=True, shell=True, encoding="UTF-8")

        if result.returncode != 0:
            raise RuntimeError(f"Failed to execute adb command: {result.stderr}")

        out_str = result.stdout
        g_start = out_str.index('mWifiInfo SSID')
        if g_start < 0:
            return None
        g_start += 16
        if out_str[g_start] == '<':
            return None
        has_back_q = False
        if out_str[g_start] == '"':
            has_back_q = True
            g_start += 1
        g_end = out_str.index(',', g_start) - (1 if has_back_q else 0)
        if g_end < 0:
            return None
        return out_str[g_start:g_end]
    except FileNotFoundError:
        raise RuntimeError("ADB not found. Ensure adb is installed and in PATH.")
    except Exception as e:
        raise RuntimeError(f"An error occurred: {e}")


def get_pc_first_linked_wifi_info():
    try:
        os_type = platform.system()

        if os_type == "Windows":  # Windows 系统
            # 使用 netsh 获取当前连接的 Wi-Fi 信息
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True,
                text=True,
                shell=True
            )
            if result.returncode == 0:
                ssid = None
                for line in result.stdout.split("\n"):
                    if "SSID" in line and "BSSID" not in line:  # 排除 BSSID 行
                        ssid = line.split(":", 1)[1].strip()
                        break

                if ssid:
                    # 获取密码（弱操作，忽略错误）
                    try:
                        result = subprocess.run(
                            ["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"],
                            capture_output=True,
                            text=True,
                            shell=True
                        )
                        password = None
                        if result.returncode == 0:
                            result_output = result.stdout.split(':')[-7]
                            password = result_output[1:result_output.index('\n')]
                        return ssid, password
                    except Exception:
                        pass  # 忽略获取密码时的错误

                    return ssid, None  # 没有获取到密码
            else:
                raise RuntimeError("Failed to execute netsh command.")

        elif os_type in ["Linux", "Darwin"]:  # Linux/macOS 系统
            # 使用 nmcli 获取当前连接的 Wi-Fi 信息
            result = subprocess.run(
                ["nmcli", "-t", "-f", "ACTIVE,SSID", "device", "wifi"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                ssid = None
                for line in result.stdout.strip().split("\n"):
                    if line.startswith("yes:"):
                        ssid = line.split(":", 1)[1]
                        break

                # Linux/macOS 获取 Wi-Fi 密码的机制依赖具体配置，默认不实现密码获取
                return ssid, None
            else:
                raise RuntimeError("Failed to execute nmcli command.")

        else:
            raise RuntimeError(f"Unsupported OS: {os_type}")

    except FileNotFoundError:
        raise RuntimeError("Required command not found. Ensure nmcli (Linux/macOS) or netsh (Windows) is installed.")
    except Exception as e:
        raise RuntimeError(f"An error occurred: {e}")


def get_pc_first_linked_wifi_ssid():
    return get_pc_first_linked_wifi_info()[0]


def get_ssid_to_network_id_dict(sn: str) -> Dict[str, int]:
    """
    返回当前设备保存的 Wi-Fi 网络中，SSID 和 networkId 的对应关系字典。

    :return: 一个字典，键为 SSID，值为 networkId。如果没有数据，返回空字典。
    """
    ssid_to_network_id = {}
    # 执行 adb shell cmd wifi list-networks 获取保存的网络列表
    result = subprocess.run(
        [ADB_EXE, "-s", sn, "shell", "cmd", "wifi", "list-networks"],
        capture_output=True,
        text=True,
        check=True
    )
    # 提取输出内容
    output = result.stdout.strip()
    if not output:
        return ssid_to_network_id

    # 按行解析
    lines = output.splitlines()
    for line in lines:
        # 假设格式为 networkId SSID other-details
        parts = line.split(maxsplit=2)
        if len(parts) > 1:
            network_id = parts[0]
            ssid = parts[1]
            ssid_to_network_id[ssid] = int(network_id)

    return ssid_to_network_id


def get_network_id_by_ssid(sn: str, ssid: str) -> Optional[int]:
    return get_ssid_to_network_id_dict(sn).get(ssid)


def forget_wifi_by_network_id(sn: str, wifi_network_id: int):
    subprocess.run(f"{ADB_EXE} -s {sn} shell cmd wifi forget-network {wifi_network_id}", shell=True)


def forget_wifi(sn: str, wifi_ssid: str):
    wifi_network_id = get_network_id_by_ssid(sn, wifi_ssid)
    if wifi_network_id is not None:
        forget_wifi_by_network_id(sn, wifi_network_id)


def set_wlan_auto_changeable(sn: str, enable_auto_change: bool):
    adb.set_settings_value(sn, 'global', 'wifi_networks_available_notification_on', '1' if enable_auto_change else '0')


def is_wlan_auto_changeable(sn: str):
    value = adb.get_settings_value(sn, 'global', 'wifi_networks_available_notification_on')
    return bool(value) and value != '0'


def connect_wifi_adb(usb_device_sn: str, device_wlan_ip: str = '') -> Optional[str]:
    if not device_wlan_ip:
        device_wlan_ip = get_wlan_ip(usb_device_sn)
    if not device_wlan_ip:
        raise Exception('Unable to fetch the WLAN IP of the device')
    set_device_tcpip_port(usb_device_sn)
    for attempt in range(5):
        result = subprocess.run(f"{ADB_EXE} connect {device_wlan_ip}", shell=True,
                                check=True, capture_output=True, text=True, encoding='utf-8')
        t_log.info(f"Wifi ADB auto link Result: {result}")
        if "connected to" in result.stdout:
            return f'{device_wlan_ip}:5555'
        time.sleep(2)
    return None


def set_device_tcpip_port(usb_device_sn: str):
    subprocess.run(f"{ADB_EXE} -s {usb_device_sn} tcpip 5555", shell=True, check=True)


def get_device_tcpip_port(sn: str):
    return '5555'


def is_wifi_adb_enabled(sn: str):
    return adb.is_wifi_adb_enabled(sn)


def set_wifi_adb_enabled(sn: str, enabled: bool):
    adb.set_wifi_adb_enabled(sn, enabled)


def get_wlan_ip(sn: str):
    ip_result = subprocess.run(f"{ADB_EXE} -s {sn} shell ifconfig wlan0", capture_output=True, text=True,
                               shell=True, check=True)
    ip_address = None
    for line in ip_result.stdout.splitlines():
        if 'inet ' in line:
            ip_address = line.split()[1][5:]
            break
    return ip_address


def is_wifi_adb_device(sn: str) -> bool:
    """
    检查给定的设备序列号是否是一个 Wi-Fi ADB 设备。

    :param sn: 设备的序列号
    :return: 如果是 Wi-Fi ADB 设备，返回 True，否则返回 False
    """
    import re
    # Wi-Fi ADB 设备的序列号格式通常为 "IP:PORT"
    pattern = r"^\d{1,3}(\.\d{1,3}){3}:\d+$"
    return bool(re.match(pattern, sn))


def link_wifi_via_u2(u2d, ssid: str, password: str = DEFAULT_WIFI_PASSWORD) -> bool:
    sn = u2d.serial
    adb.stop_settings_activity(sn)
    adb.poweron_screen_and_unlock(sn)
    time.sleep(2)
    adb.launch_app(sn, "com.android.settings", True)
    adb.open_settings_activity(sn)
    time.sleep(2)
    wifi_node = u2d.xpath('//*[@text="Wi‑Fi"]')
    if wifi_node.exists:
        wifi_node.click(timeout=5)
    else:
        wifi_node = u2d.xpath('//*[@text="WLAN"]')
        wifi_node.click(timeout=5)
    time.sleep(1)
    # 打开wifi
    # if is_wifi_on(sn):
    #     adb.open_close_wifi(sn, False)
    adb.open_close_wifi(sn, True)

    time.sleep(10)
    if get_linked_wifi_ssid(sn) == ssid:
        return True

    u2utils.scroll_find_by_xpath(u2d, f'//*[@text="{ssid}"]').click(timeout=5)
    time.sleep(1)
    edit_box = u2d.xpath('//android.widget.EditText')
    if edit_box.exists:
        # edit_box.click()
        time.sleep(2)
        # u2d.send_keys(password)  # 输入文本
        # u2d.shell(f'input text "{password}"')
        subprocess.run(f'{ADB_EXE} -s {sn} shell input text "{password}"')
        time.sleep(1)
        connect_button = u2d.xpath('//*[@resource-id="android:id/button1"]')
        if connect_button.exists:
            connect_button.click()
        else:
            connect_button = u2d.xpath('//*[@text="Connect"]').click()
            if connect_button.exists:
                connect_button.click()
            else:
                connect_button = u2d.xpath('//*[@text="连接"]').click()
                connect_button.click()
    else:
        extra_connect_button = u2d.xpath('//*[@resource-id="android:id/button1"]')
        if extra_connect_button.exists:
            extra_connect_button.click()
    for i in range(4):
        time.sleep(2)
        if get_linked_wifi_ssid(sn) == ssid:
            return True
    return False


def clean_offline_devices(use_heart_beat_check_offline=False):
    result = subprocess.run([ADB_EXE, "devices"], capture_output=True, text=True)
    if result.returncode == 0:
        devices = result.stdout.splitlines()[1:]  # 跳过标题行
        for line in devices:
            if not line:
                continue
            device_id = line.split()[0]
            if "offline" in line or (use_heart_beat_check_offline and is_device_offline(device_id)):
                t_log.info(f"Cleaning offline device: {device_id}")
                subprocess.run([ADB_EXE, "disconnect", device_id])
    else:
        t_log.info("Failed to get device list.")


def disconnect_adb(sn: str):
    subprocess.run([ADB_EXE, "disconnect", sn])


def get_real_sn(sn: str):
    return adb.getprop(sn, 'ro.serialno')


def get_wifi_adb_sn(sn: str, check_online: bool = False):
    try:
        if is_wifi_adb_device(sn):
            wifi_adb_sn = sn
        else:
            port = get_device_tcpip_port(sn)
            if not port:
                return None
            wlan_ip = get_wlan_ip(sn)
            if not wlan_ip:
                return None
            wifi_adb_sn = f'{wlan_ip}:{port}'
        if check_online:
            if is_device_offline(wifi_adb_sn):
                return None
        return wifi_adb_sn
    except:
        return None


def is_connected_wifi_adb(sn: str) -> str:
    return get_wifi_adb_sn(sn, True)


def restart_adb_server():
    subprocess.run(f'{ADB_EXE} kill-server', shell=True)
    subprocess.run(f'{ADB_EXE} start-server', shell=True)


def connect_wifi_adb_if_needed(sn: str) -> str:
    exist_wifi_adb_sn = is_connected_wifi_adb(sn)
    if exist_wifi_adb_sn:
        t_log.info(f'Device {sn} has already connected to wifi adb {exist_wifi_adb_sn}, No need to reconnect.')
        return exist_wifi_adb_sn
    t_log.info(f'Device {sn} has not yet connected to WiFi adb, it is about to connect.')
    return connect_wifi_adb(sn)


def is_device_offline(sn: str):
    """
    检查指定序列号的 ADB 设备是否为 offline。

    Args:
        sn (str): 设备的序列号。

    Returns:
        bool: 如果设备 offline 返回 True，否则返回 False。
    """
    try:
        # 尝试通过 adb 命令向设备发送心跳
        result = subprocess.run(
            [ADB_EXE, "-s", sn, "shell", "echo", "'heart beat'"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # 检查返回值是否正常
        if result.returncode == 0 and "heart beat" in result.stdout:
            return False  # 在线
        else:
            return True  # 离线或异常
    except subprocess.TimeoutExpired:
        # 超时视为设备不可用
        return True
    except Exception as e:
        # 处理其他异常
        print(f"Error checking device {sn}: {e}")
        return True


def get_wifi_adb_devices():
    return [d for d in adb.adb_devices() if is_wifi_adb_device(d)]


def get_usb_adb_devices():
    return [d for d in adb.adb_devices() if not is_wifi_adb_device(d)]


def disconnect_all_wifi_adb():
    for d in get_wifi_adb_devices():
        disconnect_adb(d)

def disconnect_pc_wifi():
    """
    断开电脑当前连接的 Wi-Fi。
    """
    try:
        os_type = platform.system()

        if os_type == "Windows":  # Windows 系统
            # 执行 netsh 命令断开 Wi-Fi
            result = subprocess.run(
                ["netsh", "wlan", "disconnect"],
                capture_output=True,
                text=True,
                shell=True
            )
            if result.returncode == 0:
                print("成功断开当前连接的 Wi-Fi。")
            else:
                raise RuntimeError(f"断开 Wi-Fi 失败: {result.stderr.strip()}")

        elif os_type in ["Linux", "Darwin"]:  # Linux/macOS 系统
            # 对于 Linux/macOS，使用 nmcli 命令断开 Wi-Fi
            result = subprocess.run(
                ["nmcli", "device", "disconnect", "wlan0"],  # 假设 Wi-Fi 设备名称为 wlan0
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("成功断开当前连接的 Wi-Fi。")
            else:
                raise RuntimeError(f"断开 Wi-Fi 失败: {result.stderr.strip()}")

        else:
            raise RuntimeError(f"不支持的操作系统: {os_type}")

    except FileNotFoundError:
        raise RuntimeError("所需命令未找到。请确保 Windows 系统安装 netsh，Linux/macOS 系统安装 nmcli。")
    except Exception as e:
        raise RuntimeError(f"发生错误: {e}")


if __name__ == '__main__':
    import uiautomator2 as u2

    #restart_adb_server()
    first_usb_device = get_usb_adb_devices()[0]
    check_device_to_link_pc_current_wifi(u2.connect(first_usb_device), check_wifi_internet=True)
    con_res = connect_wifi_adb_if_needed(first_usb_device)
    if con_res:
        print("连接成功: " + con_res)
    else:
        print("连接失败")
    # res = get_pc_first_linked_wifi_info()
    # print(res)

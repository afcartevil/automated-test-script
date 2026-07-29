"""Windows热点"""

import subprocess


def set_wifi_hotspot(ssid, password):
    # 设置和启动Wi-Fi热点
    try:
        # 配置热点
        subprocess.run(f"netsh wlan set hostednetwork mode=allow ssid={ssid} key={password}", check=True, shell=True)

        # 启动热点
        subprocess.run("netsh wlan start hostednetwork", check=True, shell=True)

        print("Hotspot started successfully.")
        print(f"SSID: {ssid}")
        print(f"Password: {password}")
    except subprocess.CalledProcessError as e:
        print(f"Error starting hotspot: {e}")


def get_wifi_hotspot_info():
    # 获取热点信息
    try:
        result = subprocess.run("netsh wlan show hostednetwork", check=True, shell=True, stdout=subprocess.PIPE,
                                text=True)
        print("Current Hotspot Info:")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving hotspot info: {e}")


# 使用示例
ssid = "PPT_AUTO_WINDOWS"
password = "1234567809"
set_wifi_hotspot(ssid, password)
get_wifi_hotspot_info()


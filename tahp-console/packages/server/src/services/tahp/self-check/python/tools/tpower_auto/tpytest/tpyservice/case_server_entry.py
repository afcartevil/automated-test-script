import asyncio
import datetime
import socket
import subprocess
import time
from typing import NamedTuple, Tuple

import psutil

from powertrde.framework.defines import HostPort
from powertrde.framework.simple_response_message import SimpleResponseMessage
from powertrde.framework.simple_tcp_client import SimpleTcpClient
from tpytest.tpyservice import tpytest_case_server
from tpytest.tpyservice.tpytest_case_server import DeviceTestResponse, SERVER_ADDRESS


class CaseServerEntrySettings(NamedTuple):
    server_launch_file: str  # 服务器的启动路径


def _start_server(entry_settings: CaseServerEntrySettings):
    args = [entry_settings.server_launch_file]
    subprocess.Popen(args, stdin=None, stdout=None, stderr=None, close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS, start_new_session=True)


def get_all_network_interfaces():
    interfaces = psutil.net_if_addrs()
    interface_info = {}

    for interface_name, addresses in interfaces.items():
        for address in addresses:
            if address.family == socket.AF_INET:  # IPv4
                interface_info[interface_name] = address.address

    return interface_info


def get_192_network_ip():
    for k, v in get_all_network_interfaces().items():
        if (k.__contains__("WLAN") or k.__contains__("Wi-Fi")) and v.startswith('192.'):
            return v
    # for v in get_all_network_interfaces().values():
    #     if v.startswith('192.'):
    #         return v
    return ''


async def start_and_connect_server(entry_settings: CaseServerEntrySettings) -> Tuple[str, SimpleTcpClient, str]:
    if not tpytest_case_server.is_server_event_exists(True):
        _start_server(entry_settings)
        for _ in range(5):
            time.sleep(1)
            if tpytest_case_server.is_server_event_exists(True):
                break

    client = SimpleTcpClient(HostPort('127.0.0.1', SERVER_ADDRESS[1]), None)
    client_ip, client_port = await client.connect()
    client_ip = get_192_network_ip()
    assert client_ip
    request_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f'{client_ip}:{client_port}', client, request_id


async def wait_device_response_or_timeout(client: SimpleTcpClient, request_id: str,
                                          timeout: float) -> DeviceTestResponse:
    future = asyncio.get_event_loop().create_future()

    def _on_received_response(response: SimpleResponseMessage):
        device_response = DeviceTestResponse(response.text, None)
        if device_response.request_id == request_id:
            future.set_result(device_response)

    async def _wait_device_response():
        return await future

    client.on_received_callback = _on_received_response
    return await asyncio.wait_for(_wait_device_response(), timeout=timeout)


# ####################################### 如下测试 ##############################################


if __name__ == '__main__':
    print(get_all_network_interfaces())
    print(get_192_network_ip())
